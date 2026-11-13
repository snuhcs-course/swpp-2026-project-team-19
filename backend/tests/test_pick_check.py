"""The pick check of the operator check (API spec 8.7, I4-P18): age, then the brand's products by embedding."""

import uuid

import pytest

from app.adapters.embedding import CharTfidfProvider
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.pick_check import EDITION_MARGIN, PickCheck, check_pick, embedding_query
from app.matching.romanize import romanize
from app.matching.types import ProductInfo


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


KILCHOMAN, DALMORE, LONE = _id(1), _id(2), _id(3)
MACHIR, LOCH_GORM, PORT, SANAIG = (_id(n) for n in range(11, 15))
D12, D12_SHERRY, D15 = _id(21), _id(22), _id(23)
LONELY = _id(31)

PRODUCTS = [
    ProductInfo(MACHIR, "Kilchoman Machir Bay", brand_id=KILCHOMAN),
    ProductInfo(LOCH_GORM, "Kilchoman Loch Gorm", edition_name="Loch Gorm", brand_id=KILCHOMAN),
    ProductInfo(PORT, "Kilchoman Port Cask Matured", edition_name="Port Cask Matured", brand_id=KILCHOMAN),
    ProductInfo(SANAIG, "Kilchoman Sanaig", edition_name="Sanaig", brand_id=KILCHOMAN),
    ProductInfo(D12, "The Dalmore 12", age_years=12, brand_id=DALMORE),
    ProductInfo(D12_SHERRY, "The Dalmore 12 Sherry Cask Select", 12, "Sherry Cask Select", brand_id=DALMORE),
    ProductInfo(D15, "The Dalmore 15", age_years=15, brand_id=DALMORE),
    ProductInfo(LONELY, "Lonely Distillery 10", age_years=10, brand_id=None),
]
ALIASES = {
    MACHIR: ["킬호만 마키어 베이"], LOCH_GORM: ["킬호만 로크 고름"], PORT: ["킬호만 포트 캐스크"], SANAIG: ["킬호만 사나이그"],
    D12: ["달모어 12년"], D12_SHERRY: ["달모어 12년 셰리 캐스크 셀렉트"], D15: ["달모어 15년"],
}


@pytest.fixture(scope="module")
def catalog():
    aliases = [(p.product_id, p.display_name) for p in PRODUCTS]
    aliases += [(pid, text) for pid, texts in ALIASES.items() for text in texts]
    return InMemoryCatalog(PRODUCTS, aliases, [(KILCHOMAN, "Kilchoman"), (KILCHOMAN, "킬호만"),
                                                (DALMORE, "The Dalmore"), (DALMORE, "달모어")])


@pytest.fixture(scope="module")
def similarities():
    entries = [(p.display_name, p.product_id) for p in PRODUCTS]
    entries += [(text, pid) for pid, texts in ALIASES.items() for text in texts]
    index = CharTfidfProvider().build_index([text for text, _ in entries])

    def scores(query):
        [row] = index.similarities([query])
        best = {}
        for score, (_, pid) in zip(row, entries):
            best[pid] = max(best.get(pid, -1.0), score)
        return best

    return scores


def test_romanize_and_query():
    assert romanize("로크곰") == "rokeugom" and romanize("솔리스트 Solist 12") == "solriseuteu Solist 12"
    query = embedding_query("달모어 12Y 쉐리")
    assert query.startswith("달모어 12Y 쉐리 ") and "sherry" in query and "dalmoeo" in query
    assert embedding_query("Glenfiddich 12") == "Glenfiddich 12"  # nothing to add, nothing repeated


@pytest.mark.parametrize(("name", "age", "right", "let_through"), [
    # menu spelling not in the catalog; Sanaig scores close enough to stay within the margin
    ("킬호만(Kilchoman) 로크곰", None, LOCH_GORM, {SANAIG}),
    ("킬호만 포트 캐스크", None, PORT, set()),
    ("Kilchoman Sanaig", None, SANAIG, set()),
    # 쉐리 vs 셰리: the vocabulary gives "sherry", so the right pick fits; the plain 12 is close
    # enough that picking it is not questioned (the kind of wrong pick the measurement lets through)
    ("달모어 12Y 쉐리", 12, D12_SHERRY, {D12}),
    ("달모어 12년", 12, D12, set()),
])
def test_the_right_pick_fits_and_a_far_sibling_does_not(catalog, similarities, name, age, right, let_through):
    assert check_pick(name, age, right, catalog, similarities) == PickCheck()
    siblings = [p.product_id for p in PRODUCTS if p.brand_id == catalog.get_product(right).brand_id
                and p.product_id != right and p.age_years in (None, age)]
    for wrong in siblings:
        result = check_pick(name, age, wrong, catalog, similarities)
        if wrong in let_through:
            assert result.fits, (name, wrong)
            continue
        assert result.reasons == ("editionNotClosest",), (name, wrong)
        assert result.evidence["closestProductId"] == str(right)
        assert result.evidence["similarity"] + EDITION_MARGIN < result.evidence["closestSimilarity"]


def test_an_age_the_product_does_not_have_is_a_conflict(catalog, similarities):
    result = check_pick("달모어 15년", 15, D12, catalog, similarities)
    assert result.reasons == ("ageConflict",) and result.evidence == {"lineAge": 15, "productAge": 12}
    assert not result.fits
    # products of another age are not compared by embedding: the age already decides
    assert check_pick("달모어 15년", 15, D15, catalog, similarities).fits


def test_nothing_to_compare(catalog, similarities):
    called = []

    def spy(query):
        called.append(query)
        return {}

    # no name, unknown product, a product without a brand, or the only product of its age
    assert check_pick(None, None, MACHIR, catalog, spy).fits
    assert check_pick("  ", None, MACHIR, catalog, spy).fits
    assert check_pick("anything", None, _id(99), catalog, spy).fits
    assert check_pick("Lonely 10", 10, LONELY, catalog, spy).fits
    assert check_pick("달모어 15년", 15, D15, catalog, spy).fits
    assert called == []
    # the age of a product without a brand is still checked
    assert check_pick("Lonely 12", 12, LONELY, catalog, spy).reasons == ("ageConflict",)


def test_within_the_margin_the_pick_stands(catalog):
    close = {MACHIR: 0.50, LOCH_GORM: 0.50 + EDITION_MARGIN - 0.001, PORT: 0.1, SANAIG: 0.1}
    assert check_pick("Kilchoman", None, MACHIR, catalog, lambda q: close).fits
    far = {**close, LOCH_GORM: 0.50 + EDITION_MARGIN + 0.001}
    assert check_pick("Kilchoman", None, MACHIR, catalog, lambda q: far).reasons == ("editionNotClosest",)
    # a product missing from the index counts as 0
    assert check_pick("Kilchoman", None, MACHIR, catalog, lambda q: {LOCH_GORM: 0.2}).reasons == ("editionNotClosest",)


def test_db_similarities_uses_one_index_per_catalog_version(monkeypatch):
    import app.matching.pick_check as pc

    built = []

    class FakeCache:
        def __init__(self, provider):
            built.append(provider.model_id)

        def get(self, session):
            return type("Index", (), {"product_similarities": staticmethod(lambda q: {MACHIR: 1.0})})()

    monkeypatch.setattr(pc, "_INDEX", None)
    monkeypatch.setattr("app.matching.embedding.CatalogIndexCache", FakeCache)
    first, second = pc.db_similarities(object()), pc.db_similarities(object())
    assert built == ["tfidf-char"] and first("x") == second("x") == {MACHIR: 1.0}
