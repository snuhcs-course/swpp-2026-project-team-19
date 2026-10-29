"""judge() in match_eval.py: how one matcher result is scored against the gold of a menu line."""

import uuid

from match_eval import judge  # puts backend/ on sys.path, so it comes before the app import

from app.matching.types import Candidate, ResolutionResult  # isort: skip

A, B, C, D = (uuid.uuid4() for _ in range(4))
KEY_TO_ID = {"a": A, "b": B, "c": C, "new:d": D}


def in_catalog(ref: str) -> bool:
    return not ref.startswith("new:")


def exact(pid):
    return ResolutionResult(status="exact_match", proposed_product_id=pid,
                            candidates=(Candidate(pid, 1, 1.0, "alias_exact"),))


def multi(*pids):
    return ResolutionResult(status="multi", parts=tuple(exact(p) for p in pids))


def test_exact_match_to_gold_is_correct_and_to_another_product_is_false_merge():
    assert judge("a", exact(A), KEY_TO_ID, in_catalog) == "correct"
    assert judge("a", exact(B), KEY_TO_ID, in_catalog) == "false_merge"


def test_two_product_line_needs_both_products():
    assert judge("both:a|b", multi(A, B), KEY_TO_ID, in_catalog) == "correct"
    assert judge("both:a|b", multi(A), KEY_TO_ID, in_catalog) == "partial"
    assert judge("both:a|b", exact(A), KEY_TO_ID, in_catalog) == "partial"


def test_three_product_line_is_correct_only_with_all_three():
    # I3 matching gold Q1: one menu line naming three products (Wild Turkey 81 / 101 / Rye).
    assert judge("both:a|b|c", multi(A, B, C), KEY_TO_ID, in_catalog) == "correct"
    assert judge("both:a|b|c", multi(A, B), KEY_TO_ID, in_catalog) == "partial"


def test_multi_line_with_a_product_absent_from_the_catalog_is_partial():
    # The absent product cannot be named, so naming the other one is not the whole line.
    assert judge("both:a|new:d", multi(A), KEY_TO_ID, in_catalog) == "partial"


def test_multi_naming_a_product_outside_the_gold_is_false_merge():
    assert judge("both:a|b", multi(A, C), KEY_TO_ID, in_catalog) == "false_merge"


def test_unknown_line_confirmed_is_overconfident():
    assert judge("unknown", exact(A), KEY_TO_ID, in_catalog) == "overconfident"
    assert judge("unknown", ResolutionResult(status="unmatched"), KEY_TO_ID, in_catalog) == "unmatched"
