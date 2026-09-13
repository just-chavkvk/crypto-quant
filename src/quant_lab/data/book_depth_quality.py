from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final

import numpy as np
import polars as pl

LEVELS: Final = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
COLUMNS: Final = ("timestamp", "percentage", "depth", "notional")


class BookDepthSchemaError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BookDayQuality:
    day: str
    rows: int
    snapshots: int
    invalid_snapshots: int
    valid_hours: int
    median_cadence_seconds: float
    max_gap_seconds: float


def _parse_csv(payload: bytes) -> pl.DataFrame:
    try:
        frame = pl.read_csv(payload, infer_schema=False)
        if set(frame.columns) != set(COLUMNS):
            raise BookDepthSchemaError(f"expected CSV columns {COLUMNS}; got {frame.columns}")
        if frame.is_empty():
            return pl.DataFrame(
                schema={
                    "timestamp": pl.Datetime("us", "UTC"),
                    "percentage": pl.Float64,
                    "depth": pl.Float64,
                    "notional": pl.Float64,
                }
            )
        frame = frame.with_columns(
            pl.col("timestamp").str.to_datetime(time_unit="us", time_zone="UTC", strict=True),
            pl.col("percentage", "depth", "notional").cast(pl.Float64, strict=True),
        )
    except pl.exceptions.PolarsError as exc:
        raise BookDepthSchemaError(f"invalid bookDepth CSV: {exc}") from exc
    if frame["timestamp"].null_count():
        raise BookDepthSchemaError("bookDepth CSV has a missing timestamp")
    return frame


def _snapshots(frame: pl.DataFrame, start: datetime) -> pl.DataFrame:
    level = pl.col("percentage")
    checks = [
        pl.len() == 10,
        level.n_unique() == 10,
        level.is_in(LEVELS).fill_null(False).all(),
    ]
    for name in ("depth", "notional"):
        value = pl.col(name)
        checks.extend(
            [
                (value.is_finite() & (value > 0)).fill_null(False).all(),
                (value.filter(level < 0).diff().drop_nulls() <= 0).all(),
                (value.filter(level > 0).diff().drop_nulls() >= 0).all(),
            ]
        )
    snapshots = (
        frame.sort("timestamp", "percentage")
        .group_by("timestamp")
        .agg(
            pl.all_horizontal(checks).alias("complete"),
            pl.col("notional").filter(level == -1).first().alias("bid"),
            pl.col("notional").filter(level == 1).first().alias("ask"),
            (pl.col("notional") / pl.col("depth")).filter(level == -1).first().alias("bid_vwap"),
            (pl.col("notional") / pl.col("depth")).filter(level == 1).first().alias("ask_vwap"),
        )
    )
    return snapshots.with_columns(
        (
            pl.col("complete")
            & pl.col("timestamp").is_between(start, start + timedelta(days=1), closed="left")
            & pl.col("bid_vwap").is_finite()
            & pl.col("ask_vwap").is_finite()
            & (pl.col("bid_vwap") < pl.col("ask_vwap"))
        )
        .fill_null(False)
        .alias("valid")
    )


def audit_book_day(payload: bytes, day: date) -> tuple[pl.DataFrame, BookDayQuality]:
    """Audit uncompressed CSV into 24 UTC hours under the preregistered gates.

    Hourly counts include only valid snapshots. Daily counts include all timestamp
    groups, including out-of-day groups as invalid. Cadence/gaps use consecutive
    valid in-day snapshots across hours; fewer than two yield NaN. Unparseable CSV
    raises BookDepthSchemaError. Invalid snapshots are never deduplicated or filled.
    """
    start = datetime.combine(day, time.min, tzinfo=UTC)
    frame = _parse_csv(payload)
    snapshots = _snapshots(frame, start)
    valid = snapshots.filter(pl.col("valid")).sort("timestamp")
    seconds = (
        np.asarray(
            valid.select((pl.col("timestamp") - start).dt.total_microseconds())
            .to_series()
            .to_numpy(),
            dtype=np.float64,
        )
        / 1_000_000
    )
    bid = np.asarray(valid["bid"].to_numpy(), dtype=np.float64)
    ask = np.asarray(valid["ask"].to_numpy(), dtype=np.float64)
    scale = np.maximum(bid, ask)
    bid, ask = bid / scale, ask / scale
    pressure = (bid - ask) / (bid + ask)
    hourly_pressure: list[float | None] = []
    hourly_valid: list[bool] = []
    hourly_count: list[int] = []
    for hour in range(24):
        mask = (seconds >= hour * 3600) & (seconds < (hour + 1) * 3600)
        observed = seconds[mask] - hour * 3600
        count = len(observed)
        valid_hour = bool(
            count >= 90
            and observed[0] <= 120
            and observed[-1] >= 3480
            and np.max(observed[1:] - observed[:-1]) <= 120
        )
        hourly_count.append(count)
        hourly_valid.append(valid_hour)
        hourly_pressure.append(float(np.median(pressure[mask])) if valid_hour else None)
    hourly = pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=hour) for hour in range(24)],
            "imbalance": pl.Series(hourly_pressure, dtype=pl.Float64),
            "valid_hour": hourly_valid,
            "snapshots": pl.Series(hourly_count, dtype=pl.Int64),
        }
    )
    gaps = seconds[1:] - seconds[:-1]
    quality = BookDayQuality(
        day=day.isoformat(),
        rows=frame.height,
        snapshots=snapshots.height,
        invalid_snapshots=snapshots.height - valid.height,
        valid_hours=sum(hourly_valid),
        median_cadence_seconds=float(np.median(gaps)) if gaps.size else float("nan"),
        max_gap_seconds=float(np.max(gaps)) if gaps.size else float("nan"),
    )
    return hourly, quality
