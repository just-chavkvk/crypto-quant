from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray


class PriceLeadLagExecutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PriceLeadLagEvaluation:
    total_return: float | None
    sharpe_ratio: float | None
    number_of_trades: int
    mean_trade_return: float | None
    median_trade_return: float | None
    win_rate: float | None


def evaluate_price_lead_lag_events(
    frame: pd.DataFrame,
    events: pd.Series,
    *,
    hold_hours: int,
    fee_bps: float,
    slippage_bps: float,
    start: str,
    end: str,
) -> PriceLeadLagEvaluation:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise PriceLeadLagExecutionError("frame index must be a DatetimeIndex")
    if "eth_open" not in frame.columns:
        raise PriceLeadLagExecutionError("frame must contain eth_open")
    if not events.index.equals(frame.index):
        raise PriceLeadLagExecutionError("events index must exactly match the market frame")
    if hold_hours <= 0 or fee_bps < 0.0 or slippage_bps < 0.0:
        raise PriceLeadLagExecutionError("hold must be positive and costs non-negative")

    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    index = pd.DatetimeIndex(frame.index)
    event_values: NDArray[np.float64] = np.asarray(
        events.to_numpy(dtype=np.float64), dtype=np.float64
    )
    target_open: NDArray[np.float64] = np.asarray(
        frame["eth_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    in_period: NDArray[np.bool_] = np.asarray(
        (index >= start_timestamp) & (index < end_timestamp), dtype=np.bool_
    )
    fee_rate = fee_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0
    trade_returns: list[float] = []
    next_allowed_signal_offset = -1

    for signal_offset, (period_member, event_value) in enumerate(
        zip(in_period.tolist(), event_values.tolist(), strict=True)
    ):
        if not period_member or event_value == 0.0 or signal_offset < next_allowed_signal_offset:
            continue
        entry_offset = signal_offset + 1
        exit_offset = entry_offset + hold_hours
        if exit_offset >= len(frame) or index[exit_offset] >= end_timestamp:
            continue
        entry_price = float(target_open[entry_offset])
        exit_price = float(target_open[exit_offset])
        side = float(event_value)
        if not (
            np.isfinite(entry_price)
            and np.isfinite(exit_price)
            and entry_price > 0.0
            and exit_price > 0.0
        ):
            continue
        entry_fill = entry_price * (1.0 + side * slippage_rate)
        exit_fill = exit_price * (1.0 - side * slippage_rate)
        gross_return = side * (exit_price - entry_price) / entry_price
        slippage_cost = (
            abs(entry_fill - entry_price) + abs(exit_fill - exit_price)
        ) / entry_price
        fee_cost = fee_rate * (entry_fill + exit_fill) / entry_price
        trade_returns.append(gross_return - slippage_cost - fee_cost)
        next_allowed_signal_offset = exit_offset

    if not trade_returns:
        return PriceLeadLagEvaluation(None, None, 0, None, None, None)
    values = np.asarray(trade_returns, dtype=np.float64)
    standard_deviation = float(np.std(values, ddof=0))
    sharpe_ratio = (
        float(np.mean(values) / standard_deviation * np.sqrt(8760.0 / hold_hours))
        if standard_deviation > 0.0
        else 0.0
    )
    return PriceLeadLagEvaluation(
        total_return=float(np.prod(1.0 + values) - 1.0),
        sharpe_ratio=sharpe_ratio,
        number_of_trades=int(values.size),
        mean_trade_return=float(np.mean(values)),
        median_trade_return=float(np.median(values)),
        win_rate=float(np.mean(values > 0.0)),
    )
