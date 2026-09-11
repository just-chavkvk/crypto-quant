import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.relative_strength_rotation import (
    RotationSpec,
    generate_rotation_targets,
)


def _rotation_frame(periods: int = 32) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    btc_close = pd.Series([100.0 + offset for offset in range(periods)], index=index)
    eth_close = pd.Series([200.0 + 0.25 * offset for offset in range(periods)], index=index)
    return pd.DataFrame(
        {
            "btc_open": btc_close,
            "btc_close": btc_close,
            "eth_open": eth_close,
            "eth_close": eth_close,
        },
        index=index,
    )


def test_rotation_target_changes_only_on_open_after_daily_signal() -> None:
    # Given: BTC has stronger momentum at the first completed 23:00 UTC decision bar.
    frame = _rotation_frame()
    spec = RotationSpec(momentum_hours=2, trend_ema_hours=3)

    # When: execution targets are generated for the 1h implementation.
    targets = generate_rotation_targets(frame, spec, timeframe_hours=1)

    # Then: the decision bar remains cash and BTC becomes active at the next 00:00 open.
    assert targets.loc[pd.Timestamp("2025-01-01 23:00", tz="UTC")] == 0.0
    assert targets.loc[pd.Timestamp("2025-01-02 00:00", tz="UTC")] == 1.0


def test_rotation_targets_are_unchanged_when_future_rows_are_appended() -> None:
    # Given: a completed rotation history and future rows with extreme ETH strength.
    frame = _rotation_frame()
    spec = RotationSpec(momentum_hours=2, trend_ema_hours=3)
    future = _rotation_frame(8).set_axis(
        pd.date_range("2025-01-02 08:00", periods=8, freq="1h", tz="UTC")
    )
    future.loc[:, "eth_close"] = [1_000.0 + offset for offset in range(8)]
    future.loc[:, "eth_open"] = future["eth_close"]
    extended = pd.concat([frame, future])

    # When: targets are recalculated with future observations present.
    original = generate_rotation_targets(frame, spec, timeframe_hours=1)
    with_future = generate_rotation_targets(extended, spec, timeframe_hours=1)

    # Then: all historical execution targets stay identical.
    pd.testing.assert_series_equal(original, with_future.loc[frame.index])
