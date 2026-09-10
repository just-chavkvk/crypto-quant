from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.005
    max_exposure: float = 1.0
    max_leverage: float = 1.0


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
