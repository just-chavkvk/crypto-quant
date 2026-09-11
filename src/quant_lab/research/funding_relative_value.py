from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.relative_value import (
    PairEvaluation,
    RelativeValueSpec,
    evaluate_pair_events,
    load_relative_value_hourly,
)


class FundingResearchError(ValueError):
    pass


class FundingVariant(StrEnum):
    PURE = "funding_diff_fade"
    PREMIUM_CONFIRMED = "funding_premium_confirmed_fade"


@dataclass(frozen=True, slots=True)
class FundingRelativeSpec:
    zscore_events: int = 90
    z_threshold: float = 2.0
    hold_hours: int = 1
    variant: FundingVariant = FundingVariant.PURE

    def __post_init__(self) -> None:
        if self.zscore_events <= 1 or self.hold_hours <= 0:
            raise FundingResearchError("z-score event window and hold must be positive")
        if self.z_threshold <= 0.0:
            raise FundingResearchError("z-score threshold must be positive")


@dataclass(frozen=True, slots=True)
class FundingCandidate:
    variant: FundingVariant
    hold_hours: int


def candidate_catalog() -> tuple[FundingCandidate, ...]:
    return (
        FundingCandidate(FundingVariant.PURE, 1),
        FundingCandidate(FundingVariant.PURE, 4),
        FundingCandidate(FundingVariant.PREMIUM_CONFIRMED, 1),
        FundingCandidate(FundingVariant.PREMIUM_CONFIRMED, 4),
    )


def _read_funding(path: Path, output_column: str) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=["funding_rate"])
    timestamp = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True)).floor("h")
    frame.index = timestamp
    frame.index.name = "timestamp"
    frame = frame.sort_index()
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    return frame.rename(columns={"funding_rate": output_column})[[output_column]]


def load_funding_relative_hourly(
    root: Path,
    *,
    start: str = "2022-01-01",
    end: str = "2026-09-01",
) -> pd.DataFrame:
    frame = load_relative_value_hourly(root, start=start, end=end)
    btc = _read_funding(root / "BTC_USDT_funding_events.parquet", "btc_funding")
    eth = _read_funding(root / "ETH_USDT_funding_events.parquet", "eth_funding")
    return frame.join(btc).join(eth)


def _prior_event_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0).mask(lambda value: value <= 0.0)
    return (series - mean) / std


def generate_funding_events(frame: pd.DataFrame, spec: FundingRelativeSpec) -> pd.Series:
    required = {"btc_funding", "eth_funding", "btc_premium_close", "eth_premium_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise FundingResearchError(f"missing required columns: {sorted(missing)}")
    funding_diff = (frame["eth_funding"] - frame["btc_funding"]).dropna()
    funding_z = _prior_event_zscore(funding_diff, spec.zscore_events)
    direction = pd.Series(
        np.sign(funding_diff.to_numpy(dtype=float)), index=funding_diff.index, dtype=float
    )
    eligible = funding_z.notna() & (funding_z.abs() >= spec.z_threshold) & (direction != 0.0)
    if spec.variant is FundingVariant.PREMIUM_CONFIRMED:
        premium_spread = (
            frame.loc[funding_diff.index, "eth_premium_close"]
            - frame.loc[funding_diff.index, "btc_premium_close"]
        )
        premium_direction = pd.Series(
            np.sign(premium_spread.to_numpy(dtype=float)), index=funding_diff.index, dtype=float
        )
        eligible &= premium_spread.notna() & (premium_direction == direction)
    events = pd.Series(0.0, index=frame.index, dtype=float)
    event_index = funding_diff.index[eligible]
    events.loc[event_index] = -direction.loc[event_index]
    return events


def _evaluation_columns(prefix: str, evaluation: PairEvaluation) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def _evaluate_candidate(
    frame: pd.DataFrame,
    candidate: FundingCandidate,
) -> dict[str, float | int | bool | str | None]:
    signal_spec = FundingRelativeSpec(hold_hours=candidate.hold_hours, variant=candidate.variant)
    execution_spec = RelativeValueSpec(hold_hours=candidate.hold_hours)
    events = generate_funding_events(frame, signal_spec)
    discovery = evaluate_pair_events(
        frame, events, execution_spec, start="2022-01-01", end="2024-01-01"
    )
    validation = evaluate_pair_events(
        frame, events, execution_spec, start="2024-01-01", end="2026-01-01"
    )
    pre_pass = (
        discovery.total_return is not None
        and discovery.sharpe_ratio is not None
        and validation.total_return is not None
        and validation.sharpe_ratio is not None
        and discovery.total_return > 0.0
        and discovery.sharpe_ratio > 0.0
        and discovery.number_of_trades >= 10
        and validation.total_return > 0.0
        and validation.sharpe_ratio > 0.0
        and validation.number_of_trades >= 10
    )
    score = (
        float(validation.sharpe_ratio + 0.25 * validation.total_return)
        if validation.sharpe_ratio is not None and validation.total_return is not None
        else float("-inf")
    )
    return {
        "variant": candidate.variant.value,
        "hold_hours": candidate.hold_hours,
        "pre_holdout_pass": pre_pass,
        "pre_holdout_score": score,
        "raw_events": int((events != 0.0).sum()),
        **_evaluation_columns("discovery", discovery),
        **_evaluation_columns("validation", validation),
    }


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = load_funding_relative_hourly(root)
    summary = pd.DataFrame([_evaluate_candidate(frame, candidate) for candidate in candidate_catalog()])
    summary = summary.sort_values(
        ["pre_holdout_pass", "pre_holdout_score", "hold_hours", "variant"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)
    champion = summary.iloc[0]
    candidate = FundingCandidate(FundingVariant(str(champion["variant"])), int(champion["hold_hours"]))
    signal_spec = FundingRelativeSpec(hold_hours=candidate.hold_hours, variant=candidate.variant)
    execution_spec = RelativeValueSpec(hold_hours=candidate.hold_hours)
    events = generate_funding_events(frame, signal_spec)
    stress = evaluate_pair_events(
        frame, events, execution_spec, start="2026-01-01", end="2026-09-01"
    )
    stress_frame = pd.DataFrame(
        [
            {
                "variant": candidate.variant.value,
                "hold_hours": candidate.hold_hours,
                "pre_holdout_pass": bool(champion["pre_holdout_pass"]),
                **_evaluation_columns("stress", stress),
            }
        ]
    )
    zero_cost_rows: list[dict[str, float | int | str | None]] = []
    for period, start, end in (
        ("discovery", "2022-01-01", "2024-01-01"),
        ("validation", "2024-01-01", "2026-01-01"),
    ):
        evaluation = evaluate_pair_events(
            frame,
            events,
            execution_spec,
            start=start,
            end=end,
            fee_bps=0.0,
            slippage_bps=0.0,
        )
        zero_cost_rows.append({"period": period, **asdict(evaluation)})
    yearly_rows: list[dict[str, float | int | None]] = []
    for year in (2022, 2023, 2024, 2025, 2026):
        year_end = "2026-09-01" if year == 2026 else f"{year + 1}-01-01"
        evaluation = evaluate_pair_events(
            frame,
            events,
            execution_spec,
            start=f"{year}-01-01",
            end=year_end,
        )
        yearly_rows.append({"year": year, **asdict(evaluation)})
    return summary, stress_frame, pd.DataFrame(zero_cost_rows), pd.DataFrame(yearly_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered funding relative-value wave")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    summary, stress, zero_cost, yearly = run_research(root)
    summary.to_csv(root / "funding_relative_value_pre_stress.csv", index=False)
    stress.to_csv(root / "funding_relative_value_champion_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "funding_relative_value_champion_zero_cost.csv", index=False)
    yearly.to_csv(root / "funding_relative_value_champion_yearly.csv", index=False)
    print("pre-stress")
    print(summary.to_string(index=False))
    print("champion stress")
    print(stress.to_string(index=False))
    print("champion zero cost")
    print(zero_cost.to_string(index=False))
    print("champion yearly")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    main()
