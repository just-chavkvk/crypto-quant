from __future__ import annotations

from dataclasses import dataclass


class RiskInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade: float = 0.005
    max_exposure: float = 1.0
    max_leverage: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.risk_per_trade <= 1.0:
            raise RiskInputError("risk_per_trade must be in (0, 1]")
        if self.max_exposure <= 0.0 or self.max_leverage <= 0.0:
            raise RiskInputError("max_exposure and max_leverage must be positive")


def position_size_from_stop(equity: float, entry: float, stop: float, cfg: RiskConfig) -> float:
    """Return base-asset quantity sized so stop-loss risk is bounded."""
    if equity <= 0 or entry <= 0:
        return 0.0
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return 0.0

    risk_budget = equity * cfg.risk_per_trade
    qty_by_risk = risk_budget / stop_distance
    max_notional = equity * cfg.max_exposure * cfg.max_leverage
    qty_by_exposure = max_notional / entry
    return max(0.0, min(qty_by_risk, qty_by_exposure))
