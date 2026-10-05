from uuid import UUID

import pytest

from app.matching import ExtractedProduct, ProductInfo, resolve_product
from app.matching.memory_catalog import InMemoryCatalog

DEANSTON_12 = UUID("00000000-0000-0000-0000-000000000001")
GLENFIDDICH_12 = UUID("00000000-0000-0000-0000-000000000002")
GLENFIDDICH_15 = UUID("00000000-0000-0000-0000-000000000003")
LASANTA = UUID("00000000-0000-0000-0000-000000000004")
MACALLAN_12_SHERRY = UUID("00000000-0000-0000-0000-000000000005")
MACALLAN_12_DOUBLE = UUID("00000000-0000-0000-0000-000000000006")
ARDBEG_10 = UUID("00000000-0000-0000-0000-000000000007")
MONKEY_SHOULDER = UUID("00000000-0000-0000-0000-000000000008")


@pytest.fixture
def catalog():
    products = [
        ProductInfo(DEANSTON_12, "Deanston 12", age_years=12),
        ProductInfo(GLENFIDDICH_12, "Glenfiddich 12", age_years=12),
        ProductInfo(GLENFIDDICH_15, "Glenfiddich 15", age_years=15),
        ProductInfo(LASANTA, "Glenmorangie Lasanta", edition_name="Lasanta"),
        ProductInfo(MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak", age_years=12, edition_name="Sherry Oak"),
        ProductInfo(MACALLAN_12_DOUBLE, "Macallan 12 Double Cask", age_years=12, edition_name="Double Cask"),
        ProductInfo(ARDBEG_10, "Ardbeg 10", age_years=10),
        ProductInfo(MONKEY_SHOULDER, "Monkey Shoulder"),
    ]
    aliases = [
        (DEANSTON_12, "Deanston 12"),
        (DEANSTON_12, "딘스톤 12년"),
        (GLENFIDDICH_12, "Glenfiddich 12"),
        (GLENFIDDICH_12, "글렌피딕 12년"),
        (GLENFIDDICH_15, "Glenfiddich 15"),
        (LASANTA, "Glenmorangie Lasanta"),
        (LASANTA, "글렌모렌지 라산타"),
        # The same ambiguous menu spelling registered for two products.
        (MACALLAN_12_SHERRY, "맥캘란 12"),
        (MACALLAN_12_DOUBLE, "맥캘란 12"),
        (ARDBEG_10, "Ardbeg 10Y"),
        (ARDBEG_10, "아드벡 10년"),
        (MONKEY_SHOULDER, "Monkey Shoulder"),
        (MONKEY_SHOULDER, "몽키숄더"),
    ]
    return InMemoryCatalog(products, aliases)


def ids(result):
    return [candidate.product_id for candidate in result.candidates]


def test_exact_match(catalog):
    result = resolve_product(ExtractedProduct(product_name=" 딘스톤 12年 "), catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == DEANSTON_12
    [candidate] = result.candidates
    assert candidate.product_id == DEANSTON_12
    assert candidate.rank == 1
    assert candidate.score == 1.0
    assert candidate.method == "alias"
    assert candidate.evidence == {"aliasExact": True, "matchedAlias": "딘스톤12"}


def test_exact_match_with_same_age_records_age_exact(catalog):
    result = resolve_product(ExtractedProduct(product_name="Deanston 12", age_years=12), catalog)

    assert result.status == "exact_match"
    assert result.candidates[0].evidence["ageExact"] is True


def test_product_name_null_is_unmatched(catalog):
    result = resolve_product(ExtractedProduct(product_name=None, brand_name="딘스톤", age_years=12), catalog)

    assert result.status == "unmatched"
    assert result.candidates == ()
    assert result.proposed_product_id is None


def test_no_alias_match_is_unmatched(catalog):
    result = resolve_product(ExtractedProduct(product_name="헤네시 VSOP"), catalog)

    assert result.status == "unmatched"
    assert result.candidates == ()
    assert result.proposed_product_id is None


def test_symbols_only_name_is_unmatched(catalog):
    assert resolve_product(ExtractedProduct(product_name=" - "), catalog).status == "unmatched"


def test_alias_shared_by_several_products_is_ambiguous(catalog):
    result = resolve_product(ExtractedProduct(product_name="맥캘란 12년"), catalog)

    assert result.status == "ambiguous"
    # Same conflict state, so ordered by display_name.
    assert ids(result) == [MACALLAN_12_DOUBLE, MACALLAN_12_SHERRY]
    assert [c.rank for c in result.candidates] == [1, 2]
    assert all(c.method == "alias" and c.evidence["aliasExact"] for c in result.candidates)
    assert result.proposed_product_id == MACALLAN_12_DOUBLE


def test_age_conflict_is_ambiguous(catalog):
    result = resolve_product(ExtractedProduct(product_name="글렌피딕 12년", age_years=15), catalog)

    assert result.status == "ambiguous"
    [candidate] = result.candidates
    assert candidate.product_id == GLENFIDDICH_12
    assert candidate.evidence["ageConflict"] is True
    assert result.proposed_product_id == GLENFIDDICH_12


def test_age_null_on_product_side_is_not_a_conflict(catalog):
    result = resolve_product(ExtractedProduct(product_name="몽키숄더", age_years=12), catalog)

    assert result.status == "exact_match"
    assert "ageConflict" not in result.candidates[0].evidence
    assert "ageExact" not in result.candidates[0].evidence


def test_edition_found_in_korean_alias_is_exact(catalog):
    item = ExtractedProduct(product_name="글렌모렌지 라산타", brand_name="글렌모렌지", edition_name="라산타")
    result = resolve_product(item, catalog)

    assert result.status == "exact_match"
    assert result.candidates[0].evidence["editionExact"] is True


def test_edition_matching_catalog_edition_name_is_exact(catalog):
    item = ExtractedProduct(product_name="글렌모렌지 라산타", edition_name="LASANTA")
    result = resolve_product(item, catalog)

    assert result.status == "exact_match"
    assert result.candidates[0].evidence["editionExact"] is True


def test_edition_conflict_is_ambiguous(catalog):
    item = ExtractedProduct(product_name="글렌모렌지 라산타", edition_name="넥타도르")
    result = resolve_product(item, catalog)

    assert result.status == "ambiguous"
    assert ids(result) == [LASANTA]
    assert result.candidates[0].evidence["editionConflict"] is True


def test_edition_only_on_product_side_is_exact(catalog):
    result = resolve_product(ExtractedProduct(product_name="글렌모렌지 라산타"), catalog)

    assert result.status == "exact_match"
    assert result.candidates[0].evidence == {"aliasExact": True, "matchedAlias": "글렌모렌지라산타"}


def test_edition_only_in_extracted_is_ambiguous(catalog):
    item = ExtractedProduct(product_name="아드벡 10년", edition_name="우거다일")
    result = resolve_product(item, catalog)

    assert result.status == "ambiguous"
    assert ids(result) == [ARDBEG_10]
    assert result.candidates[0].evidence["editionOnlyInExtracted"] is True


def test_candidates_without_conflict_rank_first(catalog):
    item = ExtractedProduct(product_name="맥캘란 12", edition_name="셰리 오크")
    result = resolve_product(item, catalog)

    # "셰리오크" is in neither product's aliases, so both conflict and keep display_name order.
    assert result.status == "ambiguous"
    assert ids(result) == [MACALLAN_12_DOUBLE, MACALLAN_12_SHERRY]

    item = ExtractedProduct(product_name="맥캘란 12", edition_name="Sherry Oak")
    result = resolve_product(item, catalog)

    assert result.status == "ambiguous"
    assert ids(result) == [MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE]
    assert result.candidates[0].evidence["editionExact"] is True
    assert result.candidates[1].evidence["editionConflict"] is True
    assert result.proposed_product_id == MACALLAN_12_SHERRY


def test_bilingual_both_parts_same_product(catalog):
    result = resolve_product(ExtractedProduct(product_name="아드벡10년 / Ardbeg 10Y"), catalog)

    assert result.status == "exact_match"
    [candidate] = result.candidates
    assert candidate.product_id == ARDBEG_10
    assert candidate.evidence["splitBilingual"] is True
    assert candidate.evidence["matchedAlias"] == "아드벡10"


def test_bilingual_only_one_part_matches(catalog):
    result = resolve_product(ExtractedProduct(product_name="몽키숄더 / Monkey Shoulderr"), catalog)

    assert result.status == "exact_match"
    assert ids(result) == [MONKEY_SHOULDER]
    assert result.candidates[0].evidence["splitBilingual"] is True


def test_bilingual_parts_on_different_products_are_ambiguous(catalog):
    result = resolve_product(ExtractedProduct(product_name="딘스톤 12년 / Glenfiddich 12"), catalog)

    assert result.status == "ambiguous"
    assert ids(result) == [DEANSTON_12, GLENFIDDICH_12]
    assert all(c.evidence["splitBilingual"] for c in result.candidates)


def test_bilingual_split_still_checks_conflicts(catalog):
    item = ExtractedProduct(product_name="아드벡10년 / Ardbeg 10Y", age_years=12)
    result = resolve_product(item, catalog)

    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["ageConflict"] is True


def test_bilingual_no_part_matches_is_unmatched(catalog):
    result = resolve_product(ExtractedProduct(product_name="헤네시vsop / Hennessy vsop"), catalog)

    assert result.status == "unmatched"


def test_whole_name_match_is_used_before_splitting():
    product_id = UUID("00000000-0000-0000-0000-0000000000aa")
    other_id = UUID("00000000-0000-0000-0000-0000000000bb")
    catalog = InMemoryCatalog(
        [ProductInfo(product_id, "A B"), ProductInfo(other_id, "A")],
        [(product_id, "에이 / A"), (other_id, "에이")],
    )

    result = resolve_product(ExtractedProduct(product_name="에이 / A"), catalog)

    assert result.status == "exact_match"
    assert ids(result) == [product_id]
    assert "splitBilingual" not in result.candidates[0].evidence
