from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.relative_value import (
    PairEvaluation,
    RelativeValueSpec,
    evaluate_pair_events,
    load_relative_value_hourly,
)


class RelativeShockError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RelativeShockSpec:
    relative_lookback_hours: int = 24
    zscore_window_hours: int = 720
    correlation_window_hours: int = 168
    correlation_threshold: float = 0.70
    z_threshold: float = 2.0
    hold_hours: int = 24

    def __post_init__(self) -> None:
        if (
            self.relative_lookback_hours <= 0
            or self.zscore_window_hours <= 1
            or self.correlation_window_hours <= 1
            or self.hold_hours <= 0
        ):
            raise RelativeShockError("lookback, z-score, correlation, and hold windows must be positive")
        if not -1.0 <= self.correlation_threshold <= 1.0:
            raise RelativeShockError("correlation threshold must be in [-1, 1]")
        if self.z_threshold <= 0.0:
            raise RelativeShockError("z-score threshold must be positive")


def _log_change(series: pd.Series, periods: int) -> pd.Series:
    positive = series.astype(float).where(series.astype(float) > 0.0)
    logged = pd.Series(np.log(positive.to_numpy(dtype=float)), index=series.index, dtype=float)
    return logged - logged.shift(periods)


def _prior_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0).mask(lambda value: value <= 0.0)
    return (series - mean) / std


def generate_relative_shock_events(frame: pd.DataFrame, spec: RelativeShockSpec) -> pd.Series:
    required = {"btc_close", "eth_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise RelativeShockError(f"missing required columns: {sorted(missing)}")
    btc_relative = _log_change(frame["btc_close"], spec.relative_lookback_hours)
    eth_relative = _log_change(frame["eth_close"], spec.relative_lookback_hours)
    relative_shock = eth_relative - btc_relative
    shock_z = _prior_zscore(relative_shock, spec.zscore_window_hours)
    btc_hourly = _log_change(frame["btc_close"], 1).shift(1)
    eth_hourly = _log_change(frame["eth_close"], 1).shift(1)
    correlation = btc_hourly.rolling(
        spec.correlation_window_hours,
        min_periods=spec.correlation_window_hours,
    ).corr(eth_hourly)
    direction = pd.Series(
        np.sign(relative_shock.to_numpy(dtype=float)), index=frame.index, dtype=float
    )
    eligible = (
        pd.concat([relative_shock, shock_z, correlation], axis=1).notna().all(axis=1)
        & (shock_z.abs() >= spec.z_threshold)
        & (correlation >= spec.correlation_threshold)
        & (direction != 0.0)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float, name="event")
    events.loc[eligible] = -direction.loc[eligible]
    return events


def _evaluation_columns(prefix: str, evaluation: PairEvaluation) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = load_relative_value_hourly(root)
    signal_spec = RelativeShockSpec()
    execution_spec = RelativeValueSpec(hold_hours=signal_spec.hold_hours)
    events = generate_relative_shock_events(frame, signal_spec)
    discovery = evaluate_pair_events(
        frame,
        events,
        execution_spec,
        start="2022-01-01",
        end="2024-01-01",
    )
    validation = evaluate_pair_events(
        frame,
        events,
        execution_spec,
        start="2024-01-01",
        end="2026-01-01",
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
    pre_stress = pd.DataFrame(
        [
            {
                "pre_holdout_pass": pre_pass,
                "raw_events": int((events != 0.0).sum()),
                **_evaluation_columns("discovery", discovery),
                **_evaluation_columns("validation", validation),
            }
        ]
    )
    stress = evaluate_pair_events(
        frame,
        events,
        execution_spec,
        start="2026-01-01",
        end="2026-09-11",
    )
    stress_frame = pd.DataFrame(
        [{"pre_holdout_pass": pre_pass, **_evaluation_columns("stress", stress)}]
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
    shadow = evaluate_pair_events(
        frame,
        events,
        execution_spec,
        start="2026-09-11",
        end="2100-01-01",
    )
    shadow_frame = (
        pd.DataFrame()
        if shadow.number_of_trades == 0
        else pd.DataFrame([asdict(shadow)])
    )
    return pre_stress, stress_frame, pd.DataFrame(zero_cost_rows), shadow_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered BTC/ETH relative-shock fade")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost, shadow = run_research(root)
    pre_stress.to_csv(root / "relative_shock_fade_pre_stress.csv", index=False)
    stress.to_csv(root / "relative_shock_fade_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "relative_shock_fade_zero_cost.csv", index=False)
    shadow.to_csv(root / "relative_shock_fade_shadow.csv", index=False)
    print("pre-stress")
    print(pre_stress.to_string(index=False))
    print("stress")
    print(stress.to_string(index=False))
    print("zero cost")
    print(zero_cost.to_string(index=False))
    print("future shadow")
    print("no completed shadow trades yet" if shadow.empty else shadow.to_string(index=False))


if __name__ == "__main__":
    main()
