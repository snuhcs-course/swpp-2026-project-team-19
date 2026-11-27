"""Older ages a product is also known by (I5-P59, catalog v2.6).

When a producer changes the age on a bottle, bars keep pouring the old bottle next to the new one
and the menu keeps the age it was first written with. The catalog keeps one product with the
current age (`age_years`). An age on a menu line, or one extraction read, that is one of the ages
here counts as that product's age: it is no ageConflict, the brand + age step (staged S2) finds the
product by it, and the evidence says which age matched (`ageAccepted`).

The table is here and not in the catalog tables because the server reads product rows from the
database only, and this needs no schema change. The database rows have the ids of
`ai/catalog/catalog_v2_service.json` (`scripts/seed_catalog.py` loads them by id), so the keys are
those ids. Every `CatalogLookup` fills `ProductInfo.accepted_ages` from here.
"""

from uuid import UUID

ACCEPTED_AGES: dict[UUID, tuple[int, ...]] = {
    UUID("ec660a60-db4b-5562-ad97-d0349b0be56b"): (10,),  # Glenmorangie The Original: 12, the old bottle 10
    UUID("a2688e71-6071-5151-acf9-af69db359d70"): (12,),  # Glenmorangie Lasanta: 15 since 2025, the old bottle 12
    UUID("59218382-d515-5e3f-b066-1b8662e98f4d"): (12,),  # Glenmorangie Quinta Ruban: 14, the old bottle 12
    # Glenmorangie The Nectar (16, formerly Nectar D'Or) has none: sources disagree on its older age.
}


def accepted_ages(product_id: UUID) -> tuple[int, ...]:
    """The older ages of the product, besides its `age_years` (empty for most products)."""
    return ACCEPTED_AGES.get(product_id, ())
