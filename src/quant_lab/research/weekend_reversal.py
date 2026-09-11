from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path

import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.data.market import load_market_data
from quant_lab.validation.lookahead import assert_no_lookahead


class WeekendReversalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WeekendReversalSpec:
    weekend_hours: int = 48
    hold_hours: int = 24

    def __post_init__(self) -> None:
        if self.weekend_hours <= 0 or self.hold_hours <= 0:
            raise WeekendReversalError("weekend and hold hours must be positive")


@dataclass(frozen=True, slots=True)
class WeekendReversalStrategy:
    spec: WeekendReversalSpec
    timeframe_hours: int
    name: str = "weekend_monday_reversal"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise WeekendReversalError("timeframe hours must be positive")
        if self.spec.weekend_hours % self.timeframe_hours != 0:
            raise WeekendReversalError("weekend hours must divide evenly by timeframe")
        if self.spec.hold_hours % self.timeframe_hours != 0:
            raise WeekendReversalError("hold hours must divide evenly by timeframe")
        if 24 % self.timeframe_hours != 0:
            raise WeekendReversalError("timeframe must divide a UTC day")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if not isinstance(data.index, pd.DatetimeIndex):
            raise WeekendReversalError("market data index must be a DatetimeIndex")
        close = data["close"].astype(float)
        weekend_bars = self.spec.weekend_hours // self.timeframe_hours
        hold_bars = self.spec.hold_hours // self.timeframe_hours
        weekend_return = close / close.shift(weekend_bars) - 1.0
        index = pd.DatetimeIndex(data.index)
        decision_hour = 24 - self.timeframe_hours
        signals = pd.Series(0.0, index=data.index, dtype=float, name="signal")
        for offset in range(len(index)):
            timestamp = index[offset]
            if timestamp.dayofweek != 6 or timestamp.hour != decision_hour:
                continue
            value = float(weekend_return.iloc[offset])
            if not isfinite(value) or value == 0.0:
                continue
            side = -1.0 if value > 0.0 else 1.0
            end = min(offset + hold_bars, len(signals))
            signals.iloc[offset:end] = side
        return signals


@dataclass(frozen=True, slots=True)
class WeekendDataset:
    label: str
    symbol: str
    timeframe_hours: int
    data: pd.DataFrame


@dataclass(frozen=True, slots=True)
class WeekendEvaluation:
    dataset: str
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    number_of_trades: int


CONFIG = BacktestConfig(
    fee_bps=5.0,
    slippage_bps=2.0,
    risk_per_trade=0.01,
    stop_loss_pct=0.05,
    volatility_slippage_multiplier=0.02,
)


def load_weekend_datasets(root: Path) -> tuple[WeekendDataset, ...]:
    datasets: list[WeekendDataset] = []
    for timeframe_hours in (1, 4):
        suffix = f"{timeframe_hours}h_microstructure.parquet"
        for asset in ("BTC", "ETH"):
            datasets.append(
                WeekendDataset(
                    label=f"{asset}_{timeframe_hours}h",
                    symbol=f"{asset}/USDT",
                    timeframe_hours=timeframe_hours,
                    data=load_market_data(root / f"{asset}_USDT_{suffix}"),
                )
            )
    return tuple(datasets)


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: WeekendDataset,
    spec: WeekendReversalSpec,
    config: BacktestConfig,
    period: str,
    start: str,
    end: str,
) -> WeekendEvaluation | None:
    data = _slice_period(dataset.data, start, end)
    if len(data) < 2:
        return None
    strategy = WeekendReversalStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
    metrics: PerformanceMetrics = run_backtest(
        data,
        strategy,
        config,
        symbol=dataset.symbol,
    ).metrics
    return WeekendEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[WeekendEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = WeekendReversalSpec()
    datasets = load_weekend_datasets(root)
    pre_rows: list[WeekendEvaluation] = []
    for dataset in datasets:
        strategy = WeekendReversalStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
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

    stress_rows: list[WeekendEvaluation] = []
    zero_cost_rows: list[WeekendEvaluation] = []
    zero_cost_config = BacktestConfig(
        fee_bps=0.0,
        slippage_bps=0.0,
        risk_per_trade=0.01,
        stop_loss_pct=0.05,
        volatility_slippage_multiplier=0.0,
    )
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
    parser = argparse.ArgumentParser(description="Run the preregistered weekend-to-Monday reversal study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost = run_research(root)
    pre_stress.to_csv(root / "weekend_reversal_pre_stress.csv", index=False)
    stress.to_csv(root / "weekend_reversal_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "weekend_reversal_zero_cost.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))


if __name__ == "__main__":
    main()
