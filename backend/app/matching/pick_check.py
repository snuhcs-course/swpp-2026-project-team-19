"""Does the product the reviewer picked fit the menu line? (I4-P18, for the operator check of API spec 8.7)

A reviewer can link a line to any product. The pick goes to the operator check when it does not
fit the line:

- `ageConflict`: the line's age (`extracted_age_years`) and the product's age are both known and differ.
- `editionNotClosest`: among the products of the picked product's brand whose age fits the line
  (same age, or no age on either side), another product is closer to the line by more than
  EDITION_MARGIN in the embedding (the server's character n-gram TF-IDF over display names and
  aliases, `app.adapters.embedding`).

The edition is compared by embedding and not as text because the line's edition is read from a
menu ("솔리스트 셰리 오크", "디스틸러리 12Y", "배치 4") and is seldom written as the catalog writes it.
The query is the name as written, then the name with the Korean whisky terms in English
(`vocab_ko_en.json`), then that in Latin letters (`app.matching.romanize`), so a Korean line is
not far from English names only because the scripts differ.

Measured with this function and an index of display names and alias texts as the server builds
it, on the dev set (184 lines needing review whose right product is in the catalog, service
catalog) and the I3 set (122, as-is catalog), picking the right product and, separately, every
other product of the same brand:

    right pick sent to the check    dev  9.8 %   I3  9.0 %
    wrong pick caught               dev 89.5 %   I3 87.7 %

Comparing the age and the edition text as matching flow section 10 does (what 8.7 first said)
sent 46.7 % and 34.4 % of the right picks and caught 84.5 % and 76.0 % of the wrong ones.

Only the age and the brand's products are used, never the candidates of the line, so a product
found by search is checked the same way. A product without a brand is checked by age only.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.matching.romanize import romanize
from app.matching.staged import _VOCABULARY
from app.matching.types import CatalogLookup, ProductInfo
from app.matching.vocabulary import to_english

# How much closer to the line another product of the brand may be before the pick is questioned.
# With 0 a few points more wrong picks are caught and a few points more right picks are sent;
# 0.10 sends fewer right picks and lets about 7 points more wrong picks through.
EDITION_MARGIN = 0.05

Similarities = Callable[[str], Mapping[UUID, float]]


@dataclass(frozen=True)
class PickCheck:
    reasons: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def fits(self) -> bool:
        return not self.reasons


def embedding_query(name: str) -> str:
    english = to_english(name, _VOCABULARY) if _VOCABULARY is not None else name
    return " ".join(dict.fromkeys((name, english, romanize(english))))


def check_pick(
    name: str | None,
    line_age: int | None,
    product_id: UUID,
    catalog: CatalogLookup,
    similarities: Similarities,
) -> PickCheck:
    """Whether `product_id` fits the line `name` with the age `line_age`. `similarities(query)`
    gives each indexed product's best similarity to the query (EmbeddingIndex.product_similarities)."""
    product = catalog.get_product(product_id)
    if product is None or not (name or "").strip():
        return PickCheck()
    if line_age is not None and product.age_years is not None and line_age != product.age_years:
        return PickCheck(("ageConflict",), {"lineAge": line_age, "productAge": product.age_years})
    family = _family(product, line_age, catalog)
    if len(family) < 2:
        return PickCheck()
    scores = similarities(embedding_query(name))
    picked = scores.get(product.product_id, 0.0)
    closest = max(family, key=lambda p: (scores.get(p.product_id, 0.0), p.product_id == product.product_id))
    best = scores.get(closest.product_id, 0.0)
    if picked + EDITION_MARGIN < best:
        return PickCheck(("editionNotClosest",), {
            "closestProductId": str(closest.product_id), "closestSimilarity": round(best, 4),
            "similarity": round(picked, 4), "margin": EDITION_MARGIN,
        })
    return PickCheck()


def _family(product: ProductInfo, line_age: int | None, catalog: CatalogLookup) -> list[ProductInfo]:
    """The brand's products the line could name: any age when the line has none, otherwise the
    same age or no age. The picked product is always in it."""
    if product.brand_id is None:
        return [product]
    family = []
    for product_id in catalog.get_brand_product_ids(product.brand_id):
        other = catalog.get_product(product_id)
        if other is not None and (line_age is None or other.age_years in (None, line_age)):
            family.append(other)
    return family if any(p.product_id == product.product_id for p in family) else [*family, product]


_INDEX = None


def db_similarities(session) -> Similarities:
    """Similarities over the current catalog (every active product's display name and aliases), with
    the index the embedding step uses, built once per catalog version in this process. Works
    whether or not the embedding step itself is turned on."""
    global _INDEX
    from app.adapters.embedding import CharTfidfProvider
    from app.matching.embedding import CatalogIndexCache

    if _INDEX is None:
        _INDEX = CatalogIndexCache(CharTfidfProvider())
    return _INDEX.get(session).product_similarities
