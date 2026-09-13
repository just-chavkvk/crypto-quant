from __future__ import annotations

import argparse
import hashlib
import json
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import httpx2
import numpy as np
import polars as pl

BASE_URL: Final = "https://bitview.space"
DATE_SERIES: Final = "date"
PRICE_SERIES: Final = "price"
LTH_SERIES: Final = "lth_supply_delta_1m_rate_ratio"
STH_SERIES: Final = "sth_supply_delta_1m_rate_ratio"
WHALE_SERIES: Final = "utxos_over_10k_btc_supply_delta_1w_rate_ratio"
FEATURE_SERIES: Final = (LTH_SERIES, STH_SERIES, WHALE_SERIES)


class HolderFlowError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class HolderFlowSpec:
    lag_days: int = 2
    hold_days: int = 7
    roundtrip_cost_bps: float = 14.0

    def __post_init__(self) -> None:
        if self.lag_days < 1 or self.hold_days < 1 or self.roundtrip_cost_bps < 0.0:
            raise HolderFlowError("invalid timing or cost contract")


@dataclass(frozen=True, slots=True)
class SourceSeries:
    name: str
    rows: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    period: str
    event_count: int
    long_count: int
    short_count: int
    mean_net_return: float
    median_net_return: float
    win_rate: float
    compounded_event_return: float
    worst_event_return: float
    pass_gate: bool


def bitview_client() -> httpx2.Client:
    """Return an optimized public Bitview HTTP session owned by the caller."""
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=httpx2.Limits(
            max_connections=20,
            max_keepalive_connections=16,
            keepalive_expiry=30.0,
        ),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.Client(
        transport=transport,
        timeout=httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0),
        follow_redirects=True,
    )


def _fetch_dates(client: httpx2.Client) -> tuple[SourceSeries, list[date]]:
    response = client.get(f"{BASE_URL}/api/series/{DATE_SERIES}/day1/data")
    _ = response.raise_for_status()
    payload: list[str] = json.loads(response.text)
    values = [date.fromisoformat(item) for item in payload]
    return (
        SourceSeries(DATE_SERIES, len(values), hashlib.sha256(response.content).hexdigest()),
        values,
    )


def _fetch_numeric_series(
    client: httpx2.Client,
    series: str,
) -> tuple[SourceSeries, list[float | None]]:
    response = client.get(f"{BASE_URL}/api/series/{series}/day1/data")
    _ = response.raise_for_status()
    payload: list[int | float | None] = json.loads(response.text)
    values = [None if item is None else float(item) for item in payload]
    return SourceSeries(series, len(values), hashlib.sha256(response.content).hexdigest()), values


def fetch_source_frame(client: httpx2.Client) -> tuple[pl.DataFrame, tuple[SourceSeries, ...]]:
    """Fetch and boundary-parse the exact preregistered daily source arrays."""
    date_meta, dates = _fetch_dates(client)
    numeric = tuple(
        _fetch_numeric_series(client, series)
        for series in (PRICE_SERIES, LTH_SERIES, STH_SERIES, WHALE_SERIES)
    )
    payloads = (date_meta, *(item[0] for item in numeric))
    lengths = {payload.rows for payload in payloads}
    if len(lengths) != 1:
        raise HolderFlowError("Bitview daily arrays have unequal lengths")
    if dates != sorted(set(dates)):
        raise HolderFlowError("date series must be unique and ascending")

    return (
        pl.DataFrame(
            {
                "date": dates,
                "price": numeric[0][1],
                "lth": numeric[1][1],
                "sth": numeric[2][1],
                "whale": numeric[3][1],
            },
            schema_overrides={"date": pl.Date},
        ),
        payloads,
    )


def build_regime_events(frame: pl.DataFrame) -> pl.DataFrame:
    """Build only transition events from the preregistered three-sign rule."""
    required = {"date", "lth", "sth", "whale"}
    if required.difference(frame.columns):
        raise HolderFlowError("missing holder-cohort columns")
    valid = pl.all_horizontal(pl.col("lth", "sth", "whale").is_not_null())
    regime = (
        pl.when(valid & (pl.col("lth") > 0) & (pl.col("sth") < 0) & (pl.col("whale") > 0))
        .then(1)
        .when(valid & (pl.col("lth") < 0) & (pl.col("sth") > 0) & (pl.col("whale") < 0))
        .then(-1)
        .otherwise(0)
        .cast(pl.Int8)
        .alias("regime")
    )
    enriched = frame.sort("date").with_columns(regime)
    return (
        enriched.with_columns(pl.col("regime").shift(1).fill_null(0).alias("prior_regime"))
        .filter((pl.col("regime") != 0) & (pl.col("regime") != pl.col("prior_regime")))
        .select("date", pl.col("regime").alias("signal"))
    )


def evaluate_events(
    events: pl.DataFrame,
    prices: pl.DataFrame,
    spec: HolderFlowSpec,
) -> pl.DataFrame:
    """Apply the frozen lag/holding/cost contract to transition events."""
    if {"date", "signal"}.difference(events.columns) or {"date", "price"}.difference(prices.columns):
        raise HolderFlowError("missing event or price columns")
    event_frame = events.with_columns(
        (pl.col("date") + pl.duration(days=spec.lag_days)).alias("entry_date"),
        (pl.col("date") + pl.duration(days=spec.lag_days + spec.hold_days)).alias("exit_date"),
    )
    entry_prices = prices.select(
        pl.col("date").alias("entry_date"), pl.col("price").alias("entry_price")
    )
    exit_prices = prices.select(
        pl.col("date").alias("exit_date"), pl.col("price").alias("exit_price")
    )
    joined = event_frame.join(entry_prices, on="entry_date", how="left").join(
        exit_prices, on="exit_date", how="left"
    )
    valid = (
        pl.col("entry_price").is_not_null()
        & pl.col("exit_price").is_not_null()
        & pl.col("entry_price").is_finite()
        & pl.col("exit_price").is_finite()
        & (pl.col("entry_price") > 0)
        & (pl.col("exit_price") > 0)
    )
    gross = (
        pl.col("signal") * (pl.col("exit_price") / pl.col("entry_price") - 1.0)
    ).round(12)
    return joined.filter(valid).with_columns(
        gross.alias("gross_signed_return"),
        (gross - spec.roundtrip_cost_bps / 10_000.0).round(12).alias("net_signed_return"),
    )


def summarize_period(events: pl.DataFrame, period: str, start: date, end: date) -> PeriodSummary:
    """Summarize one preregistered signal-date period and evaluate its gate."""
    sample = events.filter((pl.col("date") >= start) & (pl.col("date") < end))
    count = sample.height
    if count == 0:
        return PeriodSummary(period, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, False)
    returns = sample["net_signed_return"].to_numpy()
    mean_return = float(np.mean(returns))
    median_return = float(np.median(returns))
    win_rate = float(np.mean(returns > 0.0))
    compounded = float(np.prod(returns + 1.0) - 1.0)
    worst = float(np.min(returns))
    return PeriodSummary(
        period=period,
        event_count=count,
        long_count=sample.filter(pl.col("signal") == 1).height,
        short_count=sample.filter(pl.col("signal") == -1).height,
        mean_net_return=mean_return,
        median_net_return=median_return,
        win_rate=win_rate,
        compounded_event_return=compounded,
        worst_event_return=worst,
        pass_gate=count >= 10 and mean_return > 0.0 and win_rate >= 0.5,
    )


def run_research(root: Path) -> tuple[pl.DataFrame, pl.DataFrame, str]:
    """Fetch sources, execute the one frozen trial, and persist reproducible artifacts."""
    output = root / "holder_cohort_flow"
    output.mkdir(parents=True, exist_ok=True)
    with bitview_client() as client:
        source, payloads = fetch_source_frame(client)
    source.write_parquet(output / "source.parquet")
    manifest = pl.DataFrame(
        {
            "series": [payload.name for payload in payloads],
            "rows": [payload.rows for payload in payloads],
            "sha256": [payload.sha256 for payload in payloads],
            "retrieved_at_utc": [datetime.now(UTC).isoformat()] * len(payloads),
        }
    )
    manifest.write_csv(output / "source_manifest.csv")

    events = build_regime_events(source.select("date", "lth", "sth", "whale"))
    evaluated = evaluate_events(events, source.select("date", "price"), HolderFlowSpec())
    evaluated.write_csv(output / "events.csv")
    summaries = [
        summarize_period(evaluated, "discovery", date(2022, 1, 1), date(2024, 1, 1)),
        summarize_period(evaluated, "validation", date(2024, 1, 1), date(2026, 1, 1)),
        summarize_period(evaluated, "stress_2026", date(2026, 1, 1), date(2026, 9, 1)),
    ]
    summary = pl.DataFrame([asdict(item) for item in summaries])
    summary.write_csv(output / "summary.csv")
    verdict = "PRE-SCREEN" if summaries[0].pass_gate and summaries[1].pass_gate else "REJECTED"
    return summary, evaluated, verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preregistered BTC holder-cohort flow study")
    _ = parser.add_argument("--root", type=Path, default=Path("artifacts/edge_search"))
    args = parser.parse_args()
    summary, events, verdict = run_research(args.root)
    print(summary)
    print(f"events={events.height} verdict={verdict}")


if __name__ == "__main__":
    main()
