# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, M3). Reviewed by Jinwoo Park.
"""Matching LLM layer on top of S1+S2b+S3 (eval_plan.md, M3 사전 등록).

    engine = M3(llm, lines_by_photo, products)
    engine.translate(photo_id, target_names)          # M3a: one call per photo
    result, info = engine.resolve(photo_id, name, catalog, base, mode="merge", use_m3b=False)

M3a  The photo's lines go to the LLM in order, the lines S1+S2b+S3 did not confirm
     marked as targets. Per target line it returns bottler / distillery / brand, age,
     edition tokens and a kind. From that translation:
       (1) an English name is built and S1+S2b+S3 is run again on it
       (2) token match: every core token of a product's standard English name is in
           the translation and the age is the same
M3b  For target lines M3a found nothing for: the products of the brands named in the
     translation are listed and the LLM picks one, "none" or "unsure" (one call per line).

Nothing here is ever exact (principle 2). Every LLM candidate passes the vetoes
(principle 3) or is dropped with the rule name recorded:
  bottler_missing  independent bottling without that bottler in the translation
                   (and "(reverse)": a bottler in the translation, candidate not its product)
  age_mismatch     the line's age (printed, else translated) differs from the product's
  alias_of_other   the line name is a catalog alias of another product
  edition_mismatch an edition token of the translation (neutral words aside) is not in the
                   product's edition / standard name / aliases (added after dev r0, stricter only)
Short edition tokens (Latin, under 3 letters: "PX", "DR") are checked as whole words; when
one is missing the candidate stays but may not be confirm recommended. An `expansions`
entry ("DR" -> "Distillery Reserve") also counts when all of its words are in the product.
Modes: "merge" puts the LLM candidates first and keeps the S1+S2b+S3 candidates
(confirmRecommended only for one LLM candidate that is new or inside the S1+S2b+S3
candidates); "replace" (comparison only) keeps just the LLM candidates.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.normalize import normalize  # noqa: E402
from app.matching.staged import _AGE_WITH_UNIT, _parenthesis_variants, resolve_product_staged  # noqa: E402
from app.matching.types import Candidate, CatalogLookup, ExtractedProduct, ResolutionResult  # noqa: E402

PROMPT_DIR = Path(__file__).parent
# BOTTLEMAP_M3_TRANSLATE=v1 rescores the r0 translations (cache) with the current rules.
TRANSLATE_VERSION = os.environ.get("BOTTLEMAP_M3_TRANSLATE", "v2")
TRANSLATE_PROMPT = PROMPT_DIR / f"translate_prompt_{TRANSLATE_VERSION}.md"
PICK_PROMPT = PROMPT_DIR / "pick_prompt_v1.md"
BASE_STAGES = frozenset({"S1", "S2", "S2b", "S3"})
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


class Expansion(BaseModel):
    token: str
    expansion: str


class LineTranslation(BaseModel):
    line: int
    bottler_en: Optional[str]
    distillery_en: Optional[str]
    brand_en: Optional[str]
    age: Optional[int]
    edition_tokens_en: list[str]
    expansions: list[Expansion] = []  # prompt v2
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

    `normalized_aliases`: the product's aliases in this catalog (own-menu aliases already dropped).
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


class M3:
    def __init__(self, llm, lines_by_photo: dict[str, list[str]], products: dict[UUID, ProductMeta]):
        self.llm = llm
        self.lines = lines_by_photo
        self.products = products
        self.translate_prompt = TRANSLATE_PROMPT.read_text(encoding="utf-8")
        self.pick_prompt = PICK_PROMPT.read_text(encoding="utf-8")
        self._translations: dict[str, dict[str, dict | None]] = {}
        self._targets: dict[str, frozenset[str]] = {}
        self.photo_records: dict[str, dict] = {}
        self._no_confirm: dict[UUID, list[str]] = {}  # reset per resolve() call

    # --- M3a translation -----------------------------------------------------------

    def translate(self, photo_id: str, targets: set[str]) -> None:
        targets = frozenset(targets)
        if photo_id in self._translations:
            assert self._targets[photo_id] == targets, "M3a targets must be the same for C0 and C1"
            return
        self._targets[photo_id] = targets
        names = self.lines[photo_id]
        if not targets:
            self._translations[photo_id] = {}
            self.photo_records[photo_id] = {"called": False, "targets": 0}
            return
        payload = {"lines": [{"line": i, "name": n, "target": n in targets} for i, n in enumerate(names, start=1)]}
        parsed, record = self.llm.call("m3a", self.translate_prompt, payload, Translation)
        by_line = {item["line"]: item for item in (parsed or {"items": []})["items"]}
        out = {}
        for i, n in enumerate(names, start=1):
            if n in targets:
                out[n] = by_line.get(i)
        self._translations[photo_id] = out
        self.photo_records[photo_id] = {
            "called": True, "targets": len(targets), "parse_error": parsed is None,
            "missing_lines": sorted(n for n, t in out.items() if t is None),
            "cache_key": record["key"],
        }

    def translation(self, photo_id: str, name: str) -> dict | None:
        return self._translations.get(photo_id, {}).get(name)

    # --- candidates and vetoes ---------------------------------------------------------

    def _catalog_products(self, catalog: CatalogLookup) -> list[UUID]:
        return list(dict.fromkeys(pid for _, pid in catalog.list_normalized_aliases()))

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

    def _check(self, name: str, t: dict, found: dict[UUID, list[str]], catalog) -> tuple[list[UUID], list[dict]]:
        """Kept and vetoed candidates; kept ids lacking a short token are noted in self._no_confirm."""
        kept, vetoed = [], []
        for pid, via in found.items():
            rules, short = self._vetoes(name, t, pid, catalog)
            if rules:
                vetoed.append({"product": self.products[pid].display_name, "via": via, "rules": rules})
            else:
                kept.append(pid)
                if short:
                    self._no_confirm[pid] = short
        return kept, vetoed

    def m3a_candidates(self, name: str, t: dict, catalog: CatalogLookup) -> tuple[list[UUID], list[dict], dict]:
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
            product = self.products[pid]
            core = core_tokens(product)
            if core and set(core) <= have and product.age_years == t.get("age"):
                found.setdefault(pid, []).append("tokens")
        kept, vetoed = self._check(name, t, found, catalog)
        return kept, vetoed, {"english_name": english, "found": {self.products[p].display_name: v
                                                                  for p, v in found.items()}}

    # --- M3b -----------------------------------------------------------------------

    def family(self, t: dict, catalog: CatalogLookup) -> list[UUID]:
        brand_ids = []
        for field in ("bottler_en", "distillery_en", "brand_en"):
            if t.get(field):
                brand_ids += catalog.find_brand_ids_by_alias(normalize(t[field]))
        pids = {pid for b in dict.fromkeys(brand_ids) for pid in catalog.get_brand_product_ids(b)}
        return sorted(pids, key=lambda p: (self.products[p].display_name, str(p)))

    def m3b(self, photo_id: str, name: str, t: dict, catalog: CatalogLookup) -> tuple[list[UUID], list[dict], dict]:
        options = self.family(t, catalog)
        if not options:
            return [], [], {"m3b": "no_family"}
        names = self.lines[photo_id]
        i = names.index(name)
        payload = {
            "menu_line": name,
            "context_lines": names[max(0, i - CONTEXT_LINES):i],
            "translation": {k: t.get(k) for k in ("bottler_en", "distillery_en", "brand_en", "age", "edition_tokens_en",
                                                  "expansions")},
            "options": [{"no": str(n), "name": self.products[p].display_name, "age": self.products[p].age_years,
                         "edition": self.products[p].edition_name} for n, p in enumerate(options, start=1)],
        }
        parsed, record = self.llm.call("m3b", self.pick_prompt, payload, Pick)
        info = {"m3b": "parse_error" if parsed is None else parsed["choice"], "options": len(options),
                "reason": parsed["reason"] if parsed else None, "cache_key": record["key"]}
        if parsed is None or not parsed["choice"].isdigit() or not 1 <= int(parsed["choice"]) <= len(options):
            return [], [], info
        pid = options[int(parsed["choice"]) - 1]
        kept, vetoed = self._check(name, t, {pid: ["m3b"]}, catalog)
        info["picked"] = self.products[pid].display_name
        return kept, vetoed, info

    # --- one line ------------------------------------------------------------------

    def resolve(self, photo_id: str, name: str, catalog: CatalogLookup, base: ResolutionResult,
                mode: str = "merge", use_m3b: bool = False) -> tuple[ResolutionResult, dict]:
        """`base` is the S1+S2b+S3 result for a line it did not confirm."""
        t = self.translation(photo_id, name)
        self._no_confirm = {}
        info: dict = {"translation": t}
        if t is None or t["kind"] != "whisky":
            info["skipped"] = "no_translation" if t is None else t["kind"]
            return base, info
        kept, vetoed, detail = self.m3a_candidates(name, t, catalog)
        info.update(detail, vetoed=vetoed, stage="M3a")
        if not kept and use_m3b:
            kept, vetoed_b, detail_b = self.m3b(photo_id, name, t, catalog)
            info.update(detail_b, stage="M3b")
            info["vetoed"] = vetoed + vetoed_b
        if not kept:
            info["llm_candidates"] = []
            return base, info
        info["llm_candidates"] = [self.products[p].display_name for p in kept]
        if self._no_confirm:
            info["short_unverified"] = {self.products[p].display_name: s for p, s in self._no_confirm.items()}
        return combine(base, kept, mode, info["stage"], set(self._no_confirm)), info


def combine(base: ResolutionResult, kept: list[UUID], mode: str, stage: str,
            no_confirm: set[UUID] = frozenset()) -> ResolutionResult:
    base_ids = [c.product_id for c in base.candidates]
    if mode == "merge":
        confirm = len(kept) == 1 and (not base_ids or kept[0] in base_ids)
        rest = [c for c in base.candidates if c.product_id not in kept]
    elif mode == "replace":
        confirm = len(kept) == 1
        rest = []
    else:
        raise ValueError(mode)
    confirm = confirm and kept[0] not in no_confirm
    candidates = []
    for pid in kept:
        evidence = {"m3": stage}
        if confirm:
            evidence["confirmRecommended"] = True
        candidates.append(Candidate(product_id=pid, rank=0, score=LLM_SCORE, method="llm", evidence=evidence))
    for c in rest:
        candidates.append(replace(c, evidence={k: v for k, v in c.evidence.items() if k != "confirmRecommended"}))
    candidates = [replace(c, rank=rank) for rank, c in enumerate(candidates, start=1)]
    return ResolutionResult(status="ambiguous", candidates=tuple(candidates), proposed_product_id=candidates[0].product_id)
