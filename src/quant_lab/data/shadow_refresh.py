from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pandas as pd

from quant_lab.data.binance_shadow_source import (
    BinanceUsdMShadowSource,
    OhlcvPoint,
    RatioPoint,
    ShadowDataSource,
)

TIMEFRAME_HOURS: Final = {"1h": 1, "4h": 4}
SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")


class ShadowRefreshError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RefreshResult:
    symbol: str
    timeframe: str
    appended_bars: int
    filled_ratios: int
    latest_bar: pd.Timestamp


def _timeframe_delta(timeframe: str) -> timedelta:
    try:
        return timedelta(hours=TIMEFRAME_HOURS[timeframe])
    except KeyError as exc:
        raise ShadowRefreshError(f"unsupported timeframe: {timeframe}") from exc


def _last_complete_bar(now: datetime, timeframe: str) -> pd.Timestamp:
    if now.tzinfo is None:
        raise ShadowRefreshError("now must be timezone-aware")
    utc_now = now.astimezone(UTC)
    hours = TIMEFRAME_HOURS[timeframe]
    block_hour = utc_now.hour // hours * hours
    current = utc_now.replace(hour=block_hour, minute=0, second=0, microsecond=0)
    return pd.Timestamp(current - timedelta(hours=hours))


def _read_microstructure(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ShadowRefreshError(f"missing baseline microstructure file: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True), name="timestamp")
    required = {"open", "high", "low", "close", "volume", "count_long_short_ratio"}
    missing = required.difference(frame.columns)
    if missing:
        raise ShadowRefreshError(f"missing microstructure columns: {sorted(missing)}")
    return frame.sort_index()


def _fetch_ohlcv_range(
    source: ShadowDataSource,
    symbol: str,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[int, OhlcvPoint]:
    step_ms = int(_timeframe_delta(timeframe).total_seconds() * 1000)
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    points: dict[int, OhlcvPoint] = {}
    while cursor <= end_ms:
        page = source.fetch_ohlcv_page(symbol, timeframe, cursor, 1000)
        clipped = tuple(point for point in page if cursor <= point.timestamp_ms <= end_ms)
        points.update({point.timestamp_ms: point for point in clipped})
        if not page:
            break
        newest = max(point.timestamp_ms for point in page)
        if newest < cursor:
            raise ShadowRefreshError("OHLCV pagination did not advance")
        cursor = newest + step_ms
    return points


def _fetch_ratio_range(
    source: ShadowDataSource,
    symbol: str,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[int, RatioPoint]:
    step_ms = int(_timeframe_delta(timeframe).total_seconds() * 1000)
    cursor = int(start.timestamp() * 1000) + step_ms
    end_ms = int(end.timestamp() * 1000) + step_ms
    points: dict[int, RatioPoint] = {}
    while cursor <= end_ms:
        page = source.fetch_ratio_page(symbol, timeframe, cursor, end_ms, 500)
        clipped = tuple(point for point in page if cursor <= point.timestamp_ms <= end_ms)
        points.update({point.timestamp_ms - step_ms: point for point in clipped})
        if not page:
            break
        newest = max(point.timestamp_ms for point in page)
        if newest < cursor:
            raise ShadowRefreshError("ratio pagination did not advance")
        cursor = newest + step_ms
    return points


def _expected_ms(start: pd.Timestamp, end: pd.Timestamp, timeframe: str) -> set[int]:
    step_ms = int(_timeframe_delta(timeframe).total_seconds() * 1000)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    return set(range(start_ms, end_ms + 1, step_ms))


def refresh_microstructure_file(
    root: Path,
    *,
    symbol: str,
    timeframe: str,
    now: datetime,
    source: ShadowDataSource,
) -> RefreshResult:
    asset = symbol.removesuffix("USDT")
    path = root / f"{asset}_USDT_{timeframe}_microstructure.parquet"
    frame = _read_microstructure(path)
    step = _timeframe_delta(timeframe)
    last_complete = _last_complete_bar(now, timeframe)
    latest_existing = pd.Timestamp(frame.index.max())
    price_start = latest_existing + step

    combined = frame.copy()
    if price_start <= last_complete:
        ohlcv = _fetch_ohlcv_range(source, symbol, timeframe, price_start, last_complete)
        expected = _expected_ms(price_start, last_complete, timeframe)
        if expected.difference(ohlcv):
            raise ShadowRefreshError("OHLCV refresh contains missing complete bars")
        new_index = pd.date_range(price_start, last_complete, freq=step, tz="UTC", name="timestamp")
        new_rows = pd.DataFrame(index=new_index, columns=combined.columns, dtype=float)
        for timestamp in new_index:
            point = ohlcv[int(timestamp.timestamp() * 1000)]
            new_rows.loc[timestamp, ["open", "high", "low", "close", "volume"]] = (
                point.open,
                point.high,
                point.low,
                point.close,
                point.volume,
            )
        combined = pd.concat([combined, new_rows]).sort_index()

    ratio_known = combined["count_long_short_ratio"].dropna()
    ratio_start = (
        pd.Timestamp(ratio_known.index.max()) + step
        if not ratio_known.empty
        else pd.Timestamp(combined.index.min())
    )
    before_ratio_count = int(combined["count_long_short_ratio"].notna().sum())
    if ratio_start <= last_complete:
        ratios = _fetch_ratio_range(source, symbol, timeframe, ratio_start, last_complete)
        expected = _expected_ms(ratio_start, last_complete, timeframe)
        if expected.difference(ratios):
            raise ShadowRefreshError("ratio refresh contains missing complete bars")
        for timestamp_ms, point in ratios.items():
            timestamp = pd.Timestamp(timestamp_ms, unit="ms", tz="UTC")
            combined.loc[timestamp, "count_long_short_ratio"] = point.ratio

    appended_bars = max(len(combined) - len(frame), 0)
    filled_ratios = int(combined["count_long_short_ratio"].notna().sum()) - before_ratio_count
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.reset_index().to_parquet(path, index=False)
    return RefreshResult(
        symbol=symbol,
        timeframe=timeframe,
        appended_bars=appended_bars,
        filled_ratios=filled_ratios,
        latest_bar=pd.Timestamp(combined.index.max()),
    )


def refresh_shadow_data(
    root: Path,
    *,
    now: datetime | None = None,
    source: ShadowDataSource | None = None,
) -> tuple[RefreshResult, ...]:
    current = datetime.now(UTC) if now is None else now
    client = BinanceUsdMShadowSource() if source is None else source
    return tuple(
        refresh_microstructure_file(
            root,
            symbol=symbol,
            timeframe=timeframe,
            now=current,
            source=client,
        )
        for symbol in SYMBOLS
        for timeframe in TIMEFRAME_HOURS
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh frozen-strategy forward-shadow inputs")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    for result in refresh_shadow_data(args.root):
        print(result)


if __name__ == "__main__":
    main()
