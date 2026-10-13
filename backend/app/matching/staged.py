# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P22). Reviewed by Jinwoo Park.
"""Product resolution with optional stages on top of `resolve_product` (eval_plan.md, 매칭 평가).

    resolve_product_staged(item, catalog, stages={"S1", "S2"})

With no stages this is exactly `resolve_product`, which menu import still uses.
Stages only add lookups; `normalize` and the alias rules stay the same.

S1  name preprocessing, tried only when the plain lookup finds nothing
    - "제목(English) 나머지" is also looked up as "제목 나머지" and "English 나머지"
    - "A / B" in one script (both Latin or both Hangul) whose sides are exact
      matches to products of different brands is returned as status "multi"
      (one line naming two products). Korean / English pairs stay one product.
S2  brand + attributes (needs S1), tried only when no alias matched
    - the brand is found from the start of the name (or of a S1 variant) via brand aliases
    - the rest gives an age ("12년", "12Y", "12yo", a bare "12") and edition tokens
    - the brand's products are narrowed to that age, then by the edition tokens.
      Exact only for a single product that every edition token fits; with no
      age, only when edition tokens pick out one product. Anything else is
      ambiguous (owner picks) or unmatched.
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import replace
from typing import Any
from uuid import UUID

from app.core.normalize import normalize
from app.matching.resolve import BILINGUAL_SEPARATOR, resolve_product
from app.matching.types import Candidate, CatalogLookup, ExtractedProduct, ProductInfo, ResolutionResult

STAGES = frozenset({"S1", "S2"})
BRAND_ATTRIBUTE_SCORE = 0.8

UNMATCHED = ResolutionResult(status="unmatched")

# "제목(English) 나머지": the first parenthesized part and the text around it.
_PARENTHESIZED = re.compile(r"^(?P<title>[^()]*?)\s*\((?P<inner>[^()]+)\)\s*(?P<rest>.*)$")
_LATIN = re.compile(r"[A-Za-z]")
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
# Evidence keys that mean a candidate may not be an exact match.
_BLOCKING_EVIDENCE = ("ageConflict", "editionConflict", "editionOnlyInExtracted", "editionUnmatched")

# S2. Age with a unit ("12년", "12Y", "12 yo", "12yDW" -> 12 and "DW"), or a bare 1-2 digit number.
_AGE_WITH_UNIT = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:years?\s*old|years?|yo|y|년|年)", re.IGNORECASE)
_BARE_AGE = re.compile(r"^\d{1,2}$")
# Name before the first digit, for Korean menus without spaces ("라프로익25년").
_HEAD_BEFORE_DIGIT = re.compile(r"^(?P<head>\D+?)\s*(?P<rest>\d.*)$")
# Category words that say nothing about the edition.
_NEUTRAL_TOKENS = frozenset({"whisky", "whiskey", "위스키"})
# Shorter edition tokens ("DR", "PX") are too easy to find by accident inside an alias,
# so they are kept but never count as fitting a product.
_MIN_LATIN_TOKEN = 3
_MIN_OTHER_TOKEN = 2


def resolve_product_staged(
    item: ExtractedProduct, catalog: CatalogLookup, stages: Collection[str] = ()
) -> ResolutionResult:
    stages = frozenset(stages)
    if not stages <= STAGES:
        raise ValueError(f"Unknown matching stages: {sorted(stages - STAGES)}")
    if "S2" in stages and "S1" not in stages:
        raise ValueError("Stage S2 runs on top of S1")
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
    if result.status != "unmatched" or "S2" not in stages:
        return result

    # S2: the whole name, its parenthesis variants, and each side of "A / B".
    names = [item.product_name, *variants]
    if BILINGUAL_SEPARATOR in item.product_name:
        names += [side.strip() for side in item.product_name.split(BILINGUAL_SEPARATOR) if side.strip()]
    return _merge(((name, _resolve_by_brand(name, item, catalog)) for name in names), "brandName")


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


def _blocked(candidate: Candidate) -> bool:
    return any(key in candidate.evidence for key in _BLOCKING_EVIDENCE)


def _merge(results: Iterable[tuple[str, ResolutionResult]], evidence_key: str) -> ResolutionResult:
    """Combine lookups of several names for one line.

    Exact only when every name that found something returned exact_match for the
    same single product; otherwise the union of candidates is ambiguous.
    """
    found: dict[UUID, Candidate] = {}
    all_exact = True
    for name, result in results:
        if result.status == "unmatched":
            continue
        all_exact = all_exact and result.status == "exact_match"
        for candidate in result.candidates:
            if candidate.product_id not in found:
                evidence: dict[str, Any] = {**candidate.evidence, evidence_key: name}
                found[candidate.product_id] = replace(candidate, evidence=evidence)
    if not found:
        return UNMATCHED

    ordered = sorted(found.values(), key=lambda c: (_blocked(c), c.rank, str(c.product_id)))
    candidates = tuple(replace(c, rank=rank) for rank, c in enumerate(ordered, start=1))
    exact = all_exact and len(candidates) == 1 and not _blocked(candidates[0])
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


# --- S2: brand + attributes ---------------------------------------------------------


def _find_brand(name: str, catalog: CatalogLookup) -> tuple[list[UUID], str, str] | None:
    """Return (brand ids, matched brand alias, rest of the name) for the longest leading brand alias."""
    words = name.split()
    for count in range(len(words), 0, -1):
        alias = normalize(" ".join(words[:count]))
        brand_ids = catalog.find_brand_ids_by_alias(alias) if alias else []
        if brand_ids:
            return brand_ids, alias, " ".join(words[count:])
    match = _HEAD_BEFORE_DIGIT.match(name)
    if match is not None:
        alias = normalize(match["head"])
        brand_ids = catalog.find_brand_ids_by_alias(alias) if alias else []
        if brand_ids:
            return brand_ids, alias, match["rest"]
    return None


def _split_age(rest: str) -> tuple[int | None, list[str]]:
    """"더블캐스크 12Y" -> (12, ["더블캐스크"]). Only one age is taken; a second number stays a token."""
    age = None
    match = _AGE_WITH_UNIT.search(rest)
    if match is not None:
        age = int(match[1])
        rest = f"{rest[: match.start()]} {rest[match.end():]}"
    tokens = []
    for word in rest.split():
        if age is None and _BARE_AGE.match(word):
            age = int(word)
            continue
        token = normalize(word)
        if token and token not in _NEUTRAL_TOKENS:
            tokens.append(token)
    return age, tokens


def _token_fits(token: str, targets: list[str]) -> bool:
    min_length = _MIN_LATIN_TOKEN if token.isascii() else _MIN_OTHER_TOKEN
    return len(token) >= min_length and any(token in target for target in targets)


def _resolve_by_brand(name: str, item: ExtractedProduct, catalog: CatalogLookup) -> ResolutionResult:
    found = _find_brand(name, catalog)
    if found is None:
        return UNMATCHED
    brand_ids, brand_alias, rest = found
    age, tokens = _split_age(rest)
    if age is None:
        age = item.age_years

    products: list[ProductInfo] = []
    for brand_id in brand_ids:
        for product_id in catalog.get_brand_product_ids(brand_id):
            product = catalog.get_product(product_id)
            if product is not None:
                products.append(product)
    if age is not None:
        products = [product for product in products if product.age_years == age]
    if not products:
        return UNMATCHED

    # Which edition tokens fit each product (its edition name or any of its aliases).
    fits: list[tuple[ProductInfo, list[str]]] = []
    for product in products:
        targets = [*catalog.get_normalized_aliases(product.product_id)]
        if product.edition_name:
            targets.append(normalize(product.edition_name))
        fits.append((product, [token for token in tokens if _token_fits(token, targets)]))

    full = [product for product, fitted in fits if len(fitted) == len(tokens)]
    if age is not None:
        exact = len(full) == 1 and (len(products) == 1 or bool(tokens))
        chosen = full if exact else [product for product, _ in fits]
    else:
        # No age: only edition tokens can pick the product.
        exact = bool(tokens) and len(full) == 1
        chosen = full if exact else [product for product, fitted in fits if fitted or not tokens]
    if not chosen:
        return UNMATCHED

    by_fit = {product.product_id: fitted for product, fitted in fits}
    ranked = sorted(chosen, key=lambda p: (-len(by_fit[p.product_id]), p.display_name, str(p.product_id)))
    candidates = []
    for rank, product in enumerate(ranked, start=1):
        fitted = by_fit[product.product_id]
        evidence: dict[str, Any] = {"brandMatch": brand_alias}
        if age is not None:
            evidence["ageMatch"] = age
        if fitted:
            evidence["editionMatch"] = fitted
        unfitted = [token for token in tokens if token not in fitted]
        if unfitted:
            evidence["editionUnmatched"] = unfitted
        candidates.append(
            Candidate(
                product_id=product.product_id,
                rank=rank,
                score=BRAND_ATTRIBUTE_SCORE,
                method="alias",
                evidence=evidence,
            )
        )
    return ResolutionResult(
        status="exact_match" if exact else "ambiguous",
        candidates=tuple(candidates),
        proposed_product_id=candidates[0].product_id,
    )
