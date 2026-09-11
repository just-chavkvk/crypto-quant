from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.data.market import load_market_data
from quant_lab.validation.lookahead import assert_no_lookahead


class BreadthMomentumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BreadthMomentumSpec:
    lookback_hours: int = 336
    trend_ema_hours: int = 400

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0 or self.trend_ema_hours <= 0:
            raise BreadthMomentumError("momentum and EMA windows must be positive")


@dataclass(frozen=True, slots=True)
class BreadthMomentumStrategy:
    spec: BreadthMomentumSpec
    timeframe_hours: int
    other_close: pd.Series
    name: str = "breadth_confirmed_momentum"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise BreadthMomentumError("timeframe hours must be positive")

    def _bars(self, hours: int) -> int:
        return max(1, round(hours / self.timeframe_hours))

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        aligned_other = self.other_close.reindex(data.index)
        lookback = self._bars(self.spec.lookback_hours)
        ema_span = self._bars(self.spec.trend_ema_hours)
        own_momentum = close > close.shift(lookback)
        own_trend = close > close.ewm(span=ema_span, adjust=False).mean()
        other_trend = aligned_other > aligned_other.ewm(span=ema_span, adjust=False).mean()
        signals = (own_momentum & own_trend & other_trend).fillna(False).astype(float)
        signals.name = "signal"
        return signals


@dataclass(frozen=True, slots=True)
class BreadthDataset:
    label: str
    symbol: str
    timeframe_hours: int
    own: pd.DataFrame
    other_close: pd.Series


@dataclass(frozen=True, slots=True)
class BreadthEvaluation:
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


def load_breadth_datasets(root: Path) -> tuple[BreadthDataset, ...]:
    datasets: list[BreadthDataset] = []
    for timeframe_hours in (1, 4):
        suffix = f"{timeframe_hours}h_microstructure.parquet"
        btc = load_market_data(root / f"BTC_USDT_{suffix}")
        eth = load_market_data(root / f"ETH_USDT_{suffix}")
        common_index = btc.index.intersection(eth.index)
        btc = btc.loc[common_index]
        eth = eth.loc[common_index]
        datasets.extend(
            (
                BreadthDataset(
                    label=f"BTC_{timeframe_hours}h",
                    symbol="BTC/USDT",
                    timeframe_hours=timeframe_hours,
                    own=btc,
                    other_close=eth["close"],
                ),
                BreadthDataset(
                    label=f"ETH_{timeframe_hours}h",
                    symbol="ETH/USDT",
                    timeframe_hours=timeframe_hours,
                    own=eth,
                    other_close=btc["close"],
                ),
            )
        )
    return tuple(datasets)


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: BreadthDataset,
    spec: BreadthMomentumSpec,
    period: str,
    start: str,
    end: str,
) -> BreadthEvaluation | None:
    own = _slice_period(dataset.own, start, end)
    if len(own) < 2:
        return None
    other_close = dataset.other_close.reindex(own.index)
    strategy = BreadthMomentumStrategy(
        spec=spec,
        timeframe_hours=dataset.timeframe_hours,
        other_close=other_close,
    )
    metrics: PerformanceMetrics = run_backtest(
        own,
        strategy,
        CONFIG,
        symbol=dataset.symbol,
    ).metrics
    return BreadthEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _frame(evaluations: list[BreadthEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluation) for evaluation in evaluations])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spec = BreadthMomentumSpec()
    datasets = load_breadth_datasets(root)
    pre_stress_rows: list[BreadthEvaluation] = []
    for dataset in datasets:
        full_strategy = BreadthMomentumStrategy(
            spec=spec,
            timeframe_hours=dataset.timeframe_hours,
            other_close=dataset.other_close,
        )
        assert_no_lookahead(dataset.own, full_strategy, max_checks=16)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
        ):
            evaluation = _evaluate(dataset, spec, period, start, end)
            if evaluation is not None:
                pre_stress_rows.append(evaluation)
    pre_pass = all(
        evaluation.total_return > 0.0
        and evaluation.sharpe_ratio > 0.0
        and evaluation.number_of_trades >= 10
        for evaluation in pre_stress_rows
    )
    pre_stress = _frame(pre_stress_rows)
    pre_stress["pre_holdout_pass"] = pre_pass

    stress_rows: list[BreadthEvaluation] = []
    shadow_rows: list[BreadthEvaluation] = []
    for dataset in datasets:
        stress = _evaluate(dataset, spec, "stress_2026", "2026-01-01", "2026-09-11")
        if stress is not None:
            stress_rows.append(stress)
        shadow = _evaluate(dataset, spec, "future_shadow", "2026-09-11", "2100-01-01")
        if shadow is not None:
            shadow_rows.append(shadow)
    stress_frame = _frame(stress_rows)
    stress_frame["pre_holdout_pass"] = pre_pass
    return pre_stress, stress_frame, _frame(shadow_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered BTC/ETH breadth momentum study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, shadow = run_research(root)
    pre_stress.to_csv(root / "breadth_momentum_pre_stress.csv", index=False)
    stress.to_csv(root / "breadth_momentum_stress_2026.csv", index=False)
    shadow.to_csv(root / "breadth_momentum_shadow.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("future shadow")
    print("no completed shadow window yet" if shadow.empty else shadow.to_string(index=False))


if __name__ == "__main__":
    main()
