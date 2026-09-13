from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

SUPPORTED_SYMBOLS = ("BTC/USDT", "ETH/USDT")
TIMEFRAME_MS = {"1h": 3_600_000, "4h": 14_400_000}
OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class OhlcvExchange(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float]]: ...


class MarketDataInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class MarketDataGapError(RuntimeError):
    missing_candles: int

    def __init__(self, missing_candles: int) -> None:
        self.missing_candles = missing_candles
        super().__init__(f"market data contains {missing_candles} missing candle(s)")


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    cache_dir: Path = Path("data/cache")

    def __post_init__(self) -> None:
        if self.symbol not in SUPPORTED_SYMBOLS:
            raise MarketDataInputError(f"unsupported symbol: {self.symbol}")
        if self.timeframe not in TIMEFRAME_MS:
            raise MarketDataInputError(f"unsupported timeframe: {self.timeframe}")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise MarketDataInputError("start and end must be timezone-aware")
        if self.start > self.end:
            raise MarketDataInputError("start must be <= end")


@dataclass(frozen=True, slots=True)
class DownloadResult:
    data: pd.DataFrame
    path: Path
    cache_hit: bool


@dataclass(frozen=True, slots=True)
class _FetchRange:
    start_ms: int
    end_ms: int


def _cache_path(request: DownloadRequest) -> Path:
    symbol = request.symbol.replace("/", "_")
    return request.cache_dir / "binance" / symbol / f"{request.timeframe}.parquet"


def _rows_to_frame(rows: list[list[float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    if frame.empty:
        return frame.set_index("timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.drop_duplicates(subset="timestamp", keep="last")
    frame = frame.sort_values("timestamp").set_index("timestamp")
    return frame.astype(float)


def _read_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=OHLCV_COLUMNS[1:])
    frame = pd.read_parquet(path)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp")
    return frame.sort_index()


def _timestamp_ms(timestamp: datetime) -> int:
    return int(timestamp.timestamp() * 1000)


def _index_milliseconds(frame: pd.DataFrame) -> tuple[int, ...]:
    timestamps = pd.DatetimeIndex(frame.index).to_numpy(dtype="datetime64[ms]")
    return tuple(int(value) for value in timestamps.astype(np.int64))


def _fetch_range(
    request: DownloadRequest,
    exchange: OhlcvExchange,
    bounds: _FetchRange,
) -> pd.DataFrame:
    cursor = bounds.start_ms
    pages: list[pd.DataFrame] = []
    while cursor <= bounds.end_ms:
        rows = exchange.fetch_ohlcv(
            request.symbol, request.timeframe, since=cursor, limit=1000
        )
        if not rows:
            break
        page = _rows_to_frame(rows)
        newest_ms = _index_milliseconds(page)[-1]
        lower = datetime.fromtimestamp(bounds.start_ms / 1000, tz=UTC)
        upper = datetime.fromtimestamp(bounds.end_ms / 1000, tz=UTC)
        clipped = page.loc[(page.index >= lower) & (page.index <= upper)]
        if not clipped.empty:
            pages.append(clipped)
        if newest_ms >= bounds.end_ms:
            break
        next_cursor = newest_ms + TIMEFRAME_MS[request.timeframe]
        if next_cursor <= cursor:
            raise MarketDataInputError("exchange pagination did not advance")
        cursor = next_cursor
    if not pages:
        return pd.DataFrame(columns=OHLCV_COLUMNS[1:])
    return pd.concat(pages).sort_index()


def _default_exchange() -> OhlcvExchange:
    import ccxt

    return ccxt.binance({"enableRateLimit": True})


def _needed_ranges(request: DownloadRequest, cached: pd.DataFrame) -> tuple[_FetchRange, ...]:
    start_ms = _timestamp_ms(request.start)
    end_ms = _timestamp_ms(request.end)
    step = TIMEFRAME_MS[request.timeframe]
    if cached.empty:
        return (_FetchRange(start_ms, end_ms),)
    cached_ms = {
        value for value in _index_milliseconds(cached) if start_ms <= value <= end_ms
    }
    missing = [timestamp for timestamp in range(start_ms, end_ms + 1, step) if timestamp not in cached_ms]
    if not missing:
        return ()
    ranges: list[_FetchRange] = []
    range_start = missing[0]
    previous = missing[0]
    for timestamp in missing[1:]:
        if timestamp != previous + step:
            ranges.append(_FetchRange(range_start, previous))
            range_start = timestamp
        previous = timestamp
    ranges.append(_FetchRange(range_start, previous))
    return tuple(ranges)


def _validate_requested_range(frame: pd.DataFrame, request: DownloadRequest) -> None:
    step = TIMEFRAME_MS[request.timeframe]
    start_ms = _timestamp_ms(request.start)
    end_ms = _timestamp_ms(request.end)
    expected = set(range(start_ms, end_ms + 1, step))
    actual = set(_index_milliseconds(frame))
    missing = len(expected.difference(actual))
    if missing:
        raise MarketDataGapError(missing)


def download_ohlcv(request: DownloadRequest, exchange: OhlcvExchange | None = None) -> DownloadResult:
    path = _cache_path(request)
    cached = _read_cache(path)
    ranges = _needed_ranges(request, cached)
    fetched: list[pd.DataFrame] = []
    if ranges:
        client = exchange if exchange is not None else _default_exchange()
        fetched = [_fetch_range(request, client, bounds) for bounds in ranges]
    frames = [frame for frame in (cached, *fetched) if not frame.empty]
    if not frames:
        raise MarketDataInputError("no OHLCV returned for requested range")
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    requested = combined.loc[(combined.index >= request.start) & (combined.index <= request.end)]
    if requested.empty:
        raise MarketDataInputError("requested range contains no candles")
    _validate_requested_range(requested, request)
    if ranges:
        path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(path)
    return DownloadResult(data=requested, path=path, cache_hit=not ranges)
