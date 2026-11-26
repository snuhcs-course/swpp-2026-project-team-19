"""Guards on a confirmed match, applied last, after the rules and every candidate layer (I4-P18, P38).

    result = apply_linking_guards(product_name, result, catalog)                          # menu import
    result = apply_linking_guards(product_name, result, catalog, incomplete_names=True)   # measurement

A line the rules confirmed (exact_match) is shown to nobody before it is published, so a
confirmed link has to rest on a name that says which product it is and on a product somebody
has checked. Two cases do not, and are turned into a single recommended candidate (status
ambiguous, evidence confirmRecommended) that a person confirms:

unverifiedProduct (P18), always on. `ProductInfo.verified` is False for a product nobody has
checked yet (created in a review and not confirmed by an operator). Matching it is a suggestion,
not a fact. DbCatalog reports every product as verified until the catalog records that check, so
today this guard changes nothing.

incompleteName (P38), off unless `incomplete_names=True`. Measured on the rule matcher
(2026-11-13, ai/regression/guard_effect.py): it takes the confirmation from 6 of 836 dev lines and
7 of 675 I3 lines, every one of them matched to the right product, and from none of the false
merges. It costs the owner a tap per line and prevented nothing in the data we have, so menu
import does not turn it on. A menu spelling that is only a brand ("잭다니엘"), or only a brand and an
age ("발베니 12년"), can be an alias of one product because some bar's menu meant that product.
On another menu the same words can mean a sibling.
  brand_only  the name has no age and no edition word, the product has an age or an edition,
              and its brand has other products
  age_only    the name has an age and no edition word, the product has an edition, and its
              brand has another product of that age
A product whose edition is only a category word ("Four Roses Bourbon") counts as the brand's
plain bottling. A name the brand rules cannot read, and a brand with nothing to confuse the
product with, stay confirmed.

missingAge (I5-P59), off unless `missing_age=True` (menu import: MATCHING_MISSING_AGE_GUARD=true).
The line has no age and the product has one ("Ardbeg Anthology" confirmed as Ardbeg Anthology 14,
the false merge of I3 and I4): a bar may pour a sibling the catalog does not have. The line has an
age when its name has a one- or two-digit number that is not part of a longer number, a strength,
a volume or a price ("12년", "12Y", "Glenfiddich 12", "라프로익10"; not "14.1", "2025", "700ml"), or
when extraction gave one (`line_age`). Off by default until the numbers are reviewed
(ai/runs/2026-11-27_i5_p31/report.md 1b).

The rules themselves (staged.py) are not changed: they are frozen for the I3 evaluation
(ai/docs/i3_eval_freeze.md 4.5), and the guards only ever take a confirmation away.
"""

import os
import re
from dataclasses import replace

from app.matching.staged import (
    _MEASURE,
    BILINGUAL_SEPARATOR,
    _find_brand,
    _parenthesis_variants,
    _split_age,
    _without_brand,
)
from app.matching.types import CatalogLookup, ProductInfo, ResolutionResult

# An edition made only of these words names the brand's plain bottling, not a variant.
_CATEGORY_WORDS = frozenset({"bourbon", "whisky", "whiskey"})


def apply_linking_guards(name: str | None, result: ResolutionResult, catalog: CatalogLookup, *,
                         incomplete_names: bool = False, missing_age: bool = False,
                         line_age: int | None = None) -> ResolutionResult:
    if result.status != "exact_match" or result.proposed_product_id is None or not result.candidates:
        return result
    product = catalog.get_product(result.proposed_product_id)
    if product is None:
        return result
    evidence = {}
    if not product.verified:
        evidence["unverifiedProduct"] = True
    kind = incomplete_name(name or "", product, catalog) if incomplete_names else None
    if kind is not None:
        evidence["incompleteName"] = kind
    if missing_age and product.age_years is not None and line_age is None and not has_age(name or ""):
        evidence["missingAge"] = product.age_years
    if not evidence:
        return result
    first = result.candidates[0]
    first = replace(first, evidence={**first.evidence, **evidence, "confirmRecommended": True})
    return replace(result, status="ambiguous", candidates=(first, *result.candidates[1:]))


def _has_edition(product: ProductInfo) -> bool:
    return any(word not in _CATEGORY_WORDS for word in (product.edition_name or "").lower().split())


def incomplete_name(name: str, product: ProductInfo, catalog: CatalogLookup) -> str | None:
    """"brand_only" or "age_only" when `name` says less than `product` does (module docstring), else None."""
    if product.brand_id is None:
        return None
    if BILINGUAL_SEPARATOR in name:  # "A / B": each side is a whole name
        names = [side.strip() for side in name.split(BILINGUAL_SEPARATOR) if side.strip()]
    else:
        names = [name, *_parenthesis_variants(name)]
    brand_aliases = [alias for alias, brand_id in catalog.list_normalized_brand_aliases() if brand_id == product.brand_id]
    age, read = None, False
    for variant in names:
        found = _find_brand(variant, catalog)
        if found is None or product.brand_id not in found[0]:
            continue
        variant_age, tokens = _split_age(found[2])
        if _without_brand(tokens, brand_aliases):
            return None  # the name has a word beyond brand and age
        read = True
        age = age if age is not None else variant_age
    if not read:
        return None
    others = [p for pid in catalog.get_brand_product_ids(product.brand_id)
              if pid != product.product_id and (p := catalog.get_product(pid)) is not None]
    if age is None:
        return "brand_only" if others and (product.age_years is not None or _has_edition(product)) else None
    return "age_only" if _has_edition(product) and any(p.age_years == age for p in others) else None


# A one- or two-digit number on its own: not part of "14.1", "2025" or "1,000".
_AGE_NUMBER = re.compile(r"(?<![\d.,])\d{1,2}(?![\d.,])")


def has_age(name: str) -> bool:
    """Whether the line names an age (missingAge): a one- or two-digit number once strength, volume,
    servings and price are left out."""
    return bool(_AGE_NUMBER.search(_MEASURE.sub(" ", name)))


def missing_age_guard_enabled() -> bool:
    """MATCHING_MISSING_AGE_GUARD=true turns the missingAge guard on in menu import (default false)."""
    value = (os.getenv("MATCHING_MISSING_AGE_GUARD") or "false").lower()
    if value not in ("true", "false"):
        raise RuntimeError(f"MATCHING_MISSING_AGE_GUARD must be true or false, got {value!r}")
    return value == "true"
