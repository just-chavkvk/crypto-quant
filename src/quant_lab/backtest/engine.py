from __future__ import annotations

import pandas as pd

from quant_lab.backtest.execution import simulate_positions
from quant_lab.backtest.models import (
    BacktestConfig,
    BacktestInputError,
    BacktestResult,
)
from quant_lab.strategies.base import Strategy


def _validate_inputs(data: pd.DataFrame, signals: pd.Series) -> None:
    if len(data) < 2:
        raise BacktestInputError("backtest requires at least two candles")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise BacktestInputError("market data index must be a DatetimeIndex")
    if not signals.index.equals(data.index):
        raise BacktestInputError("strategy signal index must exactly match market data")
    if signals.isna().any():
        raise BacktestInputError("strategy signals must not contain missing values")
    if not signals.isin((-1.0, 0.0, 1.0)).all():
        raise BacktestInputError("v0.1 strategies must emit discrete target positions: -1, 0, or 1")
    required_columns = ["open", "high", "low", "close", "volume"]
    if data[required_columns].isna().any().any():
        raise BacktestInputError("market data must not contain missing OHLCV values")
    if (data[["open", "high", "low", "close"]] <= 0).any().any():
        raise BacktestInputError("OHLC prices must be positive")
    if (data["volume"] < 0).any():
        raise BacktestInputError("volume must be non-negative")


def run_backtest(
    data: pd.DataFrame,
    strategy: Strategy,
    config: BacktestConfig | None = None,
    *,
    symbol: str = "UNKNOWN",
) -> BacktestResult:
    cfg = config or BacktestConfig()
    signals = strategy.generate_signals(data).astype(float)
    _validate_inputs(data, signals)
    targets = pd.Series(signals.shift(1).fillna(0.0), index=data.index, dtype=float)
    return simulate_positions(data, targets, cfg, symbol)


def run_buy_and_hold(
    data: pd.DataFrame,
    config: BacktestConfig | None = None,
    *,
    symbol: str = "BTC/USDT",
) -> BacktestResult:
    cfg = config or BacktestConfig()
    targets = pd.Series(1.0, index=data.index, dtype=float)
    _validate_inputs(data, targets)
    return simulate_positions(data, targets, cfg, symbol)
