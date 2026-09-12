from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import repeat
from pathlib import Path
from typing import Final

import polars as pl

from quant_lab.data.binance_archive import ArchiveError, archive_client
from quant_lab.data.participation_data import END, START

BASE: Final = "https://api.bybit.com"


class BybitKind(StrEnum):
    FUNDING = "funding"
    TRADE = "trade"
    MARK = "mark"


@dataclass(frozen=True, slots=True)
class HistorySeries:
    symbol: str
    kind: BybitKind


@dataclass(frozen=True, slots=True)
class ResponseEvidence:
    symbol: str
    kind: str
    url: str
    query: str
    path: str
    retrieved_at: str
    sha256: str
    rows: int


def fetch_series(series: HistorySeries, root: Path) -> tuple[pl.DataFrame, list[ResponseEvidence]]:
    folder = root / "raw" / series.symbol / series.kind.value
    folder.mkdir(parents=True, exist_ok=True)
    start_ms = int(START.timestamp() * 1000)
    cursor = int(END.timestamp() * 1000) - 1
    frames: list[pl.DataFrame] = []
    evidence: list[ResponseEvidence] = []
    with archive_client() as client:
        while cursor >= start_ms:
            params: dict[str, str | int] = {"category": "linear", "symbol": series.symbol}
            match series.kind:
                case BybitKind.FUNDING:
                    endpoint = "/v5/market/funding/history"
                    params.update(startTime=start_ms, endTime=cursor, limit=200)
                case BybitKind.TRADE | BybitKind.MARK:
                    endpoint = (
                        "/v5/market/kline"
                        if series.kind == BybitKind.TRADE
                        else "/v5/market/mark-price-kline"
                    )
                    params.update(start=start_ms, end=cursor, limit=1000, interval="60")
            path = folder / f"{cursor}.json"
            if not path.exists():
                response = client.get(BASE + endpoint, params=params)
                _ = response.raise_for_status()
                _ = path.write_bytes(response.content)
            payload = path.read_bytes()
            body = json.loads(payload)
            if body["retCode"] != 0:
                raise ArchiveError(f"Bybit API error {body['retCode']}: {body['retMsg']}")
            rows = body["result"]["list"]
            if not rows:
                raise ArchiveError(
                    f"empty Bybit history page: {series.symbol}/{series.kind}/{cursor}"
                )
            match series.kind:
                case BybitKind.FUNDING:
                    frame = pl.DataFrame(
                        [
                            (int(row["fundingRateTimestamp"]), float(row["fundingRate"]))
                            for row in rows
                        ],
                        schema={"timestamp_ms": pl.Int64, "funding": pl.Float64},
                        orient="row",
                    )
                case BybitKind.TRADE:
                    frame = pl.DataFrame(
                        [(int(row[0]), *(float(v) for v in row[1:])) for row in rows],
                        schema={
                            "timestamp_ms": pl.Int64,
                            "open": pl.Float64,
                            "high": pl.Float64,
                            "low": pl.Float64,
                            "close": pl.Float64,
                            "volume": pl.Float64,
                            "turnover": pl.Float64,
                        },
                        orient="row",
                    )
                case BybitKind.MARK:
                    frame = pl.DataFrame(
                        [(int(row[0]), *(float(v) for v in row[1:])) for row in rows],
                        schema={
                            "timestamp_ms": pl.Int64,
                            "mark_open": pl.Float64,
                            "mark_high": pl.Float64,
                            "mark_low": pl.Float64,
                            "mark_close": pl.Float64,
                        },
                        orient="row",
                    )
            stamps = frame["timestamp_ms"].to_list()
            oldest, newest = min(stamps), max(stamps)
            if oldest < start_ms or newest > cursor:
                raise ArchiveError(
                    "Bybit pagination returned out-of-range or repeated observations"
                )
            evidence.append(
                ResponseEvidence(
                    series.symbol,
                    series.kind.value,
                    BASE + endpoint,
                    json.dumps(params, sort_keys=True),
                    str(path),
                    datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                    hashlib.sha256(payload).hexdigest(),
                    len(frame),
                )
            )
            frames.append(frame)
            cursor = oldest - 1
    combined = (
        pl.concat(frames)
        .sort("timestamp_ms")
        .with_columns(
            pl.from_epoch("timestamp_ms", time_unit="ms")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("timestamp")
        )
    )
    combined.write_parquet(root / f"{series.symbol}_{series.kind.value}.parquet")
    return combined, evidence


def download_bybit(root: Path) -> None:
    specs = tuple(
        HistorySeries(symbol, kind) for symbol in ("BTCUSDT", "ETHUSDT") for kind in BybitKind
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = tuple(pool.map(fetch_series, specs, repeat(root)))
    evidence = [asdict(row) for _, rows in results for row in rows]
    pl.DataFrame(evidence).write_csv(root / "bybit_response_manifest.csv")
