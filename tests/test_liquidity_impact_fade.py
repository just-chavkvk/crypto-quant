import numpy as np
import pandas as pd

from quant_lab.research.liquidity_impact_fade import (
    LiquidityImpactFadeSpec,
    LiquidityImpactFadeStrategy,
)


def _market_frame(periods: int = 24) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    returns = [0.001 if offset % 2 == 0 else -0.001 for offset in range(periods - 1)]
    if periods > 12:
        returns[11] = 0.08
    values = [100.0]
    for value in returns:
        values.append(values[-1] * float(np.exp(value)))
    close = pd.Series(values, index=index, dtype=float)
    volume = pd.Series(
        [10_000.0 + 1_000.0 * offset for offset in range(periods)],
        index=index,
        dtype=float,
    )
    if periods > 12:
        volume.iloc[12] = 5.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def test_extreme_positive_price_impact_generates_short_fade() -> None:
    # Given: a large upside move occurs on tiny quote-notional after normal liquid bars.
    frame = _market_frame()
    strategy = LiquidityImpactFadeStrategy(
        LiquidityImpactFadeSpec(history_hours=8, impact_quantile=0.95, hold_hours=4),
        timeframe_hours=1,
    )

    # When: liquidity-impact fade signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: the upside impact shock is faded short for four signal bars.
    assert (signals.iloc[12:16] == -1.0).all()
    assert signals.iloc[16] == 0.0


def test_liquidity_impact_history_is_unchanged_by_future_rows() -> None:
    # Given: a fixed impact history followed by extreme future bars.
    frame = _market_frame()
    strategy = LiquidityImpactFadeStrategy(
        LiquidityImpactFadeSpec(history_hours=8, impact_quantile=0.95, hold_hours=4),
        timeframe_hours=1,
    )
    future = _market_frame(8).set_axis(
        pd.date_range("2025-01-02", periods=8, freq="1h", tz="UTC")
    )
    future.loc[:, "volume"] = 0.1

    # When: future observations are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical signals remain identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
