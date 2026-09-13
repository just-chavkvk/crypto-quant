from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import numpy as np
import pandas as pd
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class OhlcvPoint:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class RatioPoint:
    timestamp_ms: int
    ratio: float


class _BinanceUsdM(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float]]: ...

class ShadowDataSource(Protocol):
    def fetch_ohlcv_page(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        limit: int,
    ) -> tuple[OhlcvPoint, ...]: ...

    def fetch_ratio_page(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> tuple[RatioPoint, ...]: ...


class BinanceUsdMShadowSource:
    def __init__(self) -> None:
        import ccxt

        self._exchange: _BinanceUsdM = ccxt.binanceusdm({"enableRateLimit": True})

    def fetch_ohlcv_page(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        limit: int,
    ) -> tuple[OhlcvPoint, ...]:
        asset = symbol.removesuffix("USDT")
        rows = self._exchange.fetch_ohlcv(
            f"{asset}/USDT:USDT",
            timeframe,
            since=since_ms,
            limit=limit,
        )
        return tuple(
            OhlcvPoint(
                timestamp_ms=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
        )

    def fetch_ratio_page(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        limit: int,
    ) -> tuple[RatioPoint, ...]:
        query = urlencode(
            {
                "symbol": symbol,
                "period": timeframe,
                "limit": limit,
                "startTime": start_ms,
                "endTime": end_ms,
            }
        )
        frame = pd.read_json(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?{query}"
        )
        required = {"timestamp", "longShortRatio"}
        missing = required.difference(frame.columns)
        if missing:
            raise RuntimeError(f"Binance ratio response missing columns: {sorted(missing)}")
        timestamps: NDArray[np.int64] = np.asarray(
            frame["timestamp"].to_numpy(dtype=np.int64), dtype=np.int64
        )
        ratios: NDArray[np.float64] = np.asarray(
            frame["longShortRatio"].to_numpy(dtype=np.float64), dtype=np.float64
        )
        return tuple(
            RatioPoint(timestamp_ms=int(timestamp), ratio=float(ratio))
            for timestamp, ratio in zip(timestamps.tolist(), ratios.tolist(), strict=True)
        )
