from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from quant_lab.data.binance_shadow_source import (
    OhlcvPoint,
    RatioPoint,
)
from quant_lab.data.shadow_refresh import (
    refresh_microstructure_file,
)


class FakeShadowSource:
    def __init__(self, ohlcv: tuple[OhlcvPoint, ...], ratios: tuple[RatioPoint, ...]) -> None:
        self.ohlcv: tuple[OhlcvPoint, ...] = ohlcv
        self.ratios: tuple[RatioPoint, ...] = ratios

    def fetch_ohlcv_page(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        limit: int,
    ) -> tuple[OhlcvPoint, ...]:
        del symbol, timeframe, limit
        return tuple(point for point in self.ohlcv if point.timestamp_ms >= since_ms)

    def fetch_ratio_page(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> tuple[RatioPoint, ...]:
        del symbol, timeframe, limit
        return tuple(
            point for point in self.ratios if start_ms <= point.timestamp_ms <= end_ms
        )


def _ms(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


def _write_existing(root: Path) -> None:
    index = pd.date_range("2026-09-10 00:00", periods=3, freq="1h", tz="UTC")
    pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 11.0, 12.0],
            "count_long_short_ratio": [1.0, 1.1, float("nan")],
            "timestamp": index,
        }
    ).to_parquet(root / "BTC_USDT_1h_microstructure.parquet", index=False)


def test_refresh_backfills_ratio_gap_and_appends_complete_bars(tmp_path: Path) -> None:
    # Given: OHLCV extends one bar beyond positioning, with two later complete bars available.
    _write_existing(tmp_path)
    source = FakeShadowSource(
        ohlcv=(
            OhlcvPoint(_ms("2026-09-10 03:00"), 103.0, 104.0, 102.0, 103.5, 13.0),
            OhlcvPoint(_ms("2026-09-10 04:00"), 104.0, 105.0, 103.0, 104.5, 14.0),
        ),
        ratios=(
            RatioPoint(_ms("2026-09-10 03:00"), 1.2),
            RatioPoint(_ms("2026-09-10 04:00"), 1.3),
            RatioPoint(_ms("2026-09-10 05:00"), 1.4),
        ),
    )

    # When: refresh runs at 05:30 UTC, so the 04:00-starting 1h bar is complete.
    result = refresh_microstructure_file(
        tmp_path,
        symbol="BTCUSDT",
        timeframe="1h",
        now=datetime(2026, 9, 10, 5, 30, tzinfo=UTC),
        source=source,
    )

    # Then: the old 02:00 ratio gap is filled and 03:00/04:00 bars are appended.
    refreshed = pd.read_parquet(tmp_path / "BTC_USDT_1h_microstructure.parquet")
    refreshed["timestamp"] = pd.to_datetime(refreshed["timestamp"], utc=True)
    assert result.appended_bars == 2
    assert refreshed["timestamp"].iloc[-1] == pd.Timestamp("2026-09-10 04:00", tz="UTC")
    assert refreshed["count_long_short_ratio"].tail(3).tolist() == [1.2, 1.3, 1.4]
