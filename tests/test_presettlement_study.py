from datetime import UTC, datetime

import polars as pl
import pytest

from quant_lab.research.presettlement_study import annual_primary_equity


def test_year_boundary_preserves_loss_from_a_primary_position() -> None:
    equity = pl.DataFrame(
        {
            "timestamp": [
                datetime(2022, 12, 31, 22, tzinfo=UTC),
                datetime(2022, 12, 31, 23, tzinfo=UTC),
                datetime(2023, 1, 1, tzinfo=UTC),
                datetime(2023, 1, 1, 1, tzinfo=UTC),
            ],
            "equity": [10000.0, 9900.0, 9800.0, 9700.0],
        }
    )
    result = annual_primary_equity(equity)
    assert result["total_return"][0] == pytest.approx(-0.01)
    assert result["total_return"][1] == pytest.approx(9700 / 9900 - 1)
