from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.top_trader_position_lead_lag import (
    load_top_trader_position_hourly,
)


def _write_price_fixture(root: Path, filename: str, column: str, values: list[float]) -> None:
    index = pd.date_range("2025-01-01", periods=len(values), freq="1h", tz="UTC", name="timestamp")
    pd.DataFrame({column: values}, index=index).to_parquet(root / filename)


def test_top_trader_position_loader_uses_position_ratio_not_global(tmp_path: Path) -> None:
    # Given: metrics where global and top-trader position ratios are deliberately different.
    metric_index = pd.date_range(
        "2025-01-01 00:55", periods=3, freq="1h", tz="UTC", name="timestamp"
    )
    pd.DataFrame(
        {
            "count_long_short_ratio": [9.0, 9.0, 9.0],
            "sum_toptrader_long_short_ratio": [1.1, 1.2, 1.3],
            "sum_open_interest": [1_000.0, 990.0, 980.0],
        },
        index=metric_index,
    ).to_parquet(tmp_path / "BTCUSDT_futures_metrics_5m.parquet")
    _write_price_fixture(tmp_path, "BTC_USDT_1h_futures.parquet", "close", [100.0, 101.0, 102.0])
    _write_price_fixture(tmp_path, "ETH_USDT_1h_futures.parquet", "open", [200.0, 201.0, 202.0])

    # When: the preregistered top-trader-position source is loaded.
    frame = load_top_trader_position_hourly(
        tmp_path,
        start="2025-01-01",
        end="2025-01-01 03:00",
    )

    # Then: the source is the position-weighted ratio, not the global account ratio.
    assert frame["btc_top_position_ratio"].tolist() == [1.1, 1.2, 1.3]
