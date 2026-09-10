import pandas as pd

from quant_lab.backtest.engine import BacktestConfig, run_backtest
from quant_lab.strategies.base import EmaBreakoutStrategy


def sample_data(rows: int = 400) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series(range(100, 100 + rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )


def test_backtest_runs_and_returns_metrics():
    data = sample_data()
    strategy = EmaBreakoutStrategy(fast=10, slow=30, breakout=5)
    result = run_backtest(data, strategy, BacktestConfig(fee_bps=5, slippage_bps=2))

    assert len(result.equity) == len(data)
    assert set(result.metrics) == {"total_return", "max_drawdown", "sharpe"}
    assert result.equity.iloc[-1] > 0


def test_signal_is_shifted_before_execution():
    data = sample_data()
    strategy = EmaBreakoutStrategy(fast=2, slow=3, breakout=2)
    result = run_backtest(data, strategy)

    assert result.exposure.iloc[0] == 0.0
