from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quant_lab.research.participation_execution import (
    ParticipationBoundaryWarning,
    ParticipationExecutionError,
    evaluate_events,
)

START = datetime(2025, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _frame(hours: int = 12) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + i * HOUR for i in range(hours)],
            "open": [100.0] * hours,
            "high": [102.0] * hours,
            "low": [98.0] * hours,
            "close": [100.0] * hours,
            "volume": [100.0] * hours,
            "signal": [0.0] * hours,
            "funding_rate_event": [0.0] * hours,
            "mark_open": [110.0] * hours,
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


def test_next_open_entry_exact_hold_and_calendar_mtm() -> None:
    frame = _set(_frame(), 1, signal=1.0)
    frame = _set(frame, 2, close=101.0)
    equity, trades = evaluate_events(frame, START, START + 12 * HOUR, zero_cost=True)
    assert equity.height == 12
    assert equity.columns == ["timestamp", "equity"]
    assert trades.select("signal_time", "entry_time", "exit_time").row(0) == (
        START + HOUR,
        START + 2 * HOUR,
        START + 6 * HOUR,
    )
    assert equity["equity"].to_list() == [10000.0, 10000.0, 10020.0] + [10000.0] * 9
    assert trades["reason"].to_list() == ["hold"]


def test_non_overlap_and_exit_hour_signal_only_enters_later() -> None:
    frame = _frame(14)
    for hour in range(8):
        frame = _set(frame, hour, signal=1.0)
    _, trades = evaluate_events(frame, START, START + 14 * HOUR, zero_cost=True)
    assert trades["entry_time"].to_list() == [START + HOUR, START + 6 * HOUR]
    assert trades["exit_time"].to_list() == [START + 5 * HOUR, START + 10 * HOUR]


@pytest.mark.parametrize("side", [1.0, -1.0])
def test_both_fill_costs_and_signed_funding_use_frozen_quantity(side: float) -> None:
    frame = _set(_frame(), 0, signal=side)
    frame = _set(frame, 1, funding_rate_event=0.01)
    frame = _set(frame, 3, funding_rate_event=-0.002)
    frame = _set(frame, 5, funding_rate_event=0.5)
    equity, trades = evaluate_events(frame, START, START + 12 * HOUR)
    # Prior range is 4/100: slippage 0.001; fees are charged on adverse fills.
    expected_execution = 20 * (0.1 + 100.1 * 0.0005) + 20 * (0.1 + 99.9 * 0.0005)
    expected_funding = -side * 20 * 110 * (0.01 - 0.002)
    assert trades["execution_cost"][0] == pytest.approx(expected_execution)
    assert trades["funding_pnl"][0] == pytest.approx(expected_funding)
    assert trades["net_pnl"][0] == pytest.approx(expected_funding - expected_execution)
    assert equity["equity"][-1] == pytest.approx(10000 + expected_funding - expected_execution)
    free_equity, free_trades = evaluate_events(frame, START, START + 12 * HOUR, True)
    assert free_trades["funding_pnl"][0] == pytest.approx(expected_funding)
    assert free_trades["execution_cost"][0] == 0.0
    assert free_equity["equity"][-1] == pytest.approx(10000 + expected_funding)
    assert trades.select("signal_time", "entry_time", "exit_time", "reason").equals(
        free_trades.select("signal_time", "entry_time", "exit_time", "reason")
    )


def test_open_slippage_uses_previous_completed_bar() -> None:
    frame = _set(_frame(), 0, signal=1.0, high=101.0, low=99.0)
    frame = _set(frame, 1, high=104.0, low=96.0)
    _, trades = evaluate_events(frame, START, START + 12 * HOUR)
    entry_fill, exit_fill = 100.06, 99.9
    expected = 20 * (0.06 + 0.1 + 0.0005 * (entry_fill + exit_fill))
    assert trades["execution_cost"][0] == pytest.approx(expected)


@pytest.mark.parametrize("side,gap_open", [(1.0, 90.0), (-1.0, 110.0)])
def test_gap_stop_precedes_funding_and_uses_worse_open(side: float, gap_open: float) -> None:
    frame = _set(_frame(), 0, signal=side)
    frame = _set(
        frame,
        2,
        open=gap_open,
        high=gap_open + 1,
        low=gap_open - 1,
        close=gap_open,
        funding_rate_event=0.1,
    )
    _, trades = evaluate_events(frame, START, START + 12 * HOUR, True)
    assert trades["reason"].to_list() == ["gap_stop"]
    assert trades["exit_time"][0] == START + 2 * HOUR
    assert trades["exit_price"][0] == gap_open
    assert trades["funding_pnl"][0] == 0.0
    assert trades["gross_pnl"][0] == pytest.approx(-200.0)


@pytest.mark.parametrize("side", [1.0, -1.0])
def test_intrabar_stop_charges_opening_funding_before_exit(side: float) -> None:
    frame = _set(_frame(), 0, signal=side)
    frame = _set(frame, 1, high=106.0, low=94.0, funding_rate_event=0.01)
    equity, trades = evaluate_events(frame, START, START + 12 * HOUR, True)
    assert trades["reason"].to_list() == ["stop"]
    assert START + HOUR < trades["exit_time"][0] < START + 2 * HOUR
    assert trades["exit_price"][0] == 100 * (1 - side * 0.05)
    assert trades["gross_pnl"][0] == pytest.approx(-100.0)
    assert trades["funding_pnl"][0] == pytest.approx(-side * 22.0)
    assert equity["equity"][-1] == pytest.approx(9900 - side * 22.0)


def test_period_starts_flat_and_boundary_events_never_force_liquidation() -> None:
    frame = _set(_frame(14), 0, signal=1.0)
    frame = _set(frame, 6, signal=-1.0)
    with pytest.warns(ParticipationBoundaryWarning, match="1.*boundary"):
        equity, trades = evaluate_events(frame, START + HOUR, START + 11 * HOUR)
    assert trades.is_empty()
    assert equity.height == 10
    assert equity["equity"].to_list() == [10000.0] * 10
    assert trades.columns == [
        "signal_time",
        "entry_time",
        "exit_time",
        "side",
        "entry_price",
        "exit_price",
        "gross_pnl",
        "execution_cost",
        "funding_pnl",
        "net_pnl",
        "reason",
    ]


@pytest.mark.parametrize("bad_hour", [0, 4, 11])
def test_missing_calendar_hours_fail_instead_of_compressing(bad_hour: int) -> None:
    frame = _frame().filter(pl.col("timestamp") != START + bad_hour * HOUR)
    with pytest.raises(ParticipationExecutionError, match="calendar"):
        _ = evaluate_events(frame, START, START + 12 * HOUR)


@pytest.mark.parametrize("column", ["funding_rate_event", "mark_open", "open"])
def test_unknown_execution_or_funding_values_fail(column: str) -> None:
    frame = _set(_frame(), 3, **{column: float("nan")})
    with pytest.raises(ParticipationExecutionError, match="finite"):
        _ = evaluate_events(frame, START, START + 12 * HOUR)


def test_duplicate_and_unsorted_calendar_fail() -> None:
    frame = _frame()
    for malformed in (frame.reverse(), pl.concat([frame.head(1), frame])):
        with pytest.raises(ParticipationExecutionError, match="calendar"):
            _ = evaluate_events(malformed, START, START + 12 * HOUR)


def test_second_entry_uses_realized_equity_without_position_additions() -> None:
    frame = _set(_frame(14), 0, signal=1.0)
    frame = _set(frame, 3, close=101.0)
    frame = _set(frame, 5, open=101.0, signal=-1.0)
    frame = _set(frame, 10, open=99.0)
    equity, trades = evaluate_events(frame, START, START + 14 * HOUR, True)
    assert trades["gross_pnl"].to_list() == pytest.approx([20.0, 20.04])
    assert equity["equity"][-1] == pytest.approx(10040.04)


def test_stopped_trade_can_use_exit_hour_signal_but_not_prior_hour_signal() -> None:
    frame = _set(_frame(), 0, signal=1.0)
    frame = _set(frame, 1, signal=-1.0)
    frame = _set(frame, 2, low=94.0, signal=-1.0)
    _, trades = evaluate_events(frame, START, START + 12 * HOUR, True)
    assert trades["entry_time"].to_list() == [START + HOUR, START + 3 * HOUR]
    assert trades["side"].to_list() == [1.0, -1.0]


@pytest.mark.parametrize("boundary", [START.replace(tzinfo=None), START + timedelta(minutes=1)])
def test_period_requires_aware_hourly_boundaries(boundary: datetime) -> None:
    with pytest.raises(ParticipationExecutionError):
        _ = evaluate_events(_frame(), boundary, START + 12 * HOUR)


@pytest.mark.parametrize("maintenance_hour", range(6))
@pytest.mark.parametrize("zero_cost", [False, True])
def test_zero_volume_anywhere_in_event_window_skips_whole_trade(
    maintenance_hour: int,
    zero_cost: bool,
) -> None:
    frame = _set(_frame(), 0, signal=1.0)
    frame = _set(frame, maintenance_hour, volume=0.0)
    equity, trades = evaluate_events(frame, START, START + 12 * HOUR, zero_cost)
    assert trades.is_empty()
    assert equity.height == 12
    assert equity["equity"].to_list() == [10000.0] * 12


def test_maintenance_does_not_compress_calendar_or_block_later_valid_trade() -> None:
    frame = _set(_frame(16), 0, signal=1.0)
    frame = _set(frame, 3, volume=0.0)
    frame = _set(frame, 6, signal=-1.0)
    equity, trades = evaluate_events(frame, START, START + 16 * HOUR)
    assert equity.height == 16
    assert trades["entry_time"].to_list() == [START + 7 * HOUR]
    assert trades["exit_time"].to_list() == [START + 11 * HOUR]
