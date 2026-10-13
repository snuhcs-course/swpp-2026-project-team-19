# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P22). Reviewed by Jinwoo Park.
"""Product resolution with optional stages on top of `resolve_product` (eval_plan.md, 매칭 평가).

    resolve_product_staged(item, catalog, stages={"S1"})

With no stages this is exactly `resolve_product`, which menu import still uses.
Stages only add lookup names; `normalize` and the alias rules stay the same.

S1  name preprocessing, tried only when the plain lookup finds nothing
    - "제목(English) 나머지" is also looked up as "제목 나머지" and "English 나머지"
    - "A / B" in one script (both Latin or both Hangul) whose sides are exact
      matches to products of different brands is returned as status "multi"
      (one line naming two products). Korean / English pairs stay one product.
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import replace
from typing import Any
from uuid import UUID

from app.core.normalize import normalize
from app.matching.resolve import BILINGUAL_SEPARATOR, resolve_product
from app.matching.types import Candidate, CatalogLookup, ExtractedProduct, ResolutionResult

STAGES = frozenset({"S1"})

UNMATCHED = ResolutionResult(status="unmatched")

# "제목(English) 나머지": the first parenthesized part and the text around it.
_PARENTHESIZED = re.compile(r"^(?P<title>[^()]*?)\s*\((?P<inner>[^()]+)\)\s*(?P<rest>.*)$")
_LATIN = re.compile(r"[A-Za-z]")
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
# Evidence keys `resolve_product` sets when a candidate may not be an exact match.
_BLOCKING_EVIDENCE = ("ageConflict", "editionConflict", "editionOnlyInExtracted")


def resolve_product_staged(
    item: ExtractedProduct, catalog: CatalogLookup, stages: Collection[str] = ()
) -> ResolutionResult:
    stages = frozenset(stages)
    if not stages <= STAGES:
        raise ValueError(f"Unknown matching stages: {sorted(stages - STAGES)}")
    if item.product_name is None:
        return UNMATCHED
    if "S1" in stages:
        pair = _resolve_two_products(item, catalog, stages)
        if pair is not None:
            return pair
    return _resolve_one(item, catalog, stages)


def _resolve_one(item: ExtractedProduct, catalog: CatalogLookup, stages: frozenset[str]) -> ResolutionResult:
    result = resolve_product(item, catalog)
    if result.status != "unmatched" or "S1" not in stages:
        return result
    variants = _parenthesis_variants(item.product_name)
    if variants:
        result = _merge(
            ((variant, resolve_product(replace(item, product_name=variant), catalog)) for variant in variants),
            "parenExpanded",
        )
    return result


def _parenthesis_variants(name: str) -> list[str]:
    """"아벨라워(Aberlour) 12년" -> ["아벨라워 12년", "Aberlour 12년"]."""
    match = _PARENTHESIZED.match(name.strip())
    if match is None:
        return []
    rest = match["rest"].strip()
    variants = []
    for head in (match["title"].strip(), match["inner"].strip()):
        if head:
            variant = f"{head} {rest}".strip()
            if variant not in variants:
                variants.append(variant)
    return variants


def _merge(results: Iterable[tuple[str, ResolutionResult]], evidence_key: str) -> ResolutionResult:
    """Combine lookups of several names for one line.

    Exact only when every name that found something found the same single
    product without a conflict; otherwise the union of candidates is ambiguous.
    """
    found: dict[UUID, Candidate] = {}
    for name, result in results:
        for candidate in result.candidates:
            if candidate.product_id not in found:
                evidence: dict[str, Any] = {**candidate.evidence, evidence_key: name}
                found[candidate.product_id] = replace(candidate, evidence=evidence)
    if not found:
        return UNMATCHED

    def blocked(candidate: Candidate) -> bool:
        return any(key in candidate.evidence for key in _BLOCKING_EVIDENCE)

    ordered = sorted(found.values(), key=lambda c: (blocked(c), c.rank, str(c.product_id)))
    candidates = tuple(replace(c, rank=rank) for rank, c in enumerate(ordered, start=1))
    exact = len(candidates) == 1 and not blocked(candidates[0])
    return ResolutionResult(
        status="exact_match" if exact else "ambiguous",
        candidates=candidates,
        proposed_product_id=candidates[0].product_id,
    )


def _script(text: str) -> str | None:
    latin, hangul = bool(_LATIN.search(text)), bool(_HANGUL.search(text))
    if latin == hangul:
        return None
    return "latin" if latin else "hangul"


def _resolve_two_products(
    item: ExtractedProduct, catalog: CatalogLookup, stages: frozenset[str]
) -> ResolutionResult | None:
    """"Buffalo Trace / Maker's Mark" -> status "multi", or None if the line is not two products."""
    name = item.product_name
    if BILINGUAL_SEPARATOR not in name:
        return None
    # A registered alias for the whole line means one product.
    whole = normalize(name)
    if whole and catalog.find_product_ids_by_alias(whole):
        return None
    sides = [side.strip() for side in name.split(BILINGUAL_SEPARATOR)]
    if len(sides) != 2 or not all(sides):
        return None
    scripts = {_script(side) for side in sides}
    if len(scripts) != 1 or None in scripts:
        return None

    parts = [_resolve_one(replace(item, product_name=side), catalog, stages) for side in sides]
    if any(part.status != "exact_match" for part in parts):
        return None
    products = [catalog.get_product(part.proposed_product_id) for part in parts]
    if any(product is None or product.brand_id is None for product in products):
        return None
    if products[0].brand_id == products[1].brand_id:
        return None

    candidates = tuple(
        replace(part.candidates[0], rank=rank, evidence={**part.candidates[0].evidence, "multiProduct": side})
        for rank, (side, part) in enumerate(zip(sides, parts, strict=True), start=1)
    )
    return ResolutionResult(status="multi", candidates=candidates, parts=tuple(parts))
