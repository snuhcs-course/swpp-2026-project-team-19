"""The embedding candidate step without a database: settings, the TF-IDF provider, ranking and policy."""

from uuid import uuid4

import pytest

from app.adapters.embedding import (
    CharTfidfProvider,
    EmbeddingSettings,
    load_embedding_settings,
    make_embedding_provider,
)
from app.matching.embedding import (
    EmbeddingIndex,
    EmbeddingStep,
    Ranked,
    apply_policy,
    get_embedding_step,
    rank_products,
    summarize,
)
from app.matching.types import Candidate, ResolutionResult
from tests.embedding_support import FakeEmbeddingProvider

A, B, C, D, E, F = (uuid4() for _ in range(6))


# ---- settings -------------------------------------------------------------------------------


def test_settings_default_to_off_with_tfidf_and_its_floor():
    assert load_embedding_settings() == EmbeddingSettings(enabled=False, model="tfidf", min_similarity=0.38)


def test_empty_values_mean_the_defaults(monkeypatch):
    for name in ("EMBEDDING_ENABLED", "EMBEDDING_MODEL", "EMBEDDING_MIN_SIMILARITY"):
        monkeypatch.setenv(name, "")
    assert load_embedding_settings() == EmbeddingSettings()


@pytest.mark.parametrize(("raw", "floor"), [("0", 0.0), ("0.5", 0.5), ("1", 1.0)])
def test_settings_read_the_flag_and_the_floor(monkeypatch, raw, floor):
    monkeypatch.setenv("EMBEDDING_ENABLED", "TRUE")
    monkeypatch.setenv("EMBEDDING_MODEL", "tfidf")
    monkeypatch.setenv("EMBEDDING_MIN_SIMILARITY", raw)
    assert load_embedding_settings() == EmbeddingSettings(enabled=True, model="tfidf", min_similarity=floor)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("EMBEDDING_ENABLED", "yes", "EMBEDDING_ENABLED must be true or false"),
        ("EMBEDDING_MODEL", "e5-small", "Unsupported EMBEDDING_MODEL: 'e5-small'"),
        ("EMBEDDING_MIN_SIMILARITY", "high", "EMBEDDING_MIN_SIMILARITY must be a number from 0 to 1"),
        ("EMBEDDING_MIN_SIMILARITY", "-0.1", "EMBEDDING_MIN_SIMILARITY must be a number from 0 to 1"),
        ("EMBEDDING_MIN_SIMILARITY", "1.5", "EMBEDDING_MIN_SIMILARITY must be a number from 0 to 1"),
        ("EMBEDDING_MIN_SIMILARITY", "nan", "EMBEDDING_MIN_SIMILARITY must be a number from 0 to 1"),
    ],
)
def test_invalid_settings_stop_the_server_even_while_off(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=message):
        load_embedding_settings()
    with pytest.raises(RuntimeError, match=message):
        get_embedding_step()


def test_the_step_is_off_by_default():
    assert get_embedding_step() is None


def test_enabled_step_uses_tfidf_and_the_floor_and_is_one_per_process(monkeypatch):
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_MIN_SIMILARITY", "0.4")

    step = get_embedding_step()

    assert isinstance(step.provider, CharTfidfProvider) and step.min_similarity == 0.4
    assert get_embedding_step() is step  # it holds the index, so every import shares it


def test_unknown_model_has_no_provider():
    with pytest.raises(RuntimeError, match="Unsupported EMBEDDING_MODEL"):
        make_embedding_provider(EmbeddingSettings(model="bge-m3"))


def test_server_start_checks_the_settings(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("EMBEDDING_MIN_SIMILARITY", "2")
    with pytest.raises(RuntimeError, match="EMBEDDING_MIN_SIMILARITY"):
        with TestClient(app):
            pass


# ---- the TF-IDF provider ----------------------------------------------------------------------


GLENFIDDICH_TEXTS = ["Glenfiddich 12 Year Old", "글렌피딕 12년", "Glenlivet 12 Year Old", "글렌리벳 12년", "Macallan 12"]


def test_tfidf_finds_the_korean_alias_of_the_product():
    index = CharTfidfProvider().build_index(GLENFIDDICH_TEXTS)

    [row] = index.similarities(["글렌피딕 12"])

    assert max(range(len(row)), key=row.__getitem__) == 1  # 글렌피딕 12년
    assert row[1] > 0.9 and max(row[0], row[2], row[3], row[4]) < 0.38  # only the alias passes the floor
    [latin] = index.similarities(["Glenfiddich 12"])
    assert max(range(len(latin)), key=latin.__getitem__) == 0
    assert latin[0] > 0.8 and max(latin[1:]) < 0.38


def test_tfidf_ignores_case_and_spaces_and_scores_cosines():
    index = CharTfidfProvider().build_index(["Glen Fiddich", "Talisker"])

    [same, other] = index.similarities(["glenfiddich", "zzz"])

    assert same[0] == pytest.approx(1.0) and 0 <= same[1] < 1
    assert other == [0.0, 0.0]  # unseen n-grams only: an empty vector


def test_tfidf_on_an_empty_catalog_returns_empty_rows():
    assert CharTfidfProvider().build_index([]).similarities(["글렌피딕"]) == [[]]


def test_tfidf_weights_follow_the_p24_harness():
    """Smooth idf, sublinear tf and cosine over 1-3-grams, as CharTfidf in ai/eval/p24_embedding_compare.py (#78)."""
    import math

    index = CharTfidfProvider().build_index(["ab", "ac"])
    # idf: a -> log(3/3)+1 = 1; b, c, ab, ac -> log(3/2)+1
    rare = math.log(3 / 2) + 1
    # query "ab" against "ab": identical vectors; against "ac": only "a" is shared
    [row] = index.similarities(["ab"])
    assert row[0] == pytest.approx(1.0)
    assert row[1] == pytest.approx(1 / (1 + 2 * rare**2))


# ---- ranking and policy -----------------------------------------------------------------------


def test_products_score_their_best_text_and_ties_go_by_text():
    entries = [("a1", A), ("a2", A), ("b", B), ("c", C), ("d", D)]

    ranking = rank_products([0.2, 0.7, 0.5, 0.5, 0.1], entries, top_n=3)

    assert ranking == [Ranked(A, 0.7, "a2"), Ranked(B, 0.5, "b"), Ranked(C, 0.5, "c")]


def rule_candidate(product_id, rank, **evidence):
    return Candidate(product_id=product_id, rank=rank, score=1.0, method="alias", evidence={"rule": "S2", **evidence})


def ranking(*pairs):
    return [Ranked(pid, similarity, f"text {i}") for i, (pid, similarity) in enumerate(pairs)]


FULL = ranking((A, 0.9), (B, 0.8), (C, 0.7), (D, 0.6), (E, 0.5), (F, 0.45))


@pytest.mark.parametrize(
    "base",
    [
        ResolutionResult(status="exact_match", candidates=(rule_candidate(A, 1),), proposed_product_id=A),
        ResolutionResult(status="multi", candidates=(rule_candidate(A, 1), rule_candidate(B, 2)),
                         parts=(ResolutionResult(status="exact_match"),)),
    ],
)
def test_confirmed_results_are_returned_as_they_are(base):
    assert apply_policy(base, FULL, min_similarity=0.0, model_id="m") is base


def test_unmatched_line_gets_five_ambiguous_embedding_candidates_without_confirm_recommended():
    result = apply_policy(ResolutionResult(status="unmatched"), FULL, min_similarity=0.38, model_id="tfidf-char")

    assert result.status == "ambiguous" and result.proposed_product_id == A
    assert [(c.product_id, c.rank, c.method) for c in result.candidates] == [
        (A, 1, "embedding"), (B, 2, "embedding"), (C, 3, "embedding"), (D, 4, "embedding"), (E, 5, "embedding")]
    assert result.candidates[0].score == 0.9
    assert result.candidates[0].evidence == {
        "rule": "embedding", "embeddingSimilarity": 0.9, "matchedText": "text 0", "model": "tfidf-char"}
    assert not any("confirmRecommended" in c.evidence for c in result.candidates)


def test_similarity_is_rounded_in_evidence_and_score():
    [candidate] = apply_policy(ResolutionResult(status="unmatched"), [Ranked(A, 0.123456, "x")],
                               min_similarity=0.1, model_id="m").candidates
    assert (candidate.score, candidate.evidence["embeddingSimilarity"]) == (0.1235, 0.123)


def test_candidates_below_the_floor_are_dropped():
    result = apply_policy(ResolutionResult(status="unmatched"), FULL, min_similarity=0.75, model_id="m")
    assert [c.product_id for c in result.candidates] == [A, B]


def test_unmatched_line_with_nothing_above_the_floor_stays_unmatched():
    base = ResolutionResult(status="unmatched")
    assert apply_policy(base, FULL, min_similarity=0.95, model_id="m") is base
    assert apply_policy(base, [], min_similarity=0.0, model_id="m") is base


def test_single_candidate_ambiguous_line_gets_nothing_added():
    base = ResolutionResult(status="ambiguous", candidates=(rule_candidate(C, 1),), proposed_product_id=C)
    assert apply_policy(base, FULL, min_similarity=0.0, model_id="m") is base


def test_ambiguous_line_with_confirm_recommended_is_not_reordered():
    base = ResolutionResult(status="ambiguous", candidates=(
        rule_candidate(C, 1, confirmRecommended=True), rule_candidate(A, 2)), proposed_product_id=C)
    assert apply_policy(base, FULL, min_similarity=0.0, model_id="m") is base


def test_ambiguous_line_is_reordered_by_similarity_without_new_candidates():
    llm = Candidate(product_id=C, rank=1, score=0.5, method="llm", evidence={"rule": "M3a"})
    base = ResolutionResult(status="ambiguous", candidates=(
        llm, rule_candidate(uuid4(), 2), rule_candidate(B, 3)), proposed_product_id=C)
    unranked = base.candidates[1].product_id

    result = apply_policy(base, FULL, min_similarity=0.99, model_id="m")  # the floor only limits new candidates

    assert result.status == "ambiguous" and result.proposed_product_id == B
    assert [(c.product_id, c.rank, c.method) for c in result.candidates] == [
        (B, 1, "alias"), (C, 2, "llm"), (unranked, 3, "alias")]
    assert [c.evidence for c in result.candidates] == [
        {"rule": "S2", "rerankedBy": "embedding", "embeddingSimilarity": 0.8},
        {"rule": "M3a", "rerankedBy": "embedding", "embeddingSimilarity": 0.7},
        {"rule": "S2", "rerankedBy": "embedding"},
    ]


def test_ambiguous_line_already_in_embedding_order_is_unchanged():
    base = ResolutionResult(status="ambiguous", candidates=(rule_candidate(A, 1), rule_candidate(B, 2)),
                            proposed_product_id=A)
    assert apply_policy(base, FULL, min_similarity=0.0, model_id="m") is base


def test_all_zero_similarities_keep_the_rule_order_and_the_proposed_product():
    # Ranked in text order (C before B); with no similarity at all that is no preference.
    zeros = [Ranked(C, 0.0, "a"), Ranked(B, 0.0, "b"), Ranked(A, 0.0, "c")]
    base = ResolutionResult(status="ambiguous", candidates=(rule_candidate(B, 1), rule_candidate(C, 2)),
                            proposed_product_id=B)

    assert apply_policy(base, zeros, min_similarity=0.0, model_id="m") is base


def test_zero_similarity_candidates_stay_with_the_unranked_ones_in_their_order():
    unranked = uuid4()
    base = ResolutionResult(status="ambiguous", candidates=(
        rule_candidate(unranked, 1), rule_candidate(B, 2), rule_candidate(C, 3)), proposed_product_id=unranked)

    result = apply_policy(base, [Ranked(C, 0.4, "c"), Ranked(B, 0.0, "b")], min_similarity=0.0, model_id="m")

    assert [c.product_id for c in result.candidates] == [C, unranked, B]
    assert result.proposed_product_id == C


def test_partial_ties_keep_the_incoming_order_within_the_tie():
    # D ranks above B and C, which tie; the ranking lists C before B (by text), the rules B before C.
    tied = [Ranked(D, 0.8, "d"), Ranked(C, 0.5, "a"), Ranked(B, 0.5, "z"), Ranked(A, 0.2, "y")]
    base = ResolutionResult(status="ambiguous", candidates=(
        rule_candidate(A, 1), rule_candidate(B, 2), rule_candidate(C, 3), rule_candidate(D, 4)), proposed_product_id=A)

    result = apply_policy(base, tied, min_similarity=0.0, model_id="m")

    assert [(c.product_id, c.rank) for c in result.candidates] == [(D, 1), (B, 2), (C, 3), (A, 4)]
    assert result.proposed_product_id == D


def test_a_tie_at_the_top_keeps_the_proposed_product():
    tied = [Ranked(C, 0.6, "a"), Ranked(B, 0.6, "b"), Ranked(A, 0.1, "c")]
    base = ResolutionResult(status="ambiguous", candidates=(
        rule_candidate(B, 1), rule_candidate(A, 2), rule_candidate(C, 3)), proposed_product_id=B)

    result = apply_policy(base, tied, min_similarity=0.0, model_id="m")

    assert [c.product_id for c in result.candidates] == [B, C, A]
    assert result.proposed_product_id == B


def test_summary_counts_filled_unmatched_and_reordered_lines():
    unmatched, other_unmatched = ResolutionResult(status="unmatched"), ResolutionResult(status="unmatched")
    ambiguous = ResolutionResult(status="ambiguous", candidates=(rule_candidate(B, 1), rule_candidate(A, 2)))
    exact = ResolutionResult(status="exact_match")
    before = {1: unmatched, 2: other_unmatched, 3: ambiguous, 4: exact}
    after = {**before, 1: ResolutionResult(status="ambiguous"), 3: ResolutionResult(status="ambiguous")}

    assert summarize(before, after) == {"filled": 1, "still_unmatched": 1, "reordered": 1}


def test_index_search_ranks_products_per_name():
    provider = FakeEmbeddingProvider({("q", "a"): 0.5, ("q", "b alias"): 0.9})
    index = EmbeddingIndex(provider, [("a", A), ("b", B), ("b alias", B)], version=(1,))

    assert index.search(["q", "other"]) == [[Ranked(B, 0.9, "b alias"), Ranked(A, 0.5, "a")],
                                            [Ranked(A, 0.0, "a"), Ranked(B, 0.0, "b")]]
    assert provider.builds == [["a", "b", "b alias"]]


def test_product_similarities_give_each_product_its_best_text():
    provider = FakeEmbeddingProvider({("q", "a"): 0.5, ("q", "b alias"): 0.9, ("q", "b"): 0.2})
    index = EmbeddingIndex(provider, [("a", A), ("b", B), ("b alias", B), ("c", C)], version=(1,))

    assert index.product_similarities("q") == {A: 0.5, B: 0.9, C: 0.0}


def test_apply_without_target_lines_does_not_touch_the_catalog():
    step = EmbeddingStep(FakeEmbeddingProvider(), 0.38)
    results = {1: ResolutionResult(status="exact_match"), 2: ResolutionResult(status="unmatched")}

    # No session is needed: nothing is searched (line 2 has no name).
    assert step.apply(None, {1: "x", 2: None}, results) == results
    assert step.provider.builds == []
