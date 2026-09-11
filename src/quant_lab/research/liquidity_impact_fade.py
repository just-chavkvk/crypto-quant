from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.research.wick_rejection import CONFIG, WickDataset, load_wick_datasets
from quant_lab.validation.lookahead import assert_no_lookahead


class LiquidityImpactFadeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LiquidityImpactFadeSpec:
    history_hours: int = 720
    impact_quantile: float = 0.95
    hold_hours: int = 4

    def __post_init__(self) -> None:
        if self.history_hours <= 1 or self.hold_hours <= 0:
            raise LiquidityImpactFadeError("history and hold windows must be positive")
        if not 0.0 < self.impact_quantile < 1.0:
            raise LiquidityImpactFadeError("impact quantile must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class LiquidityImpactFadeStrategy:
    spec: LiquidityImpactFadeSpec
    timeframe_hours: int
    name: str = "liquidity_impact_shock_fade"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise LiquidityImpactFadeError("timeframe hours must be positive")
        if self.spec.history_hours % self.timeframe_hours != 0:
            raise LiquidityImpactFadeError("history hours must divide evenly by timeframe")
        if self.spec.hold_hours % self.timeframe_hours != 0:
            raise LiquidityImpactFadeError("hold hours must divide evenly by timeframe")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"].astype(float)
        volume = data["volume"].astype(float)
        positive_close = close.where(close > 0.0)
        logged = pd.Series(
            np.log(positive_close.to_numpy(dtype=float)),
            index=data.index,
            dtype=float,
        )
        log_return = logged - logged.shift(1)
        quote_notional = (volume * close).where((volume > 0.0) & (close > 0.0))
        impact = log_return.abs() / quote_notional
        history_bars = self.spec.history_hours // self.timeframe_hours
        threshold = impact.shift(1).rolling(
            history_bars,
            min_periods=history_bars,
        ).quantile(self.spec.impact_quantile)
        event = (impact >= threshold) & log_return.notna() & (log_return != 0.0)

        signals = pd.Series(0.0, index=data.index, dtype=float, name="signal")
        hold_bars = self.spec.hold_hours // self.timeframe_hours
        next_allowed_offset = 0
        for offset in range(len(data)):
            if offset < next_allowed_offset or not bool(event.iloc[offset]):
                continue
            side = -1.0 if float(log_return.iloc[offset]) > 0.0 else 1.0
            end = min(offset + hold_bars, len(signals))
            signals.iloc[offset:end] = side
            next_allowed_offset = end
        return signals


@dataclass(frozen=True, slots=True)
class LiquidityImpactEvaluation:
    dataset: str
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    number_of_trades: int


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: WickDataset,
    spec: LiquidityImpactFadeSpec,
    config: BacktestConfig,
    period: str,
    start: str,
    end: str,
) -> LiquidityImpactEvaluation | None:
    data = _slice_period(dataset.data, start, end)
    if len(data) < 2:
        return None
    strategy = LiquidityImpactFadeStrategy(spec, dataset.timeframe_hours)
    metrics: PerformanceMetrics = run_backtest(
        data,
        strategy,
        config,
        symbol=dataset.symbol,
    ).metrics
    return LiquidityImpactEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[LiquidityImpactEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = LiquidityImpactFadeSpec()
    datasets = load_wick_datasets(root)
    pre_rows: list[LiquidityImpactEvaluation] = []
    for dataset in datasets:
        strategy = LiquidityImpactFadeStrategy(spec, dataset.timeframe_hours)
        assert_no_lookahead(dataset.data, strategy, max_checks=16)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
        ):
            evaluation = _evaluate(dataset, spec, CONFIG, period, start, end)
            if evaluation is not None:
                pre_rows.append(evaluation)
    pre_pass = bool(pre_rows) and all(
        row.total_return > 0.0 and row.sharpe_ratio > 0.0 and row.number_of_trades >= 10
        for row in pre_rows
    )
    pre_stress = _frame(pre_rows)
    pre_stress["pre_holdout_pass"] = pre_pass

    zero_cost_config = BacktestConfig(
        fee_bps=0.0,
        slippage_bps=0.0,
        risk_per_trade=0.01,
        stop_loss_pct=0.05,
        volatility_slippage_multiplier=0.0,
    )
    stress_rows: list[LiquidityImpactEvaluation] = []
    zero_cost_rows: list[LiquidityImpactEvaluation] = []
    for dataset in datasets:
        stress = _evaluate(dataset, spec, CONFIG, "stress_2026", "2026-01-01", "2026-09-11")
        if stress is not None:
            stress_rows.append(stress)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
            ("stress_2026", "2026-01-01", "2026-09-11"),
        ):
            evaluation = _evaluate(dataset, spec, zero_cost_config, period, start, end)
            if evaluation is not None:
                zero_cost_rows.append(evaluation)
    stress_frame = _frame(stress_rows)
    stress_frame["pre_holdout_pass"] = pre_pass
    return pre_stress, stress_frame, _frame(zero_cost_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run liquidity-impact shock fade study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost = run_research(root)
    pre_stress.to_csv(root / "liquidity_impact_fade_pre_stress.csv", index=False)
    stress.to_csv(root / "liquidity_impact_fade_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "liquidity_impact_fade_zero_cost.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))


if __name__ == "__main__":
    main()
