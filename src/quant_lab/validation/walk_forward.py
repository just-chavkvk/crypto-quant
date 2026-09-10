from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.metrics import calculate_metrics
from quant_lab.backtest.models import BacktestConfig, BacktestResult, PerformanceMetrics
from quant_lab.strategies.base import Strategy


class WalkForwardInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    train_bars: int
    test_bars: int

    def __post_init__(self) -> None:
        if self.train_bars < 2 or self.test_bars < 1:
            raise WalkForwardInputError("train_bars must be >= 2 and test_bars must be >= 1")


@dataclass(frozen=True, slots=True)
class ValidationWindow:
    train: BacktestResult
    out_of_sample: BacktestResult
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    windows: tuple[ValidationWindow, ...]
    train_metrics: tuple[PerformanceMetrics, ...]
    out_of_sample_metrics: tuple[PerformanceMetrics, ...]
    walk_forward: BacktestResult
    passed: bool


@dataclass(frozen=True, slots=True)
class _PreparedSignals:
    signals: pd.Series
    name: str = "prepared_signals"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.signals.reindex(data.index)


def walk_forward_splits(
    data: pd.DataFrame,
    train_bars: int,
    test_bars: int,
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    """Yield chronological rolling train/test windows."""
    start = 0
    while start + train_bars + test_bars <= len(data):
        train_end = start + train_bars
        test_end = train_end + test_bars
        yield data.iloc[start:train_end], data.iloc[train_end:test_end]
        start += test_bars


def _run_out_of_sample(
    train: pd.DataFrame,
    test: pd.DataFrame,
    strategy: Strategy,
    backtest_config: BacktestConfig,
    symbol: str,
) -> BacktestResult:
    combined = pd.concat([train, test])
    combined_signals = strategy.generate_signals(combined).astype(float)
    context = combined.iloc[len(train) - 1 :]
    context_signals = combined_signals.reindex(context.index)
    return run_backtest(
        context,
        _PreparedSignals(context_signals),
        backtest_config,
        symbol=symbol,
    )


def _stitch_out_of_sample(
    windows: tuple[ValidationWindow, ...],
    backtest_config: BacktestConfig,
) -> BacktestResult:
    return_parts = [window.out_of_sample.returns.iloc[1:] for window in windows]
    timestamps = [value for part in return_parts for value in pd.DatetimeIndex(part.index)]
    returns = pd.Series(
        [float(value) for part in return_parts for value in part],
        index=pd.DatetimeIndex(timestamps),
        dtype=float,
    )
    exposure_parts = [window.out_of_sample.exposure.iloc[1:] for window in windows]
    exposure = pd.Series(
        [float(value) for part in exposure_parts for value in part],
        index=returns.index,
        dtype=float,
    )
    equity = backtest_config.initial_cash * (1.0 + returns).cumprod()
    trades = tuple(trade for window in windows for trade in window.out_of_sample.trades)
    return BacktestResult(
        equity=equity,
        returns=returns,
        exposure=exposure,
        trades=trades,
        metrics=calculate_metrics(returns, equity, trades, backtest_config),
    )


def evaluate_walk_forward(
    data: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    config: WalkForwardConfig,
    backtest_config: BacktestConfig | None = None,
    *,
    symbol: str = "UNKNOWN",
) -> WalkForwardReport:
    bt_config = backtest_config or BacktestConfig()
    windows: list[ValidationWindow] = []
    for train, test in walk_forward_splits(data, config.train_bars, config.test_bars):
        strategy = strategy_factory()
        train_result = run_backtest(train, strategy, bt_config, symbol=symbol)
        oos_result = _run_out_of_sample(train, test, strategy, bt_config, symbol)
        windows.append(ValidationWindow(
            train=train_result, out_of_sample=oos_result,
            train_start=str(train.index[0]),
            train_end=str(train.index[-1]),
            test_start=str(test.index[0]),
            test_end=str(test.index[-1]),
        ))
    if not windows:
        raise WalkForwardInputError("not enough candles for one walk-forward window")
    immutable_windows = tuple(windows)
    stitched = _stitch_out_of_sample(immutable_windows, bt_config)
    passed = all(
        window.out_of_sample.metrics.total_return > 0.0
        and window.out_of_sample.metrics.sharpe_ratio > 0.0
        for window in immutable_windows
    ) and stitched.metrics.total_return > 0.0
    return WalkForwardReport(
        windows=immutable_windows,
        train_metrics=tuple(window.train.metrics for window in immutable_windows),
        out_of_sample_metrics=tuple(window.out_of_sample.metrics for window in immutable_windows),
        walk_forward=stitched,
        passed=passed,
    )
