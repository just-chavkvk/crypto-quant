from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics, TradeRecord


def _float_values(series: pd.Series) -> NDArray[np.float64]:
    return np.asarray(series.to_numpy(dtype=np.float64), dtype=np.float64)


def _annualization_periods(equity: pd.Series, fallback: int) -> float:
    timestamps = pd.DatetimeIndex(equity.index).to_numpy(dtype="datetime64[s]")
    if len(timestamps) < 2:
        return float(fallback)
    deltas = np.array(
        [float((right - left) / np.timedelta64(1, "s")) for left, right in pairwise(timestamps)],
        dtype=float,
    )
    positive_deltas = deltas[deltas > 0.0]
    if len(positive_deltas) == 0:
        return float(fallback)
    seconds_per_year = float(365 * 24 * 60 * 60)
    median_delta = float(np.median(positive_deltas))
    return seconds_per_year / median_delta


def calculate_metrics(
    returns: pd.Series,
    equity: pd.Series,
    trades: tuple[TradeRecord, ...],
    config: BacktestConfig,
) -> PerformanceMetrics:
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / config.initial_cash - 1.0
    periods_per_year = _annualization_periods(equity, config.periods_per_year)
    years = max(len(equity) - 1, 1) / periods_per_year
    if final_equity > 0:
        growth = final_equity / config.initial_cash
        with np.errstate(over="ignore"):
            cagr = float(np.expm1(np.log(growth) / years))
    else:
        cagr = -1.0
    drawdown = equity / equity.cummax() - 1.0
    max_drawdown = float(drawdown.min())

    return_values = _float_values(returns)
    mean_return = float(np.mean(return_values))
    volatility = float(np.std(return_values, ddof=0))
    sharpe_ratio = (
        mean_return / volatility * np.sqrt(periods_per_year)
        if volatility > 0
        else 0.0
    )
    downside = np.minimum(return_values, 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    sortino_ratio = (
        mean_return / downside_deviation * np.sqrt(periods_per_year)
        if downside_deviation > 0
        else 0.0
    )

    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    number_of_trades = len(trades)
    win_rate = len(wins) / number_of_trades if number_of_trades else 0.0
    loss_rate = len(losses) / number_of_trades if number_of_trades else 0.0
    gross_profit = float(sum(wins))
    gross_loss = abs(float(sum(losses)))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )
    average_win = gross_profit / len(wins) if wins else 0.0
    average_loss = float(sum(losses)) / len(losses) if losses else 0.0
    expectancy = (
        float(sum(trade.net_pnl for trade in trades)) / number_of_trades
        if number_of_trades
        else 0.0
    )

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        max_drawdown=max_drawdown,
        sharpe_ratio=float(sharpe_ratio),
        sortino_ratio=float(sortino_ratio),
        win_rate=win_rate,
        loss_rate=loss_rate,
        profit_factor=profit_factor,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        number_of_trades=number_of_trades,
    )
