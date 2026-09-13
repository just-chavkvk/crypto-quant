from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


class Strategy(Protocol):
    @property
    def name(self) -> str: ...

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return target exposure in [-1, 1], indexed like data."""
        ...


@dataclass(frozen=True, slots=True)
class EmaBreakoutStrategy:
    fast: int = 50
    slow: int = 200
    breakout: int = 20
    name: str = "ema_breakout"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        fast_ema = close.ewm(span=self.fast, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow, adjust=False).mean()
        prior_high = data["high"].rolling(self.breakout).max().shift(1)

        long_entry = (fast_ema > slow_ema) & (close > prior_high)
        flat = fast_ema < slow_ema

        signal = pd.Series(pd.NA, index=data.index, dtype="Float64")
        signal.loc[long_entry] = 1.0
        signal.loc[flat] = 0.0
        return signal.ffill().fillna(0.0).astype(float)
