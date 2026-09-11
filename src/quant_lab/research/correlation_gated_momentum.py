from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.research.breadth_momentum import CONFIG, BreadthDataset, load_breadth_datasets
from quant_lab.validation.forward_shadow import run_forward_shadow
from quant_lab.validation.lookahead import assert_no_lookahead


class CorrelationMomentumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CorrelationMomentumSpec:
    lookback_hours: int = 336
    trend_ema_hours: int = 400
    correlation_hours: int = 168
    correlation_threshold: float = 0.70

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0 or self.trend_ema_hours <= 0 or self.correlation_hours <= 1:
            raise CorrelationMomentumError("momentum, EMA, and correlation windows must be positive")
        if not -1.0 <= self.correlation_threshold <= 1.0:
            raise CorrelationMomentumError("correlation threshold must be in [-1, 1]")


@dataclass(frozen=True, slots=True)
class CorrelationMomentumStrategy:
    spec: CorrelationMomentumSpec
    timeframe_hours: int
    other_close: pd.Series
    name: str = "high_correlation_gated_momentum"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise CorrelationMomentumError("timeframe hours must be positive")

    def _bars(self, hours: int) -> int:
        return max(1, round(hours / self.timeframe_hours))

    @staticmethod
    def _log_return(series: pd.Series) -> pd.Series:
        positive = series.astype(float).where(series.astype(float) > 0.0)
        logged = pd.Series(np.log(positive.to_numpy(dtype=float)), index=series.index, dtype=float)
        return logged - logged.shift(1)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        aligned_other = self.other_close.reindex(data.index)
        lookback = self._bars(self.spec.lookback_hours)
        ema_span = self._bars(self.spec.trend_ema_hours)
        correlation_bars = self._bars(self.spec.correlation_hours)
        own_return = self._log_return(close)
        other_return = self._log_return(aligned_other)
        correlation = own_return.rolling(
            correlation_bars,
            min_periods=correlation_bars,
        ).corr(other_return)
        own_momentum = close > close.shift(lookback)
        own_trend = close > close.ewm(span=ema_span, adjust=False).mean()
        gate = correlation >= self.spec.correlation_threshold
        signals = (own_momentum & own_trend & gate).fillna(False).astype(float)
        signals.name = "signal"
        return signals


@dataclass(frozen=True, slots=True)
class CorrelationEvaluation:
    dataset: str
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    number_of_trades: int


ZERO_COST_CONFIG = replace(
    CONFIG,
    fee_bps=0.0,
    slippage_bps=0.0,
    volatility_slippage_multiplier=0.0,
)


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: BreadthDataset,
    spec: CorrelationMomentumSpec,
    period: str,
    start: str,
    end: str,
    config: BacktestConfig = CONFIG,
) -> CorrelationEvaluation | None:
    own = _slice_period(dataset.own, start, end)
    if len(own) < 2:
        return None
    strategy = CorrelationMomentumStrategy(
        spec=spec,
        timeframe_hours=dataset.timeframe_hours,
        other_close=dataset.other_close.reindex(own.index),
    )
    metrics: PerformanceMetrics = run_backtest(
        own,
        strategy,
        config,
        symbol=dataset.symbol,
    ).metrics
    return CorrelationEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[CorrelationEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def _evaluate_shadow(
    dataset: BreadthDataset,
    spec: CorrelationMomentumSpec,
) -> CorrelationEvaluation | None:
    strategy = CorrelationMomentumStrategy(spec, dataset.timeframe_hours, dataset.other_close)
    result = run_forward_shadow(
        dataset.own,
        strategy,
        start="2026-09-11",
        end="2100-01-01",
        config=CONFIG,
        symbol=dataset.symbol,
    )
    if result is None:
        return None
    metrics = result.metrics
    return CorrelationEvaluation(
        dataset=dataset.label,
        period="future_shadow",
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def run_research(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = CorrelationMomentumSpec()
    datasets = load_breadth_datasets(root)
    pre_rows: list[CorrelationEvaluation] = []
    for dataset in datasets:
        strategy = CorrelationMomentumStrategy(spec, dataset.timeframe_hours, dataset.other_close)
        assert_no_lookahead(dataset.own, strategy, max_checks=16)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
        ):
            evaluation = _evaluate(dataset, spec, period, start, end)
            if evaluation is not None:
                pre_rows.append(evaluation)
    pre_pass = all(
        row.total_return > 0.0
        and row.sharpe_ratio > 0.0
        and row.number_of_trades >= 10
        for row in pre_rows
    )
    pre_stress = _frame(pre_rows)
    pre_stress["pre_holdout_pass"] = pre_pass

    stress_rows: list[CorrelationEvaluation] = []
    zero_cost_rows: list[CorrelationEvaluation] = []
    shadow_rows: list[CorrelationEvaluation] = []
    for dataset in datasets:
        stress = _evaluate(dataset, spec, "stress_2026", "2026-01-01", "2026-09-11")
        if stress is not None:
            stress_rows.append(stress)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
            ("stress_2026", "2026-01-01", "2026-09-11"),
        ):
            evaluation = _evaluate(dataset, spec, period, start, end, ZERO_COST_CONFIG)
            if evaluation is not None:
                zero_cost_rows.append(evaluation)
        shadow = _evaluate_shadow(dataset, spec)
        if shadow is not None:
            shadow_rows.append(shadow)
    stress_frame = _frame(stress_rows)
    stress_frame["pre_holdout_pass"] = pre_pass
    return pre_stress, stress_frame, _frame(zero_cost_rows), _frame(shadow_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run high-correlation gated BTC/ETH momentum study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost, shadow = run_research(root)
    pre_stress.to_csv(root / "correlation_gated_momentum_pre_stress.csv", index=False)
    stress.to_csv(root / "correlation_gated_momentum_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "correlation_gated_momentum_zero_cost.csv", index=False)
    shadow.to_csv(root / "correlation_gated_momentum_shadow.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))
    print("future shadow")
    print("no completed shadow window yet" if shadow.empty else shadow.to_string(index=False))


if __name__ == "__main__":
    main()
