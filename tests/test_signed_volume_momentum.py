import numpy as np
import pandas as pd

from quant_lab.research.signed_volume_momentum import (
    SignedVolumeMomentumSpec,
    SignedVolumeMomentumStrategy,
)


def _market(returns: list[float], volumes: list[float]) -> pd.DataFrame:
    values = [100.0]
    for value in returns:
        values.append(values[-1] * float(np.exp(value)))
    index = pd.date_range("2025-01-01", periods=len(values), freq="1h", tz="UTC")
    close = pd.Series(values, index=index, dtype=float)
    volume = pd.Series([volumes[0], *volumes], index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def test_negative_signed_volume_balance_blocks_positive_momentum() -> None:
    # Given: price drifts up overall but down bars carry much larger volume.
    frame = _market(
        [0.04, -0.01, 0.04, -0.01, 0.04, -0.01, 0.04, -0.01],
        [100.0, 1_000.0, 100.0, 1_000.0, 100.0, 1_000.0, 100.0, 1_000.0],
    )
    strategy = SignedVolumeMomentumStrategy(
        SignedVolumeMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            balance_hours=4,
            balance_threshold=0.10,
        ),
        timeframe_hours=1,
    )

    # When: signed-volume confirmed momentum signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: positive price momentum is blocked by negative participation balance.
    assert signals.iloc[-1] == 0.0


def test_signed_volume_momentum_history_is_unchanged_by_future_rows() -> None:
    # Given: a fixed flow-supported uptrend plus extreme future bars.
    frame = _market(
        [0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01],
        [900.0, 700.0, 900.0, 700.0, 900.0, 700.0, 900.0, 700.0],
    )
    strategy = SignedVolumeMomentumStrategy(
        SignedVolumeMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            balance_hours=4,
            balance_threshold=0.10,
        ),
        timeframe_hours=1,
    )
    future = _market([0.5, -0.8, 1.0], [1.0, 10_000.0, 1.0]).set_axis(
        pd.date_range(frame.index[-1] + pd.Timedelta(hours=1), periods=4, freq="1h")
    )

    # When: future observations are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
