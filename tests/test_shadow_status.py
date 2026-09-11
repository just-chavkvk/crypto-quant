import pandas as pd

from quant_lab.research.shadow_status import ShadowState, classify_shadow


def _shadow_frame(trades: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset": ["BTC_1h", "ETH_1h", "BTC_4h", "ETH_4h"],
            "total_return": [0.01, 0.02, 0.03, 0.04],
            "sharpe_ratio": [0.1, 0.2, 0.3, 0.4],
            "number_of_trades": [trades] * 4,
        }
    )


def test_shadow_is_ready_only_after_all_four_datasets_have_ten_trades() -> None:
    # Given: all four frozen datasets are profitable but initially have too few trades.
    tracking = _shadow_frame(9)
    ready = _shadow_frame(10)

    # When: promotion-readiness is classified from the accumulated shadow metrics.
    tracking_state = classify_shadow(tracking)
    ready_state = classify_shadow(ready)

    # Then: ten trades on every dataset is required before paper review can begin.
    assert tracking_state is ShadowState.TRACKING
    assert ready_state is ShadowState.READY_FOR_PAPER_REVIEW
