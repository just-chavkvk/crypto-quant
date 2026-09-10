from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

from quant_lab.backtest.models import BacktestConfig
from quant_lab.strategies.base import EmaBreakoutStrategy
from quant_lab.validation.lookahead import assert_no_lookahead
from quant_lab.validation.walk_forward import WalkForwardConfig, evaluate_walk_forward


class SweepInputError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class EmaSweepConfig:
    fast_values: tuple[int, ...]
    slow_values: tuple[int, ...]
    breakout_values: tuple[int, ...]
    train_bars: int
    test_bars: int

    def __post_init__(self) -> None:
        values = self.fast_values + self.slow_values + self.breakout_values
        if not values or any(value <= 0 for value in values):
            raise SweepInputError("strategy parameter values must be positive")
        if self.train_bars < 2 or self.test_bars < 1:
            raise SweepInputError("train_bars must be >= 2 and test_bars must be >= 1")


@dataclass(frozen=True, slots=True)
class SweepCandidate:
    fast: int
    slow: int
    breakout: int
    passed: bool
    walk_forward_total_return: float
    walk_forward_sharpe: float
    number_of_trades: int


@dataclass(frozen=True, slots=True)
class SweepReport:
    candidates: tuple[SweepCandidate, ...]


def run_ema_sweep(
    data: pd.DataFrame,
    config: EmaSweepConfig,
    backtest_config: BacktestConfig | None = None,
    *,
    symbol: str = "UNKNOWN",
) -> SweepReport:
    bt_config = backtest_config or BacktestConfig()
    walk_config = WalkForwardConfig(train_bars=config.train_bars, test_bars=config.test_bars)
    candidates: list[SweepCandidate] = []
    for fast, slow, breakout in product(
        config.fast_values, config.slow_values, config.breakout_values
    ):
        if fast >= slow:
            continue

        def strategy_factory(
            fast_value: int = fast,
            slow_value: int = slow,
            breakout_value: int = breakout,
        ) -> EmaBreakoutStrategy:
            return EmaBreakoutStrategy(
                fast=fast_value,
                slow=slow_value,
                breakout=breakout_value,
            )

        assert_no_lookahead(data, strategy_factory())
        report = evaluate_walk_forward(
            data,
            strategy_factory=strategy_factory,
            config=walk_config,
            backtest_config=bt_config,
            symbol=symbol,
        )
        candidates.append(
            SweepCandidate(
                fast=fast,
                slow=slow,
                breakout=breakout,
                passed=report.passed,
                walk_forward_total_return=report.walk_forward.metrics.total_return,
                walk_forward_sharpe=report.walk_forward.metrics.sharpe_ratio,
                number_of_trades=report.walk_forward.metrics.number_of_trades,
            )
        )
    if not candidates:
        raise SweepInputError("parameter grid contains no valid fast < slow combination")
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            candidate.passed,
            candidate.walk_forward_sharpe,
            candidate.walk_forward_total_return,
        ),
        reverse=True,
    )
    return SweepReport(candidates=tuple(ranked))
