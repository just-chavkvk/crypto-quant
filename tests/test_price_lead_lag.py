import numpy as np
import pandas as pd

from quant_lab.research.price_lead_lag import (
    PriceLeadLagSpec,
    generate_price_lead_lag_events,
)


def _prices_from_log_returns(returns: list[float], start: float) -> list[float]:
    values = [start]
    for value in returns:
        values.append(values[-1] * float(np.exp(value)))
    return values


def _lead_lag_frame() -> pd.DataFrame:
    btc_returns = [0.001, -0.001, 0.001, -0.001, 0.001, -0.001, 0.05, 0.001, -0.001]
    eth_returns = [0.001, -0.001, 0.001, -0.001, 0.001, -0.001, 0.01, 0.001, -0.001]
    index = pd.date_range("2025-01-01", periods=len(btc_returns) + 1, freq="1h", tz="UTC")
    eth_close = _prices_from_log_returns(eth_returns, 200.0)
    return pd.DataFrame(
        {
            "btc_close": _prices_from_log_returns(btc_returns, 100.0),
            "eth_close": eth_close,
            "eth_open": eth_close,
        },
        index=index,
    )


def test_btc_shock_with_lagging_same_direction_eth_generates_follow_event() -> None:
    # Given: a large BTC upside shock while ETH moves the same way by less than half as much.
    frame = _lead_lag_frame()
    spec = PriceLeadLagSpec(zscore_window_hours=4, shock_z_threshold=2.0)

    # When: the preregistered BTC-to-ETH price lead-lag signal is generated.
    events = generate_price_lead_lag_events(frame, spec)

    # Then: ETH follows BTC on the shock bar's direction.
    assert events.loc[frame.index[7]] == 1.0


def test_price_lead_lag_events_do_not_change_when_future_rows_are_appended() -> None:
    # Given: a fixed history plus later observations that contain an extreme move.
    frame = _lead_lag_frame()
    spec = PriceLeadLagSpec(zscore_window_hours=4, shock_z_threshold=2.0)
    future_index = pd.date_range(frame.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    future = pd.DataFrame(
        {
            "btc_close": [500.0, 50.0, 700.0],
            "eth_close": [220.0, 180.0, 260.0],
            "eth_open": [220.0, 180.0, 260.0],
        },
        index=future_index,
    )

    # When: events are recalculated with future rows present.
    original = generate_price_lead_lag_events(frame, spec)
    with_future = generate_price_lead_lag_events(pd.concat([frame, future]), spec)

    # Then: the historical event series is unchanged.
    pd.testing.assert_series_equal(original, with_future.loc[frame.index])
