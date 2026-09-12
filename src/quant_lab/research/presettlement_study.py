from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

import polars as pl
import typer

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.data.participation_data import load_participation, read_archive
from quant_lab.research.participation_study import PERIODS, cached_sources, summarize_equity
from quant_lab.research.presettlement_execution import PressureRun, evaluate_presettlement

SOURCE: Final = Path("artifacts/edge_search/participation")
OUTPUT: Final = Path("artifacts/edge_search/presettlement")
app = typer.Typer()


def annual_primary_equity(equity: pl.DataFrame) -> pl.DataFrame:
    anchor = 10000.0
    rows: list[dict[str, int | float]] = []
    for year in equity["timestamp"].dt.year().unique().sort().to_list():
        portion = equity.filter(pl.col("timestamp").dt.year() == year)
        normalized = portion.with_columns((pl.col("equity") * 10000 / anchor).alias("equity"))
        total, sharpe, drawdown = summarize_equity(normalized)
        rows.append(
            {"year": year, "total_return": total, "sharpe": sharpe, "max_drawdown": drawdown}
        )
        anchor = float(portion["equity"][-1])
    return pl.DataFrame(rows)


def run_study(source_root: Path, output: Path) -> pl.DataFrame:
    sources = cached_sources(source_root)
    funding = pl.concat(
        [read_archive(s.path) for s in sources if s.product == "fundingRate"],
        how="vertical_relaxed",
    )
    hours = (funding["calc_time"] // 3600000) % 24
    if not hours.is_in([0, 8, 16]).all() or (funding["funding_interval_hours"] != 8).any():
        raise ArchiveError("pre-settlement registered funding clock mismatch")
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int | float | bool]] = []
    yearly: list[pl.DataFrame] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        frame = load_participation(sources, symbol)
        for period, start, end in PERIODS:
            primary_decisions: pl.DataFrame | None = None
            for zero_cost in (False, True):
                result = evaluate_presettlement(frame, PressureRun(start, end, zero_cost))
                decisions = result.trades.select("entry_time", "exit_time", "reason")
                if not zero_cost:
                    primary_decisions = decisions
                    yearly.append(
                        annual_primary_equity(result.equity).with_columns(
                            pl.lit(symbol).alias("symbol")
                        )
                    )
                elif primary_decisions is not None and not decisions.equals(primary_decisions):
                    raise ArchiveError("zero-cost diagnostic changed presettlement decisions")
                total, sharpe, drawdown = summarize_equity(result.equity)
                pnl = float(result.trades["net_pnl"].sum())
                if abs(float(result.equity["equity"][-1]) - 10000 - pnl) > 1e-7:
                    raise ArchiveError("presettlement equity/PnL reconciliation failed")
                rows.append(
                    {
                        "symbol": symbol,
                        "period": period,
                        "zero_execution_cost": zero_cost,
                        "total_return": total,
                        "sharpe": sharpe,
                        "max_drawdown": drawdown,
                        "trades": result.trades.height,
                        "boundary_signals": result.boundary_signals,
                        "untradable_boundaries": result.untradable_boundaries,
                        "gross_pnl": float(result.trades["gross_pnl"].sum()),
                        "execution_cost": float(result.trades["execution_cost"].sum()),
                        "net_pnl": pnl,
                        "pass_gate": total > 0
                        and sharpe > 0
                        and drawdown > -0.10
                        and result.trades.height >= 10
                        and result.untradable_boundaries == 0,
                    }
                )
                label = f"{symbol}_{period}_{'zero_cost' if zero_cost else 'net'}"
                result.trades.write_csv(output / f"{label}_trades.csv")
                result.equity.write_parquet(output / f"{label}_equity.parquet")
    years = pl.concat(yearly).sort("symbol", "year")
    years.write_csv(output / "annual_primary_results.csv")
    results = pl.DataFrame(rows)
    primary = results.filter(~pl.col("zero_execution_cost"))
    passed = (
        primary.height == 6
        and primary["pass_gate"].all()
        and years.height == 10
        and (years["total_return"] > 0).all()
    )
    results = results.with_columns(
        pl.lit("SHADOW" if passed else "REJECTED").alias("verdict"),
        pl.lit(1).alias("parameter_trials"),
    )
    results.write_csv(output / "presettlement_results.csv")
    return results


@app.command()
def main(
    source_root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = SOURCE,
    output: Path = OUTPUT,
) -> None:
    result = run_study(source_root, output)
    print(
        result.select(
            "symbol", "period", "zero_execution_cost", "total_return", "sharpe", "trades", "verdict"
        )
    )


if __name__ == "__main__":
    app()
