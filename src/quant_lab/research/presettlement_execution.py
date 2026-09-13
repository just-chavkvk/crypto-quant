from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import TypedDict

import numpy as np
import polars as pl

from quant_lab.data.binance_archive import ArchiveError


@dataclass(frozen=True, slots=True)
class PressureRun:
    start: datetime
    end: datetime
    zero_cost: bool = False


@dataclass(frozen=True, slots=True)
class PressureResult:
    equity: pl.DataFrame
    trades: pl.DataFrame
    boundary_signals: int
    untradable_boundaries: int


class PressureTrade(TypedDict):
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    execution_cost: float
    net_pnl: float
    reason: str


def _cost(price: float, signed_quantity: float, rates: tuple[float, float]) -> float:
    fee, slippage = rates
    sign = 1 if signed_quantity > 0 else -1
    fill = price * (1 + sign * slippage)
    if fill <= 0:
        raise ArchiveError("nonpositive fill in pre-settlement execution")
    return abs(signed_quantity) * (abs(fill - price) + fill * fee)


def evaluate_presettlement(frame: pl.DataFrame, run: PressureRun) -> PressureResult:
    times: list[datetime] = frame["timestamp"].to_list()
    if run.start.tzinfo is None or run.end.tzinfo is None or run.start >= run.end:
        raise ArchiveError("invalid pressure evaluation window")
    if any(right - left != timedelta(hours=1) for left, right in pairwise(times)):
        raise ArchiveError("pressure calendar is not continuous hourly")
    start, end = bisect_left(times, run.start), bisect_left(times, run.end)
    if not times or times[start] != run.start or times[-1] < run.end - timedelta(hours=1):
        raise ArchiveError("incomplete pressure evaluation calendar")
    prices = np.asarray(
        frame.select("open", "high", "low", "close", "volume", "funding_rate_event").to_numpy(),
        dtype=np.float64,
    )
    if not np.isfinite(prices).all() or (prices[:, :4] <= 0).any() or (prices[:, 4] < 0).any():
        raise ArchiveError("invalid pressure execution data")
    values = np.full(end - start, 10000.0, dtype=np.float64)
    trades: list[PressureTrade] = []
    cash, cursor, boundary, unavailable = 10000.0, 0, 0, 0
    for offset in range(start + 1, end):
        timestamp = times[offset]
        if timestamp.hour not in (7, 15, 23):
            continue
        if offset + 1 >= end:
            boundary += 1
            continue
        if prices[offset, 4] <= 0 or prices[offset + 1, 4] <= 0:
            unavailable += 1
            continue
        if prices[offset, 5] != 0:
            raise ArchiveError("unexpected funding inside pre-settlement hold")
        index = offset - start
        values[cursor:index] = cash
        entry = float(prices[offset, 0])
        quantity = 0.20 * cash / entry
        stop = bool(prices[offset, 1] >= entry * 1.05)
        exit_offset = offset if stop else offset + 1
        exit_price = entry * 1.05 if stop else float(prices[exit_offset, 0])
        exit_time = timestamp + timedelta(hours=1, microseconds=-1) if stop else times[exit_offset]
        rates: list[tuple[float, float]] = []
        for fill_offset in (offset, exit_offset):
            previous = prices[fill_offset - 1]
            slip = 0.0002 + 0.02 * float((previous[1] - previous[2]) / previous[0])
            rates.append((0.0, 0.0) if run.zero_cost else (0.0005, slip))
        entry_cost = _cost(entry, -quantity, rates[0])
        total_cost = entry_cost + _cost(exit_price, quantity, rates[1])
        gross = quantity * (entry - exit_price)
        after = cash + gross - total_cost
        values[index] = (
            after if stop else cash - entry_cost + quantity * (entry - float(prices[offset, 3]))
        )
        if not stop:
            values[index + 1] = after
        cursor = exit_offset - start + 1
        cash = after
        trades.append(
            {
                "entry_time": timestamp,
                "exit_time": exit_time,
                "entry_price": entry,
                "exit_price": exit_price,
                "quantity": quantity,
                "gross_pnl": gross,
                "execution_cost": total_cost,
                "net_pnl": gross - total_cost,
                "reason": "stop" if stop else "clock",
            }
        )
    values[cursor:] = cash
    trade_schema = {
        "entry_time": pl.Datetime("us", "UTC"),
        "exit_time": pl.Datetime("us", "UTC"),
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "quantity": pl.Float64,
        "gross_pnl": pl.Float64,
        "execution_cost": pl.Float64,
        "net_pnl": pl.Float64,
        "reason": pl.String,
    }
    return PressureResult(
        pl.DataFrame({"timestamp": times[start:end], "equity": values}),
        pl.DataFrame(trades, schema=trade_schema),
        boundary,
        unavailable,
    )
