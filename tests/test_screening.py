"""Screening engine tests.

These check the scoring arithmetic and the honesty of the model: scores stay in
range, the reasoning trace adds up, and a reference drug scores well against its
own target while a decoy does not.
"""

from __future__ import annotations

import pytest

from app.chemistry.descriptors import compute_descriptors
from app.chemistry.library import get_compound
from app.chemistry.screening import (
    HIT_THRESHOLD,
    rank_results,
    score_compound,
)
from app.chemistry.smiles import parse_smiles
from app.chemistry.targets import get_target


def _score(slug: str, target_slug: str):
    compound = get_compound(slug)
    descriptors = compute_descriptors(parse_smiles(compound.smiles))
    return score_compound(compound.name, compound.smiles, descriptors, get_target(target_slug))


def test_reference_drug_scores_above_threshold_on_its_own_target():
    """Gefitinib was designed for EGFR; if the profile is sane it must hit."""
    result = _score("gefitinib", "egfr")
    assert result.final_score >= HIT_THRESHOLD
    assert result.verdict == "hit"


def test_decoy_scores_below_the_reference_on_the_same_target():
    reference = _score("gefitinib", "egfr")
    decoy = _score("caffeine", "egfr")
    assert decoy.final_score < reference.final_score


def test_score_is_bounded():
    for slug in ("aspirin", "caffeine", "imatinib"):
        result = _score(slug, "egfr")
        assert 0.0 <= result.final_score <= 100.0


def test_raw_score_equals_weighted_mean():
    """The reported raw score must be reproducible from the term list."""
    result = _score("gefitinib", "egfr")
    total_weight = sum(term.weight for term in result.terms)
    reconstructed = 100.0 * sum(term.points for term in result.terms) / total_weight
    assert result.raw_score == pytest.approx(reconstructed, abs=1e-6)


def test_final_score_is_raw_minus_penalties():
    result = _score("imatinib", "braf")
    deductions = sum(p.points for p in result.penalties)
    assert result.final_score == pytest.approx(max(0.0, result.raw_score - deductions), abs=1e-6)


def test_every_term_carries_an_explanation():
    result = _score("gefitinib", "egfr")
    assert len(result.terms) == 8
    for term in result.terms:
        assert term.detail, f"{term.name} has no explanation"
        assert 0.0 <= term.value <= 1.0


def test_result_declares_it_is_not_docking():
    payload = _score("gefitinib", "egfr").to_dict()
    assert "not a docking" in str(payload["method"]).lower()


def test_ranking_is_total_and_orders_by_score():
    compounds = ["aspirin", "gefitinib", "caffeine", "imatinib"]
    target = get_target("egfr")
    results = [
        score_compound(
            get_compound(slug).name,
            get_compound(slug).smiles,
            compute_descriptors(parse_smiles(get_compound(slug).smiles)),
            target,
        )
        for slug in compounds
    ]
    ranked = rank_results(results)
    scores = [r.final_score for r in ranked]
    assert scores == sorted(scores, reverse=True)

    # Reversing the input must not change the output order: ties break
    # deterministically rather than on insertion order.
    assert [r.compound_name for r in rank_results(list(reversed(results)))] == [
        r.compound_name for r in ranked
    ]


def test_polar_target_penalises_a_lipophilic_compound():
    """COMT is a polar pocket; a greasy kinase inhibitor should do worse than
    the catechol it was designed for."""
    entacapone = _score("entacapone", "comt")
    imatinib = _score("imatinib", "comt")
    assert entacapone.final_score > imatinib.final_score


def test_flat_aromatic_scores_weakly_on_shape():
    """Benzene is perfectly flat, so its shape term must be zero.

    (Caffeine is *not* a good example here -- it carries three methyl groups,
    so a third of its carbons are sp3 and it legitimately scores 0.75.)
    """
    descriptors = compute_descriptors(parse_smiles("c1ccccc1"))
    result = score_compound("Benzene", "c1ccccc1", descriptors, get_target("egfr"))
    shape = next(t for t in result.terms if t.name == "shape")
    assert shape.value == 0.0
