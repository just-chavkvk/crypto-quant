from __future__ import annotations

import pandas as pd

from quant_lab.strategies.base import Strategy


class LookaheadBiasError(RuntimeError):
    timestamp: str
    full_signal: float
    prefix_signal: float

    def __init__(self, timestamp: str, full_signal: float, prefix_signal: float) -> None:
        self.timestamp = timestamp
        self.full_signal = full_signal
        self.prefix_signal = prefix_signal
        message = " ".join(
            (
                f"strategy signal changed when future candles were removed at {timestamp}:",
                f"full={full_signal}, prefix={prefix_signal}",
            )
        )
        super().__init__(message)


def assert_no_lookahead(
    data: pd.DataFrame,
    strategy: Strategy,
    max_checks: int = 64,
) -> None:
    """Reject strategies whose past signal changes when future rows are removed."""
    if len(data) < 2:
        return
    full_signals = strategy.generate_signals(data).astype(float)
    step = max(1, (len(data) - 1) // max_checks)
    ends = list(range(2, len(data) + 1, step))
    if ends[-1] != len(data):
        ends.append(len(data))
    for end in ends:
        prefix = data.iloc[:end]
        prefix_signal = float(strategy.generate_signals(prefix).astype(float).iloc[-1])
        full_signal = float(full_signals.iloc[end - 1])
        if prefix_signal != full_signal:
            timestamp = str(pd.DatetimeIndex(data.index).to_list()[end - 1])
            raise LookaheadBiasError(timestamp, full_signal, prefix_signal)
