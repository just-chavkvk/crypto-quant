from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

import pandas as pd

from quant_lab.backtest.engine import run_backtest
from quant_lab.backtest.models import BacktestConfig, PerformanceMetrics
from quant_lab.research.edge_catalog import (
    EdgeCandidateSpec,
    EdgeFamily,
    EdgeParameters,
    EdgeSearchInputError,
    build_strategy,
    candidate_catalog,
)
from quant_lab.validation.lookahead import assert_no_lookahead


@dataclass(frozen=True, slots=True)
class EdgeDataset:
    label: str
    symbol: str
    timeframe_hours: int
    data: pd.DataFrame

    def __post_init__(self) -> None:
        if self.timeframe_hours <= 0:
            raise EdgeSearchInputError("timeframe_hours must be positive")
        if len(self.data) < 2:
            raise EdgeSearchInputError(f"dataset {self.label} needs at least two candles")


@dataclass(frozen=True, slots=True)
class EdgeSearchWindows:
    discovery_start: str = "2020-01-01"
    discovery_end: str = "2023-12-31 23:59:59"
    validation_start: str = "2024-01-01"
    validation_end: str = "2025-12-31 23:59:59"
    holdout_start: str = "2026-01-01"
    holdout_end: str = "2026-12-31 23:59:59"


@dataclass(frozen=True, slots=True)
class DatasetEvaluation:
    label: str
    discovery_return: float
    validation_return: float
    validation_sharpe: float
    validation_trades: int
    holdout_return: float | None = None
    holdout_sharpe: float | None = None
    holdout_trades: int | None = None


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    family: EdgeFamily
    parameter_key: str
    parameters: EdgeParameters
    pre_holdout_pass: bool
    pre_holdout_score: float
    discovery_min_return: float
    validation_min_return: float
    validation_min_sharpe: float
    holdout_min_return: float | None
    holdout_min_sharpe: float | None
    holdout_pass: bool | None
    validation_min_trades: int = 0
    holdout_min_trades: int | None = None
    datasets: tuple[DatasetEvaluation, ...] = ()


@dataclass(frozen=True, slots=True)
class EdgeSearchReport:
    candidates: tuple[CandidateEvaluation, ...]
    champions: tuple[CandidateEvaluation, ...]


MIN_VALIDATION_TRADES: Final = 10
MIN_HOLDOUT_TRADES: Final = 3


def _period_metrics(
    dataset: EdgeDataset,
    spec: EdgeCandidateSpec,
    start: str,
    end: str,
    backtest_config: BacktestConfig,
) -> PerformanceMetrics:
    data = dataset.data.loc[start:end]
    if len(data) < 2:
        raise EdgeSearchInputError(f"dataset {dataset.label} has no usable candles in {start}..{end}")
    strategy = build_strategy(spec, dataset.timeframe_hours)
    return run_backtest(data, strategy, backtest_config, symbol=dataset.symbol).metrics


def _evaluate_pre_holdout(
    spec: EdgeCandidateSpec,
    datasets: tuple[EdgeDataset, ...],
    windows: EdgeSearchWindows,
    backtest_config: BacktestConfig,
) -> CandidateEvaluation:
    details: list[DatasetEvaluation] = []
    for dataset in datasets:
        discovery = _period_metrics(
            dataset, spec, windows.discovery_start, windows.discovery_end, backtest_config
        )
        validation = _period_metrics(
            dataset, spec, windows.validation_start, windows.validation_end, backtest_config
        )
        details.append(
            DatasetEvaluation(
                label=dataset.label,
                discovery_return=discovery.total_return,
                validation_return=validation.total_return,
                validation_sharpe=validation.sharpe_ratio,
                validation_trades=validation.number_of_trades,
            )
        )
    immutable_details = tuple(details)
    discovery_min_return = min(item.discovery_return for item in immutable_details)
    validation_min_return = min(item.validation_return for item in immutable_details)
    validation_min_sharpe = min(item.validation_sharpe for item in immutable_details)
    validation_min_trades = min(item.validation_trades for item in immutable_details)
    pre_holdout_pass = (
        discovery_min_return > 0.0
        and validation_min_return > 0.0
        and validation_min_sharpe > 0.0
        and validation_min_trades >= MIN_VALIDATION_TRADES
    )
    pre_holdout_score = validation_min_sharpe + 0.25 * validation_min_return
    return CandidateEvaluation(
        family=spec.family,
        parameter_key=spec.parameter_key,
        parameters=spec.parameters,
        pre_holdout_pass=pre_holdout_pass,
        pre_holdout_score=pre_holdout_score,
        discovery_min_return=discovery_min_return,
        validation_min_return=validation_min_return,
        validation_min_sharpe=validation_min_sharpe,
        holdout_min_return=None,
        holdout_min_sharpe=None,
        holdout_pass=None,
        validation_min_trades=validation_min_trades,
        datasets=immutable_details,
    )


def select_family_champions(
    evaluations: tuple[CandidateEvaluation, ...],
) -> tuple[CandidateEvaluation, ...]:
    champions: list[CandidateEvaluation] = []
    for family in EdgeFamily:
        family_candidates = tuple(item for item in evaluations if item.family is family)
        if not family_candidates:
            continue
        champions.append(
            max(
                family_candidates,
                key=lambda item: (item.pre_holdout_pass, item.pre_holdout_score),
            )
        )
    return tuple(champions)


def _evaluate_holdout(
    champion: CandidateEvaluation,
    spec: EdgeCandidateSpec,
    datasets: tuple[EdgeDataset, ...],
    windows: EdgeSearchWindows,
    backtest_config: BacktestConfig,
) -> CandidateEvaluation:
    holdout_returns: list[float] = []
    holdout_sharpes: list[float] = []
    holdout_trades: list[int] = []
    details: list[DatasetEvaluation] = []
    for dataset, existing in zip(datasets, champion.datasets, strict=True):
        strategy = build_strategy(spec, dataset.timeframe_hours)
        assert_no_lookahead(dataset.data, strategy, max_checks=16)
        holdout = _period_metrics(
            dataset, spec, windows.holdout_start, windows.holdout_end, backtest_config
        )
        holdout_returns.append(holdout.total_return)
        holdout_sharpes.append(holdout.sharpe_ratio)
        holdout_trades.append(holdout.number_of_trades)
        details.append(
            replace(
                existing,
                holdout_return=holdout.total_return,
                holdout_sharpe=holdout.sharpe_ratio,
                holdout_trades=holdout.number_of_trades,
            )
        )
    holdout_min_return = min(holdout_returns)
    holdout_min_sharpe = min(holdout_sharpes)
    holdout_min_trades = min(holdout_trades)
    holdout_pass = (
        champion.pre_holdout_pass
        and holdout_min_return > 0.0
        and holdout_min_sharpe > 0.0
        and holdout_min_trades >= MIN_HOLDOUT_TRADES
    )
    return replace(
        champion,
        holdout_min_return=holdout_min_return,
        holdout_min_sharpe=holdout_min_sharpe,
        holdout_min_trades=holdout_min_trades,
        holdout_pass=holdout_pass,
        datasets=tuple(details),
    )


def discover_edges(
    datasets: tuple[EdgeDataset, ...],
    backtest_config: BacktestConfig | None = None,
    windows: EdgeSearchWindows | None = None,
    candidates: tuple[EdgeCandidateSpec, ...] | None = None,
) -> EdgeSearchReport:
    if not datasets:
        raise EdgeSearchInputError("at least one dataset is required")
    config = backtest_config or BacktestConfig()
    periods = windows or EdgeSearchWindows()
    catalog = candidates or candidate_catalog()
    evaluated = tuple(
        _evaluate_pre_holdout(spec, datasets, periods, config) for spec in catalog
    )
    selected = select_family_champions(evaluated)
    spec_by_key = {(spec.family, spec.parameter_key): spec for spec in catalog}
    champions = tuple(
        _evaluate_holdout(
            champion,
            spec_by_key[(champion.family, champion.parameter_key)],
            datasets,
            periods,
            config,
        )
        for champion in selected
    )
    ranked = tuple(
        sorted(
            evaluated,
            key=lambda item: (item.pre_holdout_pass, item.pre_holdout_score),
            reverse=True,
        )
    )
    return EdgeSearchReport(candidates=ranked, champions=champions)
