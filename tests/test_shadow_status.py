from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK
import pytest

from quant_lab.research import shadow_status
from quant_lab.research.shadow_status import ShadowState, classify_shadow, run_shadow_status


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


def test_shadow_status_tracks_dual_confirmed_family(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: each frozen research family returns the same empty future-shadow frame.
    empty = pd.DataFrame()

    def position_runner(_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
        return empty, empty

    def breadth_runner(_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return empty, empty, empty

    def dual_runner(_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return empty, empty, empty

    def latest_common_bar(_root: Path) -> pd.Timestamp:
        return pd.Timestamp("2026-09-11 08:00:00", tz="UTC")

    monkeypatch.setattr(shadow_status, "run_position_cap_momentum", position_runner)
    monkeypatch.setattr(shadow_status, "run_breadth_momentum", breadth_runner)
    monkeypatch.setattr(shadow_status, "run_dual_confirmed_momentum", dual_runner, raising=False)
    monkeypatch.setattr(shadow_status, "_latest_common_bar", latest_common_bar)

    # When: common shadow status is generated.
    status = run_shadow_status(tmp_path)

    # Then: the new composite is tracked beside the two existing SHADOW families.
    assert set(status["family"].astype(str)) == {
        "global_position_cap_momentum",
        "breadth_confirmed_momentum",
        "dual_confirmed_momentum",
    }
