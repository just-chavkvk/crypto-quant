from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.data.market import load_market_data
from quant_lab.validation.lookahead import assert_no_lookahead


class WickRejectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WickRejectionSpec:
    range_history_hours: int = 168
    range_multiple: float = 2.0
    wick_share: float = 0.50
    hold_hours: int = 4

    def __post_init__(self) -> None:
        if self.range_history_hours <= 0 or self.range_multiple <= 0.0 or self.hold_hours <= 0:
            raise WickRejectionError("range history, multiple, and hold must be positive")
        if not 0.0 < self.wick_share < 1.0:
            raise WickRejectionError("wick share must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class WickRejectionStrategy:
    spec: WickRejectionSpec
    timeframe_hours: int
    name: str = "extreme_wick_rejection"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise WickRejectionError("timeframe hours must be positive")
        if self.spec.range_history_hours % self.timeframe_hours != 0:
            raise WickRejectionError("range history must divide evenly by timeframe")
        if self.spec.hold_hours % self.timeframe_hours != 0:
            raise WickRejectionError("hold hours must divide evenly by timeframe")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        open_price = data["open"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        close = data["close"].astype(float)
        candle_range = high - low
        valid_range = candle_range.where(candle_range > 0.0)
        range_pct = valid_range / open_price
        history_bars = self.spec.range_history_hours // self.timeframe_hours
        prior_median = range_pct.shift(1).rolling(
            history_bars,
            min_periods=history_bars,
        ).median()
        lower_wick = (pd.concat([open_price, close], axis=1).min(axis=1) - low) / valid_range
        upper_wick = (high - pd.concat([open_price, close], axis=1).max(axis=1)) / valid_range
        extreme = range_pct >= prior_median * self.spec.range_multiple
        lower_event = (extreme & (lower_wick >= self.spec.wick_share)).fillna(False)
        upper_event = (extreme & (upper_wick >= self.spec.wick_share)).fillna(False)

        signals = pd.Series(0.0, index=data.index, dtype=float, name="signal")
        hold_bars = self.spec.hold_hours // self.timeframe_hours
        next_allowed_offset = 0
        for offset in range(len(data)):
            if offset < next_allowed_offset:
                continue
            lower = bool(lower_event.iloc[offset])
            upper = bool(upper_event.iloc[offset])
            if lower == upper:
                continue
            side = 1.0 if lower else -1.0
            end = min(offset + hold_bars, len(signals))
            signals.iloc[offset:end] = side
            next_allowed_offset = end
        return signals


@dataclass(frozen=True, slots=True)
class WickDataset:
    label: str
    symbol: str
    timeframe_hours: int
    data: pd.DataFrame


@dataclass(frozen=True, slots=True)
class WickEvaluation:
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


def load_wick_datasets(root: Path) -> tuple[WickDataset, ...]:
    rows: list[WickDataset] = []
    for timeframe_hours in (1, 4):
        suffix = f"{timeframe_hours}h_microstructure.parquet"
        for asset in ("BTC", "ETH"):
            rows.append(
                WickDataset(
                    label=f"{asset}_{timeframe_hours}h",
                    symbol=f"{asset}/USDT",
                    timeframe_hours=timeframe_hours,
                    data=load_market_data(root / f"{asset}_USDT_{suffix}"),
                )
            )
    return tuple(rows)


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: WickDataset,
    spec: WickRejectionSpec,
    config: BacktestConfig,
    period: str,
    start: str,
    end: str,
) -> WickEvaluation | None:
    data = _slice_period(dataset.data, start, end)
    if len(data) < 2:
        return None
    strategy = WickRejectionStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
    metrics: PerformanceMetrics = run_backtest(
        data,
        strategy,
        config,
        symbol=dataset.symbol,
    ).metrics
    return WickEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[WickEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = WickRejectionSpec()
    datasets = load_wick_datasets(root)
    pre_rows: list[WickEvaluation] = []
    for dataset in datasets:
        strategy = WickRejectionStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
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
    stress_rows: list[WickEvaluation] = []
    zero_cost_rows: list[WickEvaluation] = []
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
    parser = argparse.ArgumentParser(description="Run the preregistered extreme-wick rejection study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost = run_research(root)
    pre_stress.to_csv(root / "wick_rejection_pre_stress.csv", index=False)
    stress.to_csv(root / "wick_rejection_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "wick_rejection_zero_cost.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))


if __name__ == "__main__":
    main()
