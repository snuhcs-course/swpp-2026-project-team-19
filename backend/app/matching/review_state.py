"""What an owner has to do with a matched menu line (I4-P24).

    confirmed            nothing: the rules settled on one product
    confirm_recommended  confirm one product: the first candidate is recommended but not settled
    choose_candidate     pick one: there are candidates and none is recommended
    no_candidate         register or search: the catalog offered nothing

Only `confirmed` may be accepted without a person. The other three are the review-required
states: an uncertain match, several candidates, and no catalog candidate.

A result counts as confirmed only when it is consistent with that (`can_auto_confirm`): status
exact_match, exactly one candidate, which is the proposed product, found by a rule and not by the
LLM layer or the embedding step, not marked confirmRecommended, and without evidence that blocks
an exact match (ageConflict, editionConflict, editionOnlyInExtracted, editionUnmatched). Any other exact_match is
treated as needing review, so a layer that returns a contradictory result cannot get a line
published unseen. `stored_status` gives the status menu import stores for a result.
"""

from enum import StrEnum

from app.matching.staged import _BLOCKING_EVIDENCE
from app.matching.types import ResolutionResult


class ReviewState(StrEnum):
    CONFIRMED = "confirmed"
    CONFIRM_RECOMMENDED = "confirm_recommended"
    CHOOSE_CANDIDATE = "choose_candidate"
    NO_CANDIDATE = "no_candidate"


REVIEW_REQUIRED = frozenset({ReviewState.CONFIRM_RECOMMENDED, ReviewState.CHOOSE_CANDIDATE, ReviewState.NO_CANDIDATE})


def can_auto_confirm(result: ResolutionResult) -> bool:
    if result.status != "exact_match" or result.proposed_product_id is None or len(result.candidates) != 1:
        return False
    [only] = result.candidates
    return (only.product_id == result.proposed_product_id and only.method == "alias"
            and not only.evidence.get("confirmRecommended")
            and not any(only.evidence.get(key) for key in _BLOCKING_EVIDENCE))


def review_state(result: ResolutionResult) -> ReviewState:
    if can_auto_confirm(result):
        return ReviewState.CONFIRMED
    if not result.candidates:
        return ReviewState.NO_CANDIDATE
    if result.candidates[0].evidence.get("confirmRecommended"):
        return ReviewState.CONFIRM_RECOMMENDED
    return ReviewState.CHOOSE_CANDIDATE


def stored_status(result: ResolutionResult) -> str:
    """The extracted_items.initial_resolution_status of a result: exact_match only for a
    confirmed line, unmatched for a line without candidates, ambiguous otherwise ("multi", one
    line naming two products, is stored as ambiguous with both products as candidates)."""
    state = review_state(result)
    if state is ReviewState.CONFIRMED:
        return "exact_match"
    return "unmatched" if state is ReviewState.NO_CANDIDATE else "ambiguous"
