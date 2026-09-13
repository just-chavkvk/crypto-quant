from __future__ import annotations

import numpy as np
import polars as pl

from quant_lab.data.binance_archive import ArchiveError


def mask_invalid_activity(candles: pl.DataFrame) -> pl.DataFrame:
    sizes = candles.select("volume", "quote_volume", "count").to_numpy()
    counts = candles["count"].to_numpy()
    valid = (np.isfinite(sizes) & (sizes > 0)).all(axis=1) & np.equal(counts, np.floor(counts))
    flagged = candles.with_columns(pl.Series("valid_input", valid))
    yearly = flagged.group_by(pl.col("timestamp").dt.year()).agg(pl.col("valid_input").mean())
    if (yearly["valid_input"] < 0.99).any():
        raise ArchiveError("activity quality below 99% in an input year")
    longest = run = 0
    for usable in valid:
        run = 0 if usable else run + 1
        longest = max(longest, run)
    if longest > 24:
        raise ArchiveError("activity data gap exceeds 24 hours")
    return flagged.with_columns(
        pl.when(pl.col("valid_input")).then(pl.col("count")).otherwise(None).alias("count"),
        pl.when(pl.col("valid_input"))
        .then(pl.col("quote_volume") / pl.col("count"))
        .otherwise(None)
        .alias("average_trade_size"),
    )
