from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.relative_value import (
    PairEvaluation,
    PositionSource,
    RelativeValueSpec,
    evaluate_pair_events,
    generate_position_catchup_events,
    generate_premium_crowding_events,
    generate_taker_chase_events,
    load_relative_value_hourly,
)


class RelativeValueFamily(StrEnum):
    POSITION_CATCHUP = "position_catchup"
    PREMIUM_CROWDING_FADE = "premium_crowding_fade"
    TAKER_CHASE_FADE = "taker_chase_fade"


class RelativeValueResearchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RelativeValueCandidate:
    family: RelativeValueFamily
    variant: str
    hold_hours: int
    position_source: PositionSource | None = None


def candidate_catalog() -> tuple[RelativeValueCandidate, ...]:
    return (
        RelativeValueCandidate(RelativeValueFamily.POSITION_CATCHUP, "global", 1, PositionSource.GLOBAL),
        RelativeValueCandidate(RelativeValueFamily.POSITION_CATCHUP, "global", 4, PositionSource.GLOBAL),
        RelativeValueCandidate(
            RelativeValueFamily.POSITION_CATCHUP,
            "top_position",
            1,
            PositionSource.TOP_POSITION,
        ),
        RelativeValueCandidate(
            RelativeValueFamily.POSITION_CATCHUP,
            "top_position",
            4,
            PositionSource.TOP_POSITION,
        ),
        RelativeValueCandidate(RelativeValueFamily.PREMIUM_CROWDING_FADE, "premium_oi", 1),
        RelativeValueCandidate(RelativeValueFamily.PREMIUM_CROWDING_FADE, "premium_oi", 4),
        RelativeValueCandidate(RelativeValueFamily.TAKER_CHASE_FADE, "taker", 1),
        RelativeValueCandidate(RelativeValueFamily.TAKER_CHASE_FADE, "taker", 4),
    )


def _candidate_events(
    frame: pd.DataFrame,
    candidate: RelativeValueCandidate,
    spec: RelativeValueSpec,
) -> pd.Series:
    if candidate.family is RelativeValueFamily.POSITION_CATCHUP:
        if candidate.position_source is None:
            raise RelativeValueResearchError("position catch-up candidate requires a source")
        return generate_position_catchup_events(frame, candidate.position_source, spec)
    if candidate.family is RelativeValueFamily.PREMIUM_CROWDING_FADE:
        return generate_premium_crowding_events(frame, spec)
    return generate_taker_chase_events(frame, spec)


def _evaluation_columns(prefix: str, evaluation: PairEvaluation) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def _evaluate_candidate(
    frame: pd.DataFrame,
    candidate: RelativeValueCandidate,
) -> dict[str, float | int | bool | str | None]:
    spec = RelativeValueSpec(hold_hours=candidate.hold_hours)
    events = _candidate_events(frame, candidate, spec)
    discovery = evaluate_pair_events(frame, events, spec, start="2023-01-01", end="2024-01-01")
    validation = evaluate_pair_events(frame, events, spec, start="2024-01-01", end="2026-01-01")
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
        "family": candidate.family.value,
        "variant": candidate.variant,
        "hold_hours": candidate.hold_hours,
        "pre_holdout_pass": pre_pass,
        "pre_holdout_score": score,
        "raw_events": int((events != 0.0).sum()),
        **_evaluation_columns("discovery", discovery),
        **_evaluation_columns("validation", validation),
    }


def _find_candidate(row: pd.Series) -> RelativeValueCandidate:
    family = RelativeValueFamily(str(row["family"]))
    variant = str(row["variant"])
    hold_hours = int(row["hold_hours"])
    return next(
        candidate
        for candidate in candidate_catalog()
        if candidate.family is family
        and candidate.variant == variant
        and candidate.hold_hours == hold_hours
    )


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = load_relative_value_hourly(root)
    summary = pd.DataFrame([_evaluate_candidate(frame, candidate) for candidate in candidate_catalog()])
    summary = summary.sort_values(
        ["family", "pre_holdout_pass", "pre_holdout_score", "hold_hours"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    champion_rows = summary.groupby("family", sort=False, as_index=False).head(1)
    stress_rows: list[dict[str, float | int | bool | str | None]] = []
    zero_cost_rows: list[dict[str, float | int | str | None]] = []
    yearly_rows: list[dict[str, float | int | str | None]] = []
    for _, champion_row in champion_rows.iterrows():
        candidate = _find_candidate(champion_row)
        spec = RelativeValueSpec(hold_hours=candidate.hold_hours)
        events = _candidate_events(frame, candidate, spec)
        stress = evaluate_pair_events(frame, events, spec, start="2026-01-01", end="2026-09-01")
        stress_rows.append(
            {
                "family": candidate.family.value,
                "variant": candidate.variant,
                "hold_hours": candidate.hold_hours,
                "pre_holdout_pass": bool(champion_row["pre_holdout_pass"]),
                **_evaluation_columns("stress", stress),
            }
        )
        for period, start, end in (
            ("discovery", "2023-01-01", "2024-01-01"),
            ("validation", "2024-01-01", "2026-01-01"),
        ):
            evaluation = evaluate_pair_events(
                frame,
                events,
                spec,
                start=start,
                end=end,
                fee_bps=0.0,
                slippage_bps=0.0,
            )
            zero_cost_rows.append(
                {
                    "family": candidate.family.value,
                    "variant": candidate.variant,
                    "hold_hours": candidate.hold_hours,
                    "period": period,
                    **asdict(evaluation),
                }
            )
        for year in (2023, 2024, 2025, 2026):
            year_end = "2026-09-01" if year == 2026 else f"{year + 1}-01-01"
            evaluation = evaluate_pair_events(
                frame,
                events,
                spec,
                start=f"{year}-01-01",
                end=year_end,
            )
            yearly_rows.append(
                {
                    "family": candidate.family.value,
                    "variant": candidate.variant,
                    "hold_hours": candidate.hold_hours,
                    "year": year,
                    **asdict(evaluation),
                }
            )
    return (
        summary,
        pd.DataFrame(stress_rows),
        pd.DataFrame(zero_cost_rows),
        pd.DataFrame(yearly_rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered BTC/ETH relative-value wave")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    summary, stress, zero_cost, yearly = run_research(root)
    summary.to_csv(root / "relative_value_wave_pre_stress.csv", index=False)
    stress.to_csv(root / "relative_value_wave_champions_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "relative_value_wave_champions_zero_cost.csv", index=False)
    yearly.to_csv(root / "relative_value_wave_champions_yearly.csv", index=False)
    print("pre-stress")
    print(summary.to_string(index=False))
    print("family champions stress")
    print(stress.to_string(index=False))
    print("family champions zero cost")
    print(zero_cost.to_string(index=False))
    print("family champions yearly")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    main()
