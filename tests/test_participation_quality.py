from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.data.participation_quality import mask_invalid_activity
from quant_lab.research.participation_features import participation_signals


def _candles() -> pl.DataFrame:
    size = 3000
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(size)
            ],
            "open": np.full(size, 100.0),
            "close": np.full(size, 101.0),
            "volume": np.ones(size),
            "quote_volume": np.full(size, 100.0),
            "count": np.ones(size),
        }
    )


def test_one_zero_activity_hour_invalidates_the_entire_following_warmup() -> None:
    candles = _candles().with_columns(
        pl.when(pl.int_range(pl.len()) == 1000).then(0).otherwise(pl.col("count")).alias("count")
    )
    signals = participation_signals(mask_invalid_activity(candles))
    assert signals["signal"][999] == -1
    assert signals["signal"][1000:1721].to_list() == [0] * 721
    assert signals["signal"][1721] == -1


def test_more_than_24_consecutive_invalid_hours_are_rejected() -> None:
    candles = _candles().with_columns(
        pl.when(pl.int_range(pl.len()).is_between(1000, 1024))
        .then(0)
        .otherwise(pl.col("count"))
        .alias("count")
    )
    with pytest.raises(ArchiveError, match="24 hours"):
        _ = mask_invalid_activity(candles)
