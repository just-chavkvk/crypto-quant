from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_lab.strategies.base import Strategy


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    periods_per_year: int = 24 * 365


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    exposure: pd.Series
    metrics: dict[str, float]


def _metrics(returns: pd.Series, equity: pd.Series, periods_per_year: int) -> dict[str, float]:
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())
    vol = float(returns.std(ddof=0))
    sharpe = float((returns.mean() / vol) * np.sqrt(periods_per_year)) if vol > 0 else 0.0
    return {"total_return": total_return, "max_drawdown": max_drawdown, "sharpe": sharpe}


def run_backtest(data: pd.DataFrame, strategy: Strategy, config: BacktestConfig | None = None) -> BacktestResult:
    cfg = config or BacktestConfig()
    exposure = strategy.generate_signals(data).astype(float).clip(-1.0, 1.0)

    # Execute one bar later to avoid using the same close that generated the signal.
    held_exposure = exposure.shift(1).fillna(0.0)
    asset_returns = data["close"].pct_change().fillna(0.0)
    turnover = held_exposure.diff().abs().fillna(held_exposure.abs())
    trading_cost = turnover * ((cfg.fee_bps + cfg.slippage_bps) / 10_000.0)
    strategy_returns = held_exposure * asset_returns - trading_cost
    equity = cfg.initial_cash * (1.0 + strategy_returns).cumprod()

    return BacktestResult(
        equity=equity,
        returns=strategy_returns,
        exposure=held_exposure,
        metrics=_metrics(strategy_returns, equity, cfg.periods_per_year),
    )
