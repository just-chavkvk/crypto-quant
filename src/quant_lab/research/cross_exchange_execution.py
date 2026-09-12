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
_VENUES: Final = ("binance", "bybit")
_FIELDS: Final = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "mark_open",
    "mark_high",
    "mark_low",
    "mark_close",
    "funding",
)
_COLUMNS: Final = tuple(f"{venue}_{field}" for venue in _VENUES for field in _FIELDS)
_TRADE_SCHEMA: Final = pl.Schema(
    {
        "entry_time": _TIME,
        "exit_time": _TIME,
        "binance_side": pl.Int64,
        **dict.fromkeys(
            (
                "quantity",
                "binance_price_pnl",
                "bybit_price_pnl",
                "binance_funding_pnl",
                "bybit_funding_pnl",
                "execution_cost",
                "net_pnl",
                "binance_wallet",
                "bybit_wallet",
                "min_margin_ratio",
            ),
            pl.Float64,
        ),
        "margin_breach_hours": pl.Int64,
    }
)


class CrossExecutionError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class CrossCycle:
    entry_time: datetime
    exit_time: datetime
    binance_side: int


@dataclass(frozen=True, slots=True)
class CrossRun:
    """A flat-start evaluation calendar [start, end)."""

    start: datetime
    end: datetime
    zero_cost: bool = False


class _Trade(TypedDict):
    entry_time: datetime
    exit_time: datetime
    binance_side: int
    quantity: float
    binance_price_pnl: float
    bybit_price_pnl: float
    binance_funding_pnl: float
    bybit_funding_pnl: float
    execution_cost: float
    net_pnl: float
    binance_wallet: float
    bybit_wallet: float
    min_margin_ratio: float
    margin_breach_hours: int


def _prepare(
    frame: pl.DataFrame, cycles: tuple[CrossCycle, ...], run: CrossRun
) -> tuple[list[datetime], NDArray[np.float64]]:
    boundaries = (run.start, run.end, *(t for c in cycles for t in (c.entry_time, c.exit_time)))
    if any(t.utcoffset() is None for t in boundaries):
        raise CrossExecutionError("run and cycle boundaries must be timezone-aware")
    if any(t.minute or t.second or t.microsecond for t in (b.astimezone(UTC) for b in boundaries)):
        raise CrossExecutionError("boundaries must align with the hourly calendar")
    if run.start >= run.end:
        raise CrossExecutionError("run must have start < end")
    previous_exit = run.start
    for cycle in cycles:
        if type(cycle.binance_side) is not int or cycle.binance_side not in (-1, 1):
            raise CrossExecutionError("binance_side must be integer 1 or -1")
        if not run.start <= cycle.entry_time < cycle.exit_time < run.end:
            raise CrossExecutionError("each complete cycle must lie inside [start, end)")
        if cycle.entry_time < previous_exit:
            raise CrossExecutionError("cycles must be ordered without overlap")
        previous_exit = cycle.exit_time
    if {"timestamp", *_COLUMNS}.difference(frame.columns):
        raise CrossExecutionError("missing required execution columns")
    if frame.schema["timestamp"] not in tuple(pl.Datetime(u, "UTC") for u in ("ms", "us", "ns")):
        raise CrossExecutionError("timestamp must be a UTC Datetime column")
    timestamps = frame["timestamp"]
    if timestamps.null_count():
        raise CrossExecutionError("calendar timestamps must not be null")
    times: list[datetime] = timestamps.to_list()
    if not times or times[0] > run.start - _HOUR or times[-1] < run.end - _HOUR:
        raise CrossExecutionError("frame must cover the full calendar and preceding context hour")
    if timestamps.ne(timestamps.dt.truncate("1h")).any() or any(
        right - left != _HOUR for left, right in pairwise(times)
    ):
        raise CrossExecutionError("calendar must be sorted, unique and contiguous hourly")
    if any(not frame.schema[column].is_numeric() for column in _COLUMNS):
        raise CrossExecutionError("execution columns must be numeric")
    values: NDArray[np.float64] = np.asarray(frame.select(_COLUMNS).to_numpy(), dtype=np.float64)
    values = values.reshape(len(times), 2, len(_FIELDS))
    if not np.isfinite(values).all():
        raise CrossExecutionError("OHLC, volumes and funding must be finite and known")
    if (values[:, :, 4] < 0).any():
        raise CrossExecutionError("volumes must be nonnegative")
    for column in (0, 5):
        ohlc = values[:, :, column : column + 4]
        if (ohlc <= 0).any():
            raise CrossExecutionError("OHLC must be positive")
        if (ohlc[:, :, 1] < ohlc.max(axis=2)).any() or (ohlc[:, :, 2] > ohlc.min(axis=2)).any():
            raise CrossExecutionError("invalid OHLC high/low bounds")
    for cycle in cycles:
        for boundary in (cycle.entry_time, cycle.exit_time):
            if (values[(boundary - times[0]) // _HOUR, :, 4] <= 0).any():
                raise CrossExecutionError("entry and exit require positive volume on both venues")
    return times, values


def _fill_costs(
    bars: NDArray[np.float64], signed_quantity: NDArray[np.float64]
) -> NDArray[np.float64]:
    prior, current = bars
    slippage = 0.0002 + 0.02 * (prior[:, 1] - prior[:, 2]) / prior[:, 0]
    fills = current[:, 0] * (1.0 + np.sign(signed_quantity) * slippage)
    if not np.isfinite(fills).all() or (fills <= 0).any():
        raise CrossExecutionError("adverse execution fills must be positive and finite")
    return np.abs(signed_quantity) * (
        np.abs(fills - current[:, 0]) + fills * np.array([0.0005, 0.00055])
    )


def execute_cross_exchange(
    frame: pl.DataFrame, cycles: tuple[CrossCycle, ...], run: CrossRun
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return hourly close NAV and completed trades; cash-hour margin ratios are null.

    Both wallets start at 5,000. Reference-price PnL excludes fill costs, charged once.
    Funding accrues on [entry, exit); each venue's adverse extreme precedes positive
    current funding and follows negative funding. Breaches flag the nominal path only.
    Consecutive cycles sharing an open execute the exit before the next entry.
    """
    times, values = _prepare(frame, cycles, run)
    begin = (run.start - times[0]) // _HOUR
    count = (run.end - run.start) // _HOUR
    equity = np.empty(count, dtype=np.float64)
    ratios = np.full((count, 2), np.nan, dtype=np.float64)
    breaches = np.zeros(count, dtype=np.bool_)
    wallets = np.full(2, 5000.0, dtype=np.float64)
    cursor = 0
    trades: list[_Trade] = []
    for cycle in cycles:
        entry = (cycle.entry_time - times[0]) // _HOUR
        exit_index = (cycle.exit_time - times[0]) // _HOUR
        start, stop = entry - begin, exit_index - begin
        equity[cursor:start] = wallets.sum()
        entry_prices = values[entry, :, 0]
        quantity = float(0.40 * wallets.min() / entry_prices.max())
        if not np.isfinite(quantity) or quantity <= 0:
            raise CrossExecutionError("entry wallets must fund a positive finite quantity")
        signed_quantity = quantity * np.array([cycle.binance_side, -cycle.binance_side])
        entry_cost = (
            np.zeros(2)
            if run.zero_cost
            else _fill_costs(values[entry - 1 : entry + 1], signed_quantity)
        )
        collateral = wallets - entry_cost
        held = values[entry:exit_index]
        payments = -signed_quantity * held[:, :, 5] * held[:, :, 9]
        accrued = payments.cumsum(axis=0)
        prior_funding = np.zeros_like(payments)
        prior_funding[1:] = accrued[:-1]
        extremes = held[:, :, 6].copy()
        extremes[:, signed_quantity > 0] = held[:, signed_quantity > 0, 7]
        worst_equity = (
            collateral
            + prior_funding
            + np.minimum(payments, 0.0)
            + signed_quantity * (extremes - entry_prices)
        )
        held_ratios = worst_equity / (quantity * extremes)
        ratios[start:stop] = held_ratios
        breaches[start:stop] = (held_ratios < 0.25).any(axis=1)
        equity[start:stop] = (
            collateral + accrued + signed_quantity * (held[:, :, 8] - entry_prices)
        ).sum(axis=1)
        exit_cost = (
            np.zeros(2)
            if run.zero_cost
            else _fill_costs(values[exit_index - 1 : exit_index + 1], -signed_quantity)
        )
        price_pnl = signed_quantity * (values[exit_index, :, 0] - entry_prices)
        funding_pnl = accrued[-1]
        execution_cost = entry_cost + exit_cost
        net_pnl = price_pnl + funding_pnl - execution_cost
        wallets = wallets + net_pnl
        trades.append(
            {
                "entry_time": cycle.entry_time,
                "exit_time": cycle.exit_time,
                "binance_side": cycle.binance_side,
                "quantity": quantity,
                "binance_price_pnl": float(price_pnl[0]),
                "bybit_price_pnl": float(price_pnl[1]),
                "binance_funding_pnl": float(funding_pnl[0]),
                "bybit_funding_pnl": float(funding_pnl[1]),
                "execution_cost": float(execution_cost.sum()),
                "net_pnl": float(net_pnl.sum()),
                "binance_wallet": float(wallets[0]),
                "bybit_wallet": float(wallets[1]),
                "min_margin_ratio": float(held_ratios.min()),
                "margin_breach_hours": int(breaches[start:stop].sum()),
            }
        )
        cursor = stop
    equity[cursor:] = wallets.sum()
    return (
        pl.DataFrame(
            {
                "timestamp": pl.Series(times[begin : begin + count], dtype=_TIME),
                "equity": equity,
                "binance_margin_ratio": pl.Series(ratios[:, 0], nan_to_null=True),
                "bybit_margin_ratio": pl.Series(ratios[:, 1], nan_to_null=True),
                "margin_breach": breaches,
            }
        ),
        pl.DataFrame(trades, schema=_TRADE_SCHEMA),
    )
