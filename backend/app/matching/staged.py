"""Product resolution with optional stages on top of `resolve_product` (eval_plan.md, 매칭 평가).

    resolve_product_staged(item, catalog, stages={"S1", "S2", "S2b", "S3"})

With no stages this is exactly `resolve_product`. Menu import calls it with S1, S2,
S2b and S3 (I2-A18). Stages only add lookups; `normalize` and the alias rules stay
the same.

With any stage, every candidate's evidence also gets `rule`, the step that found it:
"alias" (the plain exact alias lookup), "S1", "S2", "S2b" or "S3". An exact_match
decided by a rule can then be told apart from an exact alias match.

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
    - the brand written again ("Aberlour 12 (아벨라워)", also over two tokens) is not an
      edition token, a name variant that is only a brand is used only when the other
      names find nothing, and with no age, Latin letter tokens too short to check ("DR")
      do not rule a product out; numbers still do (I3-A4)
    - numbers on the line other than the age (a year, "#2", "16.2"; strength, volume,
      servings and prices such as "46%", "700 ml", "16,000원" left out) rule out a product
      whose name has numbers and none of them (Classic Cut 2020 for "클래식컷 2025") (I3-A4)
    - when edition tokens picked the product but its edition name has words the line
      does not have ("anCnoc Sherry" -> anCnoc Peated Sherry Cask), the line is
      ambiguous with that one candidate, evidence editionOnlyInProduct and
      confirmRecommended (I3-A4). Words such as cask, oak, finish do not count, and
      when the line has Hangul words the vocabulary does not know ("비노 바리끄"), only
      words the vocabulary could have translated count as missing.
S2b default product (needs S2), applied to the products S2 narrowed by brand + age
    - no edition token and exactly one product of that age without an edition -> exact
    - one candidate that has an edition but no edition token in the name -> ambiguous
      with evidence confirmRecommended ("확인 권장")
S3  edit distance (needs S2b), tried only when S2 found nothing either
    - menu name vs product aliases, and the start of the name vs brand aliases (then S2b)
    - the digits must be identical and in the same order; the rest may differ by an
      edit distance of 1 (6 characters or fewer) or 2 (longer), counting Hangul syllables
    - never exact, except one candidate at distance <= 1 for a name with digits;
      otherwise ambiguous, with confirmRecommended when there is one candidate
    - where that exact case has a Hangul name part of 3 syllables or fewer (the text
      before the first number, without a leading 더/The and punctuation: 달모어 18 vs
      보모어 18, 더 달무어 18, 아드백-10), S3 offers nothing (I3-A4)

Korean whisky words (with S2, I3-A4): a line that S1-S3 leave unconfirmed is looked up
again with the Hangul words of `vocab_ko_en.json` in English (셰리 캐스크 -> sherry cask,
`vocabulary.py`). The retry is taken when it confirms the line, or finds candidates for
a line that had none and an edition token fits the first candidate (not brand + age
alone: 시그나토리 쿨일라13 is not offered Signatory Macduff 13). Its candidates get
evidence `vocabulary` (the English name) and keep the `rule` of the step that found them.
"""

import re
import unicodedata
from collections.abc import Collection, Iterable
from dataclasses import replace
from typing import Any
from uuid import UUID

from app.core.normalize import normalize
from app.matching.resolve import BILINGUAL_SEPARATOR, resolve_product
from app.matching.types import Candidate, CatalogLookup, ExtractedProduct, ProductInfo, ResolutionResult
from app.matching.vocabulary import Vocabulary, load_vocabulary, to_english

STAGES = frozenset({"S1", "S2", "S2b", "S3"})
# Each stage runs on top of the one named here.
_NEEDS = {"S2": "S1", "S2b": "S2", "S3": "S2b"}
BRAND_ATTRIBUTE_SCORE = 0.8
EDIT_DISTANCE_SCORE = 0.6

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
# Korean -> English whisky words (vocab_ko_en.json): the retry after S1-S3 and the edition check.
_VOCABULARY: Vocabulary | None = load_vocabulary()
_VOCABULARY_WORDS = frozenset(word for term in _VOCABULARY.english.values() for word in term.split())
_CONFIRMED = ("exact_match", "multi")


def resolve_product_staged(
    item: ExtractedProduct, catalog: CatalogLookup, stages: Collection[str] = ()
) -> ResolutionResult:
    stages = frozenset(stages)
    if not stages <= STAGES:
        raise ValueError(f"Unknown matching stages: {sorted(stages - STAGES)}")
    for stage, needed in _NEEDS.items():
        if stage in stages and needed not in stages:
            raise ValueError(f"Stage {stage} runs on top of {needed}")
    if item.product_name is None:
        return UNMATCHED
    result = _resolve_line(item, catalog, stages)
    if "S2" not in stages or _VOCABULARY is None or result.status in _CONFIRMED:
        return result
    # Korean whisky words in English: taken when that confirms the line, or finds candidates
    # for a line that had none and an edition word fits the first of them (not brand + age only).
    english = to_english(item.product_name, _VOCABULARY)
    if english == item.product_name:
        return result
    retry = _resolve_line(replace(item, product_name=english), catalog, stages)
    if retry.status in _CONFIRMED or (result.status == "unmatched" and _words_fit(retry)):
        candidates = tuple(replace(c, evidence={**c.evidence, "vocabulary": english}) for c in retry.candidates)
        return replace(retry, candidates=candidates)
    return result


def _words_fit(result: ResolutionResult) -> bool:
    """The first candidate fits an edition token, or the line has none left over."""
    if not result.candidates:
        return False
    evidence = result.candidates[0].evidence
    return bool(evidence.get("editionMatch")) or "editionUnmatched" not in evidence


def _resolve_line(item: ExtractedProduct, catalog: CatalogLookup, stages: frozenset[str]) -> ResolutionResult:
    if "S1" in stages:
        pair = _resolve_two_products(item, catalog, stages)
        if pair is not None:
            return pair
    return _resolve_one(item, catalog, stages)


def _with_rule(result: ResolutionResult, rule: str) -> ResolutionResult:
    """Record the step that found each candidate in its evidence ("rule").

    S2 candidates chosen by the S2b default-product rule (defaultProduct, or confirmRecommended,
    which S2 only sets with S2b) are recorded as "S2b".
    """

    def rule_of(candidate: Candidate) -> str:
        evidence = candidate.evidence
        default = "defaultProduct" in evidence
        if rule == "S2" and (default or ("confirmRecommended" in evidence and "editionOnlyInProduct" not in evidence)):
            return "S2b"
        return rule

    candidates = tuple(replace(c, evidence={**c.evidence, "rule": rule_of(c)}) for c in result.candidates)
    return replace(result, candidates=candidates)


def _resolve_one(item: ExtractedProduct, catalog: CatalogLookup, stages: frozenset[str]) -> ResolutionResult:
    result = resolve_product(item, catalog)
    if not stages:
        return result
    if result.status != "unmatched" or "S1" not in stages:
        return _with_rule(result, "alias")
    variants = _parenthesis_variants(item.product_name)
    if variants:
        result = _merge(
            ((variant, resolve_product(replace(item, product_name=variant), catalog)) for variant in variants),
            "parenExpanded",
        )
    if result.status != "unmatched" or "S2" not in stages:
        return _with_rule(result, "S1")

    # S2: the whole name, its parenthesis variants, and each side of "A / B".
    names = [item.product_name, *variants]
    if BILINGUAL_SEPARATOR in item.product_name:
        names += [side.strip() for side in item.product_name.split(BILINGUAL_SEPARATOR) if side.strip()]
    default_product = "S2b" in stages

    def by_brand(lookup_names: list[str]) -> ResolutionResult:
        lookups = ((name, _resolve_by_brand(name, item, catalog, default_product)) for name in lookup_names)
        return _merge(lookups, "brandName")

    # A name that is only a brand ("아벨라워" of "Aberlour 12 (아벨라워)") offers every product
    # of it, so it is used only when the other names find nothing.
    informative = [name for name in names if not _only_brand(name, catalog)]
    result = by_brand(informative) if 0 < len(informative) < len(names) else UNMATCHED
    if result.status == "unmatched":
        result = by_brand(names)
    if result.status != "unmatched" or "S3" not in stages:
        return _with_rule(result, "S2")

    # S3: edit distance to product aliases and to brand aliases (then S2b).
    lookups = []
    for name in names:
        lookups.append((name, _resolve_by_alias_distance(name, catalog)))
        lookups.append((name, _resolve_by_brand_distance(name, item, catalog)))
    return _with_rule(_merge(lookups, "fuzzyName"), "S3")


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
        replace(part.candidates[0], rank=rank, evidence={**part.candidates[0].evidence, "multiProduct": side, "rule": "S1"})
        for rank, (side, part) in enumerate(zip(sides, parts, strict=True), start=1)
    )
    return ResolutionResult(status="multi", candidates=candidates, parts=tuple(parts))


# --- S2 / S2b: brand + attributes ---------------------------------------------------


def _brand_prefixes(name: str) -> list[tuple[str, str]]:
    """(start of the name, rest) splits to try as a brand, longest first.

    Word prefixes, then the part before the first digit for Korean menus
    without spaces ("라프로익25년").
    """
    words = name.split()
    splits = [(" ".join(words[:count]), " ".join(words[count:])) for count in range(len(words), 0, -1)]
    match = _HEAD_BEFORE_DIGIT.match(name)
    if match is not None:
        splits.append((match["head"], match["rest"]))
    return splits


def _find_brand(name: str, catalog: CatalogLookup) -> tuple[list[UUID], str, str] | None:
    """Return (brand ids, matched brand alias, rest of the name) for the longest leading brand alias."""
    for head, rest in _brand_prefixes(name):
        alias = normalize(head)
        brand_ids = catalog.find_brand_ids_by_alias(alias) if alias else []
        if brand_ids:
            return brand_ids, alias, rest
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


def _short_letters(token: str) -> bool:
    """A Latin letter token too short to check ("dr", "px"); numbers are never this."""
    return token.isascii() and token.isalpha() and len(token) < _MIN_LATIN_TOKEN


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _number_conflict(product: ProductInfo, numbers: list[str]) -> bool:
    """True when the product's name has numbers besides its age and none of the line's numbers is one
    of them ("2025" vs Classic Cut 2020, "2" vs Kim Gwajang #3, "16.2" vs Octomore 14.1)."""
    text = unicodedata.normalize("NFKC", f"{product.display_name} {product.edition_name or ''}")
    own = set(_DIGITS.findall(text)) - {str(product.age_years)}
    return bool(own) and not own & set(numbers)


# Strength, volume, serving and price ("46%", "700 ml", "2잔", "16,000원") are not product numbers.
_MEASURE = re.compile(
    r"\d+(?:[.,]\d+)*\s*(?:%|ml|cl|l|도|잔|병|샷|원|won)(?![a-z])|\d{1,3}(?:,\d{3})+", re.IGNORECASE
)


def _line_numbers(text: str) -> list[str]:
    """Numbers written on the line, without strength, volume, serving and price expressions."""
    _, tokens = _split_age(_MEASURE.sub(" ", text))
    return [token for token in tokens if _NUMBER.fullmatch(token)]


# Edition words that say nothing about which product it is (ai/match_llm NEUTRAL_TOKENS,
# plus label and bourbon): "Sherry Oak" is the same product as "Sherry".
_EDITION_NEUTRAL_WORDS = frozenset(
    {"the", "whisky", "whiskey", "scotch", "single", "malt", "year", "years", "old", "yo", "edition", "release", "no"}
    | {"cask", "casks", "oak", "barrel", "wood", "finish", "finished", "matured", "label", "bourbon"}
)
_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    """Lowercase Latin words and numbers: "Private Cask No.2" -> ["private", "cask", "no", "2"]."""
    return _WORD.findall(unicodedata.normalize("NFKC", text).lower().replace("'", "").replace("’", ""))


def _edition_words_not_in_line(
    product: ProductInfo, item: ExtractedProduct, brand_aliases: list[str], catalog: CatalogLookup
) -> list[str]:
    """Words of the product's edition name that the menu line does not have (neutral words aside).

    The line counts in English too (vocabulary). A product alias whose text after the brand
    and without digits is all in the line also covers it ("맥캘란 더블캐스크 12Y" and the alias
    "맥캘란 12년 더블 캐스크"), since Korean words cannot be compared word by word.
    """
    if not product.edition_name:
        return []
    lines = [item.product_name or ""]
    if _VOCABULARY is not None:
        lines.append(to_english(lines[0], _VOCABULARY))
    texts = [_DIGITS.sub("", normalize(line)) for line in lines]
    line_words = {word for line in lines for word in _words(line)}
    missing = []
    for word in dict.fromkeys(_words(product.edition_name)):
        if word in _EDITION_NEUTRAL_WORDS:
            continue
        # Numbers and short words ("PX") as whole words, longer words anywhere ("doublewood").
        whole_word = word.isdigit() or len(word) < _MIN_LATIN_TOKEN
        if not (word in line_words if whole_word else any(word in text for text in texts)):
            missing.append(word)
    if missing and _unexplained_hangul(lines[-1], brand_aliases):
        # The line has Hangul words the vocabulary does not know ("비노 바리끄"): they may be the
        # missing words, so only words the vocabulary could have translated count as missing.
        missing = [word for word in missing if word in _VOCABULARY_WORDS]
    if not missing:
        return []
    prefixes = sorted(brand_aliases, key=len, reverse=True)
    for alias in catalog.get_normalized_aliases(product.product_id):
        rest = next((alias[len(prefix):] for prefix in prefixes if alias.startswith(prefix)), alias)
        rest = _DIGITS.sub("", rest)
        # A remainder without letters ("." of "16.1") says nothing.
        if _LETTER.search(rest) and any(rest in text for text in texts):
            return []
    return missing


_HANGUL_WORD = re.compile(r"[가-힣]+")
_LETTER = re.compile(r"[^\W\d_]")
# Hangul that is not an edition word: the age unit and the category word.
_NOT_EDITION_HANGUL = frozenset({"년", "위스키"})


def _unexplained_hangul(line: str, brand_aliases: list[str]) -> bool:
    """True when the line (already through the vocabulary) has a Hangul word that is not a brand."""
    words = _without_brand(_HANGUL_WORD.findall(line), brand_aliases)
    return any(word not in _NOT_EDITION_HANGUL for word in words)


def _only_brand(name: str, catalog: CatalogLookup) -> bool:
    return bool(catalog.find_brand_ids_by_alias(normalize(name)))


def _without_brand(tokens: list[str], brand_aliases: list[str]) -> list[str]:
    """Drop the tokens, or runs of tokens ("컴파스", "박스"), that spell a brand alias."""
    kept, start = [], 0
    while start < len(tokens):
        end = next((end for end in range(len(tokens), start, -1) if "".join(tokens[start:end]) in brand_aliases), None)
        if end is None:
            kept.append(tokens[start])
            start += 1
        else:
            start = end
    return kept


def _resolve_by_brand(
    name: str, item: ExtractedProduct, catalog: CatalogLookup, default_product: bool
) -> ResolutionResult:
    found = _find_brand(name, catalog)
    if found is None:
        return UNMATCHED
    brand_ids, brand_alias, rest = found
    return _narrow_brand(brand_ids, {"brandMatch": brand_alias}, rest, item, catalog, default_product)


def _narrow_brand(
    brand_ids: list[UUID],
    brand_evidence: dict[str, Any],
    rest: str,
    item: ExtractedProduct,
    catalog: CatalogLookup,
    default_product: bool,
) -> ResolutionResult:
    """Narrow the brands' products by the age and edition tokens in `rest` (S2, and S2b if asked)."""
    age, tokens = _split_age(rest)
    if age is None:
        age = item.age_years
    # The brand written again ("Aberlour 12 (아벨라워)") is not an edition token.
    brand_aliases = [alias for alias, brand_id in catalog.list_normalized_brand_aliases() if brand_id in brand_ids]
    tokens = _without_brand(tokens, brand_aliases)

    products: list[ProductInfo] = []
    for brand_id in brand_ids:
        for product_id in catalog.get_brand_product_ids(brand_id):
            product = catalog.get_product(product_id)
            if product is not None:
                products.append(product)
    if age is not None:
        products = [product for product in products if product.age_years == age]
    # A number on the line other than the age (year, batch, "#2", "16.1") rules out a product
    # whose name has different numbers. The whole line counts, so a variant that is only the
    # brand ("옥토모어" of "Octomore 16.2 (옥토모어)") keeps the number too.
    line_age, _ = _split_age(item.product_name or "")
    numbers = [
        number for number in dict.fromkeys([*_line_numbers(rest), *_line_numbers(item.product_name or "")])
        if number not in (str(age), str(line_age))
    ]
    if numbers:
        products = [product for product in products if not _number_conflict(product, numbers)]
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
    if age is not None and default_product and not tokens:
        # S2b: the plain product of that age is the default; an edition is never assumed.
        plain = [product for product in products if product.edition_name is None]
        exact = len(plain) == 1
        chosen = plain if exact else products
    elif age is not None:
        exact = len(full) == 1 and (len(products) == 1 or bool(tokens))
        chosen = full if exact else [product for product, _ in fits]
    else:
        # No age: only edition tokens can pick the product.
        exact = bool(tokens) and len(full) == 1
        # Letter tokens too short to check ("DR") do not rule a product out.
        deciding = [token for token in tokens if not _short_letters(token)]
        chosen = full if exact else [product for product, fitted in fits if fitted or not deciding]
    if not chosen:
        return UNMATCHED
    confirm = (
        default_product and not exact and not tokens and len(chosen) == 1 and chosen[0].edition_name is not None
    )
    # Edition tokens picked one product, but it has edition words the line does not have
    # ("anCnoc Sherry" -> anCnoc Peated Sherry Cask): the owner confirms it.
    only_in_product = _edition_words_not_in_line(chosen[0], item, brand_aliases, catalog) if exact and tokens else []
    if only_in_product:
        exact = False

    by_fit = {product.product_id: fitted for product, fitted in fits}
    ranked = sorted(chosen, key=lambda p: (-len(by_fit[p.product_id]), p.display_name, str(p.product_id)))
    candidates = []
    for rank, product in enumerate(ranked, start=1):
        fitted = by_fit[product.product_id]
        evidence: dict[str, Any] = dict(brand_evidence)
        if age is not None:
            evidence["ageMatch"] = age
        if fitted:
            evidence["editionMatch"] = fitted
        unfitted = [token for token in tokens if token not in fitted]
        if unfitted:
            evidence["editionUnmatched"] = unfitted
        if default_product and exact and not tokens:
            evidence["defaultProduct"] = True
        if confirm:
            evidence["confirmRecommended"] = True
        if only_in_product:
            evidence["editionOnlyInProduct"] = only_in_product
            evidence["confirmRecommended"] = True
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


# --- S3: edit distance --------------------------------------------------------------

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_SHORT_TEXT = 6


def _digits_and_text(normalized: str) -> tuple[list[str], str]:
    """"macallan12sherryoak" -> (["12"], "macallansherryoak")."""
    return _DIGITS.findall(normalized), _DIGITS.sub("", normalized)


def _distance_limit(text: str) -> int:
    return 1 if len(text) <= _SHORT_TEXT else 2


def edit_distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance over characters (one Hangul syllable = one character).

    Returns `limit + 1` as soon as the distance is known to exceed `limit`.
    """
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return min(previous[-1], limit + 1)


def _closest(digits: list[str], text: str, aliases: Iterable[tuple[str, UUID]]) -> dict[UUID, tuple[int, str]]:
    """Map each owner id to (distance, alias) of its closest alias within the limit; digits must be equal."""
    if not text:
        return {}
    limit = _distance_limit(text)
    best: dict[UUID, tuple[int, str]] = {}
    for alias, owner_id in aliases:
        alias_digits, alias_text = _digits_and_text(alias)
        if alias_digits != digits:
            continue
        distance = edit_distance(text, alias_text, limit)
        if distance <= limit and (owner_id not in best or distance < best[owner_id][0]):
            best[owner_id] = (distance, alias)
    return best


# One syllable off in a short Hangul name is as likely another brand (달모어 18 / 보모어 18,
# 아녹 18 / 아란 18): where S3 would confirm such a name, it offers nothing instead.
_SHORT_HANGUL_NAME = 3
_HANGUL_SYLLABLES = re.compile(r"^[가-힣]+$")


_ARTICLE = re.compile(r"^\s*(?:the|더)\s+", re.IGNORECASE)
_NOT_WORD = re.compile(r"[\W_]")


def _short_hangul_name(name: str) -> bool:
    """True when the name before its first number, without a leading article ("더 ", "The ")
    and punctuation, is Hangul of 3 syllables or fewer ("달모어 18", "더 달무어 18", "아드백-10")."""
    text = _NOT_WORD.sub("", normalize(_ARTICLE.sub("", name)))
    head = re.split(r"\d", text, maxsplit=1)[0] or _DIGITS.sub("", text)
    return len(head) <= _SHORT_HANGUL_NAME and bool(_HANGUL_SYLLABLES.match(head))


def _exact_allowed(candidate_count: int, distance: int, has_digits: bool) -> bool:
    return candidate_count == 1 and distance <= 1 and has_digits


def _resolve_by_alias_distance(name: str, catalog: CatalogLookup) -> ResolutionResult:
    digits, text = _digits_and_text(normalize(name))
    found = []
    for product_id, (distance, alias) in _closest(digits, text, catalog.list_normalized_aliases()).items():
        product = catalog.get_product(product_id)
        if product is not None:
            found.append((distance, product, alias))
    if not found:
        return UNMATCHED
    found.sort(key=lambda entry: (entry[0], entry[1].display_name, str(entry[1].product_id)))
    exact = _exact_allowed(len(found), found[0][0], bool(digits))
    if exact and _short_hangul_name(name):
        return UNMATCHED
    candidates = []
    for rank, (distance, product, alias) in enumerate(found, start=1):
        evidence: dict[str, Any] = {"fuzzyAlias": alias, "editDistance": distance}
        if not exact and len(found) == 1:
            evidence["confirmRecommended"] = True
        candidates.append(
            Candidate(product_id=product.product_id, rank=rank, score=EDIT_DISTANCE_SCORE, method="alias", evidence=evidence)
        )
    return ResolutionResult(
        status="exact_match" if exact else "ambiguous",
        candidates=tuple(candidates),
        proposed_product_id=candidates[0].product_id,
    )


def _resolve_by_brand_distance(name: str, item: ExtractedProduct, catalog: CatalogLookup) -> ResolutionResult:
    """Brand found by edit distance (Dalwhinny -> Dalwhinnie), then narrowed by S2b."""
    brand_aliases = catalog.list_normalized_brand_aliases()
    chosen: tuple[int, list[UUID], str, str, str] | None = None  # distance, brand ids, alias, head, rest
    for head, rest in _brand_prefixes(name):
        best = _closest(*_digits_and_text(normalize(head)), brand_aliases)
        if not best:
            continue
        distance = min(found[0] for found in best.values())
        # Longer prefixes come first, so a shorter one replaces them only when strictly closer.
        if chosen is None or distance < chosen[0]:
            nearest = [brand_id for brand_id, found in best.items() if found[0] == distance]
            chosen = (distance, nearest, best[nearest[0]][1], head, rest)
    if chosen is None:
        return UNMATCHED
    distance, brand_ids, alias, head, rest = chosen
    result = _narrow_brand(
        brand_ids, {"fuzzyBrand": alias, "editDistance": distance}, rest, item, catalog, default_product=True
    )
    if result.status == "unmatched":
        return result
    has_digits = bool(_DIGITS.search(normalize(name)))
    if result.status == "exact_match" and _exact_allowed(len(brand_ids), distance, has_digits):
        return UNMATCHED if _short_hangul_name(head) else result
    single = len(result.candidates) == 1
    candidates = tuple(
        replace(
            candidate,
            score=EDIT_DISTANCE_SCORE,
            evidence={**candidate.evidence, "confirmRecommended": True} if single else candidate.evidence,
        )
        for candidate in result.candidates
    )
    return ResolutionResult(status="ambiguous", candidates=candidates, proposed_product_id=candidates[0].product_id)
