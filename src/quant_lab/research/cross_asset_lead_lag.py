from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray


class CrossAssetLeadLagInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CrossAssetLeadLagSpec:
    lookback_hours: int = 4
    zscore_window_hours: int = 720
    velocity_z_threshold: float = 2.0
    acceleration_z_threshold: float = 1.0
    hold_hours: int = 1
    fee_bps: float = 5.0
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0 or self.zscore_window_hours <= 1 or self.hold_hours <= 0:
            raise CrossAssetLeadLagInputError("lookback, z-score window, and hold must be positive")
        if self.velocity_z_threshold <= 0.0 or self.acceleration_z_threshold <= 0.0:
            raise CrossAssetLeadLagInputError("z-score thresholds must be positive")
        if self.fee_bps < 0.0 or self.slippage_bps < 0.0:
            raise CrossAssetLeadLagInputError("fee and slippage must be non-negative")


@dataclass(frozen=True, slots=True)
class CrossAssetEvaluation:
    total_return: float | None
    sharpe_ratio: float | None
    number_of_trades: int
    mean_trade_return: float | None
    median_trade_return: float | None
    win_rate: float | None


REQUIRED_COLUMNS = (
    "btc_global_ratio",
    "btc_oi_contracts",
    "btc_close",
    "eth_open",
)


def _frame_utc_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if "timestamp" in frame.columns:
        values = frame.pop("timestamp")
        return pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    return pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))


def _read_hourly_price(path: Path, value_column: str, output_column: str) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=[value_column])
    frame.index = _frame_utc_index(frame)
    frame.index.name = "timestamp"
    return frame.rename(columns={value_column: output_column}).sort_index()


def _read_btc_metrics(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(
        path,
        columns=["count_long_short_ratio", "sum_open_interest"],
    )
    timestamp = _frame_utc_index(frame)
    frame = frame.assign(source_timestamp=timestamp, hour=timestamp.floor("h"))
    frame = frame.loc[timestamp.minute == 55]
    frame = frame.sort_values("source_timestamp").drop_duplicates("hour", keep="last")
    frame = frame.set_index("hour")
    frame.index.name = "timestamp"
    return frame[["count_long_short_ratio", "sum_open_interest"]].rename(
        columns={
            "count_long_short_ratio": "btc_global_ratio",
            "sum_open_interest": "btc_oi_contracts",
        }
    )


def load_cross_asset_hourly(
    root: Path,
    *,
    start: str = "2022-01-01",
    end: str = "2026-09-01",
) -> pd.DataFrame:
    metrics = _read_btc_metrics(root / "BTCUSDT_futures_metrics_5m.parquet")
    btc = _read_hourly_price(root / "BTC_USDT_1h_futures.parquet", "close", "btc_close")
    eth = _read_hourly_price(root / "ETH_USDT_1h_futures.parquet", "open", "eth_open")
    index = pd.date_range(start, end, freq="1h", inclusive="left", tz="UTC", name="timestamp")
    return pd.DataFrame(index=index).join(metrics).join(btc).join(eth)


def _validate_frame(frame: pd.DataFrame) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise CrossAssetLeadLagInputError("frame index must be a DatetimeIndex")
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise CrossAssetLeadLagInputError(f"missing required columns: {sorted(missing)}")


def _log_change(series: pd.Series, periods: int) -> pd.Series:
    positive = series.astype(float).where(series.astype(float) > 0.0)
    logs = pd.Series(np.log(positive.to_numpy(dtype=float)), index=series.index, dtype=float)
    return logs - logs.shift(periods)


def _prior_zscore(series: pd.Series, window: int) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=window).mean()
    std = prior.rolling(window, min_periods=window).std(ddof=0).mask(lambda value: value <= 0.0)
    return (series - mean) / std


def build_cross_asset_features(frame: pd.DataFrame, spec: CrossAssetLeadLagSpec) -> pd.DataFrame:
    _validate_frame(frame)
    velocity = _log_change(frame["btc_global_ratio"], spec.lookback_hours)
    acceleration = velocity - velocity.shift(spec.lookback_hours)
    return pd.DataFrame(
        {
            "velocity": velocity,
            "velocity_z": _prior_zscore(velocity, spec.zscore_window_hours),
            "acceleration": acceleration,
            "acceleration_z": _prior_zscore(acceleration, spec.zscore_window_hours),
            "btc_price_return": _log_change(frame["btc_close"], spec.lookback_hours),
            "btc_oi_return": _log_change(frame["btc_oi_contracts"], spec.lookback_hours),
        },
        index=frame.index,
    )


def generate_cross_asset_events(frame: pd.DataFrame, spec: CrossAssetLeadLagSpec) -> pd.Series:
    features = build_cross_asset_features(frame, spec)
    velocity_direction = pd.Series(
        np.sign(features["velocity_z"].to_numpy(dtype=float)), index=features.index, dtype=float
    )
    acceleration_direction = pd.Series(
        np.sign(features["acceleration_z"].to_numpy(dtype=float)), index=features.index, dtype=float
    )
    price_direction = pd.Series(
        np.sign(features["btc_price_return"].to_numpy(dtype=float)), index=features.index, dtype=float
    )
    oi_direction = pd.Series(
        np.sign(features["btc_oi_return"].to_numpy(dtype=float)), index=features.index, dtype=float
    )
    eligible = (
        features.notna().all(axis=1)
        & (features["velocity_z"].abs() >= spec.velocity_z_threshold)
        & (features["acceleration_z"].abs() >= spec.acceleration_z_threshold)
        & (velocity_direction != 0.0)
        & (acceleration_direction == velocity_direction)
        & (price_direction == velocity_direction)
        & (oi_direction == -velocity_direction)
    )
    events = pd.Series(0.0, index=frame.index, dtype=float)
    events.loc[eligible] = velocity_direction.loc[eligible].astype(float)
    return events


def evaluate_cross_asset_events(
    frame: pd.DataFrame,
    events: pd.Series,
    spec: CrossAssetLeadLagSpec,
    *,
    start: str,
    end: str,
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
) -> CrossAssetEvaluation:
    _validate_frame(frame)
    if not events.index.equals(frame.index):
        raise CrossAssetLeadLagInputError("events index must exactly match the market frame")

    start_timestamp = pd.Timestamp(start, tz="UTC")
    end_timestamp = pd.Timestamp(end, tz="UTC")
    event_values: NDArray[np.float64] = np.asarray(
        events.to_numpy(dtype=np.float64), dtype=np.float64
    )
    target_open: NDArray[np.float64] = np.asarray(
        frame["eth_open"].to_numpy(dtype=np.float64), dtype=np.float64
    )
    index = pd.DatetimeIndex(frame.index)
    period_mask: NDArray[np.bool_] = np.asarray(
        (index >= start_timestamp) & (index < end_timestamp), dtype=np.bool_
    )
    candidate_offsets = [
        offset
        for offset, (in_period, event_value) in enumerate(
            zip(period_mask.tolist(), event_values.tolist(), strict=True)
        )
        if in_period and event_value != 0.0
    ]
    fee_rate = (spec.fee_bps if fee_bps is None else fee_bps) / 10_000.0
    slippage_rate = (spec.slippage_bps if slippage_bps is None else slippage_bps) / 10_000.0
    trade_returns: list[float] = []
    next_allowed_signal_offset = -1

    for signal_offset in candidate_offsets:
        if signal_offset < next_allowed_signal_offset:
            continue
        entry_offset = signal_offset + 1
        exit_offset = entry_offset + spec.hold_hours
        if exit_offset >= len(frame) or index[exit_offset] >= end_timestamp:
            continue
        entry_price = float(target_open[entry_offset])
        exit_price = float(target_open[exit_offset])
        side = float(event_values[signal_offset])
        if not (
            np.isfinite(entry_price)
            and np.isfinite(exit_price)
            and entry_price > 0.0
            and exit_price > 0.0
        ):
            continue
        entry_fill = entry_price * (1.0 + side * slippage_rate)
        exit_fill = exit_price * (1.0 - side * slippage_rate)
        gross_return = side * (exit_price - entry_price) / entry_price
        slippage_cost = (
            abs(entry_fill - entry_price) + abs(exit_fill - exit_price)
        ) / entry_price
        fee_cost = fee_rate * (entry_fill + exit_fill) / entry_price
        trade_returns.append(gross_return - slippage_cost - fee_cost)
        next_allowed_signal_offset = exit_offset

    if not trade_returns:
        return CrossAssetEvaluation(None, None, 0, None, None, None)

    values = np.asarray(trade_returns, dtype=np.float64)
    standard_deviation = float(np.std(values, ddof=0))
    sharpe_ratio = (
        float(np.mean(values) / standard_deviation * np.sqrt(8760.0 / spec.hold_hours))
        if standard_deviation > 0.0
        else 0.0
    )
    return CrossAssetEvaluation(
        total_return=float(np.prod(1.0 + values) - 1.0),
        sharpe_ratio=sharpe_ratio,
        number_of_trades=int(values.size),
        mean_trade_return=float(np.mean(values)),
        median_trade_return=float(np.median(values)),
        win_rate=float(np.mean(values > 0.0)),
    )


def _evaluation_columns(prefix: str, evaluation: CrossAssetEvaluation) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = load_cross_asset_hourly(root)
    rows: list[dict[str, float | int | bool | None]] = []
    for hold_hours in (1, 4):
        spec = CrossAssetLeadLagSpec(hold_hours=hold_hours)
        events = generate_cross_asset_events(frame, spec)
        discovery = evaluate_cross_asset_events(
            frame, events, spec, start="2023-01-01", end="2024-01-01"
        )
        validation = evaluate_cross_asset_events(
            frame, events, spec, start="2024-01-01", end="2026-01-01"
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
        rows.append(
            {
                "lookback_hours": spec.lookback_hours,
                "hold_hours": hold_hours,
                "pre_holdout_pass": pre_pass,
                "pre_holdout_score": score,
                "raw_events": int((events != 0.0).sum()),
                **_evaluation_columns("discovery", discovery),
                **_evaluation_columns("validation", validation),
            }
        )

    summary = pd.DataFrame(rows).sort_values("hold_hours").reset_index(drop=True)
    champion = summary.sort_values(
        ["pre_holdout_pass", "pre_holdout_score", "hold_hours"],
        ascending=[False, False, True],
    ).iloc[0]
    champion_spec = CrossAssetLeadLagSpec(hold_hours=int(champion["hold_hours"]))
    champion_events = generate_cross_asset_events(frame, champion_spec)
    stress = evaluate_cross_asset_events(
        frame,
        champion_events,
        champion_spec,
        start="2026-01-01",
        end="2026-09-01",
    )
    stress_frame = pd.DataFrame(
        [
            {
                "lookback_hours": champion_spec.lookback_hours,
                "hold_hours": champion_spec.hold_hours,
                "pre_holdout_pass": bool(champion["pre_holdout_pass"]),
                **_evaluation_columns("stress", stress),
            }
        ]
    )

    zero_cost_rows: list[dict[str, float | int | str | None]] = []
    for period, start, end in (
        ("discovery", "2023-01-01", "2024-01-01"),
        ("validation", "2024-01-01", "2026-01-01"),
    ):
        evaluation = evaluate_cross_asset_events(
            frame,
            champion_events,
            champion_spec,
            start=start,
            end=end,
            fee_bps=0.0,
            slippage_bps=0.0,
        )
        zero_cost_rows.append(
            {
                "period": period,
                "lookback_hours": champion_spec.lookback_hours,
                "hold_hours": champion_spec.hold_hours,
                **asdict(evaluation),
            }
        )
    zero_cost = pd.DataFrame(zero_cost_rows)

    yearly_rows: list[dict[str, float | int | None]] = []
    for year in (2023, 2024, 2025, 2026):
        end = "2026-09-01" if year == 2026 else f"{year + 1}-01-01"
        evaluation = evaluate_cross_asset_events(
            frame,
            champion_events,
            champion_spec,
            start=f"{year}-01-01",
            end=end,
        )
        yearly_rows.append(
            {
                "year": year,
                "lookback_hours": champion_spec.lookback_hours,
                "hold_hours": champion_spec.hold_hours,
                **asdict(evaluation),
            }
        )
    yearly = pd.DataFrame(yearly_rows)
    return summary, stress_frame, zero_cost, yearly


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the preregistered BTC→ETH lead-lag study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    summary, stress, zero_cost, yearly = run_research(root)
    summary.to_csv(root / "cross_asset_lead_lag_pre_stress.csv", index=False)
    stress.to_csv(root / "cross_asset_lead_lag_champion_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "cross_asset_lead_lag_champion_zero_cost.csv", index=False)
    yearly.to_csv(root / "cross_asset_lead_lag_champion_yearly.csv", index=False)
    print("pre-stress")
    print(summary.to_string(index=False))
    print("stress champion")
    print(stress.to_string(index=False))
    print("zero cost champion")
    print(zero_cost.to_string(index=False))
    print("yearly champion")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    main()
