from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_lab.backtest.metrics import calculate_metrics
from quant_lab.backtest.models import (
    BacktestConfig,
    BacktestInputError,
    BacktestResult,
    TradeRecord,
)
from quant_lab.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class _OpenPosition:
    side: int
    quantity: float
    entry_time: pd.Timestamp
    entry_price: float
    entry_fill_price: float
    entry_fee: float
    entry_slippage: float


def _execution_price(reference_price: float, order_side: int, slippage_rate: float) -> float:
    return reference_price * (1.0 + order_side * slippage_rate)


def _open_position(
    cash: float,
    side: int,
    reference_price: float,
    timestamp: pd.Timestamp,
    config: BacktestConfig,
) -> tuple[float, _OpenPosition]:
    quantity = side * (cash / reference_price)
    slippage_rate = config.slippage_bps / 10_000.0
    fill_price = _execution_price(reference_price, side, slippage_rate)
    fee = abs(quantity * fill_price) * config.fee_bps / 10_000.0
    slippage = abs(quantity) * abs(fill_price - reference_price)
    next_cash = cash - quantity * fill_price - fee
    return next_cash, _OpenPosition(
        side=side,
        quantity=quantity,
        entry_time=timestamp,
        entry_price=reference_price,
        entry_fill_price=fill_price,
        entry_fee=fee,
        entry_slippage=slippage,
    )


def _close_position(
    cash: float,
    position: _OpenPosition,
    reference_price: float,
    timestamp: pd.Timestamp,
    config: BacktestConfig,
    symbol: str,
) -> tuple[float, TradeRecord]:
    closing_quantity = -position.quantity
    order_side = -position.side
    slippage_rate = config.slippage_bps / 10_000.0
    fill_price = _execution_price(reference_price, order_side, slippage_rate)
    fee = abs(closing_quantity * fill_price) * config.fee_bps / 10_000.0
    slippage = abs(closing_quantity) * abs(fill_price - reference_price)
    next_cash = cash - closing_quantity * fill_price - fee

    position_size = abs(position.quantity)
    gross_pnl = position.side * position_size * (reference_price - position.entry_price)
    total_fee = position.entry_fee + fee
    total_slippage = position.entry_slippage + slippage
    net_pnl = gross_pnl - total_fee - total_slippage
    entry_notional = position_size * position.entry_price
    return_pct = net_pnl / entry_notional * 100.0 if entry_notional > 0 else 0.0

    return next_cash, TradeRecord(
        symbol=symbol,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        entry_fill_price=position.entry_fill_price,
        exit_time=timestamp,
        exit_price=reference_price,
        exit_fill_price=fill_price,
        position_size=position_size,
        gross_pnl=gross_pnl,
        fee=total_fee,
        slippage_cost=total_slippage,
        net_pnl=net_pnl,
        return_pct=return_pct,
        holding_period=timestamp - position.entry_time,
    )


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
    if (data[["open", "close"]] <= 0).any().any():
        raise BacktestInputError("open and close prices must be positive")


def _simulate_positions(
    data: pd.DataFrame,
    targets: pd.Series,
    config: BacktestConfig,
    symbol: str,
) -> BacktestResult:
    cash = config.initial_cash
    position: _OpenPosition | None = None
    trades: list[TradeRecord] = []
    equity_values: list[float] = []

    for offset, timestamp in enumerate(data.index):
        target = int(targets.iloc[offset])
        current_side = 0 if position is None else position.side
        open_price = float(data["open"].iloc[offset])
        close_price = float(data["close"].iloc[offset])

        if target != current_side:
            if position is not None:
                cash, trade = _close_position(
                    cash, position, open_price, timestamp, config, symbol
                )
                trades.append(trade)
                position = None
            if target != 0 and cash > 0:
                cash, position = _open_position(
                    cash, target, open_price, timestamp, config
                )

        quantity = 0.0 if position is None else position.quantity
        equity_values.append(cash + quantity * close_price)

        if offset == len(data) - 1 and position is not None:
            cash, trade = _close_position(
                cash, position, close_price, timestamp, config, symbol
            )
            trades.append(trade)
            equity_values[-1] = cash

    equity = pd.Series(equity_values, index=data.index, dtype=float, name="equity")
    returns = equity.pct_change().fillna(0.0)
    returns.iloc[0] = equity.iloc[0] / config.initial_cash - 1.0
    immutable_trades = tuple(trades)
    return BacktestResult(
        equity=equity,
        returns=returns,
        exposure=targets.astype(float),
        trades=immutable_trades,
        metrics=calculate_metrics(returns, equity, immutable_trades, config),
    )


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
    return _simulate_positions(data, targets, cfg, symbol)


def run_buy_and_hold(
    data: pd.DataFrame,
    config: BacktestConfig | None = None,
    *,
    symbol: str = "BTC/USDT",
) -> BacktestResult:
    cfg = config or BacktestConfig()
    targets = pd.Series(1.0, index=data.index, dtype=float)
    _validate_inputs(data, targets)
    return _simulate_positions(data, targets, cfg, symbol)
