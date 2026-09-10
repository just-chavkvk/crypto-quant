from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


class BacktestInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    periods_per_year: int = 24 * 365
    risk_per_trade: float | None = None
    stop_loss_pct: float | None = None
    max_exposure: float = 1.0
    max_leverage: float = 1.0
    max_volume_participation: float | None = None
    volatility_slippage_multiplier: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise BacktestInputError("initial_cash must be positive")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise BacktestInputError("fee_bps and slippage_bps must be non-negative")
        if self.periods_per_year <= 0:
            raise BacktestInputError("periods_per_year must be positive")
        if (self.risk_per_trade is None) != (self.stop_loss_pct is None):
            raise BacktestInputError("risk_per_trade and stop_loss_pct must be configured together")
        if self.risk_per_trade is not None and not 0.0 < self.risk_per_trade <= 1.0:
            raise BacktestInputError("risk_per_trade must be in (0, 1]")
        if self.stop_loss_pct is not None and not 0.0 < self.stop_loss_pct < 1.0:
            raise BacktestInputError("stop_loss_pct must be in (0, 1)")
        if self.max_exposure <= 0.0 or self.max_leverage <= 0.0:
            raise BacktestInputError("max_exposure and max_leverage must be positive")
        if (
            self.max_volume_participation is not None
            and not 0.0 < self.max_volume_participation <= 1.0
        ):
            raise BacktestInputError("max_volume_participation must be in (0, 1]")
        if self.volatility_slippage_multiplier < 0.0:
            raise BacktestInputError("volatility_slippage_multiplier must be non-negative")


@dataclass(frozen=True, slots=True)
class TradeRecord:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    entry_fill_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_fill_price: float
    position_size: float
    gross_pnl: float
    fee: float
    slippage_cost: float
    net_pnl: float
    return_pct: float
    holding_period: pd.Timedelta
    entry_fills: int


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    loss_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    expectancy: float
    number_of_trades: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    exposure: pd.Series
    trades: tuple[TradeRecord, ...]
    metrics: PerformanceMetrics
