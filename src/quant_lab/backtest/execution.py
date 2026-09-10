from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_lab.backtest.metrics import calculate_metrics
from quant_lab.backtest.models import BacktestConfig, BacktestResult, TradeRecord
from quant_lab.risk.sizing import RiskConfig, position_size_from_stop


@dataclass(frozen=True, slots=True)
class OpenPosition:
    side: int
    quantity: float
    entry_time: pd.Timestamp
    entry_price: float
    entry_fill_price: float
    entry_fee: float
    entry_slippage: float
    entry_fills: int


def _slippage_rate(
    config: BacktestConfig,
    reference_price: float,
    high_price: float,
    low_price: float,
) -> float:
    base = config.slippage_bps / 10_000.0
    candle_range = max(high_price - low_price, 0.0) / reference_price
    variable = candle_range * config.volatility_slippage_multiplier
    return min(base + variable, 0.95)


def _execution_price(reference_price: float, order_side: int, slippage_rate: float) -> float:
    return reference_price * (1.0 + order_side * slippage_rate)


def _desired_quantity(
    equity: float,
    reference_price: float,
    side: int,
    config: BacktestConfig,
) -> float:
    if config.risk_per_trade is None or config.stop_loss_pct is None:
        return equity * config.max_exposure * config.max_leverage / reference_price
    stop_price = reference_price * (1.0 - side * config.stop_loss_pct)
    risk_config = RiskConfig(
        risk_per_trade=config.risk_per_trade,
        max_exposure=config.max_exposure,
        max_leverage=config.max_leverage,
    )
    return position_size_from_stop(equity, reference_price, stop_price, risk_config)


def _entry_capacity(volume: float, config: BacktestConfig) -> float:
    if config.max_volume_participation is None:
        return float("inf")
    return max(volume, 0.0) * config.max_volume_participation


def _add_entry_fill(
    cash: float,
    position: OpenPosition | None,
    side: int,
    quantity: float,
    reference_price: float,
    fill_price: float,
    timestamp: pd.Timestamp,
    config: BacktestConfig,
) -> tuple[float, OpenPosition]:
    fee = quantity * fill_price * config.fee_bps / 10_000.0
    slippage = quantity * abs(fill_price - reference_price)
    next_cash = cash - side * quantity * fill_price - fee
    if position is None:
        return next_cash, OpenPosition(
            side=side,
            quantity=quantity,
            entry_time=timestamp,
            entry_price=reference_price,
            entry_fill_price=fill_price,
            entry_fee=fee,
            entry_slippage=slippage,
            entry_fills=1,
        )
    total_quantity = position.quantity + quantity
    reference_average = (
        position.entry_price * position.quantity + reference_price * quantity
    ) / total_quantity
    fill_average = (
        position.entry_fill_price * position.quantity + fill_price * quantity
    ) / total_quantity
    return next_cash, OpenPosition(
        side=side,
        quantity=total_quantity,
        entry_time=position.entry_time,
        entry_price=reference_average,
        entry_fill_price=fill_average,
        entry_fee=position.entry_fee + fee,
        entry_slippage=position.entry_slippage + slippage,
        entry_fills=position.entry_fills + 1,
    )


def _close_position(
    cash: float,
    position: OpenPosition,
    reference_price: float,
    fill_price: float,
    timestamp: pd.Timestamp,
    config: BacktestConfig,
    symbol: str,
) -> tuple[float, TradeRecord]:
    closing_quantity = -position.side * position.quantity
    fee = position.quantity * fill_price * config.fee_bps / 10_000.0
    slippage = position.quantity * abs(fill_price - reference_price)
    next_cash = cash - closing_quantity * fill_price - fee
    gross_pnl = position.side * position.quantity * (reference_price - position.entry_price)
    total_fee = position.entry_fee + fee
    total_slippage = position.entry_slippage + slippage
    net_pnl = gross_pnl - total_fee - total_slippage
    entry_notional = position.quantity * position.entry_price
    return_pct = net_pnl / entry_notional * 100.0 if entry_notional > 0.0 else 0.0
    return next_cash, TradeRecord(
        symbol=symbol,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        entry_fill_price=position.entry_fill_price,
        exit_time=timestamp,
        exit_price=reference_price,
        exit_fill_price=fill_price,
        position_size=position.quantity,
        gross_pnl=gross_pnl,
        fee=total_fee,
        slippage_cost=total_slippage,
        net_pnl=net_pnl,
        return_pct=return_pct,
        holding_period=timestamp - position.entry_time,
        entry_fills=position.entry_fills,
    )


def _stop_reference(
    position: OpenPosition,
    open_price: float,
    high_price: float,
    low_price: float,
    stop_loss_pct: float,
) -> float | None:
    stop_price = position.entry_price * (1.0 - position.side * stop_loss_pct)
    if position.side > 0 and low_price <= stop_price:
        return min(open_price, stop_price)
    if position.side < 0 and high_price >= stop_price:
        return max(open_price, stop_price)
    return None


def simulate_positions(
    data: pd.DataFrame,
    targets: pd.Series,
    config: BacktestConfig,
    symbol: str,
) -> BacktestResult:
    cash = config.initial_cash
    position: OpenPosition | None = None
    trades: list[TradeRecord] = []
    equity_values: list[float] = []
    exposure_values: list[float] = []

    for offset, timestamp in enumerate(data.index):
        target = int(targets.iloc[offset])
        open_price = float(data["open"].iloc[offset])
        high_price = float(data["high"].iloc[offset])
        low_price = float(data["low"].iloc[offset])
        close_price = float(data["close"].iloc[offset])
        volume = float(data["volume"].iloc[offset])
        current_side = 0 if position is None else position.side

        if position is not None and target != current_side:
            rate = _slippage_rate(config, open_price, high_price, low_price)
            fill_price = _execution_price(open_price, -position.side, rate)
            cash, trade = _close_position(
                cash, position, open_price, fill_price, timestamp, config, symbol
            )
            trades.append(trade)
            position = None

        if target != 0:
            signed_quantity = 0.0 if position is None else position.side * position.quantity
            equity_at_open = cash + signed_quantity * open_price
            desired = _desired_quantity(equity_at_open, open_price, target, config)
            existing = 0.0 if position is None else position.quantity
            fill_quantity = min(max(desired - existing, 0.0), _entry_capacity(volume, config))
            if fill_quantity > 0.0:
                rate = _slippage_rate(config, open_price, high_price, low_price)
                fill_price = _execution_price(open_price, target, rate)
                cash, position = _add_entry_fill(
                    cash,
                    position,
                    target,
                    fill_quantity,
                    open_price,
                    fill_price,
                    timestamp,
                    config,
                )

        if position is not None and config.stop_loss_pct is not None:
            stop_reference = _stop_reference(
                position, open_price, high_price, low_price, config.stop_loss_pct
            )
            if stop_reference is not None:
                rate = _slippage_rate(config, stop_reference, high_price, low_price)
                fill_price = _execution_price(stop_reference, -position.side, rate)
                cash, trade = _close_position(
                    cash, position, stop_reference, fill_price, timestamp, config, symbol
                )
                trades.append(trade)
                position = None

        signed_quantity = 0.0 if position is None else position.side * position.quantity
        equity = cash + signed_quantity * close_price
        equity_values.append(equity)
        exposure_values.append(
            0.0 if position is None or equity <= 0.0 else signed_quantity * close_price / equity
        )

        if offset == len(data) - 1 and position is not None:
            rate = _slippage_rate(config, close_price, high_price, low_price)
            fill_price = _execution_price(close_price, -position.side, rate)
            cash, trade = _close_position(
                cash, position, close_price, fill_price, timestamp, config, symbol
            )
            trades.append(trade)
            equity_values[-1] = cash
            exposure_values[-1] = 0.0
            position = None

    equity = pd.Series(equity_values, index=data.index, dtype=float, name="equity")
    returns = equity.pct_change().fillna(0.0)
    returns.iloc[0] = equity.iloc[0] / config.initial_cash - 1.0
    exposure = pd.Series(exposure_values, index=data.index, dtype=float, name="exposure")
    immutable_trades = tuple(trades)
    return BacktestResult(
        equity=equity,
        returns=returns,
        exposure=exposure,
        trades=immutable_trades,
        metrics=calculate_metrics(returns, equity, immutable_trades, config),
    )
