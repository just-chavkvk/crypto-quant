from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Final

import polars as pl
import pytest

from quant_lab.research.cross_exchange_execution import (
    CrossCycle,
    CrossRun,
    execute_cross_exchange,
)

START: Final = datetime(2030, 1, 1, tzinfo=UTC)
HOUR: Final = timedelta(hours=1)
RUN: Final = CrossRun(START, START + 6 * HOUR, zero_cost=True)
CYCLE: Final = CrossCycle(START, START + 3 * HOUR, 1)
VENUES: Final = ("binance", "bybit")
PRICES: Final = ("open", "high", "low", "close", "mark_open", "mark_high", "mark_low", "mark_close")


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * HOUR for i in range(-1, 6)],
            **{f"{v}_{field}": [100.0] * 7 for v in VENUES for field in PRICES},
            **{f"{v}_volume": [10.0] * 7 for v in VENUES},
            **{f"{v}_funding": [0.0] * 7 for v in VENUES},
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


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("price", [50.0, 150.0])
def test_common_move_cancels_but_wallet_imbalance_changes_next_quantity(
    side: int, price: float
) -> None:
    frame = _frame()
    for hour in (1, 3):
        frame = _set(frame, hour, **{f"{v}_{field}": price for v in VENUES for field in PRICES})
    frame = _set(frame, 1, binance_volume=0.0, bybit_volume=0.0)
    cycles = (
        replace(CYCLE, binance_side=side),
        CrossCycle(START + 4 * HOUR, START + 5 * HOUR, side),
    )
    equity, trades = execute_cross_exchange(frame, cycles, RUN)
    pnl = side * 20 * (price - 100)
    assert equity["equity"].to_list() == pytest.approx([10000.0] * 6)
    assert trades["quantity"].to_list() == pytest.approx([20.0, 16.0])
    assert trades["binance_price_pnl"].to_list() == [pnl, 0.0]
    assert trades["bybit_price_pnl"].to_list() == [-pnl, 0.0]
    assert trades["binance_wallet"].to_list() == [5000 + pnl] * 2
    assert trades["bybit_wallet"].to_list() == [5000 - pnl] * 2


@pytest.mark.parametrize("side", [1, -1])
def test_funding_uses_signed_mark_open_and_excludes_context_and_exit(side: int) -> None:
    frame = _set(_frame(), -1, binance_funding=0.5, bybit_funding=-0.5)
    frame = _set(
        frame,
        0,
        binance_funding=0.01,
        bybit_funding=0.01,
        binance_mark_open=110.0,
        binance_mark_high=110.0,
    )
    frame = _set(
        frame,
        1,
        binance_funding=-0.02,
        bybit_funding=-0.02,
        bybit_mark_open=90.0,
        bybit_mark_low=90.0,
    )
    frame = _set(frame, 3, binance_funding=0.5, bybit_funding=-0.5, bybit_mark_high=1000.0)
    equity, trades = execute_cross_exchange(frame, (replace(CYCLE, binance_side=side),), RUN)
    assert trades["binance_funding_pnl"][0] == pytest.approx(side * (-22 + 40))
    assert trades["bybit_funding_pnl"][0] == pytest.approx(side * (20 - 36))
    assert equity["equity"].to_list() == pytest.approx([10000 - side * 2] + [10000 + side * 2] * 5)
    assert trades["binance_wallet"][0] == pytest.approx(5000 + side * 18)
    assert trades["bybit_wallet"][0] == pytest.approx(5000 - side * 16)


@pytest.mark.parametrize("side", [1, -1])
def test_constant_price_roundtrip_costs_29bp_exactly_once(side: int) -> None:
    equity, trades = execute_cross_exchange(
        _frame(), (replace(CYCLE, binance_side=side),), replace(RUN, zero_cost=False)
    )
    assert trades["execution_cost"][0] == pytest.approx(2000 * 0.0029)
    assert trades["net_pnl"][0] == pytest.approx(-5.8)
    assert trades["binance_wallet"][0] == pytest.approx(4997.2)
    assert trades["bybit_wallet"][0] == pytest.approx(4997.0)
    assert equity["equity"][-1] == pytest.approx(9994.2)


def test_costs_use_previous_completed_trade_range_and_actual_fill_fees() -> None:
    frame = _set(
        _frame(), -1, binance_high=110.0, binance_low=90.0, bybit_high=102.0, bybit_low=98.0
    )
    frame = _set(frame, 0, binance_high=900.0, binance_low=1.0, bybit_high=900.0, bybit_low=1.0)
    frame = _set(frame, 2, binance_high=101.0, binance_low=99.0, bybit_high=115.0, bybit_low=85.0)
    frame = _set(
        frame,
        3,
        binance_open=120.0,
        bybit_open=130.0,
        binance_high=900.0,
        binance_low=1.0,
        bybit_high=900.0,
        bybit_low=1.0,
    )
    b_entry, y_entry = 20 * (0.42 + 100.42 * 0.0005), 20 * (0.1 + 99.9 * 0.00055)
    b_exit, y_exit = 20 * (0.072 + 119.928 * 0.0005), 20 * (0.806 + 130.806 * 0.00055)
    equity, trades = execute_cross_exchange(frame, (CYCLE,), replace(RUN, zero_cost=False))
    cost = b_entry + y_entry + b_exit + y_exit
    assert trades["execution_cost"][0] == pytest.approx(cost)
    assert trades["binance_price_pnl"][0] == 400.0
    assert trades["bybit_price_pnl"][0] == -600.0
    assert trades["net_pnl"][0] == pytest.approx(-200 - cost)
    assert equity["equity"][0] == pytest.approx(10000 - b_entry - y_entry)
    assert equity["binance_margin_ratio"][0] == pytest.approx((5000 - b_entry) / 2000)
    assert equity["bybit_margin_ratio"][0] == pytest.approx((5000 - y_entry) / 2000)
    assert trades["binance_wallet"][0] == pytest.approx(5400 - b_entry - b_exit)
    assert trades["bybit_wallet"][0] == pytest.approx(4400 - y_entry - y_exit)


def test_mark_close_nav_and_trade_open_exit_use_max_entry_price_for_quantity() -> None:
    frame = _set(_frame(), 0, binance_open=200.0, binance_high=200.0)
    frame = _set(
        frame,
        1,
        binance_mark_close=250.0,
        binance_mark_high=250.0,
        bybit_mark_close=110.0,
        bybit_mark_high=110.0,
    )
    frame = _set(
        frame,
        3,
        binance_open=220.0,
        binance_high=220.0,
        bybit_open=130.0,
        bybit_high=130.0,
        binance_mark_close=999.0,
        binance_mark_high=999.0,
        bybit_mark_high=999.0,
    )
    equity, trades = execute_cross_exchange(frame, (CYCLE,), RUN)
    assert trades["quantity"][0] == 10.0
    assert equity["equity"].to_list() == [9000.0, 10400.0, 9000.0, 9900.0, 9900.0, 9900.0]
    assert trades["binance_price_pnl"][0] == 200.0
    assert trades["bybit_price_pnl"][0] == -300.0


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize(
    "stress", [(0.1, 285.0, True), (-0.1, 275.0, True), (0.0, 280.0, False), (0.0, 400.0, True)]
)
def test_individual_margin_orders_funding_and_flags_without_altering_flat_nav(
    side: int, stress: tuple[float, float, bool]
) -> None:
    rate, extreme, breach = stress
    short = "bybit" if side == 1 else "binance"
    frame = _set(
        _frame(), 0, **{f"{v}_funding": rate for v in VENUES}, **{f"{short}_mark_high": extreme}
    )
    cycles = (
        replace(CYCLE, binance_side=side),
        CrossCycle(START + 4 * HOUR, START + 5 * HOUR, side),
    )
    equity, trades = execute_cross_exchange(frame, cycles, RUN)
    ratio = (5000 + min(2000 * rate, 0) + 20 * (100 - extreme)) / (20 * extreme)
    assert equity[f"{short}_margin_ratio"][0] == pytest.approx(ratio)
    assert equity[f"{short}_margin_ratio"][1] == pytest.approx((5000 + 2000 * rate) / 2000)
    assert equity["equity"].to_list() == pytest.approx([10000.0] * 6)
    assert equity["margin_breach"].to_list() == [breach] + [False] * 5
    assert trades["min_margin_ratio"][0] == pytest.approx(ratio)
    assert trades["margin_breach_hours"].to_list() == [int(breach), 0]
    assert trades["exit_time"].to_list() == [cycle.exit_time for cycle in cycles]


def test_long_margin_uses_mark_low_and_counts_two_venue_breaches_once() -> None:
    frame = _set(_frame(), 0, binance_funding=2.49, binance_mark_low=90.0, bybit_mark_high=400.0)
    equity, trades = execute_cross_exchange(frame, (CYCLE,), RUN)
    assert equity["binance_margin_ratio"][0] == pytest.approx((5000 - 4980 - 200) / 1800)
    assert trades["margin_breach_hours"][0] == 3
    assert equity["margin_breach"].to_list() == [True] * 3 + [False] * 3


def test_cash_hours_have_null_ratios_and_typed_empty_trades() -> None:
    equity, trades = execute_cross_exchange(_frame(), (), RUN)
    assert equity["timestamp"].to_list() == [START + i * HOUR for i in range(6)]
    assert equity["equity"].to_list() == [10000.0] * 6
    assert equity["binance_margin_ratio"].null_count() == 6
    assert equity["bybit_margin_ratio"].null_count() == 6
    assert equity["margin_breach"].to_list() == [False] * 6
    assert trades.height == 0
    assert trades.schema["binance_side"] == trades.schema["margin_breach_hours"] == pl.Int64
    assert trades.schema["entry_time"] == equity.schema["timestamp"] == pl.Datetime("us", "UTC")


def test_shared_boundary_exits_before_resizing_and_funds_only_the_new_cycle() -> None:
    frame = _set(_frame(), 3, binance_funding=0.01, bybit_funding=0.02)
    cycles = (CYCLE, CrossCycle(CYCLE.exit_time, START + 5 * HOUR, -1))
    equity, trades = execute_cross_exchange(frame, cycles, replace(RUN, zero_cost=False))
    quantity = 0.4 * 4997.0 / 100
    assert trades["quantity"].to_list() == pytest.approx([20.0, quantity])
    assert trades["binance_funding_pnl"].to_list() == pytest.approx([0.0, quantity])
    assert trades["bybit_funding_pnl"].to_list() == pytest.approx([0.0, -2 * quantity])
    assert equity["equity"][-1] == pytest.approx(10000 + trades["net_pnl"].sum())


@pytest.mark.parametrize("hour", [-1, 0, 2, 5])
def test_missing_calendar_or_context_hour_fails(hour: int) -> None:
    frame = _frame().filter(pl.col("timestamp") != START + hour * HOUR)
    with pytest.raises(ValueError, match=r"calendar|context"):
        _ = execute_cross_exchange(frame, (CYCLE,), RUN)


@pytest.mark.parametrize("hour", [0, 3])
@pytest.mark.parametrize("venue", VENUES)
@pytest.mark.parametrize("zero_cost", [False, True])
def test_zero_volume_boundary_fails_in_both_cost_modes(
    hour: int, venue: str, zero_cost: bool
) -> None:
    frame = _set(_frame(), hour, **{f"{venue}_volume": 0.0})
    with pytest.raises(ValueError, match="volume"):
        _ = execute_cross_exchange(frame, (CYCLE,), replace(RUN, zero_cost=zero_cost))


@pytest.mark.parametrize(
    "column,value",
    [
        ("binance_open", 0.0),
        ("bybit_mark_close", -1.0),
        ("binance_high", 99.0),
        ("bybit_mark_low", 101.0),
        ("bybit_volume", -1.0),
        ("binance_funding", float("nan")),
        ("bybit_funding", float("inf")),
    ],
)
def test_invalid_prices_volume_or_unknown_funding_fail(column: str, value: float) -> None:
    with pytest.raises(ValueError):
        _ = execute_cross_exchange(_set(_frame(), 1, **{column: value}), (CYCLE,), RUN)


@pytest.mark.parametrize("side", [0, 2, -2, True])
def test_invalid_side_fails(side: int) -> None:
    with pytest.raises(ValueError, match="side"):
        _ = execute_cross_exchange(_frame(), (replace(CYCLE, binance_side=side),), RUN)


@pytest.mark.parametrize(
    "cycles",
    [
        (CYCLE, CYCLE),
        (replace(CYCLE, exit_time=RUN.end),),
        (replace(CYCLE, entry_time=START - HOUR),),
        (replace(CYCLE, exit_time=START),),
        (replace(CYCLE, entry_time=START + timedelta(minutes=1)),),
        (replace(CYCLE, entry_time=START.replace(tzinfo=None)),),
    ],
)
def test_invalid_or_overlapping_cycles_fail(cycles: tuple[CrossCycle, ...]) -> None:
    with pytest.raises(ValueError):
        _ = execute_cross_exchange(_frame(), cycles, RUN)
