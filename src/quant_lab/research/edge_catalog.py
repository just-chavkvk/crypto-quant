from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import product

from quant_lab.strategies.base import Strategy
from quant_lab.strategies.edges import (
    DonchianBreakoutStrategy,
    MomentumTrendStrategy,
    VolatilityBreakoutStrategy,
    VolumeBreakoutStrategy,
)


class EdgeSearchInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class EdgeFamily(StrEnum):
    MOMENTUM = "momentum"
    DONCHIAN_BREAKOUT = "donchian_breakout"
    VOLUME_BREAKOUT = "volume_breakout"
    VOLATILITY_BREAKOUT = "volatility_breakout"


@dataclass(frozen=True, slots=True)
class EdgeParameters:
    lookback_hours: int | None = None
    trend_hours: int | None = None
    breakout_hours: int | None = None
    exit_hours: int | None = None
    volume_hours: int | None = None
    volume_multiple: float | None = None
    range_hours: int | None = None
    range_multiple: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.lookback_hours,
            self.trend_hours,
            self.breakout_hours,
            self.exit_hours,
            self.volume_hours,
            self.volume_multiple,
            self.range_hours,
            self.range_multiple,
        )
        present = tuple(value for value in values if value is not None)
        if not present:
            raise EdgeSearchInputError("at least one edge parameter is required")
        if any(value <= 0 for value in present):
            raise EdgeSearchInputError("edge parameters must be positive")


@dataclass(frozen=True, slots=True)
class EdgeCandidateSpec:
    family: EdgeFamily
    parameter_key: str
    parameters: EdgeParameters


def candidate_catalog() -> tuple[EdgeCandidateSpec, ...]:
    candidates: list[EdgeCandidateSpec] = []
    for lookback_hours, trend_hours in product((168, 336, 504), (240, 400, 504)):
        params = EdgeParameters(lookback_hours=lookback_hours, trend_hours=trend_hours)
        candidates.append(
            EdgeCandidateSpec(
                family=EdgeFamily.MOMENTUM,
                parameter_key=f"lookback={lookback_hours}h,trend={trend_hours}h",
                parameters=params,
            )
        )
    for breakout_hours, exit_hours in product((72, 168, 336), (24, 72)):
        if exit_hours >= breakout_hours:
            continue
        params = EdgeParameters(breakout_hours=breakout_hours, exit_hours=exit_hours)
        candidates.append(
            EdgeCandidateSpec(
                family=EdgeFamily.DONCHIAN_BREAKOUT,
                parameter_key=f"breakout={breakout_hours}h,exit={exit_hours}h",
                parameters=params,
            )
        )
    for breakout_hours, volume_hours, volume_multiple in product(
        (72, 168), (168, 336), (1.5, 2.0)
    ):
        params = EdgeParameters(
            breakout_hours=breakout_hours,
            exit_hours=24,
            volume_hours=volume_hours,
            volume_multiple=volume_multiple,
        )
        candidates.append(
            EdgeCandidateSpec(
                family=EdgeFamily.VOLUME_BREAKOUT,
                parameter_key=(
                    f"breakout={breakout_hours}h,volume={volume_hours}h,x{volume_multiple}"
                ),
                parameters=params,
            )
        )
    for breakout_hours, range_hours, range_multiple in product(
        (72, 168), (24, 72), (1.5, 2.0)
    ):
        params = EdgeParameters(
            breakout_hours=breakout_hours,
            exit_hours=24,
            range_hours=range_hours,
            range_multiple=range_multiple,
        )
        candidates.append(
            EdgeCandidateSpec(
                family=EdgeFamily.VOLATILITY_BREAKOUT,
                parameter_key=(
                    f"breakout={breakout_hours}h,range={range_hours}h,x{range_multiple}"
                ),
                parameters=params,
            )
        )
    return tuple(candidates)


def _bars(hours: int, timeframe_hours: int) -> int:
    return max(2, round(hours / timeframe_hours))


def _required_int(value: int | None, name: str) -> int:
    if value is None:
        raise EdgeSearchInputError(f"missing {name} parameter")
    return value


def _required_float(value: float | None, name: str) -> float:
    if value is None:
        raise EdgeSearchInputError(f"missing {name} parameter")
    return value


def build_strategy(spec: EdgeCandidateSpec, timeframe_hours: int) -> Strategy:
    params = spec.parameters
    match spec.family:
        case EdgeFamily.MOMENTUM:
            return MomentumTrendStrategy(
                lookback=_bars(_required_int(params.lookback_hours, "lookback_hours"), timeframe_hours),
                trend_ema=_bars(_required_int(params.trend_hours, "trend_hours"), timeframe_hours),
            )
        case EdgeFamily.DONCHIAN_BREAKOUT:
            return DonchianBreakoutStrategy(
                entry_window=_bars(
                    _required_int(params.breakout_hours, "breakout_hours"), timeframe_hours
                ),
                exit_window=_bars(_required_int(params.exit_hours, "exit_hours"), timeframe_hours),
            )
        case EdgeFamily.VOLUME_BREAKOUT:
            return VolumeBreakoutStrategy(
                breakout_window=_bars(
                    _required_int(params.breakout_hours, "breakout_hours"), timeframe_hours
                ),
                exit_window=_bars(_required_int(params.exit_hours, "exit_hours"), timeframe_hours),
                volume_window=_bars(
                    _required_int(params.volume_hours, "volume_hours"), timeframe_hours
                ),
                volume_multiple=_required_float(params.volume_multiple, "volume_multiple"),
            )
        case EdgeFamily.VOLATILITY_BREAKOUT:
            return VolatilityBreakoutStrategy(
                breakout_window=_bars(
                    _required_int(params.breakout_hours, "breakout_hours"), timeframe_hours
                ),
                exit_window=_bars(_required_int(params.exit_hours, "exit_hours"), timeframe_hours),
                range_window=_bars(_required_int(params.range_hours, "range_hours"), timeframe_hours),
                range_multiple=_required_float(params.range_multiple, "range_multiple"),
            )
