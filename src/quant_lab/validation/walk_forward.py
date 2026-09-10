from __future__ import annotations

import pandas as pd


def walk_forward_splits(data: pd.DataFrame, train_bars: int, test_bars: int):
    """Yield chronological train/test windows with no overlap leakage."""
    start = 0
    while start + train_bars + test_bars <= len(data):
        train = data.iloc[start : start + train_bars]
        test = data.iloc[start + train_bars : start + train_bars + test_bars]
        yield train, test
        start += test_bars
