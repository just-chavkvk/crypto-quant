import numpy as np
import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.funding_relative_value import (
    FundingRelativeSpec,
    FundingVariant,
    generate_funding_events,
)


def _funding_frame(periods: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "btc_funding": np.nan,
            "eth_funding": np.nan,
            "btc_premium_close": 0.0,
            "eth_premium_close": 0.0,
        },
        index=index,
    )


def test_funding_events_are_unchanged_when_future_settlements_are_appended() -> None:
    # Given: six funding settlements with a short prior-only z-score window.
    frame = _funding_frame(48)
    funding_offsets = [0, 8, 16, 24, 32, 40]
    eth_rates = [0.0, 0.001, -0.001, 0.0005, 0.004, -0.004]
    btc_funding = pd.Series(np.nan, index=frame.index, dtype=float)
    eth_funding = pd.Series(np.nan, index=frame.index, dtype=float)
    for offset, rate in zip(funding_offsets, eth_rates, strict=True):
        btc_funding.loc[frame.index[offset]] = 0.0
        eth_funding.loc[frame.index[offset]] = rate
    frame = frame.assign(btc_funding=btc_funding, eth_funding=eth_funding)
    spec = FundingRelativeSpec(
        zscore_events=3,
        z_threshold=0.5,
        variant=FundingVariant.PURE,
    )
    future = _funding_frame(16).set_axis(
        pd.date_range("2025-01-03", periods=16, freq="1h", tz="UTC")
    )
    future_btc = pd.Series(np.nan, index=future.index, dtype=float)
    future_eth = pd.Series(np.nan, index=future.index, dtype=float)
    future_btc.loc[future.index[0]] = 0.0
    future_eth.loc[future.index[0]] = 0.1
    future = future.assign(btc_funding=future_btc, eth_funding=future_eth)
    extended = pd.concat([frame, future])

    # When: funding events are generated before and after future settlements are appended.
    original = generate_funding_events(frame, spec)
    with_future = generate_funding_events(extended, spec).loc[frame.index]

    # Then: at least one signal exists and every historical decision is identical.
    assert bool((original != 0.0).any())
    pd.testing.assert_series_equal(original, with_future)
