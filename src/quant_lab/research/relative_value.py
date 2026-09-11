from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd  # noqa: PANDAS_OK
from numpy.typing import NDArray


class RelativeValueInputError(ValueError):
    pass


class PositionSource(StrEnum):
    GLOBAL = "global"
    TOP_POSITION = "top_position"


@dataclass(frozen=True, slots=True)
class RelativeValueSpec:
    lookback_hours: int = 4
    zscore_window_hours: int = 720
    z_threshold: float = 2.0
    acceleration_z_threshold: float = 1.0
    hold_hours: int = 1
    fee_bps: float = 5.0
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0 or self.zscore_window_hours <= 1 or self.hold_hours <= 0:
            raise RelativeValueInputError("lookback, z-score window, and hold must be positive")
        if self.z_threshold <= 0.0 or self.acceleration_z_threshold <= 0.0:
            raise RelativeValueInputError("z-score thresholds must be positive")
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0:
            raise RelativeValueInputError("fee and slippage must be non-negative")


@dataclass(frozen=True, slots=True)
class PairEvaluation:
    total_return: float | None
    sharpe_ratio: float | None
    number_of_trades: int
    mean_trade_return: float | None
    median_trade_return: float | None
    win_rate: float | None


POSITION_COLUMNS: Final = {
    PositionSource.GLOBAL: "btc_global_ratio",
    PositionSource.TOP_POSITION: "btc_top_position_ratio",
}
REQUIRED_COLUMNS: Final = (
    "btc_open",
    "eth_open",
    "btc_close",
    "eth_close",
    "btc_premium_close",
    "eth_premium_close",
    "btc_taker_ratio",
    "eth_taker_ratio",
    "btc_oi_value",
    "eth_oi_value",
    "btc_global_ratio",
    "btc_top_position_ratio",
    "btc_oi_contracts",
)


def _read_microstructure(path: Path, prefix: str) -> pd.DataFrame:
    columns = [
        "timestamp",
        "open",
        "close",
        "premium_close",
        "taker_ratio",
        "sum_open_interest_value",
    ]
    if prefix == "btc":
        columns.extend(
            ["count_long_short_ratio", "sum_toptrader_long_short_ratio", "sum_open_interest"]
        )
    frame = pd.read_parquet(path, columns=columns)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    frame = frame.set_index("timestamp")
    renamed = {
        "open": f"{prefix}_open",
        "close": f"{prefix}_close",
        "premium_close": f"{prefix}_premium_close",
        "taker_ratio": f"{prefix}_taker_ratio",
        "sum_open_interest_value": f"{prefix}_oi_value",
        "count_long_short_ratio": "btc_global_ratio",
        "sum_toptrader_long_short_ratio": "btc_top_position_ratio",
        "sum_open_interest": "btc_oi_contracts",
    }
    return frame.rename(columns=renamed)


def load_relative_value_hourly(
    root: Path,
    *,
    start: str = "2022-01-01",
    end: str = "2026-09-01",
) -> pd.DataFrame:
    btc = _read_microstructure(root / "BTC_USDT_1h_microstructure.parquet", "btc")
    eth = _read_microstructure(root / "ETH_USDT_1h_microstructure.parquet", "eth")
    index = pd.date_range(start, end, freq="1h", inclusive="left", tz="UTC", name="timestamp")
    return pd.DataFrame(index=index).join(btc).join(eth)


def _validate_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise RelativeValueInputError("frame index must be a DatetimeIndex")
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise RelativeValueInputError(f"missing required columns: {sorted(missing)}")


def _log_change(series: pd.Series, periods: int) -> pd.Series:
    positive = series.astype(float).where(series.astype(float) > 0.0)
    logged = pd.Series(np.log(positive.to_numpy(dtype=float)), index=series.index, dtype=float)
    return logged - logged.shift(periods)


def _prior_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0).mask(lambda value: value <= 0.0)
    return (series - mean) / std


def _sign(series: pd.Series) -> pd.Series:
    return pd.Series(np.sign(series.to_numpy(dtype=float)), index=series.index, dtype=float)


def generate_position_catchup_events(
    frame: pd.DataFrame,
    source: PositionSource,
    spec: RelativeValueSpec,
) -> pd.Series:
    _validate_frame(frame)
    velocity = _log_change(frame[POSITION_COLUMNS[source]], spec.lookback_hours)
    acceleration = velocity - velocity.shift(spec.lookback_hours)
    velocity_z = _prior_zscore(velocity, spec.zscore_window_hours)
    acceleration_z = _prior_zscore(acceleration, spec.zscore_window_hours)
    price_return = _log_change(frame["btc_close"], spec.lookback_hours)
    oi_return = _log_change(frame["btc_oi_contracts"], spec.lookback_hours)
    direction = _sign(velocity_z)
    eligible = (
        pd.concat([velocity_z, acceleration_z, price_return, oi_return], axis=1).notna().all(axis=1)
        & (velocity_z.abs() >= spec.z_threshold)
        & (acceleration_z.abs() >= spec.acceleration_z_threshold)
        & (direction != 0.0)
        & (_sign(acceleration_z) == direction)
        & (_sign(price_return) == direction)
        & (_sign(oi_return) == -direction)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float)
    events.loc[eligible] = direction.loc[eligible]
    return events


def generate_premium_crowding_events(frame: pd.DataFrame, spec: RelativeValueSpec) -> pd.Series:
    _validate_frame(frame)
    spread = frame["eth_premium_close"] - frame["btc_premium_close"]
    spread_z = _prior_zscore(spread, spec.zscore_window_hours)
    oi_relative = _log_change(frame["eth_oi_value"], spec.lookback_hours) - _log_change(
        frame["btc_oi_value"], spec.lookback_hours
    )
    price_relative = _log_change(frame["eth_close"], spec.lookback_hours) - _log_change(
        frame["btc_close"], spec.lookback_hours
    )
    direction = _sign(spread_z)
    eligible = (
        pd.concat([spread_z, oi_relative, price_relative], axis=1).notna().all(axis=1)
        & (spread_z.abs() >= spec.z_threshold)
        & (direction != 0.0)
        & (_sign(oi_relative) == direction)
        & (_sign(price_relative) == direction)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float)
    events.loc[eligible] = -direction.loc[eligible]
    return events


def generate_taker_chase_events(frame: pd.DataFrame, spec: RelativeValueSpec) -> pd.Series:
    _validate_frame(frame)
    eth_ratio = frame["eth_taker_ratio"].where(frame["eth_taker_ratio"] > 0.0)
    btc_ratio = frame["btc_taker_ratio"].where(frame["btc_taker_ratio"] > 0.0)
    spread = pd.Series(
        np.log(eth_ratio.to_numpy(dtype=float)) - np.log(btc_ratio.to_numpy(dtype=float)),
        index=frame.index,
        dtype=float,
    )
    spread_z = _prior_zscore(spread, spec.zscore_window_hours)
    price_relative = _log_change(frame["eth_close"], spec.lookback_hours) - _log_change(
        frame["btc_close"], spec.lookback_hours
    )
    direction = _sign(spread_z)
    eligible = (
        pd.concat([spread_z, price_relative], axis=1).notna().all(axis=1)
        & (spread_z.abs() >= spec.z_threshold)
        & (direction != 0.0)
        & (_sign(price_relative) == direction)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float)
    events.loc[eligible] = -direction.loc[eligible]
    return events


def evaluate_pair_events(
    frame: pd.DataFrame,
    events: pd.Series,
    spec: RelativeValueSpec,
    *,
    start: str,
    end: str,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
) -> PairEvaluation:
    _validate_frame(frame)
    if not events.index.equals(frame.index):
        raise RelativeValueInputError("events index must exactly match the market frame")
    index = pd.DatetimeIndex(frame.index)
    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    event_values: NDArray[np.float64] = np.asarray(
        events.to_numpy(dtype=np.float64), dtype=np.float64
    )
    btc_open: NDArray[np.float64] = np.asarray(
        frame["btc_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    eth_open: NDArray[np.float64] = np.asarray(
        frame["eth_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    candidate_offsets = [
        offset
        for offset, event in enumerate(event_values.tolist())
        if start_timestamp <= index[offset] < end_timestamp and event != 0.0
    ]
    fee_rate = (spec.fee_bps if fee_bps is None else fee_bps) / 10_000.0
    slippage_rate = (spec.slippage_bps if slippage_bps is None else slippage_bps) / 10_000.0
    round_trip_cost = 2.0 * (fee_rate + slippage_rate)
    trade_returns: list[float] = []
    next_allowed_signal_offset = -1
    for signal_offset in candidate_offsets:
        if signal_offset < next_allowed_signal_offset:
            continue
        entry_offset = signal_offset + 1
        exit_offset = entry_offset + spec.hold_hours
        if exit_offset >= len(frame) or index[exit_offset] >= end_timestamp:
            continue
        prices = (btc_open[entry_offset], btc_open[exit_offset], eth_open[entry_offset], eth_open[exit_offset])
        if not all(np.isfinite(price) and price > 0.0 for price in prices):
            continue
        btc_return = float(btc_open[exit_offset] / btc_open[entry_offset] - 1.0)
        eth_return = float(eth_open[exit_offset] / eth_open[entry_offset] - 1.0)
        gross_return = 0.5 * float(event_values[signal_offset]) * (eth_return - btc_return)
        trade_returns.append(gross_return - round_trip_cost)
        next_allowed_signal_offset = exit_offset
    if not trade_returns:
        return PairEvaluation(None, None, 0, None, None, None)
    values = np.asarray(trade_returns, dtype=np.float64)
    standard_deviation = float(np.std(values, ddof=0))
    sharpe_ratio = (
        float(np.mean(values) / standard_deviation * np.sqrt(8760.0 / spec.hold_hours))
        if standard_deviation > 0.0
        else 0.0
    )
    return PairEvaluation(
        total_return=float(np.prod(1.0 + values) - 1.0),
        sharpe_ratio=sharpe_ratio,
        number_of_trades=int(values.size),
        mean_trade_return=float(np.mean(values)),
        median_trade_return=float(np.median(values)),
        win_rate=float(np.mean(values > 0.0)),
    )
