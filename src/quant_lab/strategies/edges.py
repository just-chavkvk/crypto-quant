from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def _stateful_long_signal(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    signal = pd.Series(pd.NA, index=entry.index, dtype="Float64")
    signal.loc[entry] = 1.0
    signal.loc[exit_] = 0.0
    return signal.ffill().fillna(0.0).astype(float)


@dataclass(frozen=True, slots=True)
class MomentumTrendStrategy:
    lookback: int
    trend_ema: int
    name: str = "momentum_trend"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        trend = close.ewm(span=self.trend_ema, adjust=False).mean()
        return ((close > close.shift(self.lookback)) & (close > trend)).fillna(False).astype(float)


@dataclass(frozen=True, slots=True)
class DonchianBreakoutStrategy:
    entry_window: int
    exit_window: int
    name: str = "donchian_breakout"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        prior_high = data["high"].rolling(self.entry_window).max().shift(1)
        prior_low = data["low"].rolling(self.exit_window).min().shift(1)
        return _stateful_long_signal(close > prior_high, close < prior_low)


@dataclass(frozen=True, slots=True)
class VolumeBreakoutStrategy:
    breakout_window: int
    exit_window: int
    volume_window: int
    volume_multiple: float
    name: str = "volume_breakout"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        prior_high = data["high"].rolling(self.breakout_window).max().shift(1)
        prior_low = data["low"].rolling(self.exit_window).min().shift(1)
        prior_volume = data["volume"].rolling(self.volume_window).mean().shift(1)
        entry = (close > prior_high) & (data["volume"] > prior_volume * self.volume_multiple)
        return _stateful_long_signal(entry, close < prior_low)


@dataclass(frozen=True, slots=True)
class VolatilityBreakoutStrategy:
    breakout_window: int
    exit_window: int
    range_window: int
    range_multiple: float
    name: str = "volatility_breakout"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        prior_high = data["high"].rolling(self.breakout_window).max().shift(1)
        prior_low = data["low"].rolling(self.exit_window).min().shift(1)
        candle_range = data["high"] - data["low"]
        prior_range = candle_range.rolling(self.range_window).mean().shift(1)
        entry = (close > prior_high) & (candle_range > prior_range * self.range_multiple)
        return _stateful_long_signal(entry, close < prior_low)
