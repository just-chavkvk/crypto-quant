import pandas as pd
import pytest

from quant_lab.research.cross_asset_lead_lag import (
    CrossAssetLeadLagSpec,
    evaluate_cross_asset_events,
    generate_cross_asset_events,
)


def _sample_frame(periods: int = 16) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    ratio = [1.0 + 0.01 * ((offset % 5) - 2) for offset in range(periods)]
    return pd.DataFrame(
        {
            "btc_global_ratio": ratio,
            "btc_oi_contracts": [1_000.0 - offset for offset in range(periods)],
            "btc_close": [100.0 + offset for offset in range(periods)],
            "eth_open": [200.0 + offset for offset in range(periods)],
        },
        index=index,
    )


def test_future_rows_do_not_change_historical_cross_asset_events():
    frame = _sample_frame()
    spec = CrossAssetLeadLagSpec(
        lookback_hours=2,
        zscore_window_hours=4,
        velocity_z_threshold=0.1,
        acceleration_z_threshold=0.1,
    )
    extended = pd.concat([frame, _sample_frame(4).set_axis(pd.date_range("2025-01-01 16:00", periods=4, freq="1h", tz="UTC"))])

    original = generate_cross_asset_events(frame, spec)
    with_future = generate_cross_asset_events(extended, spec).loc[frame.index]

    pd.testing.assert_series_equal(original, with_future)


def test_cross_asset_evaluation_enters_on_next_eth_open():
    frame = _sample_frame(periods=5)
    frame.loc[:, "eth_open"] = [100.0, 110.0, 121.0, 121.0, 121.0]
    events = pd.Series([1.0, 0.0, 0.0, 0.0, 0.0], index=frame.index, dtype=float)
    spec = CrossAssetLeadLagSpec(hold_hours=1, fee_bps=0.0, slippage_bps=0.0)

    result = evaluate_cross_asset_events(
        frame,
        events,
        spec,
        start="2025-01-01",
        end="2025-01-02",
    )

    assert result.number_of_trades == 1
    assert result.total_return == pytest.approx(0.1)
