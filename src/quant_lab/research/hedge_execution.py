from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Final, TypedDict

import numpy as np
import polars as pl
from numpy.typing import NDArray

_HOUR: Final = timedelta(hours=1)
_TIME: Final = pl.Datetime("us", "UTC")
_COLUMNS: Final = (
    *(
        f"{leg}_{field}"
        for leg in ("spot", "perp", "mark")
        for field in ("open", "high", "low", "close")
    ),
    "spot_volume",
    "perp_volume",
    "funding_rate_event",
)
_TRADE_SCHEMA: Final = pl.Schema(
    {
        "entry_time": _TIME,
        "exit_time": _TIME,
        **dict.fromkeys(
            (
                "quantity",
                "entry_equity",
                "spot_pnl",
                "perp_pnl",
                "funding_pnl",
                "execution_cost",
                "net_pnl",
                "min_margin_ratio",
            ),
            pl.Float64,
        ),
        "margin_breach_hours": pl.Int64,
    }
)


class HedgeExecutionError(ValueError):
    """An invalid calendar, cycle or capital contract prevents execution."""

    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class HedgeCycle:
    """A prescribed open-to-open hedge, without resizing or early liquidation."""

    entry_time: datetime
    exit_time: datetime


@dataclass(frozen=True, slots=True)
class HedgeRun:
    """An evaluation calendar [start, end), starting flat with 10,000 USDT."""

    start: datetime
    end: datetime
    zero_cost: bool = False


class _Trade(TypedDict):
    entry_time: datetime
    exit_time: datetime
    quantity: float
    entry_equity: float
    spot_pnl: float
    perp_pnl: float
    funding_pnl: float
    execution_cost: float
    net_pnl: float
    min_margin_ratio: float
    margin_breach_hours: int


def _prepare(
    frame: pl.DataFrame,
    cycles: tuple[HedgeCycle, ...],
    run: HedgeRun,
) -> tuple[list[datetime], NDArray[np.float64]]:
    boundaries = (run.start, run.end, *(t for c in cycles for t in (c.entry_time, c.exit_time)))
    if any(t.utcoffset() is None for t in boundaries):
        raise HedgeExecutionError("run and cycle boundaries must be timezone-aware")
    if any(t.minute or t.second or t.microsecond for t in (b.astimezone(UTC) for b in boundaries)):
        raise HedgeExecutionError("run and cycle boundaries must align with the hourly calendar")
    if run.start >= run.end:
        raise HedgeExecutionError("run must have start < end")
    previous_exit = run.start - _HOUR
    for cycle in cycles:
        if not run.start <= cycle.entry_time < cycle.exit_time < run.end:
            raise HedgeExecutionError("each complete cycle must lie inside [start, end)")
        if cycle.entry_time <= previous_exit:
            raise HedgeExecutionError("cycles must be ordered without overlap or same-hour reentry")
        previous_exit = cycle.exit_time
    if {"timestamp", *_COLUMNS}.difference(frame.columns):
        raise HedgeExecutionError("missing required execution columns")
    if frame.schema["timestamp"] not in tuple(pl.Datetime(u, "UTC") for u in ("ms", "us", "ns")):
        raise HedgeExecutionError("timestamp must be a UTC Datetime column")
    timestamps = frame["timestamp"]
    if timestamps.null_count():
        raise HedgeExecutionError("calendar timestamps must not be null")
    times: list[datetime] = timestamps.to_list()
    if not times or times[0] > run.start - _HOUR or times[-1] < run.end - _HOUR:
        raise HedgeExecutionError("frame must cover the full calendar and preceding context hour")
    if timestamps.ne(timestamps.dt.truncate("1h")).any() or any(
        right - left != _HOUR for left, right in pairwise(times)
    ):
        raise HedgeExecutionError("calendar must be sorted, unique and contiguous hourly")
    if any(not frame.schema[column].is_numeric() for column in _COLUMNS):
        raise HedgeExecutionError("execution columns must be numeric")
    values: NDArray[np.float64] = np.asarray(frame.select(_COLUMNS).to_numpy(), dtype=np.float64)
    if not np.isfinite(values).all():
        raise HedgeExecutionError("OHLC, volumes and funding must be finite and known")
    if (values[:, :12] <= 0).any() or (values[:, 12:14] < 0).any():
        raise HedgeExecutionError("OHLC must be positive and volumes nonnegative")
    for column in (0, 4, 8):
        ohlc = values[:, column : column + 4]
        if (ohlc[:, 1] < ohlc.max(axis=1)).any() or (ohlc[:, 2] > ohlc.min(axis=1)).any():
            raise HedgeExecutionError("invalid OHLC high/low bounds")
    for cycle in cycles:
        for boundary in (cycle.entry_time, cycle.exit_time):
            index = (boundary - times[0]) // _HOUR
            if (values[index, 12:14] <= 0).any():
                raise HedgeExecutionError("entry and exit must have positive volume on both legs")
    return times, values


def _execution_cost(bars: NDArray[np.float64], signed_quantity: float) -> float:
    """Charge adverse fill differences plus fees on fills, using only the prior bar."""
    prior, current = bars
    spot_side = 1.0 if signed_quantity > 0 else -1.0
    cost = 0.0
    for column, fee, side in ((0, 0.001, spot_side), (4, 0.0005, -spot_side)):
        slippage = 0.0002 + 0.02 * float((prior[column + 1] - prior[column + 2]) / prior[column])
        opening = float(current[column])
        fill = opening * (1.0 + side * slippage)
        if not np.isfinite(fill) or fill <= 0:
            raise HedgeExecutionError("adverse execution fill must be positive and finite")
        cost += abs(signed_quantity) * (abs(fill - opening) + fill * fee)
    return cost


def execute_hedges(
    frame: pl.DataFrame, cycles: tuple[HedgeCycle, ...], run: HedgeRun
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return hourly close equity and reference-price PnL attribution for fixed cycles.

    Wallet excludes short notional and unrealized futures PnL. Fill differences and
    fees are charged once as execution_cost. Funding accrues on [entry, exit).
    Margin ratios audit each held hour's mark high; breaches never alter the path.
    Cycles must be complete, ordered and separated (no same-hour reentry).
    """
    times, values = _prepare(frame, cycles, run)
    begin = (run.start - times[0]) // _HOUR
    count = (run.end - run.start) // _HOUR
    equity = np.empty(count, dtype=np.float64)
    ratios = np.full(count, np.nan, dtype=np.float64)
    breaches = np.zeros(count, dtype=np.bool_)
    wallet, cursor = 10000.0, 0
    trades: list[_Trade] = []
    for cycle in cycles:
        entry = (cycle.entry_time - times[0]) // _HOUR
        exit_index = (cycle.exit_time - times[0]) // _HOUR
        start, stop = entry - begin, exit_index - begin
        equity[cursor:start] = wallet
        entry_equity = wallet
        spot_entry, perp_entry = float(values[entry, 0]), float(values[entry, 4])
        quantity = 0.40 * entry_equity / spot_entry
        if not np.isfinite(quantity) or quantity <= 0:
            raise HedgeExecutionError("entry capital must fund a positive finite quantity")
        entry_cost = (
            0.0 if run.zero_cost else _execution_cost(values[entry - 1 : entry + 1], quantity)
        )
        collateral = wallet - quantity * spot_entry - entry_cost
        if not np.isfinite(collateral) or collateral < 0:
            raise HedgeExecutionError("entry capital cannot fund spot and both entry costs")
        held = values[entry:exit_index]
        payments = quantity * held[:, 8] * held[:, 14]
        accrued = payments.cumsum()
        prior_funding = np.zeros(len(payments), dtype=np.float64)
        prior_funding[1:] = accrued[:-1]
        worst_collateral = (
            collateral
            + prior_funding
            + np.minimum(payments, 0.0)
            + quantity * (perp_entry - held[:, 9])
        )
        held_ratios = worst_collateral / (quantity * held[:, 9])
        ratios[start:stop] = held_ratios
        breaches[start:stop] = held_ratios < 0.25
        equity[start:stop] = (
            collateral + accrued + quantity * held[:, 3] + quantity * (perp_entry - held[:, 11])
        )
        exit_cost = (
            0.0
            if run.zero_cost
            else _execution_cost(values[exit_index - 1 : exit_index + 1], -quantity)
        )
        spot_pnl = quantity * (float(values[exit_index, 0]) - spot_entry)
        perp_pnl = quantity * (perp_entry - float(values[exit_index, 4]))
        funding_pnl = float(accrued[-1])
        execution_cost = entry_cost + exit_cost
        net_pnl = spot_pnl + perp_pnl + funding_pnl - execution_cost
        wallet = entry_equity + net_pnl
        trades.append(
            {
                "entry_time": cycle.entry_time,
                "exit_time": cycle.exit_time,
                "quantity": quantity,
                "entry_equity": entry_equity,
                "spot_pnl": spot_pnl,
                "perp_pnl": perp_pnl,
                "funding_pnl": funding_pnl,
                "execution_cost": execution_cost,
                "net_pnl": net_pnl,
                "min_margin_ratio": float(np.min(held_ratios)),
                "margin_breach_hours": int(breaches[start:stop].sum()),
            }
        )
        cursor = stop
    equity[cursor:] = wallet
    return (
        pl.DataFrame(
            {
                "timestamp": pl.Series(times[begin : begin + count], dtype=_TIME),
                "equity": equity,
                "min_margin_ratio": pl.Series(ratios, nan_to_null=True),
                "margin_breach": breaches,
            }
        ),
        pl.DataFrame(trades, schema=_TRADE_SCHEMA),
    )
