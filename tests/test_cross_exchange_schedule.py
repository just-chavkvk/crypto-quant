from datetime import UTC, datetime

import polars as pl

from quant_lab.research.cross_exchange_execution import CrossRun
from quant_lab.research.cross_exchange_schedule import build_monthly_schedule


def _frame() -> pl.DataFrame:
    times = pl.datetime_range(
        datetime(2021, 12, 25, tzinfo=UTC),
        datetime(2022, 2, 1, tzinfo=UTC),
        interval="1h",
        closed="left",
        eager=True,
    )
    return pl.DataFrame({"timestamp": times}).with_columns(
        pl.lit(1.0).alias("binance_volume"),
        pl.lit(1.0).alias("bybit_volume"),
        pl.when(pl.col("timestamp").dt.hour().is_in([0, 8, 16]))
        .then(0.00009)
        .otherwise(0.0)
        .alias("binance_funding"),
        pl.when(pl.col("timestamp").dt.hour().is_in([0, 8, 16]))
        .then(0.00010)
        .otherwise(0.0)
        .alias("bybit_funding"),
    )


def test_current_month_funding_cannot_change_month_entry_side() -> None:
    run = CrossRun(datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 2, 1, tzinfo=UTC))
    frame = _frame().with_columns(
        pl.when(pl.col("timestamp") >= run.start)
        .then(-1.0)
        .otherwise(pl.col("bybit_funding"))
        .alias("bybit_funding")
    )
    result = build_monthly_schedule(frame, run)
    assert len(result.cycles) == 1
    assert result.cycles[0].binance_side == 1
    assert result.cycles[0].entry_time == datetime(2022, 1, 1, 1, tzinfo=UTC)
    assert result.cycles[0].exit_time == datetime(2022, 1, 31, 23, tzinfo=UTC)


def test_identical_published_rates_produce_cash_month() -> None:
    run = CrossRun(datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 2, 1, tzinfo=UTC))
    frame = _frame().with_columns(pl.col("binance_funding").alias("bybit_funding"))
    result = build_monthly_schedule(frame, run)
    assert result.cycles == ()
    assert result.cash_months == 1
