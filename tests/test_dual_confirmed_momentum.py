import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.dual_confirmed_momentum import DualConfirmedMomentumStrategy


def _market(close_values: list[float], positioning: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(close_values), freq="1h", tz="UTC")
    close = pd.Series(close_values, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1_000.0] * len(close),
            "count_long_short_ratio": positioning,
        },
        index=index,
    )


def test_position_cap_blocks_signal_when_breadth_is_positive() -> None:
    # Given: both assets trend up but the target asset becomes excessively crowded.
    own = _market(
        [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
        [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 3.0],
    )
    other_close = pd.Series(
        [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
        index=own.index,
        dtype=float,
    )
    strategy = DualConfirmedMomentumStrategy(
        timeframe_hours=1,
        other_close=other_close,
        lookback_hours=2,
        trend_ema_hours=3,
        cap_history_hours=4,
        cap_quantile=0.90,
    )

    # When: the dual-confirmed signal is generated.
    signals = strategy.generate_signals(own)

    # Then: the final bar is blocked by the position cap despite positive breadth.
    assert signals.iloc[-1] == 0.0


def test_dual_confirmed_history_is_unchanged_by_future_rows() -> None:
    # Given: a stable dual-confirmed uptrend and extreme future observations.
    own = _market([100.0 + i for i in range(10)], [1.0] * 10)
    other = pd.Series([100.0 + i for i in range(10)], index=own.index, dtype=float)
    strategy = DualConfirmedMomentumStrategy(
        timeframe_hours=1,
        other_close=other,
        lookback_hours=2,
        trend_ema_hours=3,
        cap_history_hours=4,
        cap_quantile=0.90,
    )
    future_index = pd.date_range(own.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    future = _market([300.0, 50.0, 400.0], [5.0, 0.2, 6.0]).set_axis(future_index)
    extended_other = pd.concat(
        [other, pd.Series([300.0, 50.0, 400.0], index=future_index, dtype=float)]
    )

    # When: future observations are appended.
    original = strategy.generate_signals(own)
    extended = DualConfirmedMomentumStrategy(
        timeframe_hours=1,
        other_close=extended_other,
        lookback_hours=2,
        trend_ema_hours=3,
        cap_history_hours=4,
        cap_quantile=0.90,
    ).generate_signals(pd.concat([own, future]))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, extended.loc[own.index])
