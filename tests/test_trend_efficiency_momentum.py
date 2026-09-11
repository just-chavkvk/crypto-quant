import numpy as np
import pandas as pd

from quant_lab.research.trend_efficiency_momentum import (
    TrendEfficiencyMomentumSpec,
    TrendEfficiencyMomentumStrategy,
)


def _prices(returns: list[float], start: float = 100.0) -> pd.Series:
    values = [start]
    for value in returns:
        values.append(values[-1] * float(np.exp(value)))
    index = pd.date_range("2025-01-01", periods=len(values), freq="1h", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def _market(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1_000.0,
        },
        index=close.index,
    )


def test_choppy_uptrend_is_blocked_by_low_path_efficiency() -> None:
    # Given: net price is rising but alternating large moves make the path inefficient.
    close = _prices([0.08, -0.07, 0.08, -0.07, 0.08, -0.07, 0.08, -0.07])
    strategy = TrendEfficiencyMomentumStrategy(
        TrendEfficiencyMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            efficiency_hours=4,
            efficiency_threshold=0.25,
        ),
        timeframe_hours=1,
    )

    # When: trend-efficiency momentum signals are generated.
    signals = strategy.generate_signals(_market(close))

    # Then: positive momentum is blocked because the recent path is too choppy.
    assert signals.iloc[-1] == 0.0


def test_efficiency_momentum_history_is_unchanged_by_future_rows() -> None:
    # Given: an efficient rising history plus extreme future rows.
    close = _prices([0.01, 0.012, 0.011, 0.013, 0.01, 0.012, 0.011, 0.013])
    strategy = TrendEfficiencyMomentumStrategy(
        TrendEfficiencyMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            efficiency_hours=4,
            efficiency_threshold=0.25,
        ),
        timeframe_hours=1,
    )
    future_index = pd.date_range(close.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    future_close = pd.Series([500.0, 50.0, 700.0], index=future_index, dtype=float)

    # When: future observations are appended.
    original = strategy.generate_signals(_market(close))
    extended = strategy.generate_signals(_market(pd.concat([close, future_close])))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, extended.loc[close.index])
