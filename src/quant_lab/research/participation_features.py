from __future__ import annotations

from typing import Final

import polars as pl

HISTORY_HOURS: Final = 720
COUNT_QUANTILE: Final = 0.95
SIZE_QUANTILE: Final = 0.25


def participation_signals(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(
        pl.col("count")
        .shift(1)
        .rolling_quantile(
            COUNT_QUANTILE,
            interpolation="linear",
            window_size=HISTORY_HOURS,
            min_samples=HISTORY_HOURS,
        )
        .alias("prior_count_q95"),
        pl.col("average_trade_size")
        .shift(1)
        .rolling_quantile(
            SIZE_QUANTILE,
            interpolation="linear",
            window_size=HISTORY_HOURS,
            min_samples=HISTORY_HOURS,
        )
        .alias("prior_size_q25"),
    ).with_columns(
        pl.when(
            (pl.col("count") >= pl.col("prior_count_q95"))
            & (pl.col("average_trade_size") <= pl.col("prior_size_q25"))
        )
        .then(-(pl.col("close") - pl.col("open")).sign())
        .otherwise(0)
        .cast(pl.Int8)
        .alias("signal")
    )
