import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.breadth_momentum import (
    BreadthMomentumSpec,
    BreadthMomentumStrategy,
)


def _market_frame(periods: int = 16) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    close = pd.Series([100.0 + offset for offset in range(periods)], index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_breadth_gate_blocks_own_momentum_when_other_asset_loses_trend() -> None:
    # Given: own momentum stays positive while the other asset suddenly loses its EMA trend.
    own = _market_frame()
    other = own["close"].copy()
    other.loc[other.index[10:]] = 1.0
    spec = BreadthMomentumSpec(lookback_hours=2, trend_ema_hours=3)

    # When: breadth-confirmed signals are generated.
    signals = BreadthMomentumStrategy(
        spec=spec,
        timeframe_hours=1,
        other_close=other,
    ).generate_signals(own)

    # Then: own momentum is allowed before the breadth break and blocked after it.
    assert signals.loc[own.index[9]] == 1.0
    assert signals.loc[own.index[10]] == 0.0


def test_breadth_signals_are_unchanged_when_future_rows_are_appended() -> None:
    # Given: aligned own/other histories and future observations with an extreme reversal.
    own = _market_frame()
    other = own["close"].copy()
    spec = BreadthMomentumSpec(lookback_hours=2, trend_ema_hours=3)
    future = _market_frame(4).set_axis(
        pd.date_range("2025-01-01 16:00", periods=4, freq="1h", tz="UTC")
    )
    future_other = pd.Series([1.0] * 4, index=future.index, dtype=float)
    extended_own = pd.concat([own, future])
    extended_other = pd.concat([other, future_other])

    # When: signals are regenerated with future rows present.
    original = BreadthMomentumStrategy(spec, 1, other).generate_signals(own)
    with_future = BreadthMomentumStrategy(spec, 1, extended_other).generate_signals(extended_own)

    # Then: historical signals remain identical.
    pd.testing.assert_series_equal(original, with_future.loc[own.index])
