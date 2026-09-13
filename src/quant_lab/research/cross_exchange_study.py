from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Final

import numpy as np
import polars as pl
import typer

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.data.bybit_history import download_bybit
from quant_lab.data.cross_exchange_market import load_cross_market
from quant_lab.research.cross_exchange_execution import CrossRun, execute_cross_exchange
from quant_lab.research.cross_exchange_schedule import build_monthly_schedule
from quant_lab.research.participation_study import PERIODS, summarize_equity
from quant_lab.research.presettlement_study import annual_primary_equity

ROOT: Final = Path("artifacts/edge_search/cross_exchange_research")
BINANCE_ROOT: Final = Path("artifacts/edge_search/participation")
app = typer.Typer()


@dataclass(frozen=True, slots=True)
class CrossEvaluation:
    symbol: str
    period: str
    zero_execution_cost: bool
    total_return: float
    sharpe: float
    max_drawdown: float
    cycles: int
    cash_months: int
    untradable_boundaries: int
    min_margin_ratio: float
    margin_breach_hours: int
    price_pnl: float
    funding_pnl: float
    execution_cost: float
    net_pnl: float
    passed: bool


def run_study(root: Path, binance_root: Path) -> pl.DataFrame:
    frames = load_cross_market(root, binance_root)
    rows: list[CrossEvaluation] = []
    annual: list[pl.DataFrame] = []
    for symbol, frame in zip(("BTCUSDT", "ETHUSDT"), frames, strict=True):
        for period, start, end in PERIODS:
            schedule = build_monthly_schedule(frame, CrossRun(start, end))
            schedule.signals.write_csv(root / f"{symbol}_{period}_registered_signals.csv")
            primary_times: pl.DataFrame | None = None
            for zero_cost in (False, True):
                equity, trades = execute_cross_exchange(
                    frame, schedule.cycles, CrossRun(start, end, zero_cost)
                )
                times = trades.select("entry_time", "exit_time", "binance_side")
                if not zero_cost:
                    primary_times = times
                    annual.append(
                        annual_primary_equity(equity).with_columns(pl.lit(symbol).alias("symbol"))
                    )
                elif primary_times is not None and not times.equals(primary_times):
                    raise ArchiveError("zero-cost diagnostic changed registered cycles")
                total, sharpe, drawdown = summarize_equity(equity)
                price_pnl = float(trades["binance_price_pnl"].sum()) + float(
                    trades["bybit_price_pnl"].sum()
                )
                funding = float(trades["binance_funding_pnl"].sum()) + float(
                    trades["bybit_funding_pnl"].sum()
                )
                costs = float(trades["execution_cost"].sum())
                net = float(trades["net_pnl"].sum())
                if abs(10000 * total - net) > 1e-7 or abs(price_pnl + funding - costs - net) > 1e-7:
                    raise ArchiveError("cross-exchange PnL attribution does not reconcile")
                margin = (
                    float(np.asarray(trades["min_margin_ratio"].to_numpy(), dtype=np.float64).min())
                    if len(trades)
                    else 0.0
                )
                breaches = int(trades["margin_breach_hours"].sum())
                passed = (
                    total > 0
                    and sharpe > 0
                    and drawdown > -0.10
                    and len(trades) >= 6
                    and breaches == 0
                    and schedule.untradable_boundaries == 0
                )
                rows.append(
                    CrossEvaluation(
                        symbol,
                        period,
                        zero_cost,
                        total,
                        sharpe,
                        drawdown,
                        len(trades),
                        schedule.cash_months,
                        schedule.untradable_boundaries,
                        margin,
                        breaches,
                        price_pnl,
                        funding,
                        costs,
                        net,
                        passed,
                    )
                )
                label = f"{symbol}_{period}_{'zero_cost' if zero_cost else 'net'}"
                trades.write_csv(root / f"{label}_cycles.csv")
                equity.write_parquet(root / f"{label}_equity.parquet")
    years = pl.concat(annual).sort("symbol", "year")
    years.write_csv(root / "annual_primary_results.csv")
    results = pl.DataFrame([asdict(row) for row in rows])
    primary = results.filter(~pl.col("zero_execution_cost"))
    passed = (
        len(primary) == 6
        and primary["passed"].all()
        and len(years) == 10
        and (years["total_return"] > 0).all()
    )
    result = results.with_columns(
        pl.lit("SHADOW" if passed else "REJECTED").alias("verdict"),
        pl.lit(1).alias("parameter_trials"),
    )
    result.write_csv(root / "cross_exchange_results.csv")
    return result


@app.command()
def main(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = ROOT,
    binance_root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = BINANCE_ROOT,
    download: bool = False,
) -> None:
    if download:
        download_bybit(root)
    results = run_study(root, binance_root)
    print(
        results.select(
            "symbol",
            "period",
            "zero_execution_cost",
            "total_return",
            "sharpe",
            "cycles",
            "min_margin_ratio",
            "verdict",
        )
    )


if __name__ == "__main__":
    app()
