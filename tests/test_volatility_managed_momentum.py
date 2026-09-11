import pandas as pd

from quant_lab.research.volatility_managed_momentum import (
    VolatilityManagedMomentumSpec,
    VolatilityManagedMomentumStrategy,
)


def _market_frame(periods: int = 20) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    values = [100.0]
    for offset in range(1, periods):
        multiplier = 1.01 if offset % 2 == 0 else 1.005
        values.append(values[-1] * multiplier)
    close = pd.Series(values, index=index, dtype=float)
    if periods > 10:
        close.iloc[10] = close.iloc[9] * 1.50
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_high_recent_volatility_blocks_otherwise_positive_momentum() -> None:
    # Given: a smooth uptrend followed by one abrupt price jump.
    frame = _market_frame()
    strategy = VolatilityManagedMomentumStrategy(
        VolatilityManagedMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            recent_vol_hours=2,
            vol_history_hours=4,
        ),
        timeframe_hours=1,
    )

    # When: volatility-managed momentum signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: smooth momentum is allowed before the shock and blocked on the shock bar.
    assert signals.iloc[9] == 1.0
    assert signals.iloc[10] == 0.0


def test_volatility_managed_momentum_has_no_future_dependency() -> None:
    # Given: an established history plus later extreme prices.
    frame = _market_frame()
    strategy = VolatilityManagedMomentumStrategy(
        VolatilityManagedMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            recent_vol_hours=2,
            vol_history_hours=4,
        ),
        timeframe_hours=1,
    )
    future = _market_frame(4).set_axis(
        pd.date_range("2025-01-01 20:00", periods=4, freq="1h", tz="UTC")
    )
    future.loc[:, "close"] = [1000.0, 100.0, 1500.0, 50.0]

    # When: future rows are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical signals remain identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
