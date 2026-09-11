import pandas as pd

from quant_lab.research.turnover_momentum import (
    TurnoverMomentumSpec,
    TurnoverMomentumStrategy,
)


def _market(volumes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(volumes), freq="1h", tz="UTC")
    close = pd.Series([100.0 + offset for offset in range(len(volumes))], index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volumes,
            "sum_open_interest": [1_000.0] * len(volumes),
        },
        index=index,
    )


def test_low_recent_turnover_blocks_positive_momentum() -> None:
    # Given: price is rising while recent volume collapses relative to unchanged OI.
    frame = _market([100.0, 100.0, 100.0, 100.0, 100.0, 20.0, 10.0, 10.0, 10.0])
    strategy = TurnoverMomentumStrategy(
        TurnoverMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            turnover_hours=2,
            turnover_history_hours=4,
        ),
        timeframe_hours=1,
    )

    # When: turnover-confirmed momentum signals are generated.
    signals = strategy.generate_signals(frame)

    # Then: the final positive momentum observation is blocked by weak participation.
    assert signals.iloc[-1] == 0.0


def test_turnover_momentum_history_is_unchanged_by_future_rows() -> None:
    # Given: a rising market with stable participation and extreme future volume.
    frame = _market([100.0] * 10)
    strategy = TurnoverMomentumStrategy(
        TurnoverMomentumSpec(
            lookback_hours=2,
            trend_ema_hours=3,
            turnover_hours=2,
            turnover_history_hours=4,
        ),
        timeframe_hours=1,
    )
    future = _market([10_000.0, 1.0, 20_000.0]).set_axis(
        pd.date_range(frame.index[-1] + pd.Timedelta(hours=1), periods=3, freq="1h")
    )

    # When: future observations are appended.
    original = strategy.generate_signals(frame)
    extended = strategy.generate_signals(pd.concat([frame, future]))

    # Then: historical decisions remain identical.
    pd.testing.assert_series_equal(original, extended.loc[frame.index])
