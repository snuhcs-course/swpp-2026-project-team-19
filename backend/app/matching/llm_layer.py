"""Matching LLM layer M3 on top of S1+S2b+S3: the frozen ai/match_llm/m3.py, ported to the server.

    engine = M3Engine(llm, lines_by_image, products, max_calls=30)
    engine.translate(image_id, target_names)                   # M3a: one call per photo
    result, info = engine.resolve(image_id, name, catalog, base, use_m3b=False)

The rules, prompts, model and "merge" mode are those of m3.py at the frozen commit
(eval_plan.md "M3 사전 등록"; M3a adopted, M3b not), so the offline numbers describe
the server. Only the plumbing differs: the LLM is an adapter (`MatchingLLM`), a call
that fails, times out, returns invalid JSON or goes over the per-import cap counts as
no answer, and evidence keys are camelCase for the API.

M3a  The photo's lines go to the LLM in order, the lines S1+S2b+S3 did not confirm
     marked as targets. Per target line it returns bottler / distillery / brand, age,
     edition tokens and a kind. From that translation:
       (1) an English name is built and S1+S2b+S3 is run again on it ("relookup")
       (2) token match: every core token of a product's standard English name is in
           the translation and the age is the same ("tokens")
M3b  For target lines M3a found nothing for: the products of the brands named in the
     translation are listed and the LLM picks one, "none" or "unsure" (one call per line).

Nothing here is ever exact. Every LLM candidate passes the vetoes or is dropped with
the rule name recorded:
  bottler_missing  independent bottling without that bottler in the translation
                   (and "(reverse)": a bottler in the translation, candidate not its product)
  age_mismatch     the line's age (printed, else translated) differs from the product's
  alias_of_other   the line name is a catalog alias of another product
  edition_mismatch an edition token of the translation (neutral words aside) is not in the
                   product's edition / standard name / aliases
Short edition tokens (Latin, under 3 letters: "PX", "DR") are checked as whole words; when
one is missing the candidate stays but may not be confirm recommended. An `expansions`
entry ("DR" -> "Distillery Reserve") also counts when all of its words are in the product.
Merge: the LLM candidates come first and the S1+S2b+S3 candidates are kept after them;
confirmRecommended only for one LLM candidate that is new or inside the S1+S2b+S3 candidates.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.adapters.matching_llm import MatchingLLM
from app.core.normalize import normalize
from app.matching.staged import _AGE_WITH_UNIT, _parenthesis_variants, resolve_product_staged
from app.matching.types import Candidate, CatalogLookup, ExtractedProduct, ResolutionResult

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).with_name("prompts")
# Copies of ai/match_llm/translate_prompt_v3.md and pick_prompt_v1.md (frozen M3); the hashes
# are those of the originals and tests/test_llm_layer.py checks both.
TRANSLATE_PROMPT = PROMPT_DIR / "translate_prompt_v3.md"
PICK_PROMPT = PROMPT_DIR / "pick_prompt_v1.md"
PROMPT_SHA256 = {
    TRANSLATE_PROMPT.name: "e8b77c3a80e26c694b1a0e7566e3347a21f406155f8f067f74cd61f55cefefd4",
    PICK_PROMPT.name: "e914bbe17b67b718c7de925974b2bc1433b472c9a995a3c25d1d291b35f9bf14",
}
BASE_STAGES = frozenset({"S1", "S2", "S2b", "S3"})
CONFIRMED = ("exact_match", "multi")
LLM_SCORE = 0.5
CONTEXT_LINES = 5  # lines above a target line shown to M3b

# P17 independent bottlers (ai/naver/sample.py IB_BOTTLERS, naver_plan.md 2절), with the
# spellings a translation may use. Keys are the P17 names.
IB_BOTTLERS = {
    "Signatory": ("Signatory", "Signatory Vintage"),
    "Gordon & MacPhail": ("Gordon & MacPhail", "Gordon and MacPhail", "G&M"),
    "Douglas Laing": ("Douglas Laing",),
    "Hunter Laing": ("Hunter Laing",),
    "La Maison du Whisky": ("La Maison du Whisky", "LMDW"),
    "The Whisky Agency": ("The Whisky Agency", "Whisky Agency", "TWA"),
    "Samaroli": ("Samaroli",),
    "Wilson & Morgan": ("Wilson & Morgan", "Wilson and Morgan", "W&M"),
    "Highland Laird": ("Highland Laird",),
    "Elements of Islay": ("Elements of Islay",),
    "Port Askaig": ("Port Askaig",),
    "Blackadder": ("Blackadder",),
}
_IB_BY_ALIAS = {normalize(alias): name for name, aliases in IB_BOTTLERS.items() for alias in aliases}
# Words of a standard name that do not identify the product (token match).
GENERIC_TOKENS = frozenset({"the", "whisky", "whiskey", "scotch", "single", "malt", "year", "years", "old", "yo",
                            "edition", "release", "no"})
# Neither evidence for (token rule) nor against (edition_mismatch) a product.
NEUTRAL_TOKENS = GENERIC_TOKENS | {"cask", "casks", "oak", "barrel", "wood", "finish", "finished", "matured"}
SHORT_LATIN = 3


# Response schemas, as in m3.py: the request sends their JSON schema, which must stay the same.
class Expansion(BaseModel):
    token: str
    expansion: str


class LineTranslation(BaseModel):
    line: int
    bottler_en: str | None
    distillery_en: str | None
    brand_en: str | None
    age: int | None
    edition_tokens_en: list[str]
    expansions: list[Expansion] = []
    kind: Literal["whisky", "non_whisky", "unclear"]


class Translation(BaseModel):
    items: list[LineTranslation]


class Pick(BaseModel):
    choice: str
    reason: str


@dataclass(frozen=True)
class ProductMeta:
    display_name: str
    age_years: int | None
    edition_name: str | None
    bottler: str | None  # P17 bottler name for an independent bottling, else None
    aliases: tuple[str, ...] = ()  # alias texts as written (word-level checks); filtered by the catalog


@dataclass(frozen=True)
class LLMLayerConfig:
    """What menu import needs to run the layer; None (the default) means the layer is off."""

    llm: MatchingLLM
    max_calls: int
    use_m3b: bool = False


def load_prompt(path: Path) -> str:
    # LF regardless of how git checked the file out, so the hash matches the frozen prompt.
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bottler_of(name: str | None) -> str | None:
    """P17 bottler name for a brand / bottler string, or None if it is not an independent bottler."""
    return _IB_BY_ALIAS.get(normalize(name)) if name else None


def tokens(text: str) -> list[str]:
    """"Maker's Mark 46" -> ["makers", "mark", "46"]; "Octomore 13.1" -> ["octomore", "13.1"]."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)


def core_tokens(product: ProductMeta) -> list[str]:
    out = [t for t in tokens(product.display_name) if t not in NEUTRAL_TOKENS]
    if product.age_years is not None and str(product.age_years) in out:
        out.remove(str(product.age_years))
    return out


def translation_tokens(t: dict) -> set[str]:
    parts = [t.get("bottler_en"), t.get("distillery_en"), t.get("brand_en"), *t.get("edition_tokens_en", [])]
    return {tok for part in parts if part for tok in tokens(part)}


def english_name(t: dict) -> str | None:
    """Name to look up again with S1+S2b+S3, in the order of the standard names."""
    head = [t["bottler_en"], t.get("distillery_en")] if t.get("bottler_en") else [t.get("brand_en") or t.get("distillery_en")]
    parts = [p for p in head if p]
    if not parts:
        return None
    if t.get("age") is not None:
        parts.append(str(t["age"]))
    parts += [p for p in t.get("edition_tokens_en", []) if p]
    return " ".join(parts)


def expand(t: dict) -> dict | None:
    """The translation with each abbreviation replaced by its expansion (candidate search only)."""
    table = {normalize(e["token"]): e["expansion"] for e in t.get("expansions") or []}
    if not table:
        return None
    return {**t, "edition_tokens_en": [table.get(normalize(tok), tok) for tok in t.get("edition_tokens_en", [])]}


def _is_short(token: str) -> bool:
    return token.isascii() and token.isalpha() and len(token) < SHORT_LATIN


def edition_check(t: dict, product: ProductMeta, normalized_aliases: list[str]) -> tuple[list[str], list[str]]:
    """(tokens the product lacks -> edition_mismatch, short tokens it lacks -> no confirm recommended).

    `normalized_aliases`: the product's aliases in this catalog.
    """
    live = set(normalized_aliases)
    texts = [product.display_name, product.edition_name or "", *(a for a in product.aliases if normalize(a) in live)]
    words = {w for text in texts for w in tokens(text)}
    joined = [normalize(text) for text in texts if text] + list(live)
    expansions: dict[str, list[str]] = {}
    for e in t.get("expansions") or []:
        expansions.setdefault(normalize(e["token"]), []).append(e["expansion"])
    missing, short = [], []
    for raw in t.get("edition_tokens_en", []):
        for tok in tokens(raw):
            if tok in NEUTRAL_TOKENS:
                continue
            whole_word = _is_short(tok) or tok.replace(".", "").isdigit()
            fits = tok in words if whole_word else any(tok in j for j in joined)
            for full in expansions.get(normalize(raw), []) + (expansions.get(tok, []) if tok != normalize(raw) else []):
                need = [w for w in tokens(full) if w not in NEUTRAL_TOKENS]
                fits = fits or (bool(need) and all(w in words for w in need))
            if not fits:
                (short if _is_short(tok) else missing).append(tok)
    return missing, short


def line_age(name: str, t: dict | None) -> int | None:
    match = _AGE_WITH_UNIT.search(name)
    if match is not None:
        return int(match[1])
    return t.get("age") if t else None


class M3Engine:
    """One menu import. `stats` counts requests by outcome (ok, parse_error, error, cap_reached)."""

    def __init__(self, llm: MatchingLLM, lines_by_image: dict[str, list[str]], products: dict[UUID, ProductMeta],
                 *, max_calls: int) -> None:
        self.llm = llm
        self.lines = lines_by_image
        self.products = products
        self.max_calls = max_calls
        self.translate_prompt = load_prompt(TRANSLATE_PROMPT)
        self.pick_prompt = load_prompt(PICK_PROMPT)
        self.calls = 0
        self.stats: Counter[str] = Counter()
        self._translations: dict[str, dict[str, dict | None]] = {}
        self._core: dict[UUID, list[str]] = {}
        self._no_confirm: dict[UUID, list[str]] = {}  # reset per resolve() call

    def _call(self, kind: str, prompt: str, payload: dict[str, Any], schema: type[BaseModel]) -> dict | None:
        """Parsed answer, or None for a failed, invalid or capped call (the line keeps its rule result)."""
        if self.calls >= self.max_calls:
            self.stats["cap_reached"] += 1
            return None
        self.calls += 1
        try:
            text = self.llm.generate_json(prompt, payload, schema.model_json_schema())
        except Exception as error:  # any failure only means no answer
            # The type only: messages can carry request details.
            logger.warning("matching LLM %s call failed: %s", kind, type(error).__name__)
            self.stats["error"] += 1
            return None
        try:
            parsed = schema.model_validate_json(text).model_dump()
        except ValidationError:
            self.stats["parse_error"] += 1
            return None
        self.stats["ok"] += 1
        return parsed

    # --- M3a translation -----------------------------------------------------------

    def translate(self, image_id: str, targets: set[str]) -> None:
        names = self.lines[image_id]
        if not targets:
            self._translations[image_id] = {}
            return
        payload = {"lines": [{"line": i, "name": n, "target": n in targets} for i, n in enumerate(names, start=1)]}
        parsed = self._call("m3a", self.translate_prompt, payload, Translation)
        by_line = {item["line"]: item for item in (parsed or {"items": []})["items"]}
        self._translations[image_id] = {n: by_line.get(i) for i, n in enumerate(names, start=1) if n in targets}

    def translation(self, image_id: str, name: str) -> dict | None:
        return self._translations.get(image_id, {}).get(name)

    # --- candidates and vetoes ---------------------------------------------------------

    def _catalog_products(self, catalog: CatalogLookup) -> list[UUID]:
        return list(dict.fromkeys(pid for _, pid in catalog.list_normalized_aliases()))

    def _core_tokens(self, pid: UUID) -> list[str]:
        if pid not in self._core:
            self._core[pid] = core_tokens(self.products[pid])
        return self._core[pid]

    def _vetoes(self, name: str, t: dict, pid: UUID, catalog: CatalogLookup) -> tuple[list[str], list[str]]:
        """(veto rule names, short edition tokens the product lacks)."""
        product = self.products[pid]
        rules = []
        said = bottler_of(t.get("bottler_en"))
        if product.bottler is not None and said != product.bottler:
            rules.append("bottler_missing")
        elif said is not None and product.bottler != said:
            rules.append("bottler_missing (reverse)")
        age = line_age(name, t)
        if age is not None and product.age_years != age:
            rules.append("age_mismatch")
        owners = {o for variant in (name, *_parenthesis_variants(name))
                  for o in catalog.find_product_ids_by_alias(normalize(variant))}
        if owners and pid not in owners:
            rules.append("alias_of_other")
        missing, short = edition_check(t, product, catalog.get_normalized_aliases(pid))
        if missing:
            rules.append("edition_mismatch")
        return rules, short

    def _check(self, name: str, t: dict, found: dict[UUID, list[str]],
               catalog: CatalogLookup) -> tuple[list[UUID], list[dict]]:
        """Kept and vetoed candidates; kept ids lacking a short token are noted in self._no_confirm."""
        kept, vetoed = [], []
        for pid, via in found.items():
            rules, short = self._vetoes(name, t, pid, catalog)
            if rules:
                vetoed.append({"productId": str(pid), "displayName": self.products[pid].display_name,
                               "via": via, "rules": rules})
            else:
                kept.append(pid)
                if short:
                    self._no_confirm[pid] = short
        return kept, vetoed

    def m3a_candidates(self, name: str, t: dict,
                       catalog: CatalogLookup) -> tuple[list[UUID], list[dict], dict[UUID, list[str]], str | None]:
        """(kept, vetoed, how each candidate was found, English name)."""
        found: dict[UUID, list[str]] = {}
        english = english_name(t)
        names = [english]
        expanded = expand(t)
        if expanded is not None:
            names.append(english_name(expanded))
        for n in dict.fromkeys(filter(None, names)):
            r = resolve_product_staged(ExtractedProduct(product_name=n), catalog, BASE_STAGES)
            for c in r.candidates:
                if "relookup" not in found.setdefault(c.product_id, []):
                    found[c.product_id].append("relookup")
        have = translation_tokens(t) | (translation_tokens(expanded) if expanded else set())
        for pid in self._catalog_products(catalog):
            core = self._core_tokens(pid)
            if core and set(core) <= have and self.products[pid].age_years == t.get("age"):
                found.setdefault(pid, []).append("tokens")
        kept, vetoed = self._check(name, t, found, catalog)
        return kept, vetoed, found, english

    # --- M3b -----------------------------------------------------------------------

    def family(self, t: dict, catalog: CatalogLookup) -> list[UUID]:
        brand_ids = []
        for field in ("bottler_en", "distillery_en", "brand_en"):
            if t.get(field):
                brand_ids += catalog.find_brand_ids_by_alias(normalize(t[field]))
        pids = {pid for b in dict.fromkeys(brand_ids) for pid in catalog.get_brand_product_ids(b)}
        return sorted(pids, key=lambda p: (self.products[p].display_name, str(p)))

    def m3b(self, image_id: str, name: str, t: dict, catalog: CatalogLookup) -> tuple[list[UUID], list[dict]]:
        options = self.family(t, catalog)
        if not options:
            return [], []
        names = self.lines[image_id]
        i = names.index(name)
        payload = {
            "menu_line": name,
            "context_lines": names[max(0, i - CONTEXT_LINES):i],
            "translation": {k: t.get(k) for k in ("bottler_en", "distillery_en", "brand_en", "age", "edition_tokens_en",
                                                  "expansions")},
            "options": [{"no": str(n), "name": self.products[p].display_name, "age": self.products[p].age_years,
                         "edition": self.products[p].edition_name} for n, p in enumerate(options, start=1)],
        }
        parsed = self._call("m3b", self.pick_prompt, payload, Pick)
        if parsed is None or not parsed["choice"].isdigit() or not 1 <= int(parsed["choice"]) <= len(options):
            return [], []
        pid = options[int(parsed["choice"]) - 1]
        return self._check(name, t, {pid: ["m3b"]}, catalog)

    # --- one line ------------------------------------------------------------------

    def resolve(self, image_id: str, name: str, catalog: CatalogLookup, base: ResolutionResult,
                use_m3b: bool = False) -> ResolutionResult:
        """`base` is the S1+S2b+S3 result of a line it did not confirm; returned as is when the LLM adds nothing."""
        t = self.translation(image_id, name)
        self._no_confirm = {}
        if t is None or t["kind"] != "whisky":
            return base
        kept, vetoed, found, english = self.m3a_candidates(name, t, catalog)
        stage = "M3a"
        if not kept and use_m3b:
            kept, vetoed_b = self.m3b(image_id, name, t, catalog)
            stage = "M3b"
            vetoed = vetoed + vetoed_b
            found = {pid: ["m3b"] for pid in kept}
        if not kept:
            return base
        line_evidence: dict[str, Any] = {"englishName": english}
        if vetoed:
            line_evidence["vetoed"] = vetoed
        evidence = {}
        for pid in kept:
            evidence[pid] = {"via": found[pid], **line_evidence}
            if pid in self._no_confirm:
                evidence[pid]["shortUnverified"] = self._no_confirm[pid]
        return combine(base, kept, stage, set(self._no_confirm), evidence)


def combine(base: ResolutionResult, kept: list[UUID], stage: str, no_confirm: set[UUID] = frozenset(),
            evidence: dict[UUID, dict[str, Any]] | None = None) -> ResolutionResult:
    """m3.py "merge": LLM candidates first, then the S1+S2b+S3 candidates; always ambiguous."""
    base_ids = [c.product_id for c in base.candidates]
    confirm = len(kept) == 1 and (not base_ids or kept[0] in base_ids)
    rest = [c for c in base.candidates if c.product_id not in kept]
    confirm = confirm and kept[0] not in no_confirm
    candidates = []
    for pid in kept:
        ev: dict[str, Any] = {"rule": stage, **(evidence or {}).get(pid, {})}
        if confirm:
            ev["confirmRecommended"] = True
        candidates.append(Candidate(product_id=pid, rank=0, score=LLM_SCORE, method="llm", evidence=ev))
    for c in rest:
        candidates.append(replace(c, evidence={k: v for k, v in c.evidence.items() if k != "confirmRecommended"}))
    candidates = [replace(c, rank=rank) for rank, c in enumerate(candidates, start=1)]
    return ResolutionResult(status="ambiguous", candidates=tuple(candidates), proposed_product_id=candidates[0].product_id)
