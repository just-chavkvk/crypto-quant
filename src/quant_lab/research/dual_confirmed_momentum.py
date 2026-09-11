from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import PerformanceMetrics
from quant_lab.research.breadth_momentum import (
    CONFIG,
    BreadthDataset,
    BreadthMomentumSpec,
    BreadthMomentumStrategy,
    load_breadth_datasets,
)
from quant_lab.research.position_cap_momentum import (
    PositionCapMomentumSpec,
    PositionCapMomentumStrategy,
)
from quant_lab.validation.forward_shadow import run_forward_shadow
from quant_lab.validation.lookahead import assert_no_lookahead


class DualConfirmedMomentumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DualConfirmedMomentumStrategy:
    timeframe_hours: int
    other_close: pd.Series
    lookback_hours: int = 336
    trend_ema_hours: int = 400
    cap_history_hours: int = 2160
    cap_quantile: float = 0.90
    name: str = "dual_confirmed_momentum"

    def __post_init__(self) -> None:
        if min(
            self.timeframe_hours,
            self.lookback_hours,
            self.trend_ema_hours,
            self.cap_history_hours,
        ) <= 0:
            raise DualConfirmedMomentumError("strategy windows and timeframe must be positive")
        if not 0.0 < self.cap_quantile < 1.0:
            raise DualConfirmedMomentumError("cap quantile must be in (0, 1)")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        breadth = BreadthMomentumStrategy(
            spec=BreadthMomentumSpec(
                lookback_hours=self.lookback_hours,
                trend_ema_hours=self.trend_ema_hours,
            ),
            timeframe_hours=self.timeframe_hours,
            other_close=self.other_close,
        ).generate_signals(data)
        position_cap = PositionCapMomentumStrategy(
            spec=PositionCapMomentumSpec(
                lookback_hours=self.lookback_hours,
                trend_ema_hours=self.trend_ema_hours,
                cap_history_hours=self.cap_history_hours,
                cap_quantile=self.cap_quantile,
            ),
            timeframe_hours=self.timeframe_hours,
        ).generate_signals(data)
        signals = ((breadth > 0.0) & (position_cap > 0.0)).astype(float)
        signals.name = "signal"
        return signals


@dataclass(frozen=True, slots=True)
class DualConfirmedEvaluation:
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


def _strategy(dataset: BreadthDataset) -> DualConfirmedMomentumStrategy:
    return DualConfirmedMomentumStrategy(
        timeframe_hours=dataset.timeframe_hours,
        other_close=dataset.other_close,
    )


def _evaluate(
    dataset: BreadthDataset,
    period: str,
    start: str,
    end: str,
) -> DualConfirmedEvaluation | None:
    own = _slice_period(dataset.own, start, end)
    if len(own) < 2:
        return None
    strategy = DualConfirmedMomentumStrategy(
        timeframe_hours=dataset.timeframe_hours,
        other_close=dataset.other_close.reindex(own.index),
    )
    metrics: PerformanceMetrics = run_backtest(
        own,
        strategy,
        CONFIG,
        symbol=dataset.symbol,
    ).metrics
    return DualConfirmedEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _evaluate_shadow(dataset: BreadthDataset) -> DualConfirmedEvaluation | None:
    result = run_forward_shadow(
        dataset.own,
        _strategy(dataset),
        start="2026-09-11 08:00",
        end="2100-01-01",
        config=CONFIG,
        symbol=dataset.symbol,
    )
    if result is None:
        return None
    metrics = result.metrics
    return DualConfirmedEvaluation(
        dataset=dataset.label,
        period="future_shadow",
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(rows: list[DualConfirmedEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    datasets = load_breadth_datasets(root)
    pre_rows: list[DualConfirmedEvaluation] = []
    for dataset in datasets:
        assert_no_lookahead(dataset.own, _strategy(dataset), max_checks=16)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
        ):
            evaluation = _evaluate(dataset, period, start, end)
            if evaluation is not None:
                pre_rows.append(evaluation)
    pre_pass = bool(pre_rows) and all(
        row.total_return > 0.0 and row.sharpe_ratio > 0.0 and row.number_of_trades >= 10
        for row in pre_rows
    )
    pre_stress = _frame(pre_rows)
    pre_stress["pre_holdout_pass"] = pre_pass

    stress_rows: list[DualConfirmedEvaluation] = []
    shadow_rows: list[DualConfirmedEvaluation] = []
    for dataset in datasets:
        stress = _evaluate(dataset, "stress_2026", "2026-01-01", "2026-09-11")
        if stress is not None:
            stress_rows.append(stress)
        shadow = _evaluate_shadow(dataset)
        if shadow is not None:
            shadow_rows.append(shadow)
    stress_frame = _frame(stress_rows)
    stress_frame["pre_holdout_pass"] = pre_pass
    return pre_stress, stress_frame, _frame(shadow_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run dual-confirmed momentum study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, shadow = run_research(root)
    pre_stress.to_csv(root / "dual_confirmed_momentum_pre_stress.csv", index=False)
    stress.to_csv(root / "dual_confirmed_momentum_stress_2026.csv", index=False)
    shadow.to_csv(root / "dual_confirmed_momentum_shadow.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("future shadow")
    print("no completed shadow window yet" if shadow.empty else shadow.to_string(index=False))


if __name__ == "__main__":
    main()
