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


# --- S2b: default product, S3: edit distance -----------------------------------------

FIDDICH = _id(200)
FIDDICH_12, FIDDICH_12_SHERRY, FIDDICH_15_SOLERA = (_id(n) for n in range(201, 204))


@pytest.fixture
def glenfiddich():
    products = [
        ProductInfo(FIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=FIDDICH),
        ProductInfo(FIDDICH_12_SHERRY, "Glenfiddich 12 Sherry Cask Finish", 12, "Sherry Cask Finish", brand_id=FIDDICH),
        ProductInfo(FIDDICH_15_SOLERA, "Glenfiddich 15 Solera", 15, "Solera", brand_id=FIDDICH),
    ]
    aliases = [(product.product_id, product.display_name) for product in products]
    return InMemoryCatalog(products, aliases, [(FIDDICH, "Glenfiddich"), (FIDDICH, "글렌피딕")])


def staged(name: str, catalog, *stages: str):
    return resolve_product_staged(ExtractedProduct(product_name=name), catalog, {"S1", "S2", *stages})


def test_s2b_and_s3_need_the_stage_below(glenfiddich):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="x"), glenfiddich, {"S1", "S2b"})
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="x"), glenfiddich, {"S1", "S2", "S3"})


def test_default_product_without_edition_wins_when_no_edition_token(glenfiddich):
    assert staged("글렌피딕 12년", glenfiddich).status == "ambiguous"  # S2 alone

    result = staged("글렌피딕 12년", glenfiddich, "S2b")

    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12
    assert result.candidates[0].evidence["defaultProduct"] is True


def test_edition_token_still_picks_the_edition_product(glenfiddich):
    result = staged("Glenfiddich 12yo Sherry", glenfiddich, "S2b")

    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12_SHERRY


def test_only_product_of_that_age_with_an_edition_is_confirm_recommended(glenfiddich):
    assert staged("글렌피딕 15년", glenfiddich).status == "exact_match"  # S2 alone

    result = staged("글렌피딕 15년", glenfiddich, "S2b")

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == FIDDICH_15_SOLERA
    assert candidate.evidence["confirmRecommended"] is True


def test_s2b_leaves_the_s2_cases_with_several_editions_ambiguous(catalog):
    result = staged("Macallan 12yo", catalog, "S2b")

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE}
    assert all("confirmRecommended" not in c.evidence for c in result.candidates)


def test_edit_distance_counts_hangul_syllables():
    from app.matching.staged import edit_distance

    assert edit_distance("납크릭", "놉크릭", 1) == 1
    assert edit_distance("dalwhinny", "dalwhinnie", 2) == 2
    assert edit_distance("dalwhinny", "dalwhinnie", 1) == 2  # over the limit -> limit + 1


def test_edit_distance_needs_the_same_digits(glenfiddich):
    s3 = ("S2b", "S3")
    # 16 and 18 are not in the catalog; "glenfiddich15..." is never a candidate.
    assert staged("Glenfiddich 16yo", glenfiddich, *s3).status == "unmatched"
    assert staged("Glenfidich 18yo", glenfiddich, *s3).status == "unmatched"


def test_edit_distance_one_with_digits_and_one_candidate_is_exact(glenfiddich):
    result = staged("Glenfidich 12yo", glenfiddich, "S2b", "S3")

    assert staged("Glenfidich 12yo", glenfiddich, "S2b").status == "unmatched"
    assert result.status == "exact_match"
    assert result.proposed_product_id == FIDDICH_12
    assert result.candidates[0].evidence["editDistance"] == 1


def test_edit_distance_two_is_confirm_recommended(glenfiddich):
    result = staged("Glanfidich 15yo", glenfiddich, "S2b", "S3")

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == FIDDICH_15_SOLERA
    assert candidate.evidence["editDistance"] == 2
    assert candidate.evidence["confirmRecommended"] is True


def test_edit_distance_without_digits_is_never_exact(catalog):
    result = staged("Makers Mork", catalog, "S2b", "S3")

    assert result.status == "ambiguous"
    assert result.proposed_product_id == MAKERS_MARK
    assert result.candidates[0].evidence["confirmRecommended"] is True


def test_edit_distance_ties_are_ambiguous():
    first, second = _id(301), _id(302)
    catalog = InMemoryCatalog(
        [ProductInfo(first, "Abcd 10", 10), ProductInfo(second, "Abce 10", 10)],
        [(first, "Abcd 10"), (second, "Abce 10")],
    )

    result = staged("Abcf 10", catalog, "S2b", "S3")

    assert result.status == "ambiguous"
    assert {c.product_id for c in result.candidates} == {first, second}
    assert all("confirmRecommended" not in c.evidence for c in result.candidates)


def test_s3_runs_only_when_s2_found_nothing(catalog):
    # S2 already offers the Kavalan Solist products; S3 does not add anything.
    assert staged("Kavalan Solist", catalog, "S2b", "S3") == staged("Kavalan Solist", catalog, "S2b")
