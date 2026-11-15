from uuid import UUID

import pytest

from app.matching import ProductInfo
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.rematch import attribute_conflict, name_corrected, rematch_name


def _id(n: int) -> UUID:
    return UUID(int=n)


GLENFIDDICH, MACALLAN = _id(101), _id(102)
GLENFIDDICH_12, GLENFIDDICH_15, MACALLAN_12_SHERRY, MACALLAN_12_DOUBLE = (_id(n) for n in range(1, 5))


@pytest.fixture
def catalog():
    products = [
        ProductInfo(GLENFIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=GLENFIDDICH),
        ProductInfo(GLENFIDDICH_15, "Glenfiddich 15", age_years=15, brand_id=GLENFIDDICH),
        ProductInfo(MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak", 12, "Sherry Oak", brand_id=MACALLAN),
        ProductInfo(MACALLAN_12_DOUBLE, "Macallan 12 Double Cask", 12, "Double Cask", brand_id=MACALLAN),
    ]
    aliases = [
        (GLENFIDDICH_12, "Glenfiddich 12"),
        (GLENFIDDICH_12, "글렌피딕 12년"),
        (GLENFIDDICH_15, "Glenfiddich 15"),
        (MACALLAN_12_SHERRY, "Macallan 12 Sherry Oak"),
        (MACALLAN_12_SHERRY, "맥캘란 12년 셰리 오크"),
        (MACALLAN_12_DOUBLE, "Macallan 12 Double Cask"),
    ]
    brand_aliases = [(GLENFIDDICH, "Glenfiddich"), (GLENFIDDICH, "글렌피딕"), (MACALLAN, "Macallan"), (MACALLAN, "맥캘란")]
    return InMemoryCatalog(products, aliases, brand_aliases)


@pytest.mark.parametrize(
    ("corrected", "extracted", "expected"),
    [
        (None, "Glenfiddich 12", False),  # no corrected name sent
        (None, None, False),
        ("Glenfiddich 12", None, True),  # the AI read no name
        ("Glenfiddich  12!", "glenfiddich 12", False),  # spacing, symbols and case only
        ("Glenfiddich 15", "Glenfiddich 12", True),
    ],
)
def test_a_name_is_corrected_only_when_it_normalizes_differently(corrected, extracted, expected):
    assert name_corrected(corrected, extracted) is expected


def test_rematch_confirms_the_one_product_the_name_names(catalog):
    assert rematch_name("글렌피딕 12년", catalog) == GLENFIDDICH_12
    assert rematch_name("Glenfiddich 15", catalog) == GLENFIDDICH_15


def test_rematch_confirms_nothing_for_a_name_of_several_products_or_none(catalog):
    assert rematch_name("Macallan 12", catalog) is None  # Sherry Oak or Double Cask
    assert rematch_name("Unknown Whisky", catalog) is None


def test_rematch_ignores_the_values_read_from_the_old_name(catalog):
    # Only the name is matched: an age read from the old name cannot make the new name ambiguous.
    assert rematch_name("Glenfiddich 15", catalog) == GLENFIDDICH_15


@pytest.mark.parametrize(
    ("product_id", "age", "edition", "expected"),
    [
        (GLENFIDDICH_12, None, None, False),  # nothing read
        (GLENFIDDICH_12, 12, None, False),
        (GLENFIDDICH_12, 15, None, True),  # ageConflict
        (GLENFIDDICH_12, None, "Sherry Cask", True),  # editionOnlyInExtracted
        (MACALLAN_12_SHERRY, 12, "Sherry Oak", False),
        (MACALLAN_12_SHERRY, 12, "셰리 오크", False),  # found in the product's aliases
        (MACALLAN_12_SHERRY, 12, "Double Cask", True),  # editionConflict
        (_id(999), 15, "Anything", False),  # not an active product of the catalog
    ],
)
def test_attribute_conflict_follows_the_matching_rules(catalog, product_id, age, edition, expected):
    assert attribute_conflict(product_id, age, edition, catalog) is expected
