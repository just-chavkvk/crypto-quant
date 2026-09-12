from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from quant_lab.data.binance_archive import ArchiveError
from quant_lab.research.presettlement_execution import PressureRun, evaluate_presettlement


def _frame() -> pl.DataFrame:
    times = [datetime(2022, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(17)]
    return pl.DataFrame(
        {
            "timestamp": times,
            **{n: np.full(17, 100.0) for n in ("open", "high", "low", "close")},
            "volume": np.ones(17),
            "funding_rate_event": [0.0] * 8 + [0.5] + [0.0] * 8,
        }
    )


def _run(zero_cost: bool = False) -> PressureRun:
    return PressureRun(
        datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 1, 1, 16, tzinfo=UTC), zero_cost
    )


def test_clock_entry_and_pre_funding_exit_with_exact_friction() -> None:
    r = evaluate_presettlement(_frame(), _run())
    assert r.trades.height == 1
    assert r.trades["entry_time"][0].hour == 7
    assert r.trades["exit_time"][0].hour == 8
    assert r.trades["execution_cost"][0] == pytest.approx(2.8)
    assert r.equity["equity"][-1] == pytest.approx(9997.2)
    assert r.boundary_signals == 1


def test_zero_cost_diagnostic_preserves_clock_and_excludes_exit_funding() -> None:
    r = evaluate_presettlement(_frame(), _run(True))
    assert r.equity["equity"][-1] == 10000.0
    assert r.trades["execution_cost"][0] == 0.0


def test_stop_exits_during_held_hour_without_future_range_entry_cost() -> None:
    frame = _frame().with_columns(
        pl.when(pl.col("timestamp").dt.hour() == 7)
        .then(106.0)
        .otherwise(pl.col("high"))
        .alias("high")
    )
    r = evaluate_presettlement(frame, _run())
    assert r.trades["reason"][0] == "stop"
    assert r.trades["exit_price"][0] == 105.0
    assert r.trades["gross_pnl"][0] == -100.0
    assert r.trades["exit_time"][0].hour == 7


def test_missing_hour_is_rejected_instead_of_compressed() -> None:
    frame = _frame().filter(pl.col("timestamp").dt.hour() != 4)
    with pytest.raises(ArchiveError, match="continuous"):
        _ = evaluate_presettlement(frame, _run())


def test_unavailable_boundary_is_counted_without_synthetic_fill() -> None:
    frame = _frame().with_columns(
        pl.when(pl.col("timestamp").dt.hour() == 8)
        .then(0.0)
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    r = evaluate_presettlement(frame, _run())
    assert r.trades.height == 0
    assert r.untradable_boundaries == 1
