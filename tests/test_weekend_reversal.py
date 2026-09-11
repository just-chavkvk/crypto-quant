import pandas as pd

from quant_lab.research.weekend_reversal import (
    WeekendReversalSpec,
    WeekendReversalStrategy,
)


def _market_frame(periods: int = 96) -> pd.DataFrame:
    index = pd.date_range("2025-01-03 00:00", periods=periods, freq="1h", tz="UTC")
    close = pd.Series(100.0, index=index, dtype=float)
    close.iloc[71] = 110.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def test_positive_weekend_move_generates_monday_short_for_24_hours() -> None:
    # Given: the weekend ends 10% above its level 48 hours earlier.
    frame = _market_frame()
    strategy = WeekendReversalStrategy(WeekendReversalSpec(), timeframe_hours=1)

    # When: calendar reversal targets are generated from closed bars.
    signals = strategy.generate_signals(frame)

    # Then: Sunday 23:00 starts a short signal that persists for 24 signal bars.
    decision = pd.Timestamp("2025-01-05 23:00", tz="UTC")
    assert signals.loc[decision] == -1.0
    assert (signals.loc[decision : decision + pd.Timedelta(hours=23)] == -1.0).all()
    assert signals.loc[decision + pd.Timedelta(hours=24)] == 0.0


def test_weekend_reversal_history_is_unchanged_by_future_rows() -> None:
    # Given: a fixed history and later prices that move sharply.
    frame = _market_frame()
    strategy = WeekendReversalStrategy(WeekendReversalSpec(), timeframe_hours=1)
    future_index = pd.date_range(frame.index[-1] + pd.Timedelta(hours=1), periods=24, freq="1h")
    future = pd.DataFrame(
        {"open": 500.0, "high": 500.0, "low": 500.0, "close": 500.0, "volume": 1_000.0},
        index=future_index,
    )

    # When: signals are recalculated with future rows appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: every historical signal is identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
