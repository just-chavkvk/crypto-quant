from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd  # noqa: PANDAS_OK


class TakerDivergenceInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class TakerDivergenceSpec:
    timeframe_minutes: int
    lookback_hours: int
    flow_z_threshold: float
    response_z_cap: float
    hold_minutes: int

    def __post_init__(self) -> None:
        if self.timeframe_minutes <= 0 or self.lookback_hours <= 0 or self.hold_minutes <= 0:
            raise TakerDivergenceInputError("timeframe, lookback, and hold must be positive")
        if self.lookback_hours * 60 % self.timeframe_minutes != 0:
            raise TakerDivergenceInputError("lookback must align with timeframe")
        if self.hold_minutes % self.timeframe_minutes != 0:
            raise TakerDivergenceInputError("hold must align with timeframe")
        if self.flow_z_threshold <= 0.0:
            raise TakerDivergenceInputError("flow_z_threshold must be positive")
        if self.response_z_cap < 0.0:
            raise TakerDivergenceInputError("response_z_cap must be non-negative")

    @property
    def lookback_bars(self) -> int:
        return self.lookback_hours * 60 // self.timeframe_minutes

    @property
    def hold_bars(self) -> int:
        return self.hold_minutes // self.timeframe_minutes


def _prior_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0)
    safe_std = std.mask(std <= 0.0)
    return (series - mean) / safe_std


def taker_divergence_events(data: pd.DataFrame, spec: TakerDivergenceSpec) -> pd.Series:
    required = {"open", "close", "quote_volume", "taker_buy_quote_volume"}
    missing = required.difference(data.columns)
    if missing:
        raise TakerDivergenceInputError(f"missing required columns: {sorted(missing)}")

    quote_volume = data["quote_volume"].astype(float)
    taker_buy_quote = data["taker_buy_quote_volume"].astype(float)
    flow_imbalance = (2.0 * taker_buy_quote / quote_volume.mask(quote_volume <= 0.0) - 1.0).clip(
        -1.0, 1.0
    )
    bar_ratio = data["close"].astype(float) / data["open"].astype(float)
    bar_return = pd.Series(
        np.log(bar_ratio.to_numpy(dtype=float)), index=data.index, dtype=float
    )
    flow_z = _prior_zscore(flow_imbalance, spec.lookback_bars)
    return_z = _prior_zscore(bar_return, spec.lookback_bars)

    buy_absorption = (flow_z >= spec.flow_z_threshold) & (return_z <= spec.response_z_cap)
    sell_absorption = (flow_z <= -spec.flow_z_threshold) & (return_z >= -spec.response_z_cap)
    events = pd.Series(0.0, index=data.index, dtype=float)
    events.loc[buy_absorption.fillna(False)] = -1.0
    events.loc[sell_absorption.fillna(False)] = 1.0
    return events


def hold_non_overlapping_events(events: pd.Series, hold_bars: int) -> pd.Series:
    if hold_bars <= 0:
        raise TakerDivergenceInputError("hold_bars must be positive")

    event_values = events.to_numpy(dtype=float)
    signal_values = np.zeros(len(events), dtype=float)
    active_side = 0.0
    remaining = 0
    for offset, event in enumerate(event_values):
        if remaining == 0 and event != 0.0:
            active_side = float(event)
            remaining = hold_bars
        if remaining > 0:
            signal_values[offset] = active_side
            remaining -= 1
        if remaining == 0:
            active_side = 0.0
    return pd.Series(signal_values, index=events.index, dtype=float)


@dataclass(frozen=True, slots=True)
class TakerDivergenceStrategy:
    spec: TakerDivergenceSpec
    name: str = "taker_flow_price_divergence"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        events = taker_divergence_events(data, self.spec)
        return hold_non_overlapping_events(events, self.spec.hold_bars)
