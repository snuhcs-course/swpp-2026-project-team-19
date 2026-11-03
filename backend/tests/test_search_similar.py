"""The similar-products step of customer search (API spec 3.10.1, step 5), behind SEARCH_SIMILAR_ENABLED.

Most tests use the real character TF-IDF on a small catalog shaped like the service catalog; the
tie, failure and index tests use the fake provider of tests/embedding_support.py.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.adapters.embedding import CharTfidfProvider
from app.core.normalize import normalize
from app.matching.embedding import catalog_entries, catalog_version
from app.models import ProductAlias, ProductSearchCount, UnmatchedSearchQuery
from app.services import search_query
from app.services.search_similar import (
    SIMILAR_LIMIT,
    SimilarProducts,
    SimilarSearchSettings,
    get_similar_products,
    load_similar_search_settings,
)
from tests.embedding_support import FakeEmbeddingProvider
from tests.factories import make_bar, make_brand, make_product, publish_menu

T0 = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)


# ---- settings -------------------------------------------------------------------------------


def test_settings_default_to_off_with_the_tfidf_floor():
    assert load_similar_search_settings() == SimilarSearchSettings(enabled=False, min_similarity=0.38)
    assert get_similar_products() is None


def test_empty_values_mean_the_defaults(monkeypatch):
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "")
    monkeypatch.setenv("SEARCH_SIMILAR_MIN_SIMILARITY", "")
    assert load_similar_search_settings() == SimilarSearchSettings()


@pytest.mark.parametrize(("raw", "floor"), [("0", 0.0), ("0.5", 0.5), ("1", 1.0)])
def test_settings_read_the_flag_and_the_floor(monkeypatch, raw, floor):
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "TRUE")
    monkeypatch.setenv("SEARCH_SIMILAR_MIN_SIMILARITY", raw)
    assert load_similar_search_settings() == SimilarSearchSettings(enabled=True, min_similarity=floor)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SEARCH_SIMILAR_ENABLED", "yes", "SEARCH_SIMILAR_ENABLED must be true or false"),
        ("SEARCH_SIMILAR_MIN_SIMILARITY", "high", "SEARCH_SIMILAR_MIN_SIMILARITY must be a number from 0 to 1"),
        ("SEARCH_SIMILAR_MIN_SIMILARITY", "-0.1", "SEARCH_SIMILAR_MIN_SIMILARITY must be a number from 0 to 1"),
        ("SEARCH_SIMILAR_MIN_SIMILARITY", "1.5", "SEARCH_SIMILAR_MIN_SIMILARITY must be a number from 0 to 1"),
        ("SEARCH_SIMILAR_MIN_SIMILARITY", "nan", "SEARCH_SIMILAR_MIN_SIMILARITY must be a number from 0 to 1"),
    ],
)
def test_invalid_settings_raise_even_while_off(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=message):
        load_similar_search_settings()
    with pytest.raises(RuntimeError, match=message):
        get_similar_products()


def test_enabled_step_uses_tfidf_and_the_floor_and_is_one_per_process(monkeypatch):
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "true")
    monkeypatch.setenv("SEARCH_SIMILAR_MIN_SIMILARITY", "0.5")

    finder = get_similar_products()

    assert isinstance(finder._cache.provider, CharTfidfProvider) and finder.min_similarity == 0.5
    assert finder._cache.searchable_only
    assert get_similar_products() is finder  # it holds the index, so every search shares it


def test_server_start_checks_the_settings(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("SEARCH_SIMILAR_MIN_SIMILARITY", "2")
    with pytest.raises(RuntimeError, match="SEARCH_SIMILAR_MIN_SIMILARITY"):
        with TestClient(app):
            pass


# ---- fixtures ---------------------------------------------------------------------------------


@pytest.fixture
def catalog(db_session):
    """A few products with aliases as in ai/catalog/catalog_v2_service.json."""
    glenfiddich = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    jack = make_brand(db_session, "Jack Daniel's", aliases=("잭다니엘", "잭 다니엘스"))
    balvenie = make_brand(db_session, "The Balvenie", aliases=("발베니",))
    products = {
        "gf12": make_product(db_session, glenfiddich, "Glenfiddich 12", age_years=12, aliases=(
            "글렌피딕 12년", "Glenfiddich Aged 12 Years", "글렌피딕 12년 숙성")),
        "gf12sherry": make_product(db_session, glenfiddich, "Glenfiddich 12 Sherry Cask Finish", age_years=12, aliases=(
            "글렌피딕 12년 셰리 캐스크 피니시", "글렌피딕 12년 쉐리")),
        "gf15": make_product(db_session, glenfiddich, "Glenfiddich 15", age_years=15, aliases=(
            "글렌피딕 15년", "글렌피딕 15년 솔레라")),
        "gf18": make_product(db_session, glenfiddich, "Glenfiddich 18", age_years=18, aliases=(
            "글렌피딕 18년",)),
        "jd7": make_product(db_session, jack, "Jack Daniel's Old No.7", aliases=(
            "잭다니엘 올드 넘버 7", "잭 다니엘스 올드 넘버 7", "잭다니엘 넘버 7", "잭다니엘 Old No.7")),
        "jd100": make_product(db_session, jack, "Jack Daniel's Single Barrel 100 Proof", aliases=(
            "잭다니엘 싱글 배럴 100 프루프", "잭다니엘스 싱글 배럴 100 프루프")),
        "dw12": make_product(db_session, balvenie, "The Balvenie 12 DoubleWood", age_years=12, aliases=(
            "발베니 12년 더블우드", "발베니 더블우드 12")),
    }
    return products


@pytest.fixture
def similar_on(monkeypatch):
    """Turn the step on as the server would, with the real TF-IDF provider."""
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "true")
    get_similar_products.cache_clear()


@pytest.fixture
def use_finder(monkeypatch):
    """Turn the step on with a given finder (e.g. one with a fake provider)."""

    def use(finder):
        monkeypatch.setattr(search_query, "get_similar_products", lambda: finder)
        return finder

    return use


def search(client, **params):
    response = client.get("/api/search/bars", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def names(body):
    return [p["displayName"] for p in body["matchedProducts"]]


def counts(db_session):
    products = {(row.product_id, row.search_count) for row in db_session.scalars(select(ProductSearchCount))}
    unmatched = {(row.normalized_query, row.search_count) for row in db_session.scalars(select(UnmatchedSearchQuery))}
    return products, unmatched


# ---- off: unchanged -----------------------------------------------------------------------------


def test_off_a_close_query_stays_none_and_counts_as_unrecognized(client, db_session, catalog):
    body = search(client, query="글렌피딕 12년산")

    assert body == {"query": "글렌피딕 12년산", "matchType": "none", "matchedProducts": [], "items": [], "truncated": False}
    assert counts(db_session) == (set(), {("글렌피딕12산", 1)})


# ---- on: similar products -----------------------------------------------------------------------


def test_a_query_no_alias_matches_returns_the_most_similar_products(client, db_session, catalog, similar_on):
    near = make_bar(db_session, "Near Bar", latitude="37.478100", longitude="126.951000")
    far = make_bar(db_session, "Far Bar", latitude="37.490000", longitude="126.951000")
    publish_menu(db_session, far, [(catalog["gf12"], "글렌피딕 12Y", [("잔", 30, 15000)])], published_at=T0)
    publish_menu(db_session, near, [(catalog["gf15"], "글렌피딕 15", [("잔", 30, 19000)]),
                                    (catalog["gf12"], "Glenfiddich 12", [("잔", 30, 14000)])],
                 published_at=T0 - timedelta(days=1))

    body = search(client, query="글렌피딕 12년산", lat=37.478, lng=126.951)

    assert (body["query"], body["matchType"], body["truncated"]) == ("글렌피딕 12년산", "similar", False)
    # Best first: the 12, then the 12 Sherry, then the other ages; never more than five.
    assert names(body)[:2] == ["Glenfiddich 12", "Glenfiddich 12 Sherry Cask Finish"]
    assert set(names(body)) <= {p.display_name for p in catalog.values()} and len(names(body)) <= SIMILAR_LIMIT
    assert "Jack Daniel's Old No.7" not in names(body)
    result_counts = {p["displayName"]: p["resultCount"] for p in body["matchedProducts"]}
    assert (result_counts["Glenfiddich 12"], result_counts["Glenfiddich 15"]) == (2, 1)
    assert body["matchedProducts"][0] == {
        "productId": str(catalog["gf12"].id), "displayName": "Glenfiddich 12", "brandName": "Glenfiddich",
        "ageYears": 12, "editionName": None, "resultCount": 2,
    }
    # Rows as in partial: by distance, then bar name and product name.
    assert [(i["barName"], i["productDisplayName"]) for i in body["items"]] == [
        ("Near Bar", "Glenfiddich 12"), ("Near Bar", "Glenfiddich 15"), ("Far Bar", "Glenfiddich 12")]


def test_rows_without_a_location_are_newest_menu_first(client, db_session, catalog, similar_on):
    old = make_bar(db_session, "Old Menu Bar")
    new = make_bar(db_session, "New Menu Bar")
    publish_menu(db_session, old, [(catalog["gf12"], "12", [(None, 30, 1)])], published_at=T0 - timedelta(days=2))
    publish_menu(db_session, new, [(catalog["gf12"], "12", [(None, 30, 1)])], published_at=T0)

    body = search(client, query="글렌피딕 12년산", limit=1)

    assert [i["barName"] for i in body["items"]] == ["New Menu Bar"]
    assert body["truncated"] and body["matchedProducts"][0]["resultCount"] == 2


def test_jack_daniels_7_finds_old_no_7(client, db_session, catalog, similar_on):
    body = search(client, query="잭다니엘 7")

    assert body["matchType"] == "similar"
    assert names(body)[0] == "Jack Daniel's Old No.7"
    assert body["items"] == []  # recognized as similar, but no bar sells it


def test_at_most_five_products_come_back(client, db_session, catalog, similar_on):
    brand = make_brand(db_session, "Glen Test")
    for age in (10, 11, 13, 14, 16, 17):
        make_product(db_session, brand, f"Glenfiddich Test {age}", aliases=(f"글렌피딕 {age}년",), age_years=age)

    body = search(client, query="글렌피딕 1년산")

    assert body["matchType"] == "similar"
    assert len(body["matchedProducts"]) == SIMILAR_LIMIT


def test_below_the_floor_the_query_stays_none_and_counts_as_unrecognized(client, db_session, catalog, similar_on):
    body = search(client, query="아드벡 우가달")

    assert (body["matchType"], body["matchedProducts"], body["items"]) == ("none", [], [])
    assert counts(db_session) == (set(), {("아드벡우가달", 1)})


def test_the_floor_is_inclusive(client, db_session, use_finder):
    brand = make_brand(db_session, "Kavalan")
    make_product(db_session, brand, "Kavalan Solist Vinho")
    make_product(db_session, brand, "Kavalan Classic")
    use_finder(SimilarProducts(FakeEmbeddingProvider(
        {("카발란 솔리", "Kavalan Solist Vinho"): 0.38, ("카발란 솔리", "Kavalan Classic"): 0.3799}), 0.38))

    assert names(search(client, query="카발란 솔리")) == ["Kavalan Solist Vinho"]


def test_a_higher_floor_drops_weaker_products(client, db_session, catalog, monkeypatch):
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "true")
    monkeypatch.setenv("SEARCH_SIMILAR_MIN_SIMILARITY", "0.9")
    get_similar_products.cache_clear()

    body = search(client, query="글렌피딕 12년산")

    assert (body["matchType"], names(body)) == ("similar", ["Glenfiddich 12"])


def test_similar_searches_count_nowhere(client, db_session, catalog, similar_on):
    search(client, query="글렌피딕 12년산")
    search(client, query="잭다니엘 7", source="recent")

    assert counts(db_session) == (set(), set())


def test_the_earlier_steps_give_the_same_responses_when_on(client, db_session, catalog, monkeypatch):
    publish_menu(db_session, make_bar(db_session), [(catalog["gf12"], "12", [(None, 30, 1)])], published_at=T0)
    queries = {"글렌피딕 12년": "alias_exact", "글렌피딕": "brand", "피딕 1": "partial", "더블우드": "partial"}

    off = {query: search(client, query=query) for query in queries}
    monkeypatch.setenv("SEARCH_SIMILAR_ENABLED", "true")
    get_similar_products.cache_clear()
    on = {query: search(client, query=query) for query in queries}

    assert {query: body["matchType"] for query, body in on.items()} == queries
    assert on == off


def test_product_id_searches_never_reach_the_step(client, db_session, catalog, use_finder):
    provider = FakeEmbeddingProvider()
    use_finder(SimilarProducts(provider, 0.38))
    retired = make_product(db_session, make_brand(db_session, "Port Ellen"), "Port Ellen", is_active=False)

    assert search(client, productId=str(catalog["jd7"].id))["matchType"] == "product"
    assert search(client, productId=str(retired.id))["matchType"] == "none"
    assert provider.builds == provider.searches == []


def test_inactive_products_and_unsearchable_aliases_are_not_indexed(client, db_session, catalog, similar_on):
    brand = make_brand(db_session, "Kavalan")
    make_product(db_session, brand, "Kavalan Solist Vinho", aliases=("카발란 솔리스트 비노",), is_active=False)
    make_product(db_session, brand, "Kavalan Classic", unsearchable_aliases=("카발란 솔리스트 포트",))

    body = search(client, query="카발란 솔리스트")

    assert (body["matchType"], body["matchedProducts"]) == ("none", [])


def test_the_index_holds_display_names_and_searchable_aliases_of_active_products(db_session):
    brand = make_brand(db_session, "Kavalan")
    solist = make_product(db_session, brand, "Kavalan Solist Vinho", aliases=("카발란 솔리스트 비노",),
                          unsearchable_aliases=("카발란 쏠리스트",))
    make_product(db_session, brand, "Kavalan Classic", aliases=("카발란 클래식",), is_active=False)

    assert sorted(catalog_entries(db_session, searchable_only=True)) == sorted([
        ("Kavalan Solist Vinho", solist.id), ("카발란 솔리스트 비노", solist.id)])


def test_ties_are_broken_by_display_name(client, db_session, use_finder):
    brand = make_brand(db_session, "Twin")
    make_product(db_session, brand, "Twin B", aliases=("트윈 비",))
    make_product(db_session, brand, "Twin A", aliases=("트윈 에이",))
    make_product(db_session, brand, "Twin C", aliases=("트윈 씨",))
    use_finder(SimilarProducts(FakeEmbeddingProvider(
        {("트윈즈", "트윈 비"): 0.6, ("트윈즈", "트윈 에이"): 0.6, ("트윈즈", "Twin C"): 0.7,
         ("트윈즈", "트윈 씨"): 0.2}), 0.38))

    body = search(client, query="트윈즈")

    # Twin C scores its best text (0.7); A and B tie at 0.6.
    assert (body["matchType"], names(body)) == ("similar", ["Twin C", "Twin A", "Twin B"])


def test_the_index_is_reused_and_rebuilt_when_searchable_aliases_change(client, db_session, use_finder):
    product = make_product(db_session, make_brand(db_session, "Kavalan"), "Kavalan Solist Vinho")
    provider = FakeEmbeddingProvider({("카발란 솔리스트 빈", "카발란 솔리스트 비노"): 0.9})
    use_finder(SimilarProducts(provider, 0.38))

    assert search(client, query="카발란 솔리스트 빈")["matchType"] == "none"
    assert search(client, query="카발란 솔리스트 빈")["matchType"] == "none"
    assert len(provider.builds) == 1  # same catalog: one index

    # An alias customer search does not use does not change the search index.
    db_session.add(ProductAlias(product_id=product.id, alias_text="카발란 쏠리스트",
                                normalized_alias=normalize("카발란 쏠리스트"), is_searchable=False))
    db_session.flush()
    assert search(client, query="카발란 솔리스트 빈")["matchType"] == "none"
    assert len(provider.builds) == 1

    db_session.add(ProductAlias(product_id=product.id, alias_text="카발란 솔리스트 비노",
                                normalized_alias=normalize("카발란 솔리스트 비노")))
    db_session.flush()
    body = search(client, query="카발란 솔리스트 빈")

    assert (body["matchType"], names(body)) == ("similar", ["Kavalan Solist Vinho"])
    assert len(provider.builds) == 2 and "카발란 솔리스트 비노" in provider.builds[1]


def test_the_searchable_version_ignores_unsearchable_aliases(db_session):
    product = make_product(db_session, make_brand(db_session, "Kavalan"), "Kavalan Solist Vinho")
    before = (catalog_version(db_session), catalog_version(db_session, searchable_only=True))

    db_session.add(ProductAlias(product_id=product.id, alias_text="카발란 쏠리스트",
                                normalized_alias=normalize("카발란 쏠리스트"), is_searchable=False))
    db_session.flush()

    assert catalog_version(db_session) != before[0]
    assert catalog_version(db_session, searchable_only=True) == before[1]


def test_a_failure_answers_none_and_is_logged(client, db_session, catalog, use_finder, caplog):
    use_finder(SimilarProducts(FakeEmbeddingProvider(fail=RuntimeError("index broken")), 0.38))

    with caplog.at_level(logging.ERROR, logger="app.services.search_query"):
        body = search(client, query="글렌피딕 12년산")

    assert (body["matchType"], body["matchedProducts"]) == ("none", [])
    assert "Similar-products search failed" in caplog.text
    assert counts(db_session) == (set(), {("글렌피딕12산", 1)})


def test_the_query_is_compared_as_typed_not_normalized(client, db_session, use_finder):
    make_product(db_session, make_brand(db_session, "Kavalan"), "Kavalan Solist Vinho")
    provider = FakeEmbeddingProvider()
    use_finder(SimilarProducts(provider, 0.38))

    search(client, query="  Kavalan  Solista! ")

    assert provider.searches == [["Kavalan  Solista!"]]


def test_products_tied_at_the_fifth_place_are_cut_by_display_name(client, db_session, use_finder):
    brand = make_brand(db_session, "Six")
    for letter in "FEDCBA":
        make_product(db_session, brand, f"Six {letter}")
    use_finder(SimilarProducts(FakeEmbeddingProvider(
        {("식스", f"Six {letter}"): 0.5 for letter in "ABCDEF"} | {("식스", "Six F"): 0.9}), 0.38))

    body = search(client, query="식스")

    assert names(body) == ["Six F", "Six A", "Six B", "Six C", "Six D"]
