from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from math import isnan
from typing import Final

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from quant_lab.data.book_depth_quality import BookDayQuality, audit_book_day

DAY: Final = date(2023, 1, 1)
START: Final = datetime(2023, 1, 1, tzinfo=UTC)
HEADER: Final = b"timestamp,percentage,depth,notional\n"
Row = tuple[str, float, float, float]


def snapshot(seconds: float, bid_notional: float = 150.0) -> list[Row]:
    timestamp = (START + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")
    return [
        (
            timestamp,
            float(level),
            abs(level) * (bid_notional / 99 if level < 0 else 100 / 101),
            abs(level) * (bid_notional if level < 0 else 100),
        )
        for level in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
    ]


def csv_bytes(rows: Sequence[Row]) -> bytes:
    return HEADER + "".join(",".join(str(value) for value in row) + "\n" for row in rows).encode()


def test_complete_hour_has_median_pressure_and_exact_utc_grid() -> None:
    rows = [row for second in range(0, 3600, 30) for row in snapshot(second)]
    rows.extend(row for second in range(3600, 7200, 30) for row in snapshot(second, 50))
    rows.extend(row for second in range(7200, 7800, 30) for row in snapshot(second))

    frame, quality = audit_book_day(csv_bytes(rows[::-1]), DAY)

    assert frame.columns == ["timestamp", "imbalance", "valid_hour", "snapshots"]
    assert frame.schema == {
        "timestamp": pl.Datetime("us", "UTC"),
        "imbalance": pl.Float64,
        "valid_hour": pl.Boolean,
        "snapshots": pl.Int64,
    }
    assert frame["timestamp"].to_list() == [START + timedelta(hours=h) for h in range(24)]
    assert frame["imbalance"].head(2).to_list() == pytest.approx([0.2, -1 / 3])
    assert frame["imbalance"].null_count() == 22
    assert frame["snapshots"].head(4).to_list() == [120, 120, 20, 0]
    assert quality == BookDayQuality(DAY.isoformat(), 2600, 260, 0, 2, 30.0, 30.0)


def test_imbalance_uses_median_of_snapshot_ratios() -> None:
    rows = [
        row
        for second in range(0, 3600, 30)
        for row in snapshot(second, 150 if second < 3000 else 10_000)
    ]

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert quality.valid_hours == 1
    assert frame["imbalance"][0] == pytest.approx(0.2)


@pytest.mark.parametrize("missing_level", [1, -1, 5])
def test_missing_signed_level_invalidates_snapshot(missing_level: int) -> None:
    rows = [row for row in snapshot(0) if row[1] != missing_level]

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert (quality.rows, quality.snapshots, quality.invalid_snapshots) == (9, 1, 1)
    assert frame["snapshots"].sum() == 0


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_level_invalidates_whole_snapshot(conflicting: bool) -> None:
    rows = snapshot(0)
    duplicate = rows[4]
    rows.append((*duplicate[:3], duplicate[3] + int(conflicting)))

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert (quality.rows, quality.snapshots, quality.invalid_snapshots) == (11, 1, 1)
    assert frame["snapshots"].sum() == 0


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        pytest.param(4, 1, -1.5, id="fractional-original-level"),
        (4, 1, 0.0),
        pytest.param(0, 2, 1.0, id="decreasing-bid-depth"),
        pytest.param(6, 3, 50.0, id="decreasing-ask-notional"),
        (4, 2, 0.0),
        (4, 3, -1.0),
        (4, 2, float("inf")),
        (4, 3, float("nan")),
        pytest.param(4, 2, 150 / 101, id="locked-vwap"),
        pytest.param(4, 2, 150 / 102, id="crossed-vwap"),
    ],
)
def test_invalid_values_or_cumulative_bands_invalidate_snapshot(
    index: int, field: int, value: float
) -> None:
    rows = snapshot(0)
    timestamp, level, depth, notional = rows[index]
    values = [level, depth, notional]
    values[field - 1] = value
    rows[index] = (timestamp, values[0], values[1], values[2])

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert quality.invalid_snapshots == 1
    assert frame["snapshots"].sum() == 0
    assert frame["imbalance"].null_count() == 24


@pytest.mark.parametrize(
    ("seconds", "valid"),
    [
        pytest.param([*range(0, 3521, 40), 3570], True, id="exactly-90"),
        pytest.param([*range(0, 3481, 40), 3570], False, id="only-89"),
        pytest.param(list(range(120, 3481, 30)), True, id="inclusive-coverage"),
        (list(range(121, 3600, 30)), False),
        (list(range(0, 3480, 30)), False),
        ([s for s in range(0, 3600, 30) if not 1500 <= s <= 1560], True),
        ([s for s in range(0, 3600, 30) if not 1500 <= s <= 1590], False),
    ],
)
def test_hour_gates_are_fixed(seconds: list[int], valid: bool) -> None:
    rows = [row for second in seconds for row in snapshot(second)]

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert frame["valid_hour"][0] is valid
    assert (frame["imbalance"][0] is None) is not valid
    assert frame["snapshots"][0] == len(seconds)
    assert quality.valid_hours == int(valid)


def test_invalid_snapshots_cannot_satisfy_hour_count() -> None:
    seconds = [*range(0, 3521, 40), 3570]
    rows = [row for second in seconds for row in snapshot(second)]
    rows.append(rows[104])

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert quality.invalid_snapshots == 1
    assert frame["snapshots"][0] == 89
    assert frame["valid_hour"][0] is False


def test_future_snapshot_cannot_change_prior_hour() -> None:
    rows = [row for second in range(0, 3480, 30) for row in snapshot(second)]
    before, _ = audit_book_day(csv_bytes(rows), DAY)

    after, _ = audit_book_day(csv_bytes([*rows, *snapshot(3600, 10_000)]), DAY)

    assert_frame_equal(before.head(1), after.head(1))
    assert after["valid_hour"][0] is False
    assert after["snapshots"][1] == 1


def test_out_of_day_snapshots_are_counted_and_excluded() -> None:
    rows = [*snapshot(-0.001), *snapshot(0), *snapshot(86_400)]

    frame, quality = audit_book_day(csv_bytes(rows), DAY)

    assert (quality.rows, quality.snapshots, quality.invalid_snapshots) == (30, 3, 2)
    assert frame["snapshots"].sum() == 1
    assert isnan(quality.median_cadence_seconds)
    assert isnan(quality.max_gap_seconds)


def test_header_only_day_is_all_unavailable() -> None:
    frame, quality = audit_book_day(HEADER, DAY)

    assert (quality.rows, quality.snapshots, quality.valid_hours) == (0, 0, 0)
    assert frame.height == 24
    assert frame["imbalance"].null_count() == 24
    assert frame["snapshots"].sum() == 0


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"timestamp,percentage,depth\n2023-01-01 00:00:00,1,2\n",
        b"timestamp,percentage,depth,depth\n2023-01-01 00:00:00,1,2,3\n",
        HEADER + b"not-a-timestamp,1,2,3\n",
        HEADER + b",1,2,3\n",
        HEADER + b"2023-01-01 00:00:00,ask,2,3\n",
        HEADER + b"2023-01-01 00:00:00,1,2,3,extra\n",
    ],
)
def test_invalid_csv_schema_fails_explicitly(payload: bytes) -> None:
    with pytest.raises(ValueError):
        _ = audit_book_day(payload, DAY)
