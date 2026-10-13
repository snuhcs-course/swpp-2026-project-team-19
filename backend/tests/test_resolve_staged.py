# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P22). Reviewed by Jinwoo Park.
from uuid import UUID

import pytest

from app.matching import ExtractedProduct, ProductInfo, resolve_product
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.staged import resolve_product_staged


def _id(n: int) -> UUID:
    return UUID(int=n)


ABERLOUR, GLENFIDDICH, BUFFALO, MAKERS, MACALLAN, KAVALAN = (_id(100 + n) for n in range(6))
ABERLOUR_12, GLENFIDDICH_12, GLENFIDDICH_15, BUFFALO_TRACE, MAKERS_MARK = (_id(n) for n in range(1, 6))
MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE, MACALLAN_15_DOUBLE = (_id(n) for n in range(6, 9))
SOLIST_SHERRY, SOLIST_VINHO, TRIPLE_SHERRY = (_id(n) for n in range(9, 12))


@pytest.fixture
def catalog():
    products = [
        ProductInfo(ABERLOUR_12, "Aberlour 12", age_years=12, brand_id=ABERLOUR),
        ProductInfo(GLENFIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=GLENFIDDICH),
        ProductInfo(GLENFIDDICH_15, "Glenfiddich 15", age_years=15, brand_id=GLENFIDDICH),
        ProductInfo(BUFFALO_TRACE, "Buffalo Trace", brand_id=BUFFALO),
        ProductInfo(MAKERS_MARK, "Maker's Mark", brand_id=MAKERS),
        ProductInfo(MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak", 12, "Sherry Oak", brand_id=MACALLAN),
        ProductInfo(MACALLAN_12_DOUBLE, "Macallan 12 Double Cask", 12, "Double Cask", brand_id=MACALLAN),
        ProductInfo(MACALLAN_15_DOUBLE, "Macallan 15 Double Cask", 15, "Double Cask", brand_id=MACALLAN),
        ProductInfo(SOLIST_SHERRY, "Kavalan Solist Oloroso Sherry", None, "Solist Oloroso Sherry", brand_id=KAVALAN),
        ProductInfo(SOLIST_VINHO, "Kavalan Solist Vinho Barrique", None, "Solist Vinho Barrique", brand_id=KAVALAN),
        ProductInfo(TRIPLE_SHERRY, "Kavalan Triple Sherry Cask", None, "Triple Sherry Cask", brand_id=KAVALAN),
    ]
    aliases = [
        (ABERLOUR_12, "Aberlour 12"),
        (ABERLOUR_12, "아벨라워 12년"),
        (GLENFIDDICH_12, "Glenfiddich 12"),
        (GLENFIDDICH_12, "글렌피딕 12년"),
        (GLENFIDDICH_15, "Glenfiddich 15"),
        (BUFFALO_TRACE, "Buffalo Trace"),
        (MAKERS_MARK, "Maker's Mark"),
        (MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak"),
        (MACALLAN_12_SHERRY, "맥캘란 12년 셰리 오크"),
        (MACALLAN_12_DOUBLE, "Macallan 12 Double Cask"),
        (MACALLAN_12_DOUBLE, "맥캘란 12년 더블 캐스크"),
        (MACALLAN_15_DOUBLE, "Macallan 15 Double Cask"),
        (SOLIST_SHERRY, "Kavalan Solist Oloroso Sherry"),
        (SOLIST_SHERRY, "카발란 솔리스트 셰리"),
        (SOLIST_VINHO, "Kavalan Solist Vinho Barrique"),
        (TRIPLE_SHERRY, "Kavalan Triple Sherry Cask"),
        (TRIPLE_SHERRY, "카발란 트리플 셰리 캐스크"),
    ]
    brand_aliases = [
        (ABERLOUR, "Aberlour"),
        (ABERLOUR, "아벨라워"),
        (GLENFIDDICH, "Glenfiddich"),
        (MACALLAN, "Macallan"),
        (MACALLAN, "The Macallan"),
        (MACALLAN, "맥캘란"),
        (KAVALAN, "Kavalan"),
        (KAVALAN, "카발란"),
    ]
    return InMemoryCatalog(products, aliases, brand_aliases)


def s1(name: str, catalog, **fields):
    return resolve_product_staged(ExtractedProduct(product_name=name, **fields), catalog, {"S1"})


def test_no_stages_is_resolve_product(catalog):
    for name in ("아벨라워(Aberlour) 12년", "Buffalo Trace / Maker's Mark", "Glenfiddich 12", None):
        item = ExtractedProduct(product_name=name)
        assert resolve_product_staged(item, catalog) == resolve_product(item, catalog)


def test_unknown_stage_is_rejected(catalog):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="Aberlour 12"), catalog, {"S9"})


@pytest.mark.parametrize("name", ["아벨라워(Aberlour) 12년", "Aberlour (아벨라워) 12Y", "아벨라워 (Aberlour)12년"])
def test_parenthesized_name_is_looked_up_both_ways(catalog, name):
    assert resolve_product(ExtractedProduct(product_name=name), catalog).status == "unmatched"

    result = s1(name, catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == ABERLOUR_12
    assert result.candidates[0].evidence["parenExpanded"] in ("아벨라워 12년", "Aberlour 12년", "Aberlour 12Y")


def test_parenthesized_name_keeps_the_age_conflict_check(catalog):
    result = s1("아벨라워(Aberlour) 12년", catalog, age_years=15)

    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["ageConflict"] is True


def test_two_products_of_different_brands_are_multi(catalog):
    result = s1("Buffalo Trace / Maker's Mark", catalog)

    assert result.status == "multi"
    assert result.proposed_product_id is None
    assert [part.proposed_product_id for part in result.parts] == [BUFFALO_TRACE, MAKERS_MARK]
    assert [part.status for part in result.parts] == ["exact_match", "exact_match"]
    assert [c.product_id for c in result.candidates] == [BUFFALO_TRACE, MAKERS_MARK]
    assert result.candidates[1].evidence["multiProduct"] == "Maker's Mark"


def test_two_products_need_both_sides_exact(catalog):
    # A typo on one side: M0 behaviour (the side that matched) is kept.
    result = s1("Buffalo Trace / Makrt's Mark", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == BUFFALO_TRACE


def test_two_products_of_the_same_brand_are_not_multi(catalog):
    result = s1("Glenfiddich 12 / Glenfiddich 15", catalog)

    assert result.status == "ambiguous"
    assert result.parts == ()


def test_korean_english_pair_stays_one_product(catalog):
    result = s1("글렌피딕 12년 / Glenfiddich 12", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == GLENFIDDICH_12
    assert result.parts == ()


def test_korean_english_pair_of_different_products_is_not_multi(catalog):
    # Different scripts mean "Korean / English" of one line, never two products.
    result = s1("아벨라워 12년 / Glenfiddich 12", catalog)

    assert result.status == "ambiguous"


def s2(name: str, catalog, **fields):
    return resolve_product_staged(ExtractedProduct(product_name=name, **fields), catalog, {"S1", "S2"})


def test_s2_needs_s1(catalog):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="Macallan 15yo"), catalog, {"S2"})


def test_s2_does_not_touch_alias_matches(catalog):
    for name in ("Macallan 12 Sherry Oak", "맥캘란 12년 셰리 오크", "Glenfiddich 12 / Glenfiddich 15"):
        assert s2(name, catalog) == s1(name, catalog)


def test_brand_and_the_only_product_of_that_age_is_exact(catalog):
    assert s1("Macallan 15yo", catalog).status == "unmatched"

    result = s2("Macallan 15yo", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE
    assert result.candidates[0].evidence == {"brandMatch": "macallan", "ageMatch": 15, "brandName": "Macallan 15yo"}


def test_edition_token_picks_one_of_the_products_of_that_age(catalog):
    result = s2("맥캘란 더블캐스크 12Y", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_12_DOUBLE
    evidence = result.candidates[0].evidence
    assert (evidence["brandMatch"], evidence["ageMatch"], evidence["editionMatch"]) == ("맥캘란", 12, ["더블캐스크"])


def test_brand_found_without_spaces_and_in_parentheses(catalog):
    assert s2("맥캘란15년", catalog).proposed_product_id == MACALLAN_15_DOUBLE
    result = s2("맥켈란(The Macallan) 15Y", catalog)
    assert result.status == "exact_match"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE


def test_same_age_several_products_is_ambiguous(catalog):
    result = s2("Macallan 12yo", catalog)

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE}


def test_age_conflict_is_never_exact(catalog):
    # No Macallan 18 in the catalog: the 12 and 15 year products are not offered.
    assert s2("Macallan 18yo", catalog).status == "unmatched"
    # The extracted age is used when the name has none, and it conflicts too.
    assert s2("Macallan Double Cask", catalog, age_years=18).status == "unmatched"


def test_edition_token_that_fits_no_product_blocks_exact(catalog):
    result = s2("Macallan 15yo Sherry Oak", catalog)

    assert result.status == "ambiguous"
    assert result.proposed_product_id == MACALLAN_15_DOUBLE
    assert result.candidates[0].evidence["editionUnmatched"] == ["sherry", "oak"]


def test_without_age_edition_tokens_must_pick_one_product(catalog):
    assert s2("카발란 트리플 셰리", catalog).proposed_product_id == TRIPLE_SHERRY
    assert s2("카발란 트리플 셰리", catalog).status == "exact_match"

    solist = s2("Kavalan Solist", catalog)
    assert solist.status == "ambiguous"
    assert {c.product_id for c in solist.candidates} == {SOLIST_SHERRY, SOLIST_VINHO}

    # Brand only: the owner chooses.
    assert s2("Kavalan", catalog).status == "ambiguous"
    # Nothing in the name fits any Kavalan product.
    assert s2("Kavalan Distillery Reserve", catalog).status == "unmatched"


def test_short_and_neutral_tokens(catalog):
    # "PX" is too short to check, so it blocks exact; "Whisky" is ignored.
    assert s2("Macallan 15yo PX", catalog).status == "ambiguous"
    assert s2("Macallan 15yo Whisky", catalog).status == "exact_match"


def test_unknown_brand_is_unmatched(catalog):
    assert s2("Dalwhinny 15yo", catalog).status == "unmatched"


def test_two_products_found_by_brand_and_age(catalog):
    result = s2("Macallan 15yo / Aberlour 12yo", catalog)

    assert result.status == "multi"
    assert [part.proposed_product_id for part in result.parts] == [MACALLAN_15_DOUBLE, ABERLOUR_12]
