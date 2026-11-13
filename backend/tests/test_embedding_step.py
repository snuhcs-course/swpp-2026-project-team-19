"""The embedding candidate step (I3-P40) against the catalog tables and through menu import processing.

The embedder is a fake (tests/embedding_support.py) except in the TF-IDF tests at the end.
"""

from decimal import Decimal

import pytest

from app.core.normalize import normalize
from app.matching.embedding import EmbeddingStep, catalog_entries, catalog_version, get_embedding_step
from app.matching.types import ResolutionResult
from app.models import MatchMethod, ProductAlias, ResolutionStatus
from app.services import menu_import_processing
from tests.embedding_support import FakeEmbeddingProvider
from tests.factories import make_bar, make_brand, make_product
from tests.test_menu_import_processing import (  # noqa: F401 (fixtures)
    CAOL_ILA_12,
    FakeMatchingLLM,
    caol_ila,
    glenfiddich,
    items_of,
    load_import,
    menu_lines,
    operator,
    upload,
    use_extractor,
    use_llm_layer,
)


@pytest.fixture
def use_embedding(monkeypatch):
    """Turn the step on with a fake provider (table of similarities) and the given floor."""

    def use(table=None, min_similarity=0.38, **fake):
        step = EmbeddingStep(FakeEmbeddingProvider(table, **fake), min_similarity)
        monkeypatch.setattr(menu_import_processing, "get_embedding_step", lambda: step)
        return step

    return use


def candidates_of(item):
    return [(c.product_id, c.candidate_rank, c.method, c.evidence) for c in item.candidates]


# ---- the catalog the index embeds ---------------------------------------------------------------


def test_index_embeds_display_names_and_all_aliases_of_active_products(db_session):
    brand = make_brand(db_session, "Kavalan")
    solist = make_product(db_session, brand, "Kavalan Solist Vinho", aliases=("카발란 솔리스트 비노",),
                          unsearchable_aliases=("카발란 쏠리스트",))
    make_product(db_session, brand, "Kavalan Classic", aliases=("카발란 클래식",), is_active=False)

    entries = catalog_entries(db_session)

    # make_product also stores the display name as an alias; each text is embedded once per product.
    assert sorted(entries) == sorted([
        ("Kavalan Solist Vinho", solist.id), ("카발란 솔리스트 비노", solist.id), ("카발란 쏠리스트", solist.id)])


def test_catalog_version_changes_with_aliases_and_active_products(db_session):
    brand = make_brand(db_session, "Kavalan")
    product = make_product(db_session, brand, "Kavalan Solist Vinho")
    before = catalog_version(db_session)
    assert catalog_version(db_session) == before

    db_session.add(ProductAlias(product_id=product.id, alias_text="카발란", normalized_alias=normalize("카발란")))
    db_session.flush()
    with_alias = catalog_version(db_session)
    assert with_alias != before

    product.is_active = False
    db_session.flush()
    assert catalog_version(db_session) not in (before, with_alias)


def test_new_alias_is_found_after_the_catalog_changes(db_session):
    brand = make_brand(db_session, "Kavalan")
    solist = make_product(db_session, brand, "Kavalan Solist Vinho")
    provider = FakeEmbeddingProvider({("카발란 솔리스트", "카발란 솔리스트 비노"): 0.9})
    step = EmbeddingStep(provider, 0.38)
    unmatched = {1: ResolutionResult(status="unmatched")}

    assert step.apply(db_session, {1: "카발란 솔리스트"}, unmatched) == unmatched
    assert step.apply(db_session, {1: "카발란 솔리스트"}, unmatched) == unmatched
    assert len(provider.builds) == 1  # same catalog: the index is reused

    db_session.add(ProductAlias(product_id=solist.id, alias_text="카발란 솔리스트 비노",
                                normalized_alias=normalize("카발란 솔리스트 비노")))
    db_session.flush()
    [candidate] = step.apply(db_session, {1: "카발란 솔리스트"}, unmatched)[1].candidates

    assert len(provider.builds) == 2 and "카발란 솔리스트 비노" in provider.builds[1]
    assert (candidate.product_id, candidate.method, candidate.evidence["matchedText"]) == (
        solist.id, "embedding", "카발란 솔리스트 비노")


# ---- through menu import processing -------------------------------------------------------------


def test_confirmed_lines_are_unchanged_and_unmatched_lines_get_embedding_candidates(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_embedding
):
    buffalo = make_product(db_session, make_brand(db_session, "Buffalo Trace"), "Buffalo Trace")
    makers = make_product(db_session, make_brand(db_session, "Maker's Mark"), "Maker's Mark")
    menu_lines("글렌피딕 12년", "Buffalo Trace / Maker's Mark", "글렌피딕 십이년")
    # The fake would rank other products first for the confirmed lines if they were searched.
    step = use_embedding({
        ("글렌피딕 12년", "Glenfiddich 15"): 1.0,
        ("Buffalo Trace / Maker's Mark", "Glenfiddich 12"): 1.0,
        ("글렌피딕 십이년", "글렌피딕 12년"): 0.6,
        ("글렌피딕 십이년", "Glenfiddich 15"): 0.5,
        ("글렌피딕 십이년", "Buffalo Trace"): 0.2,  # below the floor
    })

    import_id = upload(client, make_bar(db_session), operator)

    exact, multi, filled = items_of(load_import(db_session, import_id))
    assert step.provider.searches == [["글렌피딕 십이년"]]  # only the line the rules left unmatched
    assert exact.initial_resolution_status == ResolutionStatus.EXACT_MATCH
    assert [(c.product_id, c.method) for c in exact.candidates] == [(glenfiddich[12].id, MatchMethod.ALIAS)]
    assert multi.initial_resolution_status == ResolutionStatus.AMBIGUOUS  # "multi" is stored as ambiguous
    assert [(c.product_id, c.evidence["rule"]) for c in multi.candidates] == [(buffalo.id, "S1"), (makers.id, "S1")]

    assert filled.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    assert [(c.product_id, c.candidate_rank, c.method, c.score) for c in filled.candidates] == [
        (glenfiddich[12].id, 1, MatchMethod.EMBEDDING, Decimal("0.600000")),
        (glenfiddich[15].id, 2, MatchMethod.EMBEDDING, Decimal("0.500000")),
    ]
    assert filled.candidates[0].evidence == {
        "rule": "embedding", "embeddingSimilarity": 0.6, "matchedText": "글렌피딕 12년", "model": "fake-embedder"}
    assert filled.selected_product_id is None and filled.review_status.value == "pending"

    [image] = client.get(f"/api/menu-imports/{import_id}", headers=operator).json()["images"]
    item = image["items"][2]
    assert (item["initialResolutionStatus"], item["proposedProductId"]) == ("ambiguous", str(glenfiddich[12].id))
    assert [c["matchMethod"] for c in item["candidates"]] == ["embedding", "embedding"]
    assert not any("confirmRecommended" in c["evidence"] for c in item["candidates"])


def test_single_candidate_ambiguous_line_gets_nothing_added(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_embedding
):
    menu_lines("글렌피딕 12년 한정판")  # S2: ambiguous with Glenfiddich 12 only
    use_embedding({("글렌피딕 12년 한정판", "Glenfiddich 15"): 0.99})

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert item.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    [(product_id, rank, method, evidence)] = candidates_of(item)
    assert (product_id, rank, method, evidence["rule"]) == (glenfiddich[12].id, 1, MatchMethod.ALIAS, "S2")
    assert "rerankedBy" not in evidence


def test_ambiguous_line_is_reordered_but_not_extended(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_embedding
):
    sherry = make_product(db_session, glenfiddich[12].brand, "Glenfiddich 12 Sherry Cask", age_years=12,
                          edition_name="Sherry Cask")
    menu_lines("글렌피딕 12년 한정판")  # S2: brand + age, two products of that age
    use_embedding({("글렌피딕 12년 한정판", "Glenfiddich 12 Sherry Cask"): 0.7,
                   ("글렌피딕 12년 한정판", "Glenfiddich 12"): 0.5,
                   ("글렌피딕 12년 한정판", "Glenfiddich 15"): 0.9})

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert not any("confirmRecommended" in c.evidence for c in item.candidates)
    assert item.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    assert [(c.product_id, c.candidate_rank, c.method) for c in item.candidates] == [
        (sherry.id, 1, MatchMethod.ALIAS), (glenfiddich[12].id, 2, MatchMethod.ALIAS)]
    assert [c.evidence["rerankedBy"] for c in item.candidates] == ["embedding", "embedding"]


def test_unmatched_line_stays_unmatched_below_the_floor(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_embedding
):
    menu_lines("하이볼")
    use_embedding({("하이볼", "Glenfiddich 12"): 0.37}, min_similarity=0.38)

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert (item.initial_resolution_status, item.candidates) == (ResolutionStatus.UNMATCHED, [])


@pytest.mark.parametrize("fail_on", ["build", "search"])
def test_failure_in_the_step_keeps_the_earlier_results(
    client, db_session, image_storage, operator, glenfiddich, menu_lines, use_embedding, caplog, fail_on
):
    menu_lines("글렌피딕 12년", "글렌피딕 12년 한정판", "글렌피딕 십이년")
    use_embedding({("글렌피딕 십이년", "글렌피딕 12년"): 0.9}, fail=RuntimeError("embedder down"), fail_on=fail_on)

    menu_import = load_import(db_session, upload(client, make_bar(db_session), operator))

    assert menu_import.status.value == "ready_for_review"
    exact, rule_line, unknown = items_of(menu_import)
    assert [i.initial_resolution_status for i in (exact, rule_line, unknown)] == [
        ResolutionStatus.EXACT_MATCH, ResolutionStatus.AMBIGUOUS, ResolutionStatus.UNMATCHED]
    assert [(c.product_id, c.evidence["rule"]) for c in rule_line.candidates] == [(glenfiddich[12].id, "S2")]
    assert unknown.candidates == []
    assert "the embedding step failed; keeping the earlier results" in caplog.text


def test_step_runs_on_the_llm_layer_results(
    client, db_session, image_storage, operator, caol_ila, menu_lines, use_llm_layer, use_embedding
):
    menu_lines("카올 일라 12", "카올 일라 18 리미티드")
    llm = use_llm_layer(FakeMatchingLLM({"카올 일라 12": CAOL_ILA_12}))
    step = use_embedding({("카올 일라 12", "Caol Ila 18"): 0.99,  # would be first if the LLM line were searched
                          ("카올 일라 18 리미티드", "Caol Ila 18"): 0.8})

    llm_line, filled = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert len(llm.payloads) == 1
    # The LLM confirmRecommended line is not searched; the line the LLM left unmatched is filled.
    assert step.provider.searches == [["카올 일라 18 리미티드"]]
    assert [(c.product_id, c.method, c.evidence.get("confirmRecommended")) for c in llm_line.candidates] == [
        (caol_ila[12].id, MatchMethod.LLM, True)]
    assert filled.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    assert [(c.product_id, c.method) for c in filled.candidates] == [(caol_ila[18].id, MatchMethod.EMBEDDING)]


# ---- the real TF-IDF provider ----------------------------------------------------------------------


def test_tfidf_step_fills_a_line_the_rules_miss(client, db_session, image_storage, operator, menu_lines, monkeypatch):
    brand = make_brand(db_session, "Glenfiddich")  # no Korean brand alias: the rules cannot read the line
    target = make_product(db_session, brand, "Glenfiddich 12 Year Old", aliases=("글렌피딕 12년",), age_years=12)
    make_product(db_session, make_brand(db_session, "Glenlivet"), "Glenlivet 12 Year Old", aliases=("글렌리벳 12년",),
                 age_years=12)
    menu_lines("글렌피딕12 스페셜")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    get_embedding_step.cache_clear()

    [item] = items_of(load_import(db_session, upload(client, make_bar(db_session), operator)))

    assert item.initial_resolution_status == ResolutionStatus.AMBIGUOUS
    [candidate] = item.candidates  # Glenlivet stays under the 0.38 floor
    assert (candidate.product_id, candidate.method, candidate.evidence["model"], candidate.evidence["matchedText"]) == (
        target.id, MatchMethod.EMBEDDING, "tfidf-char", "글렌피딕 12년")
    assert 0.38 <= candidate.evidence["embeddingSimilarity"] < 1
