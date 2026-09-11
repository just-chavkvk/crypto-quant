from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
from polars.testing import assert_frame_equal

from quant_lab.research.participation_features import participation_signals


def _history() -> pl.DataFrame:
    length = 725
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2022, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(length)
            ],
            "open": np.full(length, 100.0),
            "close": np.full(length, 101.0),
            "count": [100] * 720 + [10000, 10000, 10000, 10000, 10000],
            "average_trade_size": [1000.0] * 720 + [10.0] * 5,
        }
    )


def test_current_burst_uses_only_prior_complete_720_hours() -> None:
    result = participation_signals(_history())
    assert result["signal"][:720].to_list() == [0] * 720
    assert result["signal"][720] == -1
    assert result["prior_count_q95"][720] == 100
    assert result["prior_size_q25"][720] == 1000


def test_future_modifications_leave_all_existing_signals_unchanged() -> None:
    frame = _history()
    first = participation_signals(frame.head(722))
    appended = frame.with_columns(
        pl.when(pl.int_range(pl.len()) >= 722).then(1).otherwise(pl.col("count")).alias("count")
    )
    assert_frame_equal(first, participation_signals(appended).head(722))


def test_move_direction_is_faded_without_a_trend_filter() -> None:
    frame = _history().with_columns(pl.lit(99.0).alias("close"))
    assert participation_signals(frame)["signal"][720] == 1
    flat = frame.with_columns(pl.col("open").alias("close"))
    assert participation_signals(flat)["signal"][720] == 0
