from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import polars as pl

from quant_lab.research.hedge_execution import HedgeCycle, HedgeRun


class HedgeFamily(StrEnum):
    CARRY = "monthly_funding_carry"
    DISLOCATION = "spot_perp_dislocation"


@dataclass(frozen=True, slots=True)
class HedgeSchedule:
    cycles: tuple[HedgeCycle, ...]
    boundary_signals: int = 0
    untradable_boundaries: int = 0


def monthly_cycles(run: HedgeRun) -> tuple[HedgeCycle, ...]:
    year, month = run.start.year, run.start.month
    cycles: list[HedgeCycle] = []
    while datetime(year, month, 1, tzinfo=UTC) < run.end:
        entry = datetime(year, month, 1, 1, tzinfo=UTC)
        exit_time = datetime(year, month, monthrange(year, month)[1], 23, tzinfo=UTC)
        if run.start <= entry and exit_time < run.end:
            cycles.append(HedgeCycle(entry, exit_time))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(cycles)


def dislocation_signals(frame: pl.DataFrame) -> pl.Series:
    return (
        (frame["perp_close"] / frame["spot_close"] - 1 >= 0.005)
        & frame["spot_available"]
        & (frame["perp_volume"] > 0)
    ).rename("event")


def build_schedule(frame: pl.DataFrame, family: HedgeFamily, run: HedgeRun) -> HedgeSchedule:
    boundary = 0
    match family:
        case HedgeFamily.CARRY:
            cycles = monthly_cycles(run)
        case HedgeFamily.DISLOCATION:
            events = frame.filter(dislocation_signals(frame))["timestamp"].to_list()
            selected: list[HedgeCycle] = []
            next_signal = run.start
            for timestamp in events:
                if not run.start <= timestamp < run.end or timestamp < next_signal:
                    continue
                entry = timestamp + timedelta(hours=1)
                exit_time = entry + timedelta(hours=24)
                if exit_time >= run.end:
                    boundary += 1
                    continue
                selected.append(HedgeCycle(entry, exit_time))
                next_signal = exit_time
            cycles = tuple(selected)
    valid_times = set(
        frame.filter((pl.col("spot_volume") > 0) & (pl.col("perp_volume") > 0))[
            "timestamp"
        ].to_list()
    )
    usable = tuple(c for c in cycles if c.entry_time in valid_times and c.exit_time in valid_times)
    return HedgeSchedule(usable, boundary, len(cycles) - len(usable))
