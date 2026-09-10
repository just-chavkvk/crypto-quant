import pytest

from quant_lab.research.edge_catalog import (
    EdgeFamily,
    EdgeParameters,
    EdgeSearchInputError,
    candidate_catalog,
)
from quant_lab.research.edge_discovery import (
    CandidateEvaluation,
    select_family_champions,
)


def test_candidate_catalog_covers_distinct_edge_families():
    # Given: the default research catalog.
    catalog = candidate_catalog()

    # When: the represented edge families are collected.
    families = {candidate.family for candidate in catalog}

    # Then: research spans four economically different hypotheses.
    assert families == {
        EdgeFamily.MOMENTUM,
        EdgeFamily.DONCHIAN_BREAKOUT,
        EdgeFamily.VOLUME_BREAKOUT,
        EdgeFamily.VOLATILITY_BREAKOUT,
    }
    assert all(candidate.parameter_key for candidate in catalog)


def test_family_champion_is_selected_before_holdout_results_are_known():
    # Given: one stronger pre-holdout candidate and one candidate with a better holdout result.
    stronger_pre_holdout = CandidateEvaluation(
        family=EdgeFamily.MOMENTUM,
        parameter_key="strong_pre",
        parameters=EdgeParameters(lookback_hours=336, trend_hours=400),
        pre_holdout_pass=True,
        pre_holdout_score=1.2,
        discovery_min_return=0.10,
        validation_min_return=0.08,
        validation_min_sharpe=0.7,
        holdout_min_return=-0.02,
        holdout_min_sharpe=-0.1,
        holdout_pass=False,
    )
    better_holdout = CandidateEvaluation(
        family=EdgeFamily.MOMENTUM,
        parameter_key="better_holdout",
        parameters=EdgeParameters(lookback_hours=168, trend_hours=240),
        pre_holdout_pass=True,
        pre_holdout_score=0.8,
        discovery_min_return=0.08,
        validation_min_return=0.06,
        validation_min_sharpe=0.5,
        holdout_min_return=0.20,
        holdout_min_sharpe=1.5,
        holdout_pass=True,
    )

    # When: the family champion is selected.
    champions = select_family_champions((stronger_pre_holdout, better_holdout))

    # Then: holdout performance cannot change which parameters win the family.
    assert champions[0].parameter_key == "strong_pre"


def test_edge_parameters_reject_empty_parameter_sets():
    # Given / When / Then: at least one research parameter must be present.
    with pytest.raises(EdgeSearchInputError, match="at least one"):
        _ = EdgeParameters()
