"""Guards on a confirmed match (I4-P18 unverified product, I4-P38 incomplete name) and the
product draft read from a menu line (I4-P18)."""

from uuid import UUID

import pytest

from app.matching import ProductInfo
from app.matching.linking_guards import apply_linking_guards, incomplete_name
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.product_draft import ProductDraft, draft_from_name, whole_spellings
from app.matching.review_state import ReviewState, review_state, stored_status
from app.matching.staged import resolve_product_staged
from app.matching.types import ExtractedProduct, ResolutionResult

STAGES = {"S1", "S2", "S2b", "S3"}
BALVENIE, JACK, ROSES, JAMESON, NEW = (UUID(int=100 + n) for n in range(5))
DOUBLEWOOD, SINGLE_BARREL, CARIBBEAN, NO7, JD_SINGLE, ROSES_BOURBON, ROSES_SMALL, JAMESON_BASE, OWNER_MADE = (
    UUID(int=n) for n in range(1, 10))


def make_catalog(owner_made_verified=False):
    products = [
        ProductInfo(DOUBLEWOOD, "The Balvenie 12 DoubleWood", 12, "DoubleWood", brand_id=BALVENIE),
        ProductInfo(SINGLE_BARREL, "The Balvenie 12 Single Barrel", 12, "Single Barrel", brand_id=BALVENIE),
        ProductInfo(CARIBBEAN, "The Balvenie 14 Caribbean Cask", 14, "Caribbean Cask", brand_id=BALVENIE),
        ProductInfo(NO7, "Jack Daniel's Old No.7", None, "Old No.7", brand_id=JACK),
        ProductInfo(JD_SINGLE, "Jack Daniel's Single Barrel", None, "Single Barrel", brand_id=JACK),
        ProductInfo(ROSES_BOURBON, "Four Roses Bourbon", None, "Bourbon", brand_id=ROSES),
        ProductInfo(ROSES_SMALL, "Four Roses Small Batch", None, "Small Batch", brand_id=ROSES),
        ProductInfo(JAMESON_BASE, "Jameson", brand_id=JAMESON),
        ProductInfo(OWNER_MADE, "Kim Gwajang #4 Clynelish", None, "#4 Clynelish", brand_id=NEW, verified=owner_made_verified),
    ]
    aliases = [(p.product_id, p.display_name) for p in products] + [
        # spellings some bar's menu used for one product: they say less than the product does
        (DOUBLEWOOD, "발베니 12년"), (CARIBBEAN, "발베니 14년"), (NO7, "잭다니엘"), (ROSES_BOURBON, "포로지스"),
        (JAMESON_BASE, "제임슨"), (OWNER_MADE, "김과장 #4 클라이넬리쉬"), (DOUBLEWOOD, "발베니 12년 더블우드"),
    ]
    brand_aliases = [(BALVENIE, "발베니"), (BALVENIE, "Balvenie"), (BALVENIE, "The Balvenie"), (JACK, "잭다니엘"),
                     (JACK, "Jack Daniel's"), (ROSES, "포로지스"), (ROSES, "Four Roses"), (JAMESON, "제임슨"),
                     (JAMESON, "Jameson"), (NEW, "김과장")]
    return InMemoryCatalog(products, aliases, brand_aliases)


@pytest.fixture
def catalog():
    return make_catalog()


def resolve(name, catalog, **kwargs):
    result = resolve_product_staged(ExtractedProduct(product_name=name), catalog, STAGES)
    return result, apply_linking_guards(name, result, catalog, **kwargs)


# ---- incomplete name (P38) ----


@pytest.mark.parametrize("name, product, kind", [
    ("발베니 12년", DOUBLEWOOD, "age_only"),          # Single Barrel is 12 too
    ("Balvenie 12y", DOUBLEWOOD, "age_only"),
    ("발베니(Balvenie) 12년", DOUBLEWOOD, "age_only"),
    ("발베니 12년 / Balvenie 12y", DOUBLEWOOD, "age_only"),
    ("잭다니엘", NO7, "brand_only"),                  # the brand has a Single Barrel
    ("발베니 14년", CARIBBEAN, None),                 # the only 14 of the brand
    ("발베니 12년 더블우드", DOUBLEWOOD, None),         # the name has the edition
    ("포로지스", ROSES_BOURBON, None),                # "Bourbon" is the plain bottling
    ("제임슨", JAMESON_BASE, None),                   # the product is the brand
    ("모르는 술 12년", DOUBLEWOOD, None),               # the brand rules cannot read the name
])
def test_incomplete_name(catalog, name, product, kind):
    assert incomplete_name(name, catalog.get_product(product), catalog) == kind


def test_a_product_without_a_brand_is_not_judged(catalog):
    assert incomplete_name("발베니 12년", ProductInfo(UUID(int=50), "x", 12, "y"), catalog) is None


def test_incomplete_name_guard_is_off_unless_asked(catalog):
    before, after = resolve("발베니 12년", catalog)
    assert before.status == "exact_match" and after is before
    _, guarded = resolve("발베니 12년", catalog, incomplete_names=True)
    assert guarded.status == "ambiguous" and guarded.proposed_product_id == DOUBLEWOOD
    assert guarded.candidates[0].evidence["incompleteName"] == "age_only"
    assert guarded.candidates[0].evidence["confirmRecommended"] is True
    assert review_state(guarded) is ReviewState.CONFIRM_RECOMMENDED and stored_status(guarded) == "ambiguous"


def test_a_complete_name_stays_confirmed_with_the_guard_on(catalog):
    for name in ("발베니 12년 더블우드", "The Balvenie 12 Single Barrel", "제임슨", "포로지스"):
        before, after = resolve(name, catalog, incomplete_names=True)
        assert before.status == "exact_match" and after is before, name


# ---- unverified product (P18) ----


def test_a_match_to_an_unverified_product_is_a_recommendation(catalog):
    before, after = resolve("김과장 #4 클라이넬리쉬", catalog)
    assert before.status == "exact_match" and before.proposed_product_id == OWNER_MADE
    assert after.status == "ambiguous" and after.proposed_product_id == OWNER_MADE
    assert after.candidates[0].evidence["unverifiedProduct"] is True
    assert after.candidates[0].evidence["confirmRecommended"] is True
    assert review_state(after) is ReviewState.CONFIRM_RECOMMENDED and stored_status(after) == "ambiguous"


def test_the_same_product_confirms_once_it_is_verified():
    catalog = make_catalog(owner_made_verified=True)
    before, after = resolve("김과장 #4 클라이넬리쉬", catalog)
    assert after is before and stored_status(after) == "exact_match"


def test_guards_leave_other_results_alone(catalog):
    for name in ("발베니", "없는 술"):                       # ambiguous, unmatched
        before, after = resolve(name, catalog, incomplete_names=True)
        assert before.status != "exact_match" and after is before
    odd = ResolutionResult("exact_match", (), UUID(int=999))
    assert apply_linking_guards("x", odd, catalog) is odd
    gone = ResolutionResult("exact_match", resolve("제임슨", catalog)[0].candidates, UUID(int=999))
    assert apply_linking_guards("x", gone, catalog) is gone
    assert apply_linking_guards(None, resolve("제임슨", catalog)[0], catalog, incomplete_names=True).status == "exact_match"


def test_product_info_is_verified_unless_said_otherwise():
    assert ProductInfo(UUID(int=1), "x").verified is True


# ---- product draft (P18) ----


@pytest.mark.parametrize("name, expected", [
    ("발베니(Balvenie) 16년 프렌치 오크", ProductDraft(
        "발베니(Balvenie) 16년 프렌치 오크", ("발베니 16년 프렌치 오크", "Balvenie 16년 프렌치 오크"), BALVENIE, "발베니", 16,
        "프렌치 오크", "french oak")),
    ("Balvenie 21 Portwood", ProductDraft("Balvenie 21 Portwood", (), BALVENIE, "Balvenie", 21, "Portwood")),
    ("발베니25년", ProductDraft("발베니25년", (), BALVENIE, "발베니", 25)),
    # the first reading is only the brand, so the next one is used
    ("발베니(Balvenie 30y)", ProductDraft("발베니(Balvenie 30y)", (), BALVENIE, "Balvenie", 30)),
    ("발베니 17년 / Balvenie 17Y", ProductDraft(
        "발베니 17년 / Balvenie 17Y", ("발베니 17년", "Balvenie 17Y"), BALVENIE, "발베니", 17)),
    # a bare small number after the brand is a batch or series number, not an age
    ("김과장 5 탈리스커", ProductDraft("김과장 5 탈리스커", (), NEW, "김과장", None, "5 탈리스커")),
    ("발베니 튠 1509 배치 4", ProductDraft("발베니 튠 1509 배치 4", (), BALVENIE, "발베니", None, "튠 1509 배치 4")),
    # no catalog brand: the age with a unit is still read, nothing is guessed
    ("러셀 10년 버번", ProductDraft("러셀 10년 버번", (), None, None, 10)),
    ("모히토", ProductDraft("모히토")),
    # a trailing parenthesis is not a whole name, so it is not offered as a spelling
    ("Balvenie 12y DoubleWood (발베니)", ProductDraft("Balvenie 12y DoubleWood (발베니)", (), BALVENIE, "Balvenie", 12, "DoubleWood")),
])
def test_draft_from_name(catalog, name, expected):
    assert draft_from_name(name, catalog) == expected


def test_draft_needs_a_name(catalog):
    assert draft_from_name(None, catalog) is None and draft_from_name("  ", catalog) is None


@pytest.mark.parametrize("name, spellings", [
    ("글렌그란트 18년 / Glen Grant 18Y", ("글렌그란트 18년", "Glen Grant 18Y")),
    ("와일드터키 골드포일16 / 행사", ()),               # the second side is not the name
    ("헤네시vsop / Hennessy vsop", ()),                 # both sides mix scripts
    ("글렌그란트 18년 / Glen Grant 15Y", ()),           # different numbers: two products
    ("라가불린(Lagavulin) 8년", ("라가불린 8년", "Lagavulin 8년")),
    ("Blair Athol Sangiovese Cask (블레어 아쏠)", ()),
])
def test_whole_spellings(name, spellings):
    assert whole_spellings(name) == spellings


def test_a_draft_never_confirms_a_line(catalog):
    # the line reads cleanly (brand, age, edition) and the catalog has no such product
    name = "발베니(Balvenie) 16년 프렌치 오크"
    draft = draft_from_name(name, catalog)
    assert draft.brand_id == BALVENIE and draft.age_years == 16
    _, result = resolve(name, catalog)
    assert review_state(result) is not ReviewState.CONFIRMED and stored_status(result) != "exact_match"


@pytest.mark.parametrize("name, suggestions", [
    ("라가불린(Lagavulin) 8년", ["라가불린 8년", "Lagavulin 8년"]),
    ("글렌그란트 18년 / Glen Grant 18Y", ["글렌그란트 18년", "Glen Grant 18Y"]),
    ("  라프로익   10년 CS ", ["라프로익 10년 CS"]),                                  # one script: the name as written
    ("Blair Athol Sangiovese Cask (블레어 아쏠)", ["Blair Athol Sangiovese Cask (블레어 아쏠)"]),  # never the partial
    ("글렌그란트 18년 / Glen Grant 15Y", ["글렌그란트 18년 / Glen Grant 15Y"]),
    (None, []), ("   ", []), ("가" * 201, []),
])
def test_alias_suggestions(name, suggestions):
    from app.matching.product_draft import alias_suggestions

    assert alias_suggestions(name) == suggestions
