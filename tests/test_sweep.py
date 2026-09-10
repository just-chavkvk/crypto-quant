from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from quant_lab.backtest.models import BacktestConfig
from quant_lab.cli import app
from quant_lab.research.sweep import EmaSweepConfig, run_ema_sweep


def market_data(rows: int = 80) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series(range(100, 100 + rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 10_000.0,
        },
        index=index,
    )


def test_ema_sweep_runs_valid_parameter_combinations_and_ranks_results():
    # Given: a grid containing three valid fast/slow combinations and one invalid combination.
    config = EmaSweepConfig(
        fast_values=(2, 4),
        slow_values=(3, 5),
        breakout_values=(2,),
        train_bars=40,
        test_bars=20,
    )

    # When: all candidate strategies are walk-forward tested.
    report = run_ema_sweep(
        market_data(),
        config,
        BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    # Then: invalid fast >= slow pairs are skipped and ranking is best-first.
    assert len(report.candidates) == 3
    assert all(candidate.fast < candidate.slow for candidate in report.candidates)
    ranking = [
        (
            candidate.passed,
            candidate.walk_forward_sharpe,
            candidate.walk_forward_total_return,
        )
        for candidate in report.candidates
    ]
    assert ranking == sorted(ranking, reverse=True)


def test_sweep_cli_reports_ranked_candidates(tmp_path: Path):
    # Given: a local OHLCV file that can form two walk-forward windows.
    path = tmp_path / "market.parquet"
    market_data().to_parquet(path)

    # When: the user runs the sweep command with a small parameter grid.
    result = CliRunner().invoke(
        app,
        [
            "sweep",
            str(path),
            "--fast-values",
            "2,4",
            "--slow-values",
            "3,5",
            "--breakout-values",
            "2",
            "--train-bars",
            "40",
            "--test-bars",
            "20",
            "--fee-bps",
            "0",
            "--slippage-bps",
            "0",
            "--top",
            "2",
        ],
    )

    # Then: the CLI returns ranked research candidates to the user.
    assert result.exit_code == 0
    assert "RANK 1" in result.stdout
    assert "RANK 2" in result.stdout
