"""Matching a menu name the reviewer or owner corrected, and comparing a chosen product with what the AI read.

Used when a review is submitted (API spec 8.7, 8.11) and when a menu item is edited (3.14.4). Neither
request calls the AI: only the rule matcher runs, on the corrected name alone.
"""

from uuid import UUID

from app.core.normalize import normalize
from app.matching.resolve import _compare_attributes
from app.matching.staged import STAGES, resolve_product_staged
from app.matching.types import CatalogLookup, ExtractedProduct


def name_corrected(corrected: str | None, extracted: str | None) -> bool:
    """Whether a corrected menu name is a different name (spec 8.11): spacing and symbols alone are not.
    A line the AI read no name for counts as corrected once a name is sent."""
    if corrected is None:
        return False
    if extracted is None:
        return True
    return normalize(corrected) != normalize(extracted)


def rematch_name(name: str, catalog: CatalogLookup) -> UUID | None:
    """The one product the rule matcher confirms for `name` alone, else None (spec 8.11).

    The brand, age, edition and ABV the AI read came from the old name, so they are left out; the LLM
    and embedding layers never run. The catalog finds active products only, so an inactive product is
    never confirmed. A line naming two products ("multi") is not one product.
    """
    result = resolve_product_staged(ExtractedProduct(product_name=name), catalog, STAGES)
    return result.proposed_product_id if result.status == "exact_match" else None


def attribute_conflict(
    product_id: UUID, age_years: int | None, edition_name: str | None, catalog: CatalogLookup
) -> bool:
    """Whether the product's age or edition conflicts with what the AI read from the line (spec 8.7,
    matching flow 10): both ages known and different, an extracted edition found neither in the product's
    edition name nor in its aliases, or an edition only on the extracted side. The same rule that keeps
    a line from being confirmed automatically, so an automatic match never conflicts."""
    product = catalog.get_product(product_id)
    if product is None:
        return False
    item = ExtractedProduct(age_years=age_years, edition_name=edition_name)
    return _compare_attributes(item, product, catalog, {})
