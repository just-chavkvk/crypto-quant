from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.data.market import load_market_data
from quant_lab.validation.lookahead import assert_no_lookahead


class PositionCapMomentumError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PositionCapMomentumSpec:
    lookback_hours: int = 336
    trend_ema_hours: int = 400
    cap_history_hours: int = 2160
    cap_quantile: float = 0.90

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0 or self.trend_ema_hours <= 0 or self.cap_history_hours <= 0:
            raise PositionCapMomentumError("strategy hour windows must be positive")
        if not 0.0 < self.cap_quantile < 1.0:
            raise PositionCapMomentumError("cap quantile must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class PositionCapMomentumStrategy:
    spec: PositionCapMomentumSpec
    timeframe_hours: int
    name: str = "global_position_cap_momentum"

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise PositionCapMomentumError("timeframe hours must be positive")

    def _bars(self, hours: int) -> int:
        return max(1, round(hours / self.timeframe_hours))

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        momentum = (close > close.shift(self._bars(self.spec.lookback_hours))) & (
            close
            > close.ewm(span=self._bars(self.spec.trend_ema_hours), adjust=False).mean()
        )
        positioning = data["count_long_short_ratio"]
        cap_bars = self._bars(self.spec.cap_history_hours)
        cap = (
            positioning.rolling(cap_bars, min_periods=cap_bars)
            .quantile(self.spec.cap_quantile)
            .shift(1)
        )
        return (momentum & (positioning <= cap)).fillna(False).astype(float)


@dataclass(frozen=True, slots=True)
class ResearchDataset:
    label: str
    symbol: str
    timeframe_hours: int
    data: pd.DataFrame


@dataclass(frozen=True, slots=True)
class WindowEvaluation:
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


def load_research_datasets(root: Path) -> tuple[ResearchDataset, ...]:
    return (
        ResearchDataset(
            "BTC_1h",
            "BTC/USDT",
            1,
            load_market_data(root / "BTC_USDT_1h_microstructure.parquet"),
        ),
        ResearchDataset(
            "ETH_1h",
            "ETH/USDT",
            1,
            load_market_data(root / "ETH_USDT_1h_microstructure.parquet"),
        ),
        ResearchDataset(
            "BTC_4h",
            "BTC/USDT",
            4,
            load_market_data(root / "BTC_USDT_4h_microstructure.parquet"),
        ),
        ResearchDataset(
            "ETH_4h",
            "ETH/USDT",
            4,
            load_market_data(root / "ETH_USDT_4h_microstructure.parquet"),
        ),
    )


def _slice_period(data: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    index = pd.DatetimeIndex(data.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    return data.loc[(index >= start_timestamp) & (index < end_timestamp)]


def _evaluate(
    dataset: ResearchDataset,
    spec: PositionCapMomentumSpec,
    period: str,
    start: str,
    end: str,
) -> WindowEvaluation | None:
    data = _slice_period(dataset.data, start, end)
    if len(data) < 2:
        return None
    strategy = PositionCapMomentumStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
    metrics: PerformanceMetrics = run_backtest(
        data,
        strategy,
        CONFIG,
        symbol=dataset.symbol,
    ).metrics
    return WindowEvaluation(
        dataset=dataset.label,
        period=period,
        total_return=metrics.total_return,
        sharpe_ratio=metrics.sharpe_ratio,
        max_drawdown=metrics.max_drawdown,
        number_of_trades=metrics.number_of_trades,
    )


def _to_frame(evaluations: list[WindowEvaluation]) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluation) for evaluation in evaluations])


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    spec = PositionCapMomentumSpec()
    datasets = load_research_datasets(root)
    historical: list[WindowEvaluation] = []
    shadow: list[WindowEvaluation] = []
    for dataset in datasets:
        strategy = PositionCapMomentumStrategy(spec=spec, timeframe_hours=dataset.timeframe_hours)
        assert_no_lookahead(dataset.data, strategy, max_checks=16)
        for period, start, end in (
            ("discovery", "2022-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
            ("stress_2026", "2026-01-01", "2026-09-11"),
        ):
            evaluation = _evaluate(dataset, spec, period, start, end)
            if evaluation is not None:
                historical.append(evaluation)
        shadow_evaluation = _evaluate(
            dataset,
            spec,
            "future_shadow",
            "2026-09-11",
            "2100-01-01",
        )
        if shadow_evaluation is not None:
            shadow.append(shadow_evaluation)
    return _to_frame(historical), _to_frame(shadow)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed global-position-cap momentum study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    historical, shadow = run_research(root)
    historical.to_csv(root / "position_cap_momentum_historical.csv", index=False)
    shadow.to_csv(root / "position_cap_momentum_shadow.csv", index=False)
    print("historical")
    print(historical.to_string(index=False))
    print("future shadow")
    if shadow.empty:
        print("no completed shadow window yet")
    else:
        print(shadow.to_string(index=False))


if __name__ == "__main__":
    main()
