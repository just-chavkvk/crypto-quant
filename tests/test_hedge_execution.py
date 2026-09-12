from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Final

import polars as pl
import pytest

from quant_lab.research.hedge_execution import HedgeCycle, HedgeRun, execute_hedges

START: Final = datetime(2030, 1, 1, tzinfo=UTC)
HOUR: Final = timedelta(hours=1)
RUN: Final = HedgeRun(START, START + 6 * HOUR, zero_cost=True)
CYCLE: Final = HedgeCycle(START, START + 3 * HOUR)


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * HOUR for i in range(-1, 6)],
            **{
                f"{leg}_{field}": [100.0] * 7
                for leg in ("spot", "perp", "mark")
                for field in ("open", "high", "low", "close")
            },
            "spot_volume": [10.0] * 7,
            "perp_volume": [10.0] * 7,
            "funding_rate_event": [0.0] * 7,
        }
    )


def _set(frame: pl.DataFrame, hour: int, **values: float) -> pl.DataFrame:
    return frame.with_columns(
        pl.when(pl.col("timestamp") == START + hour * HOUR)
        .then(pl.lit(value))
        .otherwise(pl.col(column))
        .alias(column)
        for column, value in values.items()
    )


@pytest.mark.parametrize("price", [50.0, 150.0])
def test_cash_funded_hedge_cancels_common_move_with_frozen_quantity(price: float) -> None:
    frame = _frame()
    for hour in (1, 3):
        frame = _set(
            frame,
            hour,
            **{
                f"{leg}_{field}": price
                for leg in ("spot", "perp", "mark")
                for field in ("open", "high", "low", "close")
            },
        )
    frame = _set(frame, 1, spot_volume=0.0, perp_volume=0.0)
    equity, trades = execute_hedges(frame, (CYCLE,), RUN)
    assert equity["equity"].to_list() == pytest.approx([10000.0] * 6)
    assert trades["quantity"][0] == 40.0
    assert trades["spot_pnl"][0] == 40 * (price - 100)
    assert trades["perp_pnl"][0] == -40 * (price - 100)
    assert trades["execution_cost"][0] == trades["net_pnl"][0] == 0.0


def test_short_notional_never_becomes_cash_or_spot_collateral() -> None:
    frame = _frame().with_columns(
        pl.lit(200.0).alias(f"{leg}_{field}")
        for leg in ("perp", "mark")
        for field in ("open", "high", "low", "close")
    )
    equity, _ = execute_hedges(frame, (CYCLE,), RUN)
    assert equity["equity"].to_list() == [10000.0] * 6
    assert equity["min_margin_ratio"].to_list() == [0.75] * 3 + [None] * 3


def test_signed_funding_uses_mark_open_and_excludes_exit_and_context() -> None:
    frame = _set(_frame(), -1, funding_rate_event=0.5)
    frame = _set(frame, 0, funding_rate_event=0.01, mark_open=110.0, mark_high=110.0)
    frame = _set(frame, 1, funding_rate_event=-0.02, mark_open=90.0, mark_low=90.0)
    frame = _set(frame, 3, funding_rate_event=0.5, mark_high=1000.0)
    equity, trades = execute_hedges(frame, (CYCLE,), RUN)
    assert trades["funding_pnl"][0] == pytest.approx(44 - 72)
    assert equity["equity"].to_list() == pytest.approx([10044.0] + [9972.0] * 5)
    assert equity["margin_breach"].to_list() == [False] * 6


def test_mark_close_valuation_preserves_executable_perpetual_exit_basis() -> None:
    frame = _set(_frame(), 0, perp_open=110.0, perp_high=110.0)
    frame = _set(frame, 1, mark_close=120.0, mark_high=120.0)
    frame = _set(frame, 3, perp_open=105.0, perp_high=105.0, mark_high=500.0, mark_close=500.0)
    equity, trades = execute_hedges(frame, (CYCLE,), RUN)
    assert equity["equity"].to_list() == [10400.0, 9600.0, 10400.0] + [10200.0] * 3
    assert trades["perp_pnl"][0] == trades["net_pnl"][0] == 200.0


def test_adverse_fill_fees_and_slippage_use_each_legs_previous_completed_hour() -> None:
    frame = _set(_frame(), -1, spot_high=110.0, spot_low=90.0, perp_high=102.0, perp_low=98.0)
    frame = _set(frame, 0, spot_high=900.0, spot_low=1.0, perp_high=900.0, perp_low=1.0)
    frame = _set(frame, 2, spot_high=101.0, spot_low=99.0, perp_high=115.0, perp_low=85.0)
    frame = _set(
        frame,
        3,
        spot_open=120.0,
        perp_open=130.0,
        spot_high=900.0,
        spot_low=1.0,
        perp_high=900.0,
        perp_low=1.0,
    )
    entry_cost = 40 * (0.42 + 100.42 * 0.001 + 0.1 + 99.9 * 0.0005)
    exit_cost = 40 * (0.072 + 119.928 * 0.001 + 0.806 + 130.806 * 0.0005)
    equity, trades = execute_hedges(frame, (CYCLE,), replace(RUN, zero_cost=False))
    assert trades["execution_cost"][0] == pytest.approx(entry_cost + exit_cost)
    assert trades["spot_pnl"][0] == 800.0
    assert trades["perp_pnl"][0] == -1200.0
    assert trades["net_pnl"][0] == pytest.approx(-400 - entry_cost - exit_cost)
    assert equity["equity"][0] == pytest.approx(10000 - entry_cost)
    assert equity["min_margin_ratio"][0] == pytest.approx((6000 - entry_cost) / 4000)
    assert equity["equity"][-1] == pytest.approx(10000 + trades["net_pnl"][0])


@pytest.mark.parametrize(
    "rate,high,breach",
    [(0.1, 205.0, True), (-0.1, 195.0, True), (0.0, 200.0, False), (0.0, 300.0, True)],
)
def test_collateral_high_bound_orders_funding_without_changing_trade_path(
    rate: float,
    high: float,
    breach: bool,
) -> None:
    frame = _set(_frame(), 0, funding_rate_event=rate, mark_high=high)
    cycles = (CYCLE, HedgeCycle(START + 4 * HOUR, START + 5 * HOUR))
    equity, trades = execute_hedges(frame, cycles, RUN)
    ratio = (6000 + min(4000 * rate, 0) + 40 * (100 - high)) / (40 * high)
    assert equity["min_margin_ratio"][0] == pytest.approx(ratio)
    assert equity["min_margin_ratio"][1] == pytest.approx((6000 + 4000 * rate) / 4000)
    assert trades["min_margin_ratio"][0] == pytest.approx(ratio)
    assert trades["margin_breach_hours"].to_list() == [int(breach), 0]
    assert equity["margin_breach"].to_list() == [breach] + [False] * 5
    assert trades["exit_time"].to_list() == [cycle.exit_time for cycle in cycles]
    assert equity["equity"][-1] == pytest.approx(10000 + 4000 * rate)


def test_quantity_changes_only_at_next_cycle_using_realized_entry_equity() -> None:
    frame = _set(_frame(), 0, funding_rate_event=0.01)
    frame = _set(frame, 2, funding_rate_event=0.01)
    frame = _set(frame, 4, funding_rate_event=0.01)
    cycles = (CYCLE, HedgeCycle(START + 4 * HOUR, START + 5 * HOUR))
    equity, trades = execute_hedges(frame, cycles, RUN)
    assert trades["quantity"].to_list() == pytest.approx([40.0, 40.32])
    assert trades["entry_equity"].to_list() == [10000.0, 10080.0]
    assert trades["funding_pnl"].to_list() == pytest.approx([80.0, 40.32])
    assert equity["equity"][-1] == pytest.approx(10120.32)


def test_zero_cost_diagnostic_preserves_cycle_and_funding() -> None:
    frame = _set(_frame(), 0, funding_rate_event=0.01)
    _, paid = execute_hedges(frame, (CYCLE,), replace(RUN, zero_cost=False))
    _, free = execute_hedges(frame, (CYCLE,), RUN)
    assert paid.select("entry_time", "exit_time", "quantity", "funding_pnl").equals(
        free.select("entry_time", "exit_time", "quantity", "funding_pnl")
    )
    assert free["execution_cost"][0] == 0.0 < paid["execution_cost"][0]
    assert free["net_pnl"][0] == pytest.approx(paid["net_pnl"][0] + paid["execution_cost"][0])


@pytest.mark.parametrize("hour", [-1, 0, 2, 5])
def test_missing_hours_and_missing_context_fail_without_compression(hour: int) -> None:
    frame = _frame().filter(pl.col("timestamp") != START + hour * HOUR)
    with pytest.raises(ValueError, match=r"calendar|context"):
        _ = execute_hedges(frame, (CYCLE,), RUN)


@pytest.mark.parametrize("hour", [0, 3])
@pytest.mark.parametrize("leg", ["spot", "perp"])
@pytest.mark.parametrize("zero_cost", [False, True])
def test_untradable_boundaries_fail_including_zero_cost(
    hour: int, leg: str, zero_cost: bool
) -> None:
    frame = _set(_frame(), hour, **{f"{leg}_volume": 0.0})
    with pytest.raises(ValueError, match=r"volume|tradable"):
        _ = execute_hedges(frame, (CYCLE,), replace(RUN, zero_cost=zero_cost))


@pytest.mark.parametrize(
    "column",
    [
        f"{leg}_{field}"
        for leg in ("spot", "perp", "mark")
        for field in ("open", "high", "low", "close")
    ],
)
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_ohlc_fails(column: str, value: float) -> None:
    with pytest.raises(ValueError):
        _ = execute_hedges(_set(_frame(), 1, **{column: value}), (CYCLE,), RUN)


@pytest.mark.parametrize(
    "column,value",
    [
        ("spot_high", 99.0),
        ("perp_low", 101.0),
        ("mark_high", 99.0),
        ("spot_volume", -1.0),
        ("perp_volume", float("nan")),
        ("funding_rate_event", float("nan")),
    ],
)
def test_invalid_bounds_volumes_and_unknown_funding_fail(column: str, value: float) -> None:
    with pytest.raises(ValueError):
        _ = execute_hedges(_set(_frame(), 1, **{column: value}), (CYCLE,), RUN)


@pytest.mark.parametrize(
    "cycles",
    [
        (HedgeCycle(START - HOUR, START + HOUR),),
        (HedgeCycle(START, RUN.end),),
        (HedgeCycle(START, START),),
        (HedgeCycle(START + HOUR, START),),
        (CYCLE, HedgeCycle(START + 2 * HOUR, START + 4 * HOUR)),
        (CYCLE, HedgeCycle(CYCLE.exit_time, START + 5 * HOUR)),
        (CYCLE, CYCLE),
        (HedgeCycle(START.replace(tzinfo=None), START + HOUR),),
        (HedgeCycle(START + timedelta(minutes=1), START + HOUR),),
    ],
)
def test_incomplete_overlapping_or_misaligned_cycles_fail(cycles: tuple[HedgeCycle, ...]) -> None:
    with pytest.raises(ValueError):
        _ = execute_hedges(_frame(), cycles, RUN)


@pytest.mark.parametrize(
    "frame",
    [
        _frame().reverse(),
        pl.concat([_frame().head(1), _frame()]),
        _frame().with_columns(pl.col("timestamp").dt.replace_time_zone(None)),
        _frame().with_columns(pl.col("timestamp") + pl.duration(minutes=1)),
        _frame().with_columns(
            pl.col("timestamp").cast(pl.Datetime("ns", "UTC")) + pl.duration(nanoseconds=1)
        ),
        _frame().with_columns(pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("timestamp")),
        _frame().with_columns(pl.lit("100").alias("spot_open")),
        _frame().drop("mark_low"),
    ],
)
def test_malformed_schema_or_calendar_fails(frame: pl.DataFrame) -> None:
    with pytest.raises(ValueError):
        _ = execute_hedges(frame, (CYCLE,), RUN)


@pytest.mark.parametrize(
    "start,end",
    [
        (START, START),
        (START, START - HOUR),
        (START.replace(tzinfo=None), RUN.end),
        (START + timedelta(minutes=1), RUN.end),
    ],
)
def test_invalid_run_boundaries_fail(start: datetime, end: datetime) -> None:
    with pytest.raises(ValueError):
        _ = execute_hedges(_frame(), (CYCLE,), HedgeRun(start, end))


def test_flat_calendar_and_empty_trade_schema_are_stable() -> None:
    equity, trades = execute_hedges(_frame(), (), RUN)
    assert equity.columns == ["timestamp", "equity", "min_margin_ratio", "margin_breach"]
    assert equity["timestamp"].to_list() == [START + i * HOUR for i in range(6)]
    assert equity["equity"].to_list() == [10000.0] * 6
    assert equity["min_margin_ratio"].null_count() == 6
    assert equity["margin_breach"].to_list() == [False] * 6
    assert trades.is_empty()
    assert (
        trades.columns
        == (
            "entry_time exit_time quantity entry_equity spot_pnl perp_pnl funding_pnl "
            "execution_cost net_pnl min_margin_ratio margin_breach_hours"
        ).split()
    )
    assert trades.schema["entry_time"] == pl.Datetime("us", "UTC")
    assert trades.schema["quantity"] == pl.Float64
    assert trades.schema["margin_breach_hours"] == pl.Int64


@pytest.mark.parametrize("column,reason", [("spot_high", "capital"), ("perp_high", "fill")])
def test_unfundable_spot_or_invalid_adverse_fill_fails(column: str, reason: str) -> None:
    frame = _set(_frame(), -1, **{column: 10000.0})
    with pytest.raises(ValueError, match=reason):
        _ = execute_hedges(frame, (CYCLE,), replace(RUN, zero_cost=False))
