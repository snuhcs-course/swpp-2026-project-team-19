"""I4-P24: every expected line of the regression photos is either confirmed or in one of the three
review-required states, and nothing uncertain is confirmed."""

import collections
import json

import pytest
import regression as reg

BASELINE = json.loads(reg.BASELINE.read_text(encoding="utf-8"))
NOW = reg.match_lines(reg.load_fixtures())
REVIEW_REQUIRED = {"confirm_recommended", "choose_candidate", "no_candidate"}


def rows(condition):
    return [(pid, r) for pid, photo in NOW[condition].items() for r in photo]


@pytest.mark.parametrize("condition", reg.CONDITIONS)
def test_only_a_confirmed_line_is_stored_as_exact_match(condition):
    for _, r in rows(condition):
        assert r["state"] in REVIEW_REQUIRED | {"confirmed"}
        assert (r["state"] == "confirmed") == (r["status"] == "exact_match"), r


@pytest.mark.parametrize("condition", reg.CONDITIONS)
def test_every_confirmed_line_is_the_right_product(condition):
    confirmed = [r for _, r in rows(condition) if r["state"] == "confirmed"]
    assert confirmed and all(r["outcome"] == "correct" and r["kind"] == "known" for r in confirmed)


@pytest.mark.parametrize("condition", reg.CONDITIONS)
def test_a_line_without_a_known_product_always_needs_review(condition):
    # the product is not in the catalog, is not whisky, or the menu does not say which bottling it is
    unsure = [r for _, r in rows(condition) if r["kind"] != "known"]
    assert unsure and all(r["state"] in REVIEW_REQUIRED for r in unsure)


def test_the_three_review_states_all_occur_and_their_counts_are_pinned():
    counts = {c: dict(collections.Counter(r["state"] for _, r in rows(c))) for c in reg.CONDITIONS}
    assert counts == {
        "deployed": {"confirmed": 397, "choose_candidate": 5, "no_candidate": 16},
        "heldout": {"confirmed": 313, "confirm_recommended": 26, "choose_candidate": 44, "no_candidate": 35},
    }
    pinned = {c: dict(collections.Counter(r["state"] for photo in BASELINE["matching"][c].values() for r in photo))
              for c in reg.CONDITIONS}
    assert pinned == counts


def test_a_recommended_candidate_can_be_wrong_which_is_why_it_is_not_confirmed():
    # 미라보_02 "글렌가일(Glengyle) 킬커란 12년" with the bar's own spellings dropped: the rules recommend
    # one product and it is not Kilkerran 12. Confirming it unseen would publish the wrong bottle.
    wrong = [(pid, r) for pid, r in rows("heldout") if r["state"] == "confirm_recommended" and r["outcome"] == "ambiguous_bad"]
    assert [(pid, r["name"], r["gold"]) for pid, r in wrong] == [("011_미라보_02", "글렌가일(Glengyle) 킬커란 12년", "kilkerran-12")]
    assert wrong[0][1]["status"] == "ambiguous" and wrong[0][1]["rank1"] != "kilkerran-12"


def test_several_candidates_without_the_right_one_stay_with_the_owner():
    bad = [r for _, r in rows("heldout") if r["outcome"] == "ambiguous_bad"]
    assert len(bad) == 5 and all(r["state"] in REVIEW_REQUIRED for r in bad)


def test_a_changed_review_state_of_one_line_is_reported():
    # swapping two lines' states leaves the counts equal; the per-line check still sees it
    rows = [{"name": "A", "gold": "a", "kind": "known", "outcome": "ambiguous_ok", "status": "ambiguous", "rank1": "a",
             "state": "confirm_recommended"},
            {"name": "B", "gold": "b", "kind": "known", "outcome": "ambiguous_ok", "status": "ambiguous", "rank1": "b",
             "state": "choose_candidate"}]
    swapped = [dict(rows[0], state="choose_candidate"), dict(rows[1], state="confirm_recommended")]
    worse, better = reg.compare_matching({"heldout": {"p": rows}}, {"heldout": {"p": swapped}})
    assert len(worse) == 2 and all("review state" in line for line in worse) and not better
    assert reg.compare_matching({"heldout": {"p": rows}}, {"heldout": {"p": [dict(r) for r in rows]}}) == ([], [])
