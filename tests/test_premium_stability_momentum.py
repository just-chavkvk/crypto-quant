import pandas as pd

from quant_lab.research.premium_stability_momentum import (
    PremiumStabilityMomentumSpec,
    PremiumStabilityMomentumStrategy,
)


def _market(premium: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(premium), freq="1h", tz="UTC")
    close = pd.Series([100.0 + offset for offset in range(len(premium))], index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1_000.0] * len(premium),
            "premium_close": premium,
        },
        index=index,
    )


def test_unstable_recent_premium_blocks_positive_momentum() -> None:
    # Given: price rises while recent premium becomes much more volatile than its history.
    frame = _market([0.001, 0.001, 0.001, 0.001, 0.001, -0.05, 0.05, -0.05, 0.05])
    strategy = PremiumStabilityMomentumStrategy(
        PremiumStabilityMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            premium_vol_hours=2,
            premium_history_hours=4,
        ),
        timeframe_hours=1,
    )

    # When: premium-stability confirmed momentum signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: the final positive momentum observation is blocked by unstable premium.
    assert signals.iloc[-1] == 0.0


def test_premium_stability_history_is_unchanged_by_future_rows() -> None:
    # Given: a rising market with stable premium followed by extreme future premium values.
    frame = _market([0.001] * 10)
    strategy = PremiumStabilityMomentumStrategy(
        PremiumStabilityMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            premium_vol_hours=2,
            premium_history_hours=4,
        ),
        timeframe_hours=1,
    )
    future = _market([0.2, -0.2, 0.3]).set_axis(
        pd.date_range(frame.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    )

    # When: future observations are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
