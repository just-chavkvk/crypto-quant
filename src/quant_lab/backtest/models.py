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

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise BacktestInputError("initial_cash must be positive")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise BacktestInputError("fee_bps and slippage_bps must be non-negative")
        if self.periods_per_year <= 0:
            raise BacktestInputError("periods_per_year must be positive")


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
