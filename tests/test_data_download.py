from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.data.download import DownloadRequest, MarketDataGapError, download_ohlcv


def utc_timestamp(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


@dataclass(slots=True)
class FakeExchange:
    pages: list[list[list[float]]]
    calls: list[int] = field(default_factory=list)

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float]]:
        del symbol, timeframe, limit
        self.calls.append(0 if since is None else since)
        return self.pages.pop(0) if self.pages else []


def test_downloader_paginates_deduplicates_sorts_and_reuses_cache(tmp_path: Path):
    hour = 3_600_000
    exchange = FakeExchange(
        pages=[
            [[hour, 1, 2, 0.5, 1.5, 10], [0, 1, 2, 0.5, 1.5, 10]],
            [
                [hour, 1, 2, 0.5, 1.5, 10],
                [2 * hour, 1, 2, 0.5, 1.5, 10],
                [3 * hour, 1, 2, 0.5, 1.5, 10],
            ],
        ]
    )
    request = DownloadRequest(
        symbol="BTC/USDT",
        timeframe="1h",
        start=utc_timestamp(0),
        end=utc_timestamp(2 * hour),
        cache_dir=tmp_path,
    )

    first = download_ohlcv(request, exchange=exchange)

    assert first.data.index.equals(
        pd.DatetimeIndex([utc_timestamp(0), utc_timestamp(hour), utc_timestamp(2 * hour)])
    )
    assert first.path.exists()
    assert len(pd.read_parquet(first.path)) == 3
    assert len(exchange.calls) == 2

    cached_exchange = FakeExchange(pages=[])
    second = download_ohlcv(request, exchange=cached_exchange)

    assert second.cache_hit is True
    assert cached_exchange.calls == []
    assert len(second.data) == 3


def test_downloader_rejects_missing_candles(tmp_path: Path):
    hour = 3_600_000
    exchange = FakeExchange(
        pages=[[[0, 1, 2, 0.5, 1.5, 10], [2 * hour, 1, 2, 0.5, 1.5, 10]]]
    )
    request = DownloadRequest(
        symbol="ETH/USDT",
        timeframe="1h",
        start=utc_timestamp(0),
        end=utc_timestamp(2 * hour),
        cache_dir=tmp_path,
    )

    with pytest.raises(MarketDataGapError):
        _ = download_ohlcv(request, exchange=exchange)

    assert not (tmp_path / "binance" / "ETH_USDT" / "1h.parquet").exists()


def test_downloader_repairs_internal_cached_gap(tmp_path: Path):
    hour = 3_600_000
    cache_path = tmp_path / "binance" / "BTC_USDT" / "1h.parquet"
    cache_path.parent.mkdir(parents=True)
    cached = pd.DataFrame(
        {
            "open": [1.0, 1.0],
            "high": [2.0, 2.0],
            "low": [0.5, 0.5],
            "close": [1.5, 1.5],
            "volume": [10.0, 10.0],
        },
        index=pd.to_datetime([0, 2 * hour], unit="ms", utc=True),
    )
    cached.to_parquet(cache_path)
    exchange = FakeExchange(pages=[[[hour, 1, 2, 0.5, 1.5, 10]]])
    request = DownloadRequest(
        symbol="BTC/USDT",
        timeframe="1h",
        start=utc_timestamp(0),
        end=utc_timestamp(2 * hour),
        cache_dir=tmp_path,
    )

    result = download_ohlcv(request, exchange=exchange)

    assert len(result.data) == 3
    assert result.cache_hit is False
    assert exchange.calls == [hour]
