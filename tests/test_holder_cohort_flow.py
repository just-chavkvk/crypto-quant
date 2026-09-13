from datetime import date

import polars as pl

from quant_lab.research.holder_cohort_flow import (
    HolderFlowSpec,
    build_regime_events,
    evaluate_events,
)


def test_build_regime_events_uses_fixed_sign_contract_and_transitions() -> None:
    # Given: accumulation persists for two days, then distribution begins.
    frame = pl.DataFrame(
        {
            "date": [date(2025, 1, d) for d in range(1, 7)],
            "lth": [1.0, 2.0, 2.0, -1.0, -2.0, 1.0],
            "sth": [-1.0, -2.0, -1.0, 1.0, 2.0, -1.0],
            "whale": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0],
        }
    )

    # When: the preregistered sign rule is evaluated.
    events = build_regime_events(frame)

    # Then: only the first day of each non-zero regime is an event.
    assert events.select("date", "signal").rows() == [
        (date(2025, 1, 1), 1),
        (date(2025, 1, 4), -1),
    ]


def test_evaluate_events_applies_two_day_lag_seven_day_hold_and_cost() -> None:
    # Given: one accumulation event and a deterministic daily price path.
    events = pl.DataFrame({"date": [date(2025, 1, 1)], "signal": [1]})
    prices = pl.DataFrame(
        {
            "date": [date(2025, 1, d) for d in range(1, 13)],
            "price": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 110.0, 110.0, 110.0],
        }
    )

    # When: the event is evaluated with the frozen timing contract.
    result = evaluate_events(events, prices, HolderFlowSpec())

    # Then: entry is D+2, exit is D+9, and 14 bp is charged once round trip.
    row = result.row(0, named=True)
    assert row["entry_date"] == date(2025, 1, 3)
    assert row["exit_date"] == date(2025, 1, 10)
    assert row["gross_signed_return"] == 0.1
    assert abs(row["net_signed_return"] - 0.0986) < 1e-12
