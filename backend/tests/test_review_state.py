"""Review states of matched lines (I4-P24): only a consistent exact_match is confirmed."""

from uuid import UUID

import pytest

from app.matching import ProductInfo
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.review_state import REVIEW_REQUIRED, ReviewState, can_auto_confirm, review_state, stored_status
from app.matching.staged import resolve_product_staged
from app.matching.types import Candidate, ExtractedProduct, ResolutionResult

STAGES = {"S1", "S2", "S2b", "S3"}
A, B = UUID(int=1), UUID(int=2)


def candidate(product=A, rank=1, method="alias", **evidence):
    return Candidate(product_id=product, rank=rank, score=1.0, method=method, evidence=evidence)


def exact(*candidates, proposed=A):
    return ResolutionResult("exact_match", tuple(candidates), proposed)


def ambiguous(*candidates):
    return ResolutionResult("ambiguous", tuple(candidates))


@pytest.mark.parametrize("result, state, status", [
    (exact(candidate(rule="alias")), ReviewState.CONFIRMED, "exact_match"),
    (exact(candidate(rule="S2")), ReviewState.CONFIRMED, "exact_match"),
    # uncertain: one recommended product, also when an LLM pick is merged ahead of rule candidates
    (ambiguous(candidate(confirmRecommended=True, rule="S2b")), ReviewState.CONFIRM_RECOMMENDED, "ambiguous"),
    (ambiguous(candidate(method="llm", confirmRecommended=True), candidate(B, 2)), ReviewState.CONFIRM_RECOMMENDED, "ambiguous"),
    # several candidates, or one that nothing recommends
    (ambiguous(candidate(), candidate(B, 2)), ReviewState.CHOOSE_CANDIDATE, "ambiguous"),
    (ambiguous(candidate(rule="S2")), ReviewState.CHOOSE_CANDIDATE, "ambiguous"),
    (ambiguous(candidate(method="embedding"), candidate(B, 2, method="embedding")), ReviewState.CHOOSE_CANDIDATE, "ambiguous"),
    # one line naming two products
    (ResolutionResult("multi", (candidate(multiProduct=True), candidate(B, 2, multiProduct=True))), ReviewState.CHOOSE_CANDIDATE, "ambiguous"),
    # no catalog candidate
    (ResolutionResult("unmatched"), ReviewState.NO_CANDIDATE, "unmatched"),
    (ResolutionResult("ambiguous"), ReviewState.NO_CANDIDATE, "unmatched"),
])
def test_states_and_stored_status(result, state, status):
    assert review_state(result) is state and stored_status(result) == status
    assert (state in REVIEW_REQUIRED) == (state is not ReviewState.CONFIRMED) == (not can_auto_confirm(result))


@pytest.mark.parametrize("result, state", [
    (exact(candidate(method="llm")), ReviewState.CHOOSE_CANDIDATE),                    # the LLM layer never confirms
    (exact(candidate(method="embedding")), ReviewState.CHOOSE_CANDIDATE),              # nor does the embedding step
    (exact(candidate(confirmRecommended=True)), ReviewState.CONFIRM_RECOMMENDED),      # recommended is not settled
    (exact(candidate(B), candidate(A, 2)), ReviewState.CHOOSE_CANDIDATE),              # proposes another product than rank 1
    (exact(candidate(), proposed=None), ReviewState.CHOOSE_CANDIDATE),
    (exact(), ReviewState.NO_CANDIDATE),
])
def test_a_contradictory_exact_match_needs_review(result, state):
    assert not can_auto_confirm(result) and review_state(result) is state
    assert stored_status(result) != "exact_match"


@pytest.fixture
def catalog():
    brand = UUID(int=100)
    products = [ProductInfo(UUID(int=1), "Glenfiddich 12", age_years=12, brand_id=brand),
                ProductInfo(UUID(int=2), "Glenfiddich 15", age_years=15, brand_id=brand),
                ProductInfo(UUID(int=3), "Glenfiddich 15 Distillery Edition", 15, "Distillery Edition", brand_id=brand)]
    aliases = [(UUID(int=1), "Glenfiddich 12"), (UUID(int=1), "글렌피딕 12"), (UUID(int=2), "Glenfiddich 15"),
               (UUID(int=3), "Glenfiddich 15 Distillery Edition")]
    return InMemoryCatalog(products, aliases, brand_aliases=[(brand, "Glenfiddich"), (brand, "글렌피딕")])


@pytest.mark.parametrize("name, state", [
    ("Glenfiddich 12", ReviewState.CONFIRMED),            # exact alias
    ("글렌피딕 12년", ReviewState.CONFIRMED),               # brand + age rule, one product
    ("Glenfiddich", ReviewState.CHOOSE_CANDIDATE),        # brand only: several products
    ("Glenfidich 15", ReviewState.CONFIRMED),             # one letter off with the same number (S3)
    ("Glenfidic 15", ReviewState.CONFIRM_RECOMMENDED),    # two letters off: recommended, not settled
    ("Lagavulin 16", ReviewState.NO_CANDIDATE),           # not in the catalog
])
def test_rule_matcher_results_fall_into_the_four_states(catalog, name, state):
    result = resolve_product_staged(ExtractedProduct(product_name=name), catalog, STAGES)
    assert review_state(result) is state, (result.status, result.candidates)
    assert (stored_status(result) == "exact_match") == (state is ReviewState.CONFIRMED)
