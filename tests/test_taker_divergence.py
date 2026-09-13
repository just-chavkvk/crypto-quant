import pandas as pd  # noqa: PANDAS_OK

from quant_lab.research.taker_divergence import (
    TakerDivergenceSpec,
    TakerDivergenceStrategy,
)


def _sample_flow_data(*, final_flow: float) -> pd.DataFrame:
    # Given: one hour of varied but balanced flow followed by an extreme flow bar.
    index = pd.date_range("2025-01-01", periods=14, freq="5min", tz="UTC")
    flow = [-0.10, 0.10, -0.08, 0.08, -0.06, 0.06, -0.04, 0.04, -0.02, 0.02, -0.05, 0.05, 0.0, final_flow]
    open_price = [100.0] * len(index)
    close_price = [100.0, 100.1, 99.9, 100.1, 99.9, 100.1, 99.9, 100.1, 99.9, 100.1, 99.9, 100.1, 100.0, 100.0]
    quote_volume = [1_000.0] * len(index)
    taker_buy_quote_volume = [(value + 1.0) * 500.0 for value in flow]
    return pd.DataFrame(
        {
            "open": open_price,
            "high": [100.2] * len(index),
            "low": [99.8] * len(index),
            "close": close_price,
            "volume": [10.0] * len(index),
            "quote_volume": quote_volume,
            "taker_buy_quote_volume": taker_buy_quote_volume,
        },
        index=index,
    )


def test_absorbed_buy_flow_emits_short_signal():
    data = _sample_flow_data(final_flow=0.90)
    strategy = TakerDivergenceStrategy(
        TakerDivergenceSpec(
            timeframe_minutes=5,
            lookback_hours=1,
            flow_z_threshold=2.0,
            response_z_cap=0.5,
            hold_minutes=15,
        )
    )

    # When: aggressive buying becomes extreme while the bar price stays flat.
    signals = strategy.generate_signals(data)

    # Then: the primary absorption hypothesis takes the opposite, short direction.
    assert signals.iloc[-1] == -1.0


def test_absorbed_sell_flow_emits_long_signal():
    data = _sample_flow_data(final_flow=-0.90)
    strategy = TakerDivergenceStrategy(
        TakerDivergenceSpec(
            timeframe_minutes=5,
            lookback_hours=1,
            flow_z_threshold=2.0,
            response_z_cap=0.5,
            hold_minutes=15,
        )
    )

    # When: aggressive selling becomes extreme while the bar price stays flat.
    signals = strategy.generate_signals(data)

    # Then: the primary absorption hypothesis takes the opposite, long direction.
    assert signals.iloc[-1] == 1.0


def test_future_rows_do_not_change_historical_divergence_signals():
    data = _sample_flow_data(final_flow=0.90)
    extended = pd.concat(
        [
            data,
            pd.DataFrame(
                {
                    "open": [100.0, 100.0],
                    "high": [150.0, 150.0],
                    "low": [50.0, 50.0],
                    "close": [150.0, 50.0],
                    "volume": [1_000_000.0, 1_000_000.0],
                    "quote_volume": [1_000_000_000.0, 1_000_000_000.0],
                    "taker_buy_quote_volume": [999_000_000.0, 1_000_000.0],
                },
                index=pd.date_range("2025-01-01 01:10", periods=2, freq="5min", tz="UTC"),
            ),
        ]
    )
    strategy = TakerDivergenceStrategy(
        TakerDivergenceSpec(
            timeframe_minutes=5,
            lookback_hours=1,
            flow_z_threshold=2.0,
            response_z_cap=0.5,
            hold_minutes=15,
        )
    )

    # When: the same historical prefix is evaluated with arbitrary future rows appended.
    original = strategy.generate_signals(data)
    with_future = strategy.generate_signals(extended).loc[data.index]

    # Then: historical signals are identical.
    pd.testing.assert_series_equal(original, with_future)
