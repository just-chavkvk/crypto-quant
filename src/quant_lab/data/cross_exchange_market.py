from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.data.participation_data import END, START, load_participation, read_archive
from quant_lab.research.participation_study import cached_sources

PRICE_FIELDS: Final = ("open", "high", "low", "close", "volume")
MARK_FIELDS: Final = ("mark_open", "mark_high", "mark_low", "mark_close")


def require_calendar(frame: pl.DataFrame, hours: int, label: str) -> None:
    expected = pl.datetime_range(START, END, interval=f"{hours}h", closed="left", eager=True)
    times = frame["timestamp"].cast(pl.Datetime("us", "UTC"))
    if not times.equals(expected):
        raise ArchiveError(f"{label}: missing, duplicate, out-of-order or shifted calendar")


def require_ohlc(frame: pl.DataFrame, prefix: str) -> None:
    cols = [prefix + field for field in ("open", "high", "low", "close")]
    values = frame.select(cols).to_numpy()
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ArchiveError(f"{prefix}: nonfinite/nonpositive prices")
    if frame.filter(
        (pl.col(cols[1]) < pl.max_horizontal(cols[0], cols[2], cols[3]))
        | (pl.col(cols[2]) > pl.min_horizontal(cols[0], cols[1], cols[3]))
    ).height:
        raise ArchiveError(f"{prefix}: inconsistent OHLC bounds")


def load_cross_market(root: Path, binance_root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    sources = cached_sources(binance_root)
    result: list[pl.DataFrame] = []
    quality: list[dict[str, str | int | float]] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        trade = pl.read_parquet(root / f"{symbol}_trade.parquet")
        mark = pl.read_parquet(root / f"{symbol}_mark.parquet")
        funding = pl.read_parquet(root / f"{symbol}_funding.parquet")
        for kind, frame, interval in (
            ("trade", trade, 1),
            ("mark", mark, 1),
            ("funding", funding, 8),
        ):
            require_calendar(frame, interval, f"Bybit {symbol} {kind}")
            numeric = frame.select(pl.selectors.numeric()).to_numpy()
            if not np.isfinite(numeric).all():
                raise ArchiveError(f"nonfinite Bybit {kind} values")
        require_ohlc(trade, "")
        require_ohlc(mark, "mark_")
        if (trade["volume"] < 0).any():
            raise ArchiveError("negative Bybit trade volume")
        bybit = (
            trade.select("timestamp", *PRICE_FIELDS)
            .join(mark.select("timestamp", *MARK_FIELDS), on="timestamp", validate="1:1")
            .join(
                funding.select("timestamp", "funding"), on="timestamp", how="left", validate="1:1"
            )
            .with_columns(pl.col("funding").fill_null(0.0))
        )
        binance = load_participation(sources, symbol).select(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
            *PRICE_FIELDS,
            pl.col("funding_rate_event").alias("funding"),
        )
        mark_binance = pl.concat(
            [
                read_archive(s.path)
                for s in sources
                if s.symbol == symbol and s.product == "markPriceKlines"
            ],
            how="vertical_relaxed",
        ).select(
            pl.from_epoch("open_time", time_unit="ms")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("timestamp"),
            *[pl.col(f).alias(f"mark_{f}") for f in ("open", "high", "low", "close")],
        )
        binance = binance.join(mark_binance, on="timestamp", validate="1:1").sort("timestamp")
        rates = pl.concat(
            [
                read_archive(s.path)
                for s in sources
                if s.symbol == symbol and s.product == "fundingRate"
            ],
            how="vertical_relaxed",
        ).sort("calc_time")
        if (rates["funding_interval_hours"] != 8).any():
            raise ArchiveError("Binance funding interval differs from registered 8h regime")
        for venue, frame in (("binance", binance), ("bybit", bybit)):
            require_calendar(frame, 1, f"{venue} {symbol}")
            require_ohlc(frame, "")
            require_ohlc(frame, "mark_")
            quality.append(
                {
                    "symbol": symbol,
                    "venue": venue,
                    "price_hours": len(frame),
                    "funding_events": len(funding) if venue == "bybit" else len(rates),
                    "zero_volume_hours": int((frame["volume"] == 0).sum()),
                    "first": str(frame["timestamp"][0]),
                    "last": str(frame["timestamp"][-1]),
                }
            )
        a = binance.rename({c: f"binance_{c}" for c in binance.columns if c != "timestamp"})
        b = bybit.rename({c: f"bybit_{c}" for c in bybit.columns if c != "timestamp"})
        merged = a.join(b, on="timestamp", validate="1:1").sort("timestamp")
        merged.write_parquet(root / f"{symbol}_paired.parquet")
        result.append(merged)
    pl.DataFrame(quality).write_csv(root / "data_quality.csv")
    return result[0], result[1]
