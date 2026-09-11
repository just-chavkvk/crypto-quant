from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Final, TypedDict

import numpy as np
import polars as pl
from numpy.typing import NDArray

_HOUR: Final = timedelta(hours=1)
_COLUMNS: Final = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "signal",
    "funding_rate_event",
    "mark_open",
)
_TIME: Final = pl.Datetime("us", "UTC")
_TRADE_SCHEMA: Final = pl.Schema(
    {
        "signal_time": _TIME,
        "entry_time": _TIME,
        "exit_time": _TIME,
        "side": pl.Float64,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "gross_pnl": pl.Float64,
        "execution_cost": pl.Float64,
        "funding_pnl": pl.Float64,
        "net_pnl": pl.Float64,
        "reason": pl.String,
    }
)


class ParticipationExecutionError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ParticipationBoundaryWarning(UserWarning):
    pass


class _Trade(TypedDict):
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    side: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    execution_cost: float
    funding_pnl: float
    net_pnl: float
    reason: str


@dataclass(frozen=True, slots=True)
class _Position:
    signal_time: datetime
    entry_time: datetime
    side: float
    entry_price: float
    quantity: float
    entry_cost: float
    funding_pnl: float = 0.0


def _prepare(
    frame: pl.DataFrame,
    start: datetime,
    end: datetime,
) -> tuple[list[datetime], NDArray[np.float64]]:
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ParticipationExecutionError("period must be timezone-aware with start < end")
    boundaries = (start.astimezone(UTC), end.astimezone(UTC))
    if any(t.minute or t.second or t.microsecond for t in boundaries):
        raise ParticipationExecutionError("period boundaries must align with the hourly calendar")
    if {"timestamp", *_COLUMNS}.difference(frame.columns):
        raise ParticipationExecutionError("missing required execution columns")
    if frame.schema["timestamp"] not in tuple(
        pl.Datetime(unit, "UTC") for unit in ("us", "ms", "ns")
    ):
        raise ParticipationExecutionError("timestamp must be a UTC Datetime column")
    if frame["timestamp"].null_count():
        raise ParticipationExecutionError("calendar timestamps must not be null")
    times: list[datetime] = frame["timestamp"].to_list()
    if not times or times[0] > start or times[-1] < end - _HOUR:
        raise ParticipationExecutionError("frame must cover the complete evaluation calendar")
    if any(t.minute or t.second or t.microsecond for t in times) or any(
        right - left != _HOUR for left, right in pairwise(times)
    ):
        raise ParticipationExecutionError("calendar must be sorted, unique and contiguous hourly")
    if any(not frame.schema[column].is_numeric() for column in _COLUMNS):
        raise ParticipationExecutionError("execution columns must be numeric and finite")
    values: NDArray[np.float64] = np.asarray(frame.select(_COLUMNS).to_numpy(), dtype=np.float64)
    if not np.isfinite(values).all():
        raise ParticipationExecutionError("execution prices, funding and signals must be finite")
    if (values[:, :4] <= 0.0).any() or (values[:, 7] <= 0.0).any():
        raise ParticipationExecutionError("OHLC and mark_open must be positive")
    if (
        (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any()
        or (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any()
        or not ((values[:, 5] == -1.0) | (values[:, 5] == 0.0) | (values[:, 5] == 1.0)).all()
    ):
        raise ParticipationExecutionError("invalid OHLC bounds or discrete signal")
    return times, values


def _execution_cost(price: float, signed_quantity: float, rates: tuple[float, float]) -> float:
    fee, slippage = rates
    side = 1.0 if signed_quantity > 0.0 else -1.0
    fill = price * (1.0 + side * slippage)
    if fill <= 0.0:
        raise ParticipationExecutionError("adverse execution fill must remain positive")
    return abs(signed_quantity) * (abs(fill - price) + fill * fee)


def evaluate_events(
    frame: pl.DataFrame,
    start: datetime,
    end: datetime,
    zero_cost: bool = False,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Evaluate fixed hourly signals, starting flat over [start, end).

    Equity is valued at candle close and labeled by candle open. Trade prices are
    reference prices; execution_cost includes adverse fills and fees. Intrabar stops
    are timestamped at candle end minus one microsecond to express funding ordering,
    not an observed tick time. Boundary-truncated signals are counted in a warning.
    """
    times, values = _prepare(frame, start, end)
    cash = 10_000.0
    position: _Position | None = None
    trades: list[_Trade] = []
    equity_times: list[datetime] = []
    equity_values: list[float] = []
    boundary_skips = sum(
        1
        for i, timestamp in enumerate(times)
        if start <= timestamp < end and values[i, 5] != 0.0 and timestamp + 5 * _HOUR >= end
    )
    for offset, timestamp in enumerate(times):
        if not start <= timestamp < end:
            continue
        opening, high, low, close, _, _, funding, mark = values[offset].tolist()
        rates = (0.0, 0.0)
        if not zero_cost and offset > 0:
            prior = values[offset - 1]
            rates = (0.0005, 0.0002 + 0.02 * float((prior[1] - prior[2]) / prior[0]))
        if (
            position is None
            and cash > 0.0
            and offset > 0
            and times[offset - 1] >= start
            and timestamp + 4 * _HOUR < end
            and bool((values[offset - 1 : offset + 5, 4] > 0.0).all())
        ):
            side = float(values[offset - 1, 5])
            if side != 0.0:
                quantity = 0.20 * cash / opening
                cost = _execution_cost(opening, side * quantity, rates)
                position = _Position(times[offset - 1], timestamp, side, opening, quantity, cost)
                cash -= cost
        if position is not None:
            stop = position.entry_price * (1.0 - position.side * 0.05)
            gap_stop = position.side * (opening - stop) <= 0.0
            scheduled = timestamp == position.entry_time + 4 * _HOUR
            exit_price, exit_time = opening, timestamp
            reason = "gap_stop" if gap_stop else "hold"
            exiting = gap_stop or scheduled
            if not exiting:
                payment = -position.side * position.quantity * mark * funding
                cash += payment
                position = replace(position, funding_pnl=position.funding_pnl + payment)
                extreme = low if position.side > 0.0 else high
                if position.side * (extreme - stop) <= 0.0:
                    exiting, reason, exit_price = True, "stop", stop
                    exit_time = timestamp + _HOUR - timedelta(microseconds=1)
            if exiting:
                gross = position.side * position.quantity * (exit_price - position.entry_price)
                exit_cost = _execution_cost(exit_price, -position.side * position.quantity, rates)
                execution_cost = position.entry_cost + exit_cost
                cash += gross - exit_cost
                trades.append(
                    {
                        "signal_time": position.signal_time,
                        "entry_time": position.entry_time,
                        "exit_time": exit_time,
                        "side": position.side,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "gross_pnl": gross,
                        "execution_cost": execution_cost,
                        "funding_pnl": position.funding_pnl,
                        "net_pnl": gross - execution_cost + position.funding_pnl,
                        "reason": reason,
                    }
                )
                position = None
        unrealized = (
            0.0
            if position is None
            else position.side * position.quantity * (close - position.entry_price)
        )
        equity_times.append(timestamp)
        equity_values.append(cash + unrealized)
    if boundary_skips:
        warnings.warn(
            f"Skipped {boundary_skips} period-boundary truncated signal(s)",
            ParticipationBoundaryWarning,
            stacklevel=2,
        )
    return (
        pl.DataFrame(
            {"timestamp": equity_times, "equity": equity_values},
            schema={"timestamp": _TIME, "equity": pl.Float64},
        ),
        pl.DataFrame(trades, schema=_TRADE_SCHEMA),
    )
