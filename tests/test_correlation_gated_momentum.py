import numpy as np
import pandas as pd

from quant_lab.research.correlation_gated_momentum import (
    CorrelationMomentumSpec,
    CorrelationMomentumStrategy,
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


def test_low_cross_asset_correlation_blocks_positive_own_momentum() -> None:
    # Given: own price trends up while the other asset moves with opposite return variation.
    own = _prices([0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02])
    other = _prices([0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01])
    spec = CorrelationMomentumSpec(
        lookback_hours=2,
        trend_ema_hours=3,
        correlation_hours=4,
        correlation_threshold=0.70,
    )

    # When: correlation-gated momentum signals are generated.
    signals = CorrelationMomentumStrategy(spec, 1, other).generate_signals(_market(own))

    # Then: positive own momentum is blocked because recent cross-asset returns are anti-correlated.
    assert signals.iloc[-1] == 0.0


def test_correlation_momentum_history_is_unchanged_by_future_rows() -> None:
    # Given: a fixed correlated history plus extreme future rows.
    own = _prices([0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02])
    other = _prices([0.011, 0.019, 0.011, 0.019, 0.011, 0.019, 0.011, 0.019])
    spec = CorrelationMomentumSpec(
        lookback_hours=2,
        trend_ema_hours=3,
        correlation_hours=4,
        correlation_threshold=0.70,
    )
    future_index = pd.date_range(own.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    future_own = pd.Series([500.0, 50.0, 700.0], index=future_index, dtype=float)
    future_other = pd.Series([10.0, 1_000.0, 5.0], index=future_index, dtype=float)

    # When: signals are recalculated with future observations appended.
    original = CorrelationMomentumStrategy(spec, 1, other).generate_signals(_market(own))
    with_future = CorrelationMomentumStrategy(
        spec,
        1,
        pd.concat([other, future_other]),
    ).generate_signals(_market(pd.concat([own, future_own])))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, with_future.loc[own.index])
