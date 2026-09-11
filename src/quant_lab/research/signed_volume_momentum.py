from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.research.volatility_managed_momentum import (
    CONFIG,
    VolatilityDataset,
    load_volatility_datasets,
)
from quant_lab.validation.forward_shadow import run_forward_shadow
from quant_lab.validation.lookahead import assert_no_lookahead


class SignedVolumeMomentumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SignedVolumeMomentumSpec:
    lookback_hours: int = 336
    trend_ema_hours: int = 400
    balance_hours: int = 168
    balance_threshold: float = 0.10

    def __post_init__(self) -> None:
        if min(self.lookback_hours, self.trend_ema_hours, self.balance_hours) <= 0:
            raise SignedVolumeMomentumError("strategy hour windows must be positive")
        if not -1.0 <= self.balance_threshold <= 1.0:
            raise SignedVolumeMomentumError("balance threshold must be in [-1, 1]")


@dataclass(frozen=True, slots=True)
class SignedVolumeMomentumStrategy:
    spec: SignedVolumeMomentumSpec
    timeframe_hours: int
    name: str = "signed_volume_confirmed_momentum"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise SignedVolumeMomentumError("timeframe hours must be positive")
        for hours in (
            self.spec.lookback_hours,
            self.spec.trend_ema_hours,
            self.spec.balance_hours,
        ):
            if hours % self.timeframe_hours != 0:
                raise SignedVolumeMomentumError("strategy windows must divide by timeframe")

    def _bars(self, hours: int) -> int:
        return hours // self.timeframe_hours

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"].astype(float)
        volume = data["volume"].astype(float)
        positive = close.where(close > 0.0)
        logged = pd.Series(np.log(positive.to_numpy(dtype=float)), index=data.index, dtype=float)
        log_return = logged - logged.shift(1)
        direction = pd.Series(
            np.sign(log_return.to_numpy(dtype=float)),
            index=data.index,
            dtype=float,
        )
        balance_bars = self._bars(self.spec.balance_hours)
        signed_volume = volume * direction
        numerator = signed_volume.rolling(balance_bars, min_periods=balance_bars).sum()
        denominator = volume.rolling(balance_bars, min_periods=balance_bars).sum()
        balance = numerator / denominator.mask(denominator <= 0.0)
        momentum = close > close.shift(self._bars(self.spec.lookback_hours))
        trend = close > close.ewm(
            span=self._bars(self.spec.trend_ema_hours),
            adjust=False,
        ).mean()
        gate = balance >= self.spec.balance_threshold
        signals = (momentum & trend & gate).fillna(False).astype(float)
        signals.name = "signal"
        return signals


@dataclass(frozen=True, slots=True)
class SignedVolumeEvaluation:
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
    dataset: VolatilityDataset,
    spec: SignedVolumeMomentumSpec,
    config: BacktestConfig,
    period: str,
    start: str,
    end: str,
) -> SignedVolumeEvaluation | None:
    data = _slice_period(dataset.data, start, end)
    if len(data) < 2:
        return None
    strategy = SignedVolumeMomentumStrategy(spec, dataset.timeframe_hours)
    metrics: PerformanceMetrics = run_backtest(
        data,
        strategy,
        config,
        symbol=dataset.symbol,
    ).metrics
    return SignedVolumeEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _evaluate_shadow(
    dataset: VolatilityDataset,
    spec: SignedVolumeMomentumSpec,
) -> SignedVolumeEvaluation | None:
    strategy = SignedVolumeMomentumStrategy(spec, dataset.timeframe_hours)
    result = run_forward_shadow(
        dataset.data,
        strategy,
        start="2026-09-11",
        end="2100-01-01",
        config=CONFIG,
        symbol=dataset.symbol,
    )
    if result is None:
        return None
    metrics = result.metrics
    return SignedVolumeEvaluation(
        dataset=dataset.label,
        period="future_shadow",
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[SignedVolumeEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = SignedVolumeMomentumSpec()
    datasets = load_volatility_datasets(root)
    pre_rows: list[SignedVolumeEvaluation] = []
    for dataset in datasets:
        strategy = SignedVolumeMomentumStrategy(spec, dataset.timeframe_hours)
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
    stress_rows: list[SignedVolumeEvaluation] = []
    shadow_rows: list[SignedVolumeEvaluation] = []
    zero_cost_rows: list[SignedVolumeEvaluation] = []
    for dataset in datasets:
        stress = _evaluate(dataset, spec, CONFIG, "stress_2026", "2026-01-01", "2026-09-11")
        if stress is not None:
            stress_rows.append(stress)
        shadow = _evaluate_shadow(dataset, spec)
        if shadow is not None:
            shadow_rows.append(shadow)
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
    return pre_stress, stress_frame, _frame(shadow_rows), _frame(zero_cost_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run signed-volume confirmed momentum study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, shadow, zero_cost = run_research(root)
    pre_stress.to_csv(root / "signed_volume_momentum_pre_stress.csv", index=False)
    stress.to_csv(root / "signed_volume_momentum_stress_2026.csv", index=False)
    shadow.to_csv(root / "signed_volume_momentum_shadow.csv", index=False)
    zero_cost.to_csv(root / "signed_volume_momentum_zero_cost.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("future shadow")
    print("no completed shadow window yet" if shadow.empty else shadow.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))


if __name__ == "__main__":
    main()
