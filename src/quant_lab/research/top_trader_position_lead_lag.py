from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Final

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.cross_asset_lead_lag import (
    CrossAssetEvaluation,
    CrossAssetLeadLagSpec,
    evaluate_cross_asset_events,
    generate_cross_asset_events,
)

SOURCE_RATIO_COLUMN: Final = "sum_toptrader_long_short_ratio"
OUTPUT_RATIO_COLUMN: Final = "btc_top_position_ratio"
ENGINE_RATIO_COLUMN: Final = "btc_global_ratio"


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


def _read_top_position_metrics(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=[SOURCE_RATIO_COLUMN, "sum_open_interest"])
    timestamp = _frame_utc_index(frame)
    frame = frame.assign(source_timestamp=timestamp, hour=timestamp.floor("h"))
    frame = frame.loc[timestamp.minute == 55]
    frame = frame.sort_values("source_timestamp").drop_duplicates("hour", keep="last")
    frame = frame.set_index("hour")
    frame.index.name = "timestamp"
    return frame[[SOURCE_RATIO_COLUMN, "sum_open_interest"]].rename(
        columns={
            SOURCE_RATIO_COLUMN: OUTPUT_RATIO_COLUMN,
            "sum_open_interest": "btc_oi_contracts",
        }
    )


def load_top_trader_position_hourly(
    root: Path,
    *,
    start: str = "2022-01-01",
    end: str = "2026-09-01",
) -> pd.DataFrame:
    metrics = _read_top_position_metrics(root / "BTCUSDT_futures_metrics_5m.parquet")
    btc = _read_hourly_price(root / "BTC_USDT_1h_futures.parquet", "close", "btc_close")
    eth = _read_hourly_price(root / "ETH_USDT_1h_futures.parquet", "open", "eth_open")
    index = pd.date_range(start, end, freq="1h", inclusive="left", tz="UTC", name="timestamp")
    return pd.DataFrame(index=index).join(metrics).join(btc).join(eth)


def _engine_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={OUTPUT_RATIO_COLUMN: ENGINE_RATIO_COLUMN})


def _evaluation_columns(
    prefix: str,
    evaluation: CrossAssetEvaluation,
) -> dict[str, float | int | None]:
    return {f"{prefix}_{key}": value for key, value in asdict(evaluation).items()}


def run_research(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = _engine_frame(load_top_trader_position_hourly(root))
    rows: list[dict[str, float | int | bool | str | None]] = []
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
                "positioning_source": "top_trader_position_ratio",
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
                "positioning_source": "top_trader_position_ratio",
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
                "positioning_source": "top_trader_position_ratio",
                "lookback_hours": champion_spec.lookback_hours,
                "hold_hours": champion_spec.hold_hours,
                **asdict(evaluation),
            }
        )
    zero_cost = pd.DataFrame(zero_cost_rows)

    yearly_rows: list[dict[str, float | int | str | None]] = []
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
                "positioning_source": "top_trader_position_ratio",
                "lookback_hours": champion_spec.lookback_hours,
                "hold_hours": champion_spec.hold_hours,
                **asdict(evaluation),
            }
        )
    yearly = pd.DataFrame(yearly_rows)
    return summary, stress_frame, zero_cost, yearly


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the preregistered BTC top-trader-position to ETH lead-lag study"
    )
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    root: Path = args.root
    summary, stress, zero_cost, yearly = run_research(root)
    summary.to_csv(root / "top_trader_position_lead_lag_pre_stress.csv", index=False)
    stress.to_csv(root / "top_trader_position_lead_lag_champion_stress_2026.csv", index=False)
    zero_cost.to_csv(root / "top_trader_position_lead_lag_champion_zero_cost.csv", index=False)
    yearly.to_csv(root / "top_trader_position_lead_lag_champion_yearly.csv", index=False)
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
