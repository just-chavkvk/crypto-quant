from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def load_market_data(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")

    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    return df.sort_index()


@dataclass(frozen=True, slots=True)
class MarketUniverse:
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT")
    timeframe: str = "1h"
