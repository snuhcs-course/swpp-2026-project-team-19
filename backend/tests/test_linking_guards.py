"""Guards on a confirmed match (I4-P18 unverified product, I4-P38 incomplete name, I5-P59 missing
age) and the product draft read from a menu line (I4-P18)."""

from uuid import UUID, uuid4

import pytest

from app.matching import ProductInfo
from app.matching.linking_guards import apply_linking_guards, has_age, incomplete_name, missing_age_guard_enabled
from app.matching.memory_catalog import InMemoryCatalog
from app.matching import product_draft
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


# ---- missing age (I5-P59) ----

ARDBEG, ANTHOLOGY, WEE_BEASTIE, UIGEADAIL = UUID(int=200), UUID(int=201), UUID(int=202), UUID(int=203)


def ardbeg_catalog():
    products = [
        ProductInfo(ANTHOLOGY, "Ardbeg Anthology 14", 14, "Anthology", brand_id=ARDBEG),
        ProductInfo(WEE_BEASTIE, "Ardbeg Wee Beastie 5", 5, "Wee Beastie", brand_id=ARDBEG),
        ProductInfo(UIGEADAIL, "Ardbeg Uigeadail", None, "Uigeadail", brand_id=ARDBEG),
    ]
    aliases = [(p.product_id, p.display_name) for p in products] + [
        (ANTHOLOGY, "Ardbeg Anthology"), (WEE_BEASTIE, "아드벡 위비스티"), (WEE_BEASTIE, "아드벡 위비스티 5년")]
    return InMemoryCatalog(products, aliases, [(ARDBEG, "Ardbeg"), (ARDBEG, "아드벡")])


def test_missing_age_is_off_by_default():
    catalog = ardbeg_catalog()
    before, after = resolve("Ardbeg Anthology", catalog)
    assert before.status == "exact_match" and after is before


@pytest.mark.parametrize("name, product", [("Ardbeg Anthology", ANTHOLOGY), ("아드벡 위비스티", WEE_BEASTIE)])
def test_missing_age_takes_the_confirmation_from_a_line_without_an_age(name, product):
    catalog = ardbeg_catalog()
    before, after = resolve(name, catalog, missing_age=True)
    assert before.status == "exact_match" and before.proposed_product_id == product
    assert after.status == "ambiguous" and after.proposed_product_id == product
    evidence = after.candidates[0].evidence
    assert evidence["missingAge"] == catalog.get_product(product).age_years and evidence["confirmRecommended"] is True
    assert review_state(after) is ReviewState.CONFIRM_RECOMMENDED and stored_status(after) == "ambiguous"


def test_missing_age_keeps_a_line_with_an_age_and_a_product_without_one():
    catalog = ardbeg_catalog()
    for name in ("아드벡 위비스티 5년", "Ardbeg Wee Beastie 5", "Ardbeg Uigeadail"):
        before, after = resolve(name, catalog, missing_age=True)
        assert before.status == "exact_match" and after is before, name


def test_missing_age_counts_the_extracted_age():
    catalog = ardbeg_catalog()
    before = resolve_product_staged(ExtractedProduct(product_name="Ardbeg Anthology"), catalog, STAGES)
    assert apply_linking_guards("Ardbeg Anthology", before, catalog, missing_age=True, line_age=14) is before
    assert apply_linking_guards("Ardbeg Anthology", before, catalog, missing_age=True).status == "ambiguous"


@pytest.mark.parametrize("name, expected", [
    ("Glenfiddich 12", True), ("글렌피딕 12년", True), ("Lagavulin 16Y", True), ("라프로익10", True),
    ("발베니(Balvenie) 12", True), ("Kim Gwajang #4", True),
    ("Ardbeg Anthology", False), ("Octomore 14.1", False), ("Classic Cut 2025", False), ("Ardbeg 700ml 46%", False),
    ("Johnnie Walker Black 2잔 16,000원", False), ("", False),
])
def test_has_age_reads_a_one_or_two_digit_number(name, expected):
    assert has_age(name) is expected


def test_the_missing_age_setting(monkeypatch):
    monkeypatch.delenv("MATCHING_MISSING_AGE_GUARD", raising=False)
    assert missing_age_guard_enabled() is False
    monkeypatch.setenv("MATCHING_MISSING_AGE_GUARD", "TRUE")
    assert missing_age_guard_enabled() is True
    monkeypatch.setenv("MATCHING_MISSING_AGE_GUARD", "yes")
    with pytest.raises(RuntimeError, match="MATCHING_MISSING_AGE_GUARD"):
        missing_age_guard_enabled()


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
    # brackets in the same script are part of the name, not a second spelling: the edition is kept
    ("Balvenie 12 (Sherry Oak)", ProductDraft("Balvenie 12 (Sherry Oak)", (), BALVENIE, "Balvenie", 12, "Sherry Oak")),
    ("Balvenie (Sherry Oak) 12 Years", ProductDraft(
        "Balvenie (Sherry Oak) 12 Years", (), BALVENIE, "Balvenie", 12, "Sherry Oak")),
    ("발베니 (12년) 셰리 오크", ProductDraft("발베니 (12년) 셰리 오크", (), BALVENIE, "발베니", 12, "셰리 오크", "sherry oak")),
    # of two spellings of one line, the one that says more is read
    ("발베니 16년 / Balvenie 16 French Oak", ProductDraft(
        "발베니 16년 / Balvenie 16 French Oak", ("발베니 16년", "Balvenie 16 French Oak"), BALVENIE, "Balvenie", 16,
        "French Oak")),
    # brackets in the other script that hold the age or the edition are part of the name, not the
    # name again: the brand and the edition are kept
    ("발베니 (12Y DoubleWood)", ProductDraft("발베니 (12Y DoubleWood)", (), BALVENIE, "발베니", 12, "DoubleWood")),
    ("발베니 (Caribbean Cask) 14년", ProductDraft(
        "발베니 (Caribbean Cask) 14년", (), BALVENIE, "발베니", 14, "Caribbean Cask")),
    ("Balvenie 14y (럼 캐스크)", ProductDraft("Balvenie 14y (럼 캐스크)", (), BALVENIE, "Balvenie", 14, "럼 캐스크")),
    # brackets that say more but start with the title's brand are the name again: each side is
    # read on its own, so "Balvenie" is not taken for the edition
    ("발베니 (Balvenie 12) 더블우드", ProductDraft(
        "발베니 (Balvenie 12) 더블우드", (), BALVENIE, "Balvenie", 12, "더블우드", "double wood")),
    # the age on one side of the brackets and the edition on the other: both are kept
    ("발베니 14년 (Balvenie Caribbean Cask)", ProductDraft(
        "발베니 14년 (Balvenie Caribbean Cask)", (), BALVENIE, "발베니", 14, "Caribbean Cask")),
    ("Balvenie Caribbean Cask (발베니 14년)", ProductDraft(
        "Balvenie Caribbean Cask (발베니 14년)", (), BALVENIE, "Balvenie", 14, "Caribbean Cask")),
    # a part the chosen reading has is not replaced by the other reading's
    ("발베니 12년 (Balvenie 14 DoubleWood)", ProductDraft(
        "발베니 12년 (Balvenie 14 DoubleWood)", (), BALVENIE, "Balvenie", 14, "DoubleWood")),
    # brackets that only repeat the title's edition in the other script add nothing
    ("Balvenie 16y French Oak (프렌치 오크)", ProductDraft(
        "Balvenie 16y French Oak (프렌치 오크)", (), BALVENIE, "Balvenie", 16, "French Oak")),
    # OCR text with double spaces: the brand is the brand, not "Balvenie  2"
    ("Balvenie  21  Portwood", ProductDraft("Balvenie 21 Portwood", (), BALVENIE, "Balvenie", 21, "Portwood")),
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
    ("Yamazaki Dr (야마자키 Dr) 12", ("Yamazaki Dr 12", "야마자키 Dr 12")),  # the brackets hold the other script
    # brackets in the same script are not a second spelling: "12년 셰리 오크" must never become an alias
    ("맥캘란 (12년) 셰리 오크", ()),
    ("Macallan (Sherry Oak) 12 Years", ()),
    ("맥캘란 Macallan (12년) 셰리 오크", ()),          # the text before the brackets mixes scripts
    # brackets in the other script with a number or a whisky word the title lacks are not the
    # name again: "12Y Sherry Oak 나머지" must never become an alias
    ("맥캘란 (12Y Sherry Oak)", ()),
    ("맥캘란 (12Y) 셰리 오크", ()),
    ("맥캘란 (SherryOak) 12년", ()),                    # written together
    ("Macallan (셰리 오크) 12 Years", ()),
    # a whisky word the title has too, in its own script, is the name again
    ("포트샬롯(Port Charlotte) 10년", ("포트샬롯 10년", "Port Charlotte 10년")),
    ("맥캘란 셰리오크(Macallan Sherry Oak) 12년", ("맥캘란 셰리오크 12년", "Macallan Sherry Oak 12년")),
    ("Macallan Sherry Oak (맥캘란 셰리 오크) 12", ("Macallan Sherry Oak 12", "맥캘란 셰리 오크 12")),
    ("더 위스키 에이전시(TWA) 카발란 7년", ("더 위스키 에이전시 카발란 7년", "TWA 카발란 7년")),
    ("글렌그란트(Glen Grant) 18년", ("글렌그란트 18년", "Glen Grant 18년")),
    # a Korean whisky word inside a longer word is not that word: "라이" (rye) in 클라이넬리쉬,
    # "몰트" (malt) in 몰트락
    ("Clynelish (클라이넬리쉬) 14년", ("Clynelish 14년", "클라이넬리쉬 14년")),
    ("Mortlach (몰트락) 16", ("Mortlach 16", "몰트락 16")),
    ("Macallan (피트 몰트) 12", ()),                     # as a word of its own it is
    ("Macallan (12년 몰트)", ()),
])
def test_whole_spellings(name, spellings):
    assert whole_spellings(name) == spellings


ARDBEG, UIGEADAIL, TEN = uuid4(), uuid4(), uuid4()


@pytest.fixture
def ardbeg():
    products = [ProductInfo(UIGEADAIL, "Ardbeg Uigeadail", None, "Uigeadail", brand_id=ARDBEG),
                ProductInfo(TEN, "Ardbeg 10", 10, None, brand_id=ARDBEG)]
    return InMemoryCatalog(products, [(p.product_id, p.display_name) for p in products],
                           [(ARDBEG, "아드벡"), (ARDBEG, "Ardbeg")])


@pytest.mark.parametrize("name, brand_text, age, edition, spellings", [
    # an edition the catalog has for the brand, in brackets after the brand alone: part of the name,
    # though it is no vocabulary word and has no number
    ("아드벡 (Uigeadail)", "아드벡", None, "Uigeadail", ()),
    ("아드벡(Uigeadail) 10년", "아드벡", 10, "Uigeadail", ()),
    ("아드벡 (UIGEADAIL)", "아드벡", None, "UIGEADAIL", ()),
    # the brand again in a spelling the catalog does not have stays a second spelling: menus write
    # "맥캘란(Maccallan)", "산토리(Santory)"
    ("아드벡(Ardbegg) 10년", "아드벡", 10, None, ("아드벡 10년", "Ardbegg 10년")),
    ("아드벡 (Ardbeg) 10년", "아드벡", 10, None, ("아드벡 10년", "Ardbeg 10년")),
    # an edition the catalog does not have cannot be told from the brand in another spelling: the
    # brand is kept, the edition is left for the reviewer
    ("아드벡 (Corryvreckan)", "아드벡", None, None, ()),
    ("아드벡 (Corryvreckan) 10년", "아드벡", 10, None, ("아드벡 10년", "Corryvreckan 10년")),
    # the edition after the age
    ("아드벡 10년 (Uigeadail)", "아드벡", 10, "Uigeadail", ()),
    # the title already has an edition: the brackets repeat it and are not added to it
    ("아드벡 우가달 (Uigeadail)", "아드벡", None, "우가달", ()),
    ("아드벡 우가달 10년 (Uigeadail)", "아드벡", 10, "우가달", ()),
    # the title is not a brand the catalog knows: the brackets stay a second spelling
    ("라프로익 (Uigeadail) 10년", None, 10, None, ("라프로익 10년", "Uigeadail 10년")),
])
def test_an_edition_of_the_brand_in_brackets_is_part_of_the_name(ardbeg, name, brand_text, age, edition, spellings):
    draft = draft_from_name(name, ardbeg)

    assert (draft.brand_id, draft.brand_text, draft.age_years, draft.edition_text, draft.spellings) == (
        ARDBEG if brand_text else None, brand_text, age, edition, spellings)


def test_two_readings_that_are_different_brands_give_no_brand(catalog):
    draft = draft_from_name("발베니 (Jameson)", catalog)
    assert (draft.brand_id, draft.brand_text, draft.edition_text) == (None, None, None)
    same = draft_from_name("발베니 (Balvenie)", catalog)
    assert (same.brand_id, same.brand_text) == (BALVENIE, "발베니")


def test_parts_are_taken_only_from_a_reading_of_the_same_known_brand():
    fill = product_draft._with_parts_of_the_other_readings
    best = ProductDraft("x", (), BALVENIE, "발베니", 14, None)
    assert fill(best, [best, ProductDraft("x", (), JACK, "Jack", None, "Old No.7")]) == best
    unknown = ProductDraft("x", (), None, "?", 14, None)
    assert fill(unknown, [unknown, ProductDraft("x", (), None, "?", None, "Cask")]) == unknown
    filled = fill(best, [best, ProductDraft("x", (), BALVENIE, "Balvenie", 12, "더블우드", "double wood")])
    assert (filled.age_years, filled.edition_text, filled.edition_english) == (14, "더블우드", "double wood")
    without_age = ProductDraft("x", (), BALVENIE, "발베니", None, "DoubleWood")
    assert fill(without_age, [ProductDraft("x", (), BALVENIE, "Balvenie", 12, None), without_age]).age_years == 12


def test_brackets_are_read_by_script_alone_without_a_vocabulary(monkeypatch):
    monkeypatch.setattr(product_draft, "_VOCABULARY", None)
    assert whole_spellings("맥캘란 (Sherry Oak) 12년") == ("맥캘란 12년", "Sherry Oak 12년")
    assert whole_spellings("맥캘란 (12Y) 셰리 오크") == ()  # the number is still seen


def test_a_draft_never_confirms_a_line(catalog):
    # the line reads cleanly (brand, age, edition) and the catalog has no such product
    name = "발베니(Balvenie) 16년 프렌치 오크"
    draft = draft_from_name(name, catalog)
    assert draft.brand_id == BALVENIE and draft.age_years == 16
    _, result = resolve(name, catalog)
    assert review_state(result) is not ReviewState.CONFIRMED and stored_status(result) != "exact_match"
