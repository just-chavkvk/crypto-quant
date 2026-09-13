from datetime import UTC, datetime

import polars as pl
import pytest

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.data.cross_exchange_market import require_calendar, require_ohlc
from quant_lab.data.participation_data import END, START


def test_funding_gap_cannot_be_treated_as_zero() -> None:
    timestamps = pl.datetime_range(START, END, interval="8h", closed="left", eager=True)
    frame = pl.DataFrame({"timestamp": timestamps}).filter(
        pl.col("timestamp") != datetime(2023, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(ArchiveError, match="calendar"):
        require_calendar(frame, 8, "funding")


def test_duplicate_hour_fails_full_calendar() -> None:
    timestamps = pl.datetime_range(START, END, interval="1h", closed="left", eager=True)
    frame = pl.DataFrame({"timestamp": timestamps})
    frame = pl.concat([frame, frame.head(1)]).sort("timestamp")
    with pytest.raises(ArchiveError, match="calendar"):
        require_calendar(frame, 1, "prices")


def test_inverted_price_range_is_rejected() -> None:
    frame = pl.DataFrame({"open": [100.0], "high": [99.0], "low": [98.0], "close": [100.0]})
    with pytest.raises(ArchiveError, match="bounds"):
        require_ohlc(frame, "")
