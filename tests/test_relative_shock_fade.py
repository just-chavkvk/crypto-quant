import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.relative_shock_fade import (
    RelativeShockSpec,
    generate_relative_shock_events,
)


def _shock_frame(periods: int = 20) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    btc = pd.Series([100.0 + offset for offset in range(periods)], index=index)
    eth = pd.Series([200.0 + 2.0 * offset for offset in range(periods)], index=index)
    return pd.DataFrame({"btc_close": btc, "eth_close": eth}, index=index)


def test_positive_eth_relative_shock_generates_short_eth_pair_event() -> None:
    # Given: a stable pair followed by an extreme ETH-only upside move.
    frame = _shock_frame()
    for offset, delta in zip(range(6, 12), (0.0, 0.5, -0.4, 0.7, -0.3, 0.2), strict=True):
        frame.loc[frame.index[offset], "eth_close"] += delta
    frame.loc[frame.index[12], "eth_close"] = 400.0
    spec = RelativeShockSpec(
        relative_lookback_hours=2,
        zscore_window_hours=4,
        correlation_window_hours=4,
        correlation_threshold=-1.0,
        z_threshold=0.5,
    )

    # When: the relative-shock fade signal is generated.
    events = generate_relative_shock_events(frame, spec)

    # Then: the positive ETH relative shock is faded with short ETH / long BTC.
    assert events.loc[frame.index[12]] == -1.0


def test_relative_shock_events_are_unchanged_when_future_rows_are_appended() -> None:
    # Given: a complete history and future observations containing extreme dislocations.
    frame = _shock_frame()
    spec = RelativeShockSpec(
        relative_lookback_hours=2,
        zscore_window_hours=4,
        correlation_window_hours=4,
        correlation_threshold=-1.0,
        z_threshold=0.5,
    )
    future = _shock_frame(4).set_axis(
        pd.date_range("2025-01-01 20:00", periods=4, freq="1h", tz="UTC")
    )
    future.loc[:, "eth_close"] = 10_000.0
    extended = pd.concat([frame, future])

    # When: signals are recalculated with future rows available.
    original = generate_relative_shock_events(frame, spec)
    with_future = generate_relative_shock_events(extended, spec)

    # Then: historical events remain identical.
    pd.testing.assert_series_equal(original, with_future.loc[frame.index])
