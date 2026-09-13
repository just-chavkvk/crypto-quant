import pandas as pd

from quant_lab.research.wick_rejection import (
    WickRejectionSpec,
    WickRejectionStrategy,
)


def _market_frame(periods: int = 32) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    low = pd.Series(99.0, index=index, dtype=float)
    if periods > 20:
        low.iloc[20] = 80.0
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": low,
            "close": 100.0,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_extreme_lower_wick_generates_four_hour_long_signal() -> None:
    # Given: a candle with a dominant lower wick and range far above prior median.
    frame = _market_frame()
    strategy = WickRejectionStrategy(
        WickRejectionSpec(range_history_hours=8, range_multiple=2.0, wick_share=0.5, hold_hours=4),
        timeframe_hours=1,
    )

    # When: wick-rejection signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: the event is faded long for four signal bars.
    assert (signals.iloc[20:24] == 1.0).all()
    assert signals.iloc[24] == 0.0


def test_wick_rejection_history_is_unchanged_by_future_rows() -> None:
    # Given: a fixed history followed by future extreme candles.
    frame = _market_frame()
    strategy = WickRejectionStrategy(
        WickRejectionSpec(range_history_hours=8, range_multiple=2.0, wick_share=0.5, hold_hours=4),
        timeframe_hours=1,
    )
    future = _market_frame(8).set_axis(
        pd.date_range("2025-01-02 08:00", periods=8, freq="1h", tz="UTC")
    )
    future.loc[:, "high"] = 200.0

    # When: future observations are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical signals do not change.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
