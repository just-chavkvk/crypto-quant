from dataclasses import dataclass

import pandas as pd
import pytest

from quant_lab.backtest.models import BacktestConfig
from quant_lab.validation.lookahead import LookaheadBiasError, assert_no_lookahead
from quant_lab.validation.walk_forward import WalkForwardConfig, evaluate_walk_forward


@dataclass(frozen=True, slots=True)
class AlwaysLongStrategy:
    name: str = "always_long"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=data.index, dtype=float)


@dataclass(frozen=True, slots=True)
class FutureLeakStrategy:
    name: str = "future_leak"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        future_close = data["close"].shift(-1)
        return (future_close > data["close"]).fillna(False).astype(float)


def market_data(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(closes), freq="h", tz="UTC")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        },
        index=index,
    )


def test_lookahead_validator_rejects_future_dependent_strategy():
    with pytest.raises(LookaheadBiasError):
        assert_no_lookahead(market_data([100, 101, 99, 102, 98]), FutureLeakStrategy())


def test_walk_forward_marks_candidate_failed_when_oos_loses():
    data = market_data([100, 110, 120, 130, 120, 110])

    report = evaluate_walk_forward(
        data,
        strategy_factory=AlwaysLongStrategy,
        config=WalkForwardConfig(train_bars=4, test_bars=2),
        backtest_config=BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    assert report.windows[0].train.metrics.total_return > 0
    assert report.windows[0].out_of_sample.metrics.total_return < 0
    assert report.passed is False
    assert report.walk_forward.metrics.total_return < 0
