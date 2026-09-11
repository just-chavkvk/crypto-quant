from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.data.shadow_refresh import refresh_shadow_data
from quant_lab.research.breadth_momentum import run_research as run_breadth_momentum
from quant_lab.research.dual_confirmed_momentum import (
    run_research as run_dual_confirmed_momentum,
)
from quant_lab.research.position_cap_momentum import (
    load_research_datasets,
)
from quant_lab.research.position_cap_momentum import (
    run_research as run_position_cap_momentum,
)

SHADOW_START: Final = pd.Timestamp("2026-09-11 00:00:00", tz="UTC")
EXPECTED_DATASETS: Final = frozenset({"BTC_1h", "ETH_1h", "BTC_4h", "ETH_4h"})


class ShadowState(StrEnum):
    WAITING_FOR_DATA = "WAITING_FOR_DATA"
    TRACKING = "TRACKING"
    READY_FOR_PAPER_REVIEW = "READY_FOR_PAPER_REVIEW"


@dataclass(frozen=True, slots=True)
class ShadowFamilyStatus:
    family: str
    state: ShadowState
    latest_common_bar: str
    evaluated_datasets: int
    minimum_trades: int


def classify_shadow(frame: pd.DataFrame) -> ShadowState:
    if frame.empty:
        return ShadowState.WAITING_FOR_DATA
    required = {"dataset", "total_return", "sharpe_ratio", "number_of_trades"}
    missing = required.difference(frame.columns)
    if missing:
        return ShadowState.TRACKING
    datasets = set(frame["dataset"].astype(str).tolist())
    if datasets != set(EXPECTED_DATASETS) or len(frame) != len(EXPECTED_DATASETS):
        return ShadowState.TRACKING
    ready = (
        (frame["total_return"].astype(float) > 0.0).all()
        and (frame["sharpe_ratio"].astype(float) > 0.0).all()
        and (frame["number_of_trades"].astype(int) >= 10).all()
    )
    return ShadowState.READY_FOR_PAPER_REVIEW if ready else ShadowState.TRACKING


def _latest_common_bar(root: Path) -> pd.Timestamp:
    datasets = load_research_datasets(root)
    return min(pd.DatetimeIndex(dataset.data.index).max() for dataset in datasets)


def _family_status(
    family: str,
    shadow: pd.DataFrame,
    latest_common_bar: pd.Timestamp,
) -> ShadowFamilyStatus:
    state = classify_shadow(shadow)
    if latest_common_bar < SHADOW_START:
        state = ShadowState.WAITING_FOR_DATA
    minimum_trades = (
        0 if shadow.empty else int(shadow["number_of_trades"].astype(int).min())
    )
    evaluated_datasets = 0 if shadow.empty else int(shadow["dataset"].nunique())
    return ShadowFamilyStatus(
        family=family,
        state=state,
        latest_common_bar=latest_common_bar.isoformat(),
        evaluated_datasets=evaluated_datasets,
        minimum_trades=minimum_trades,
    )


def run_shadow_status(root: Path) -> pd.DataFrame:
    _, position_shadow = run_position_cap_momentum(root)
    _, _, breadth_shadow = run_breadth_momentum(root)
    _, _, dual_shadow = run_dual_confirmed_momentum(root)
    position_shadow.to_csv(root / "position_cap_momentum_shadow.csv", index=False)
    breadth_shadow.to_csv(root / "breadth_momentum_shadow.csv", index=False)
    dual_shadow.to_csv(root / "dual_confirmed_momentum_shadow.csv", index=False)
    latest_common_bar = _latest_common_bar(root)
    statuses = (
        _family_status("global_position_cap_momentum", position_shadow, latest_common_bar),
        _family_status("breadth_confirmed_momentum", breadth_shadow, latest_common_bar),
        _family_status("dual_confirmed_momentum", dual_shadow, latest_common_bar),
    )
    frame = pd.DataFrame([asdict(status) for status in statuses])
    frame.to_csv(root / "shadow_status.csv", index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate frozen strategies on forward shadow data")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    _ = parser.add_argument(
        "--refresh",
        action="store_true",
        help="append complete Binance USD-M bars and positioning before evaluation",
    )
    args = parser.parse_args()
    root: Path = args.root
    if args.refresh:
        for result in refresh_shadow_data(root):
            print(result)
    status = run_shadow_status(root)
    print(status.to_string(index=False))


if __name__ == "__main__":
    main()
