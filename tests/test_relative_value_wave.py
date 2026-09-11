import pandas as pd  # noqa: PANDAS_OK
import pytest

from quant_lab.research.relative_value import (
    RelativeValueSpec,
    evaluate_pair_events,
    generate_premium_crowding_events,
)


def _pair_frame(periods: int = 10) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "btc_open": [100.0] * periods,
            "eth_open": [200.0] * periods,
            "btc_close": [100.0 + offset for offset in range(periods)],
            "eth_close": [200.0 + 2.0 * offset for offset in range(periods)],
            "btc_premium_close": [0.0] * periods,
            "eth_premium_close": [0.0] * periods,
            "btc_taker_ratio": [1.0] * periods,
            "eth_taker_ratio": [1.0] * periods,
            "btc_oi_value": [1_000.0] * periods,
            "eth_oi_value": [1_000.0] * periods,
            "btc_global_ratio": [1.0] * periods,
            "btc_top_position_ratio": [1.0] * periods,
            "btc_oi_contracts": [1_000.0] * periods,
        },
        index=index,
    )


def test_pair_evaluation_enters_next_open_and_uses_equal_leg_weights() -> None:
    # Given: ETH gains 20% while BTC gains 10% after the next-bar entry.
    frame = _pair_frame(periods=4)
    frame.loc[:, "eth_open"] = [200.0, 200.0, 240.0, 240.0]
    frame.loc[:, "btc_open"] = [100.0, 100.0, 110.0, 110.0]
    events = pd.Series([1.0, 0.0, 0.0, 0.0], index=frame.index, dtype=float)
    spec = RelativeValueSpec(hold_hours=1, fee_bps=0.0, slippage_bps=0.0)

    # When: the pair trade is evaluated.
    result = evaluate_pair_events(
        frame,
        events,
        spec,
        start="2025-01-01",
        end="2025-01-02",
    )

    # Then: long ETH / short BTC earns half of the 10-point relative return gap.
    assert result.number_of_trades == 1
    assert result.total_return == pytest.approx(0.05)


def test_premium_crowding_events_do_not_change_when_future_rows_are_appended() -> None:
    # Given: a short-window synthetic frame and a preregistered-style premium signal.
    frame = _pair_frame(periods=12)
    frame.loc[:, "eth_premium_close"] = [
        0.0,
        0.1,
        -0.1,
        0.0,
        0.1,
        -0.1,
        0.0,
        0.1,
        2.0,
        2.1,
        2.2,
        2.3,
    ]
    frame.loc[:, "eth_oi_value"] = [1_000.0 + 20.0 * offset for offset in range(12)]
    frame.loc[:, "eth_close"] = [200.0 + 4.0 * offset for offset in range(12)]
    spec = RelativeValueSpec(
        lookback_hours=2,
        zscore_window_hours=4,
        z_threshold=0.5,
    )
    future = _pair_frame(periods=3).set_axis(
        pd.date_range("2025-01-01 12:00", periods=3, freq="1h", tz="UTC")
    )
    future.loc[:, "eth_premium_close"] = 100.0
    extended = pd.concat([frame, future])

    # When: events are generated before and after appending future observations.
    original = generate_premium_crowding_events(frame, spec)
    with_future = generate_premium_crowding_events(extended, spec).loc[frame.index]

    # Then: historical event decisions are unchanged.
    pd.testing.assert_series_equal(original, with_future)
