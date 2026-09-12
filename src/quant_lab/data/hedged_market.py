from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from quant_lab.data.binance_archive import (
    ArchiveEntry,
    ArchiveError,
    archive_client,
    list_archives,
    verified_download,
)
from quant_lab.data.participation_data import (
    END,
    START,
    SourceFile,
    load_participation,
    read_archive,
)
from quant_lab.research.participation_study import cached_sources


def download_spot(root: Path) -> tuple[SourceFile, ...]:
    jobs: list[tuple[str, ArchiveEntry, Path]] = []
    with archive_client() as client:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            entries = list_archives(client, f"data/spot/monthly/klines/{symbol}/1h/")
            selected = [entry for entry in entries if "2021-12" <= entry.key[-11:-4] <= "2026-08"]
            if len(selected) != 57:
                raise ArchiveError(f"{symbol}: incomplete spot monthly inventory")
            folder = root / "spot" / symbol
            folder.mkdir(parents=True, exist_ok=True)
            jobs.extend((symbol, entry, folder) for entry in selected)

        def fetch(job: tuple[str, ArchiveEntry, Path]) -> SourceFile:
            symbol, entry, folder = job
            path = verified_download(client, entry, folder)
            return SourceFile(
                symbol, "spot", entry, path, hashlib.sha256(path.read_bytes()).hexdigest()
            )

        with ThreadPoolExecutor(max_workers=12) as pool:
            sources = tuple(pool.map(fetch, jobs))
    pl.DataFrame(
        [
            {
                "symbol": s.symbol,
                "product": s.product,
                **asdict(s.entry),
                "path": str(s.path),
                "sha256": s.sha256,
            }
            for s in sources
        ]
    ).write_csv(root / "source_manifest.csv")
    return sources


def normalized_spot(source: SourceFile) -> pl.DataFrame:
    frame = read_archive(source.path)
    microseconds = source.entry.key[-11:-4] >= "2025-01"
    unit = "us" if microseconds else "ms"
    duration = 3_600_000_000 if microseconds else 3_600_000
    frame = frame.with_columns(
        pl.from_epoch("open_time", time_unit=unit)
        .dt.replace_time_zone("UTC")
        .cast(pl.Datetime("us", "UTC"))
        .alias("timestamp")
    )
    if (frame["timestamp"].dt.strftime("%Y-%m") != source.entry.key[-11:-4]).any():
        raise ArchiveError(f"spot timestamp-unit or archive-month error: {source.entry.key}")
    delta = frame["close_time"] - frame["open_time"]
    if ((delta < 0) | (delta >= duration)).any():
        raise ArchiveError(f"spot close-time outside hourly interval: {source.entry.key}")
    complete = delta == duration - 1
    idle = (frame["volume"] == 0) & (frame["count"] == 0)
    for field in ("high", "low", "close"):
        idle = idle & (frame[field] == frame["open"])
    evaluated = frame["timestamp"] >= datetime(2022, 1, 1, tzinfo=UTC)
    if (evaluated & ~complete & ~idle).any():
        raise ArchiveError(f"incomplete traded candle in evaluated time: {source.entry.key}")
    return frame.with_columns((complete & (frame["volume"] > 0)).alias("spot_available"))


def _check_prices(frame: pl.DataFrame, prefix: str) -> None:
    names = [f"{prefix}_{field}" for field in ("open", "high", "low", "close")]
    values = frame.select(names).to_numpy()
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ArchiveError(f"{prefix}: nonfinite/nonpositive OHLC")
    if frame.filter(
        (pl.col(names[1]) < pl.max_horizontal(names[0], names[2], names[3]))
        | (pl.col(names[2]) > pl.min_horizontal(names[0], names[1], names[3]))
    ).height:
        raise ArchiveError(f"{prefix}: invalid OHLC bounds")


def load_hedged_markets(root: Path, futures_root: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    spot_sources = cached_sources(root)
    futures_sources = cached_sources(futures_root)
    expected = pl.datetime_range(START, END, interval="1h", closed="left", eager=True)
    frames: list[pl.DataFrame] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        spot = pl.concat(
            [normalized_spot(s) for s in spot_sources if s.symbol == symbol], how="vertical_relaxed"
        ).sort("timestamp")
        if not spot["timestamp"].equals(expected):
            raise ArchiveError(f"{symbol}: incomplete, duplicate or shifted spot calendar")
        spot = spot.select(
            "timestamp",
            "spot_available",
            *[
                pl.col(field).alias(f"spot_{field}")
                for field in ("open", "high", "low", "close", "volume")
            ],
        )
        futures = load_participation(futures_sources, symbol).select(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
            "funding_rate_event",
            *[
                pl.col(field).alias(f"perp_{field}")
                for field in ("open", "high", "low", "close", "volume")
            ],
        )
        mark = pl.concat(
            [
                read_archive(s.path)
                for s in futures_sources
                if s.symbol == symbol and s.product == "markPriceKlines"
            ],
            how="vertical_relaxed",
        ).select(
            pl.from_epoch("open_time", time_unit="ms")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("timestamp"),
            *[pl.col(field).alias(f"mark_{field}") for field in ("open", "high", "low", "close")],
        )
        frame = (
            spot.join(futures, on="timestamp", how="left", validate="1:1")
            .join(mark, on="timestamp", how="left", validate="1:1")
            .sort("timestamp")
        )
        for prefix in ("spot", "perp", "mark"):
            _check_prices(frame, prefix)
        volumes = frame.select("spot_volume", "perp_volume").to_numpy()
        if not np.isfinite(volumes).all() or (volumes < 0).any():
            raise ArchiveError(f"{symbol}: invalid volumes")
        frame.write_parquet(root / f"{symbol}_hedged_inputs.parquet")
        frames.append(frame)
    manifest = pl.concat(
        [
            pl.read_csv(root / "source_manifest.csv"),
            pl.read_csv(futures_root / "source_manifest.csv"),
        ]
    )
    manifest.write_csv(root / "combined_source_manifest.csv")
    return frames[0], frames[1]
