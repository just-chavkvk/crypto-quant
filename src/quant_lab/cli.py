from __future__ import annotations

from pathlib import Path

import typer

from quant_lab.backtest.engine import BacktestConfig, run_backtest
from quant_lab.data.market import load_market_data
from quant_lab.strategies.base import EmaBreakoutStrategy

app = typer.Typer(help="Crypto Quant Lab CLI")


@app.command()
def test(
    path: Path,
    fee_bps: float = 5.0,
    slippage_bps: float = 2.0,
    fast: int = 50,
    slow: int = 200,
    breakout: int = 20,
):
    """Run the fast backtester on a BTC/ETH OHLCV CSV or parquet file."""
    data = load_market_data(path)
    strategy = EmaBreakoutStrategy(fast=fast, slow=slow, breakout=breakout)
    result = run_backtest(
        data,
        strategy,
        BacktestConfig(fee_bps=fee_bps, slippage_bps=slippage_bps),
    )

    typer.echo(f"strategy: {strategy.name}")
    for key, value in result.metrics.items():
        typer.echo(f"{key}: {value:.4f}")


if __name__ == "__main__":
    app()
