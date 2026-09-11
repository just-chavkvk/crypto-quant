from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.metrics import calculate_metrics
from quant_lab.backtest.models import BacktestConfig, BacktestResult
from quant_lab.strategies.base import Strategy


class ForwardShadowInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _PreparedSignals:
    signals: pd.Series
    name: str = "forward_shadow_signals"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.signals.reindex(data.index)


def run_forward_shadow(
    data: pd.DataFrame,
    strategy: Strategy,
    *,
    start: str,
    end: str,
    config: BacktestConfig,
    symbol: str,
) -> BacktestResult | None:
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ForwardShadowInputError("market data index must be a DatetimeIndex")
    if data.empty:
        return None

    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    if start_timestamp >= end_timestamp:
        raise ForwardShadowInputError("shadow start must be before end")

    index = pd.DatetimeIndex(data.index)
    history = data.loc[index < end_timestamp]
    history_index = pd.DatetimeIndex(history.index)
    shadow_mask = history_index >= start_timestamp
    shadow_offsets = [offset for offset, included in enumerate(shadow_mask.tolist()) if included]
    if not shadow_offsets:
        return None

    signals = strategy.generate_signals(history).astype(float)
    first_shadow_offset = shadow_offsets[0]
    last_shadow_offset = shadow_offsets[-1]
    context_offset = max(first_shadow_offset - 1, 0)
    context = history.iloc[context_offset : last_shadow_offset + 1]
    context_signals = signals.reindex(context.index)
    if len(context) < 2:
        return None

    result = run_backtest(
        context,
        _PreparedSignals(context_signals),
        config,
        symbol=symbol,
    )
    if context_offset == first_shadow_offset:
        return result

    equity = result.equity.iloc[1:].copy()
    returns = result.returns.iloc[1:].copy()
    exposure = result.exposure.iloc[1:].copy()
    metrics = calculate_metrics(returns, equity, result.trades, config)
    return BacktestResult(
        equity=equity,
        returns=returns,
        exposure=exposure,
        trades=result.trades,
        metrics=metrics,
    )
