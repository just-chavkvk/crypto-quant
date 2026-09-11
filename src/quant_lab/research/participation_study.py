from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final

import numpy as np
import polars as pl
import typer

from quant_lab.data.binance_archive import ArchiveEntry, ArchiveError
from quant_lab.data.participation_data import (
    SourceFile,
    download_participation,
    load_participation,
)
from quant_lab.research.participation_execution import evaluate_events
from quant_lab.research.participation_features import participation_signals

PERIODS: Final = (
    ("discovery", datetime(2022, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC)),
    ("validation", datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
    ("stress_2026", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)),
)
ROOT: Final = Path("artifacts/edge_search/participation")
app = typer.Typer()


@dataclass(frozen=True, slots=True)
class Evaluation:
    symbol: str
    period: str
    zero_execution_cost: bool
    hours: int
    signal_hours: int
    trades: int
    total_return: float
    sharpe: float
    max_drawdown: float
    gross_pnl: float
    execution_cost: float
    funding_pnl: float
    net_pnl: float
    pass_gate: bool


def cached_sources(root: Path) -> tuple[SourceFile, ...]:
    manifest = pl.read_csv(root / "source_manifest.csv")
    sources: list[SourceFile] = []
    for symbol, product, key, size, modified, path_text, digest in manifest.iter_rows():
        path = Path(path_text)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ArchiveError(f"cached source changed: {path}")
        sources.append(SourceFile(symbol, product, ArchiveEntry(key, size, modified), path, digest))
    return tuple(sources)


def summarize_equity(equity: pl.DataFrame) -> tuple[float, float, float]:
    values = np.asarray(equity["equity"].to_numpy(), dtype=np.float64)
    prior = np.empty_like(values)
    prior[0] = 10000.0
    prior[1:] = values[:-1]
    returns = values / prior - 1
    deviation = float(np.std(returns, ddof=1))
    sharpe = float(np.mean(returns) / deviation * np.sqrt(8760)) if deviation > 0 else 0.0
    peaks = np.asarray(
        equity["equity"].cum_max().clip(lower_bound=10000.0).to_numpy(), dtype=np.float64
    )
    return float(values[-1] / 10000 - 1), sharpe, float(np.min(values / peaks - 1))


def run_study(root: Path, sources: tuple[SourceFile, ...]) -> pl.DataFrame:
    rows: list[Evaluation] = []
    quality: list[pl.DataFrame] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        inputs = load_participation(sources, symbol)
        inputs.write_parquet(root / f"{symbol}_inputs.parquet")
        frame = participation_signals(inputs)
        for offset in (721, 10000, 25000, len(frame) - 20):
            prefix = participation_signals(inputs.head(offset))
            if not prefix["signal"].equals(frame["signal"].head(offset)):
                raise ArchiveError("participation signal lookahead detected")
        frame.write_parquet(root / f"{symbol}_features.parquet")
        quality.append(
            inputs.group_by(pl.col("timestamp").dt.year().alias("year"))
            .agg(
                pl.len().alias("hours"),
                pl.col("valid_input").sum().alias("valid_input_hours"),
                pl.col("count").min().alias("min_count"),
                pl.col("count").median().alias("median_count"),
                pl.col("count").max().alias("max_count"),
                pl.col("average_trade_size").min().alias("min_average_size"),
                pl.col("average_trade_size").median().alias("median_average_size"),
                pl.col("average_trade_size").max().alias("max_average_size"),
            )
            .with_columns(pl.lit(symbol).alias("symbol"))
        )
        for period, start, end in PERIODS:
            primary_decisions: pl.DataFrame | None = None
            for zero_cost in (False, True):
                equity, trades = evaluate_events(frame, start, end, zero_cost=zero_cost)
                decisions = trades.select(
                    "signal_time", "entry_time", "exit_time", "side", "reason"
                )
                if (
                    zero_cost
                    and primary_decisions is not None
                    and not decisions.equals(primary_decisions)
                ):
                    raise ArchiveError("zero-cost diagnostic changed trading decisions")
                if not zero_cost:
                    primary_decisions = decisions
                total_return, sharpe, drawdown = summarize_equity(equity)
                in_period = frame.filter(
                    (pl.col("timestamp") >= start) & (pl.col("timestamp") < end)
                )
                rows.append(
                    Evaluation(
                        symbol,
                        period,
                        zero_cost,
                        len(equity),
                        in_period.filter(pl.col("signal") != 0).height,
                        len(trades),
                        total_return,
                        sharpe,
                        drawdown,
                        float(trades["gross_pnl"].sum()),
                        float(trades["execution_cost"].sum()),
                        float(trades["funding_pnl"].sum()),
                        float(trades["net_pnl"].sum()),
                        total_return > 0 and sharpe > 0 and len(trades) >= 10,
                    )
                )
                label = f"{symbol}_{period}_{'zero_cost' if zero_cost else 'net'}"
                trades.write_csv(root / f"{label}_trades.csv")
                equity.write_parquet(root / f"{label}_equity.parquet")
    pl.concat(quality).sort("symbol", "year").write_csv(root / "input_quality_by_year.csv")
    result = pl.DataFrame([asdict(row) for row in rows])
    primary = result.filter(~pl.col("zero_execution_cost"))
    verdict = "SHADOW" if len(primary) == 6 and primary["pass_gate"].all() else "REJECTED"
    result = result.with_columns(
        pl.lit(verdict).alias("family_verdict"), pl.lit(1).alias("parameter_trials")
    )
    result.write_csv(root / "participation_results.csv")
    return result


@app.command()
def main(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = ROOT,
    download: bool = False,
) -> None:
    sources = download_participation(root) if download else cached_sources(root)
    results = run_study(root, sources)
    print(
        results.select(
            "symbol",
            "period",
            "zero_execution_cost",
            "trades",
            "total_return",
            "sharpe",
            "family_verdict",
        )
    )


if __name__ == "__main__":
    app()
