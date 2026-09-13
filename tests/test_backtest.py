from dataclasses import dataclass

import pandas as pd
import pytest

from quant_lab.backtest.engine import run_backtest, run_buy_and_hold
from quant_lab.backtest.models import BacktestConfig
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
    assert result.metrics.number_of_trades >= 0
    assert result.metrics.max_drawdown <= 0
    assert result.equity.iloc[-1] > 0


def test_signal_is_shifted_before_execution():
    data = sample_data()
    strategy = EmaBreakoutStrategy(fast=2, slow=3, breakout=2)
    result = run_backtest(data, strategy)

    assert result.exposure.iloc[0] == 0.0


def test_ema_breakout_can_exit_after_fast_ema_crosses_below_slow():
    data = sample_data(rows=80)
    rising = pd.Series(range(100, 140), index=data.index[:40], dtype=float)
    falling = pd.Series(range(140, 100, -1), index=data.index[40:], dtype=float)
    close = pd.concat([rising, falling])
    data.loc[:, "open"] = close
    data.loc[:, "high"] = close
    data.loc[:, "low"] = close - 1
    data.loc[:, "close"] = close

    signals = EmaBreakoutStrategy(fast=2, slow=5, breakout=2).generate_signals(data)

    assert signals.max() == 1.0
    assert signals.iloc[-1] == 0.0


@dataclass(frozen=True, slots=True)
class FixedSignalStrategy:
    signals: tuple[float, ...]
    name: str = "fixed"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(self.signals[: len(data)], index=data.index, dtype=float)


def test_backtest_executes_prior_close_signal_at_next_open():
    index = pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 200.0, 100.0],
            "high": [100.0, 200.0, 100.0],
            "low": [100.0, 200.0, 100.0],
            "close": [100.0, 200.0, 100.0],
            "volume": [1.0, 1.0, 1.0],
        },
        index=index,
    )

    result = run_backtest(
        data,
        FixedSignalStrategy((1.0, 1.0, 1.0)),
        BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    assert result.trades[0].entry_time == index[1]
    assert result.trades[0].entry_price == pytest.approx(200.0)
    assert result.trades[0].exit_price == pytest.approx(100.0)
    assert result.equity.iloc[-1] == pytest.approx(5_000.0)


def test_trade_ledger_reconciles_fee_and_slippage_costs():
    index = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0] * 4,
            "low": [100.0] * 4,
            "close": [100.0] * 4,
            "volume": [1.0] * 4,
        },
        index=index,
    )

    result = run_backtest(
        data,
        FixedSignalStrategy((1.0, 0.0, 0.0, 0.0)),
        BacktestConfig(initial_cash=10_000.0, fee_bps=10.0, slippage_bps=20.0),
        symbol="BTC/USDT",
    )

    trade = result.trades[0]
    assert trade.symbol == "BTC/USDT"
    assert trade.position_size == pytest.approx(100.0)
    assert trade.gross_pnl == pytest.approx(0.0)
    assert trade.fee == pytest.approx(20.0)
    assert trade.slippage_cost == pytest.approx(40.0)
    assert trade.net_pnl == pytest.approx(-60.0)
    assert trade.return_pct == pytest.approx(-0.6)
    assert trade.holding_period == pd.Timedelta(hours=1)
    assert result.equity.iloc[-1] == pytest.approx(9_940.0)


def test_buy_and_hold_benchmark_uses_first_open_and_last_close():
    data = sample_data(rows=2)
    data.loc[data.index[0], ["open", "high", "low", "close"]] = 100.0
    data.loc[data.index[1], ["open", "high", "low", "close"]] = 150.0

    result = run_buy_and_hold(
        data,
        BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    assert result.metrics.total_return == pytest.approx(0.5)
    assert result.trades[0].entry_price == pytest.approx(100.0)
    assert result.trades[0].exit_price == pytest.approx(150.0)


def test_annualized_metrics_infer_four_hour_cadence():
    index = pd.date_range("2025-01-01", periods=2, freq="4h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 100.01],
            "high": [100.0, 100.01],
            "low": [100.0, 100.01],
            "close": [100.0, 100.01],
            "volume": [1.0, 1.0],
        },
        index=index,
    )

    result = run_buy_and_hold(
        data,
        BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    expected_cagr = (1.0001 ** (365 * 6)) - 1.0
    assert result.metrics.cagr == pytest.approx(expected_cagr)


def test_risk_sizing_limits_loss_to_configured_budget_when_stop_is_hit():
    # Given: a 1% risk budget and a stop 5% below a 100 USDT entry.
    index = pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 101.0, 100.0],
            "low": [100.0, 94.0, 100.0],
            "close": [100.0, 96.0, 100.0],
            "volume": [1_000.0, 1_000.0, 1_000.0],
        },
        index=index,
    )

    # When: the long entry immediately reaches its stop.
    result = run_backtest(
        data,
        FixedSignalStrategy((1.0, 0.0, 0.0)),
        BacktestConfig(
            initial_cash=10_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            risk_per_trade=0.01,
            stop_loss_pct=0.05,
        ),
        symbol="BTC/USDT",
    )

    # Then: the position is 20 BTC and the stop loss is exactly 100 USDT.
    trade = result.trades[0]
    assert trade.position_size == pytest.approx(20.0)
    assert trade.exit_price == pytest.approx(95.0)
    assert trade.net_pnl == pytest.approx(-100.0)
    assert result.equity.iloc[-1] == pytest.approx(9_900.0)


def test_volume_participation_spreads_large_entry_across_multiple_candles():
    # Given: each candle only permits 0.5 BTC of the desired 100 BTC position to fill.
    index = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0] * 4,
            "high": [100.0] * 4,
            "low": [100.0] * 4,
            "close": [100.0] * 4,
            "volume": [5.0] * 4,
        },
        index=index,
    )

    # When: the target stays long while participation is capped at 10% of candle volume.
    result = run_backtest(
        data,
        FixedSignalStrategy((1.0, 1.0, 1.0, 1.0)),
        BacktestConfig(
            initial_cash=10_000.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            max_volume_participation=0.10,
        ),
        symbol="BTC/USDT",
    )

    # Then: the entry is accumulated over three separate fills.
    trade = result.trades[0]
    assert trade.position_size == pytest.approx(1.5)
    assert trade.entry_fills == 3


def test_volatile_candle_adds_adverse_slippage_to_fill_price():
    # Given: a candle with a 20% high-low range and a 50% volatility multiplier.
    index = pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 110.0, 100.0],
            "low": [100.0, 90.0, 100.0],
            "close": [100.0, 100.0, 100.0],
            "volume": [1_000.0] * 3,
        },
        index=index,
    )

    # When: a long order executes during the volatile candle.
    result = run_backtest(
        data,
        FixedSignalStrategy((1.0, 0.0, 0.0)),
        BacktestConfig(
            fee_bps=0.0,
            slippage_bps=0.0,
            volatility_slippage_multiplier=0.5,
        ),
        symbol="BTC/USDT",
    )

    # Then: the entry pays 10% adverse slippage.
    assert result.trades[0].entry_fill_price == pytest.approx(110.0)
