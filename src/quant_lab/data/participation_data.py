from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Final
from zipfile import ZipFile

import numpy as np
import polars as pl

from quant_lab.data.binance_archive import (
    ArchiveEntry,
    ArchiveError,
    archive_client,
    list_archives,
    verified_download,
)
from quant_lab.data.participation_quality import mask_invalid_activity

COLUMNS: Final = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)
START: Final = datetime(2021, 12, 1, tzinfo=UTC)
END: Final = datetime(2026, 9, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class SourceFile:
    symbol: str
    product: str
    entry: ArchiveEntry
    path: Path
    sha256: str


def download_participation(root: Path) -> tuple[SourceFile, ...]:
    jobs: list[tuple[str, str, ArchiveEntry, Path]] = []
    with archive_client() as client:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            for product in ("klines", "markPriceKlines", "fundingRate"):
                suffix = "" if product == "fundingRate" else "/1h"
                prefix = f"data/futures/um/monthly/{product}/{symbol}{suffix}/"
                entries = list_archives(client, prefix)
                folder = root / product / symbol
                folder.mkdir(parents=True, exist_ok=True)
                selected = [e for e in entries if "2021-12" <= e.key[-11:-4] <= "2026-08"]
                if len(selected) != 57:
                    raise ArchiveError(f"{symbol}/{product}: expected 57 monthly files")
                jobs.extend((symbol, product, entry, folder) for entry in selected)

        def fetch(job: tuple[str, str, ArchiveEntry, Path]) -> SourceFile:
            symbol, product, entry, folder = job
            path = verified_download(client, entry, folder)
            return SourceFile(
                symbol, product, entry, path, hashlib.sha256(path.read_bytes()).hexdigest()
            )

        with ThreadPoolExecutor(max_workers=12) as pool:
            sources = tuple(pool.map(fetch, jobs))
    sources = supplement_mark_days(sources, root)
    rows = [
        {
            "symbol": s.symbol,
            "product": s.product,
            **asdict(s.entry),
            "path": str(s.path),
            "sha256": s.sha256,
        }
        for s in sources
    ]
    pl.DataFrame(rows).write_csv(root / "source_manifest.csv")
    return sources


def read_archive(path: Path) -> pl.DataFrame:
    with ZipFile(path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise ArchiveError(f"expected one CSV member in {path}")
        payload = archive.read(members[0])
    header = payload.startswith((b"open_time", b"calc_time"))
    columns = None if header else COLUMNS
    return pl.read_csv(
        BytesIO(payload), has_header=header, new_columns=columns, infer_schema_length=None
    )


def _klines(sources: tuple[SourceFile, ...], product: str) -> pl.DataFrame:
    frame = pl.concat(
        [read_archive(s.path) for s in sources if s.product == product], how="vertical_relaxed"
    ).sort("open_time")
    return frame.with_columns(
        pl.from_epoch("open_time", time_unit="ms").dt.replace_time_zone("UTC").alias("timestamp")
    )


def _require_calendar(frame: pl.DataFrame, label: str) -> None:
    expected = pl.datetime_range(START, END, interval="1h", closed="left", eager=True)
    times = frame["timestamp"].cast(pl.Datetime("us", "UTC"))
    if not times.equals(expected):
        raise ArchiveError(f"{label}: missing, duplicate, out-of-order or unexpected calendar hour")
    if (frame["close_time"] - frame["open_time"] != 3_599_999).any():
        raise ArchiveError(f"{label}: incomplete hourly candle")


def load_participation(sources: tuple[SourceFile, ...], symbol: str) -> pl.DataFrame:
    selected = tuple(s for s in sources if s.symbol == symbol)
    candles = _klines(selected, "klines")
    mark = _klines(selected, "markPriceKlines")
    _require_calendar(candles, f"{symbol} klines")
    _require_calendar(mark, f"{symbol} mark price")
    for frame, label in ((candles, "klines"), (mark, "mark")):
        values = frame.select("open", "high", "low", "close").to_numpy()
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ArchiveError(f"{symbol} {label}: nonpositive or nonfinite OHLC")
        invalid_bounds = frame.filter(
            (pl.col("high") < pl.max_horizontal("open", "close", "low"))
            | (pl.col("low") > pl.min_horizontal("open", "close", "high"))
        )
        if invalid_bounds.height:
            raise ArchiveError(f"{symbol} {label}: invalid high/low bounds")
    candles = mask_invalid_activity(candles)

    funding = pl.concat(
        [read_archive(s.path) for s in selected if s.product == "fundingRate"],
        how="vertical_relaxed",
    ).sort("calc_time")
    funding = funding.with_columns(
        (pl.col("calc_time") // 3_600_000 * 3_600_000).alias("scheduled_ms")
    )
    offsets = funding["calc_time"] - funding["scheduled_ms"]
    if (offsets < 0).any() or (offsets > 1000).any():
        raise ArchiveError(f"{symbol}: funding timestamp more than 1s from scheduled hour")
    intervals = funding["funding_interval_hours"].to_numpy()
    times = funding["scheduled_ms"].to_numpy()
    if not np.isfinite(intervals).all() or (intervals <= 0).any():
        raise ArchiveError(f"{symbol}: invalid funding interval")
    if not np.equal((times[1:] - times[:-1]), intervals[1:] * 3_600_000).all():
        raise ArchiveError(f"{symbol}: incomplete or duplicate funding settlement sequence")
    start_ms, end_ms = int(START.timestamp() * 1000), int(END.timestamp() * 1000)
    if times[0] != start_ms or times[-1] + intervals[-1] * 3_600_000 != end_ms:
        raise ArchiveError(f"{symbol}: funding coverage does not span the entire study")
    if not np.isfinite(funding["last_funding_rate"].to_numpy()).all():
        raise ArchiveError(f"{symbol}: nonfinite funding rate")
    funding = funding.select(
        pl.from_epoch("scheduled_ms", time_unit="ms")
        .dt.replace_time_zone("UTC")
        .alias("timestamp"),
        pl.col("last_funding_rate").alias("funding_rate_event"),
    )
    return (
        candles.join(
            mark.select("timestamp", pl.col("open").alias("mark_open")),
            on="timestamp",
            how="left",
            validate="1:1",
        )
        .join(funding, on="timestamp", how="left", validate="1:1")
        .with_columns(
            pl.col("funding_rate_event").fill_null(0.0),
        )
    )


def supplement_mark_days(sources: tuple[SourceFile, ...], root: Path) -> tuple[SourceFile, ...]:
    repaired = list(sources)
    expected = pl.DataFrame(
        {"timestamp": pl.datetime_range(START, END, interval="1h", closed="left", eager=True)}
    )
    with archive_client() as client:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            mark = _klines(tuple(s for s in sources if s.symbol == symbol), "markPriceKlines")
            observed = mark.select(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))
            missing = expected.join(observed, on="timestamp", how="anti")
            days = missing.group_by(pl.col("timestamp").dt.date().alias("day")).len().sort("day")
            for day, hours in days.iter_rows():
                if hours != 24:
                    raise ArchiveError(f"{symbol}: partial-day mark gap needs an explicit contract")
                name = f"{symbol}-1h-{day.isoformat()}.zip"
                prefix = f"data/futures/um/daily/markPriceKlines/{symbol}/1h/{name}"
                entries = list_archives(client, prefix)
                if len(entries) != 1 or entries[0].key != prefix:
                    raise ArchiveError(f"missing official daily repair: {prefix}")
                folder = root / "markPriceKlines_daily" / symbol
                folder.mkdir(parents=True, exist_ok=True)
                path = verified_download(client, entries[0], folder)
                repaired.append(
                    SourceFile(
                        symbol,
                        "markPriceKlines",
                        entries[0],
                        path,
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
    return tuple(repaired)
