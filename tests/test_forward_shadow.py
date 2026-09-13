from dataclasses import dataclass

import pandas as pd
import pytest

from quant_lab.backtest.models import BacktestConfig
from quant_lab.validation.forward_shadow import run_forward_shadow


@dataclass(frozen=True, slots=True)
class RollingMomentumStrategy:
    name: str = "rolling_momentum"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        average = data["close"].rolling(3, min_periods=3).mean()
        return (data["close"] > average).fillna(False).astype(float)


def test_forward_shadow_keeps_pre_start_warmup_for_first_shadow_entry() -> None:
    # Given: a signal that needs three historical bars and is active just before shadow starts.
    index = pd.date_range("2026-09-10 21:00", periods=6, freq="1h", tz="UTC")
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], index=index)
    data = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1_000.0},
        index=index,
    )

    # When: only the 2026-09-11 forward-shadow window is measured.
    result = run_forward_shadow(
        data,
        RollingMomentumStrategy(),
        start="2026-09-11 01:00",
        end="2026-09-11 03:00",
        config=BacktestConfig(fee_bps=0.0, slippage_bps=0.0),
        symbol="BTC/USDT",
    )

    # Then: the prior-bar signal enters on the first shadow open and earns the next-bar gain.
    assert result is not None
    assert result.metrics.number_of_trades == 1
    assert result.metrics.total_return == pytest.approx(0.2)
