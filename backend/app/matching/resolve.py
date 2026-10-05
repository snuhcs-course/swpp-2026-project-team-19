"""Initial product resolution for one extracted menu line (matching flow doc, sections 6, 8, 10).

Iteration 1 covers normalization and exact alias matching only. Brand lookup,
similarity scoring and LLM reranking are not implemented yet, so a name with
no exact alias match is returned as unmatched. This module never writes to
the database; the caller stores the result.
"""

from typing import Any
from uuid import UUID

from app.core.normalize import normalize
from app.matching.types import (
    Candidate,
    CatalogLookup,
    ExtractedProduct,
    ProductInfo,
    ResolutionResult,
)

# Menus often print "Korean / English" on one line, e.g. "아드벡10년 / Ardbeg 10Y".
BILINGUAL_SEPARATOR = " / "
ALIAS_EXACT_SCORE = 1.0

UNMATCHED = ResolutionResult(status="unmatched")


def resolve_product(item: ExtractedProduct, catalog: CatalogLookup) -> ResolutionResult:
    if item.product_name is None:
        return UNMATCHED

    hits, split = _find_alias_hits(item.product_name, catalog)

    assessed: list[tuple[ProductInfo, dict[str, Any], bool]] = []
    for product_id, matched_alias in hits.items():
        product = catalog.get_product(product_id)
        if product is None:
            continue
        evidence: dict[str, Any] = {"aliasExact": True, "matchedAlias": matched_alias}
        if split:
            evidence["splitBilingual"] = True
        blocks_exact = _compare_attributes(item, product, catalog, evidence)
        assessed.append((product, evidence, blocks_exact))

    if not assessed:
        return UNMATCHED

    # Candidates without a conflict first, then a stable order for reproducible output.
    assessed.sort(key=lambda entry: (entry[2], entry[0].display_name, str(entry[0].product_id)))
    candidates = tuple(
        Candidate(
            product_id=product.product_id,
            rank=rank,
            score=ALIAS_EXACT_SCORE,
            method="alias",
            evidence=evidence,
        )
        for rank, (product, evidence, _) in enumerate(assessed, start=1)
    )

    exact = len(assessed) == 1 and not assessed[0][2]
    return ResolutionResult(
        status="exact_match" if exact else "ambiguous",
        candidates=candidates,
        proposed_product_id=candidates[0].product_id,
    )


def _find_alias_hits(product_name: str, catalog: CatalogLookup) -> tuple[dict[UUID, str], bool]:
    """Map each matched product id to the normalized alias that found it.

    The whole name is tried first. Only when it has no match and the name has
    the bilingual separator is each part looked up separately.
    """
    whole = normalize(product_name)
    if whole:
        hits = {product_id: whole for product_id in catalog.find_product_ids_by_alias(whole)}
        if hits:
            return hits, False

    if BILINGUAL_SEPARATOR not in product_name:
        return {}, False

    hits: dict[UUID, str] = {}
    for part in product_name.split(BILINGUAL_SEPARATOR):
        key = normalize(part)
        if not key:
            continue
        for product_id in catalog.find_product_ids_by_alias(key):
            hits.setdefault(product_id, key)
    return hits, True


def _compare_attributes(
    item: ExtractedProduct,
    product: ProductInfo,
    catalog: CatalogLookup,
    evidence: dict[str, Any],
) -> bool:
    """Record age and edition signals in `evidence`; return True if exact match is not allowed."""
    blocks_exact = False

    # Age: a conflict only when both values exist and differ.
    if item.age_years is not None and product.age_years is not None:
        if item.age_years == product.age_years:
            evidence["ageExact"] = True
        else:
            evidence["ageConflict"] = True
            blocks_exact = True

    # Edition: the catalog stores English edition names while menus may use
    # Korean (Lasanta vs 라산타), so the extracted edition is also looked for
    # inside the product's aliases. An edition only on the product side is fine;
    # one only on the extracted side cannot be checked and blocks exact match.
    extracted_edition = normalize(item.edition_name) if item.edition_name else ""
    if extracted_edition:
        if product.edition_name is None:
            evidence["editionOnlyInExtracted"] = True
            blocks_exact = True
        else:
            targets = [normalize(product.edition_name), *catalog.get_normalized_aliases(product.product_id)]
            if any(extracted_edition in target for target in targets):
                evidence["editionExact"] = True
            else:
                evidence["editionConflict"] = True
                blocks_exact = True

    return blocks_exact
