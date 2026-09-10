from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pandas as pd
import typer

from quant_lab.backtest.engine import run_backtest, run_buy_and_hold
from quant_lab.backtest.models import BacktestConfig
from quant_lab.data.download import DownloadRequest, download_ohlcv
from quant_lab.data.market import load_market_data
from quant_lab.strategies.base import EmaBreakoutStrategy
from quant_lab.validation.lookahead import assert_no_lookahead
from quant_lab.validation.walk_forward import WalkForwardConfig, evaluate_walk_forward

app = typer.Typer(help="BTC/ETH Quant Research Lab", no_args_is_help=True)
data_app = typer.Typer(help="Public OHLCV data cache", no_args_is_help=True)
app.add_typer(data_app, name="data")
DEFAULT_CACHE_DIR: Final = Path("data/cache")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _last_complete_candle(timeframe: str) -> datetime:
    hours = {"1h": 1, "4h": 4}[timeframe]
    now = datetime.now(UTC)
    candle_hour = (now.hour // hours) * hours
    current_candle = now.replace(hour=candle_hour, minute=0, second=0, microsecond=0)
    return current_candle - timedelta(hours=hours)


@data_app.command("download")
def data_download(
    symbol: str,
    timeframe: str = "1h",
    start: str = "2019-01-01T00:00:00Z",
    end: str | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> None:
    end_time = _timestamp(end) if end is not None else _last_complete_candle(timeframe)
    request = DownloadRequest(
        symbol=symbol, timeframe=timeframe, start=_timestamp(start), end=end_time, cache_dir=cache_dir
    )
    result = download_ohlcv(request)
    typer.echo(f"path: {result.path}")
    typer.echo(f"candles: {len(result.data)}")
    typer.echo(f"cache_hit: {str(result.cache_hit).lower()}")


@app.command("test")
def test(
    path: Path,
    symbol: str = "BTC/USDT",
    fee_bps: float = 5.0,
    slippage_bps: float = 2.0,
    fast: int = 50,
    slow: int = 200,
    breakout: int = 20,
    benchmark_path: Path | None = None,
    ledger_out: Path | None = None,
) -> None:
    data = load_market_data(path)
    strategy = EmaBreakoutStrategy(fast=fast, slow=slow, breakout=breakout)
    assert_no_lookahead(data, strategy)
    backtest_config = BacktestConfig(fee_bps=fee_bps, slippage_bps=slippage_bps)
    result = run_backtest(data, strategy, backtest_config, symbol=symbol)
    typer.echo(f"strategy: {strategy.name}")
    typer.echo(f"METRICS: {result.metrics}")
    typer.echo(f"TRADE LEDGER: {len(result.trades)} trade(s)")
    if ledger_out is not None:
        ledger_out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([asdict(trade) for trade in result.trades]).to_csv(ledger_out, index=False)
        typer.echo(f"ledger: {ledger_out}")
    benchmark_data = load_market_data(benchmark_path) if benchmark_path is not None else None
    if benchmark_data is None and symbol == "BTC/USDT":
        benchmark_data = data
    if benchmark_data is not None:
        benchmark = run_buy_and_hold(benchmark_data, backtest_config, symbol="BTC/USDT")
        typer.echo(f"BTC BUY & HOLD: {benchmark.metrics}")
        typer.echo(f"EXCESS TOTAL RETURN: {result.metrics.total_return - benchmark.metrics.total_return:.4f}")


@app.command("walk-forward")
def walk_forward(
    path: Path,
    symbol: str = "BTC/USDT",
    train_bars: int = 1000,
    test_bars: int = 250,
    fast: int = 50,
    slow: int = 200,
    breakout: int = 20,
    fee_bps: float = 5.0,
    slippage_bps: float = 2.0,
) -> None:
    data = load_market_data(path)

    def strategy_factory() -> EmaBreakoutStrategy:
        return EmaBreakoutStrategy(fast=fast, slow=slow, breakout=breakout)

    assert_no_lookahead(data, strategy_factory())
    report = evaluate_walk_forward(
        data,
        strategy_factory=strategy_factory,
        config=WalkForwardConfig(train_bars=train_bars, test_bars=test_bars),
        backtest_config=BacktestConfig(fee_bps=fee_bps, slippage_bps=slippage_bps),
        symbol=symbol,
    )
    typer.echo(f"TRAIN: {report.train_metrics}")
    typer.echo(f"OUT OF SAMPLE: {report.out_of_sample_metrics}")
    typer.echo(f"WALK FORWARD: {report.walk_forward.metrics}")
    verdict = "PASS" if report.passed else "FAIL"
    typer.echo(f"VERDICT: {verdict}")
