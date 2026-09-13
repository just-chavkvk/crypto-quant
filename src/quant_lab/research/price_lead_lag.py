from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.data.market import load_market_data
from quant_lab.research.price_lead_lag_execution import (
    PriceLeadLagEvaluation,
    evaluate_price_lead_lag_events,
)


class PriceLeadLagInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PriceLeadLagSpec:
    zscore_window_hours: int = 720
    shock_z_threshold: float = 2.0
    underreaction_ratio: float = 0.5
    hold_hours: int = 4
    fee_bps: float = 5.0
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.zscore_window_hours <= 1 or self.hold_hours <= 0:
            raise PriceLeadLagInputError("z-score window and hold must be positive")
        if self.shock_z_threshold <= 0.0:
            raise PriceLeadLagInputError("shock z-score threshold must be positive")
        if not 0.0 < self.underreaction_ratio <= 1.0:
            raise PriceLeadLagInputError("underreaction ratio must be in (0, 1]")
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0:
            raise PriceLeadLagInputError("fee and slippage must be non-negative")


REQUIRED_COLUMNS = ("btc_close", "eth_close", "eth_open")


def load_price_lead_lag_hourly(root: Path) -> pd.DataFrame:
    btc = load_market_data(root / "BTC_USDT_1h_futures.parquet")[["close"]].rename(
        columns={"close": "btc_close"}
    )
    eth = load_market_data(root / "ETH_USDT_1h_futures.parquet")[["open", "close"]].rename(
        columns={"open": "eth_open", "close": "eth_close"}
    )
    return btc.join(eth, how="inner").sort_index()


def _validate_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise PriceLeadLagInputError("frame index must be a DatetimeIndex")
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise PriceLeadLagInputError(f"missing required columns: {sorted(missing)}")


def _log_change(series: pd.Series) -> pd.Series:
    positive = series.astype(float).where(series.astype(float) > 0.0)
    logged = pd.Series(np.log(positive.to_numpy(dtype=float)), index=series.index, dtype=float)
    return logged - logged.shift(1)


def _prior_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0).mask(lambda value: value <= 0.0)
    return (series - mean) / std


def generate_price_lead_lag_events(frame: pd.DataFrame, spec: PriceLeadLagSpec) -> pd.Series:
    _validate_frame(frame)
    btc_return = _log_change(frame["btc_close"])
    eth_return = _log_change(frame["eth_close"])
    btc_zscore = _prior_zscore(btc_return, spec.zscore_window_hours)
    btc_direction = pd.Series(
        np.sign(btc_return.to_numpy(dtype=float)), index=frame.index, dtype=float
    )
    eth_direction = pd.Series(
        np.sign(eth_return.to_numpy(dtype=float)), index=frame.index, dtype=float
    )
    eligible = (
        pd.concat([btc_return, eth_return, btc_zscore], axis=1).notna().all(axis=1)
        & (btc_zscore.abs() >= spec.shock_z_threshold)
        & (btc_direction != 0.0)
        & (eth_direction == btc_direction)
        & (eth_return.abs() <= btc_return.abs() * spec.underreaction_ratio)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float, name="event")
    events.loc[eligible] = btc_direction.loc[eligible]
    return events


def _evaluation_columns(
    prefix: str, evaluation: PriceLeadLagEvaluation
) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = load_price_lead_lag_hourly(root)
    spec = PriceLeadLagSpec()
    events = generate_price_lead_lag_events(frame, spec)
    discovery = evaluate_price_lead_lag_events(
        frame,
        events,
        hold_hours=spec.hold_hours,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
        start="2022-01-01",
        end="2024-01-01",
    )
    validation = evaluate_price_lead_lag_events(
        frame,
        events,
        hold_hours=spec.hold_hours,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
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
                "zscore_window_hours": spec.zscore_window_hours,
                "shock_z_threshold": spec.shock_z_threshold,
                "underreaction_ratio": spec.underreaction_ratio,
                "hold_hours": spec.hold_hours,
                "pre_holdout_pass": pre_pass,
                "raw_events": int((events != 0.0).sum()),
                **_evaluation_columns("discovery", discovery),
                **_evaluation_columns("validation", validation),
            }
        ]
    )
    stress = evaluate_price_lead_lag_events(
        frame,
        events,
        hold_hours=spec.hold_hours,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
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
        ("stress_2026", "2026-01-01", "2026-09-11"),
    ):
        evaluation = evaluate_price_lead_lag_events(
            frame,
            events,
            hold_hours=spec.hold_hours,
            fee_bps=0.0,
            slippage_bps=0.0,
            start=start,
            end=end,
        )
        zero_cost_rows.append({"period": period, **asdict(evaluation)})
    shadow = evaluate_price_lead_lag_events(
        frame,
        events,
        hold_hours=spec.hold_hours,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
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
    parser = argparse.ArgumentParser(description="Run the preregistered BTC price to ETH lead-lag study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    pre_stress, stress, zero_cost, shadow = run_research(root)
    pre_stress.to_csv(root / "price_lead_lag_pre_stress.csv", index=False)
    stress.to_csv(root / "price_lead_lag_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "price_lead_lag_zero_cost.csv", index=False)
    shadow.to_csv(root / "price_lead_lag_shadow.csv", index=False)
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
