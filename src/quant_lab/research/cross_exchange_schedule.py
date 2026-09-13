from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.research.cross_exchange_execution import CrossCycle, CrossRun


@dataclass(frozen=True, slots=True)
class CrossSchedule:
    cycles: tuple[CrossCycle, ...]
    cash_months: int
    untradable_boundaries: int
    signals: pl.DataFrame


def build_monthly_schedule(frame: pl.DataFrame, run: CrossRun) -> CrossSchedule:
    year, month = run.start.year, run.start.month
    cycles: list[CrossCycle] = []
    rows: list[dict[str, str | int | float]] = []
    cash_months = untradable = 0
    tradable = set(
        frame.filter((pl.col("binance_volume") > 0) & (pl.col("bybit_volume") > 0))[
            "timestamp"
        ].to_list()
    )
    while datetime(year, month, 1, tzinfo=UTC) < run.end:
        first = datetime(year, month, 1, tzinfo=UTC)
        entry = first + timedelta(hours=1)
        exit_time = datetime(year, month, monthrange(year, month)[1], 23, tzinfo=UTC)
        if run.start <= entry < exit_time < run.end:
            history = frame.filter(
                (pl.col("timestamp") >= first - timedelta(days=7)) & (pl.col("timestamp") < first)
            )
            if len(history) != 168:
                raise ArchiveError("incomplete seven-day prior funding context")
            rate_a = sum(
                (Decimal(str(v)) for v in history["binance_funding"].to_list()), Decimal(0)
            )
            rate_b = sum((Decimal(str(v)) for v in history["bybit_funding"].to_list()), Decimal(0))
            gap = rate_b - rate_a
            side = 1 if gap > 0 else (-1 if gap < 0 else 0)
            rows.append(
                {
                    "month": first.date().isoformat(),
                    "binance_side": side,
                    "prior_binance_sum": float(rate_a),
                    "prior_bybit_sum": float(rate_b),
                    "prior_difference": float(gap),
                }
            )
            if side == 0:
                cash_months += 1
            elif entry not in tradable or exit_time not in tradable:
                untradable += 1
            else:
                cycles.append(CrossCycle(entry, exit_time, side))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return CrossSchedule(tuple(cycles), cash_months, untradable, pl.DataFrame(rows))
