import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.position_cap_momentum import (
    PositionCapMomentumSpec,
    PositionCapMomentumStrategy,
)


def _sample_frame(periods: int = 16) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    close = pd.Series([100.0 + offset for offset in range(periods)], index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
            "count_long_short_ratio": [1.0] * periods,
        },
        index=index,
    )


def test_position_cap_uses_only_prior_crowding_history() -> None:
    # Given: a rising market and a current crowding spike above prior observations.
    frame = _sample_frame()
    frame.loc[frame.index[8], "count_long_short_ratio"] = 10.0
    spec = PositionCapMomentumSpec(
        lookback_hours=2,
        trend_ema_hours=3,
        cap_history_hours=4,
        cap_quantile=0.90,
    )

    # When: the filtered momentum signal is generated.
    signals = PositionCapMomentumStrategy(spec=spec, timeframe_hours=1).generate_signals(frame)

    # Then: the spike is filtered even though including itself would lift the quantile cap.
    assert signals.loc[frame.index[7]] == 1.0
    assert signals.loc[frame.index[8]] == 0.0


def test_position_cap_signals_are_unchanged_when_future_rows_are_appended() -> None:
    # Given: an established signal history and extreme observations only in the future.
    frame = _sample_frame()
    spec = PositionCapMomentumSpec(
        lookback_hours=2,
        trend_ema_hours=3,
        cap_history_hours=4,
        cap_quantile=0.90,
    )
    future = _sample_frame(4).set_axis(
        pd.date_range("2025-01-01 16:00", periods=4, freq="1h", tz="UTC")
    )
    future.loc[:, "count_long_short_ratio"] = 100.0
    extended = pd.concat([frame, future])

    # When: signals are regenerated with future data present.
    original = PositionCapMomentumStrategy(spec=spec, timeframe_hours=1).generate_signals(frame)
    with_future = PositionCapMomentumStrategy(spec=spec, timeframe_hours=1).generate_signals(extended)

    # Then: every historical decision remains identical.
    pd.testing.assert_series_equal(original, with_future.loc[frame.index])
