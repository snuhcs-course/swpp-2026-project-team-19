"""Matching LLM layer with tool calling (experiment E10): the model searches the catalog itself.

    engine = ToolEngine(llm, lines_by_image, products)
    engine.translate(image_id, target_names, catalog)        # one conversation per photo
    result = engine.resolve(image_id, name, catalog, base)

Where M3a (llm_layer.py) only translates a line and lets code look the catalog up, here
the model gets the photo's lines (targets marked, as in M3a) and three tools:
  search_catalog(query)     products of this catalog whose names look like the query
                            (rules S1+S2b+S3 on the query, then word overlap with names/aliases)
  get_product(product_id)   age, edition, bottler and aliases of one search result
  submit_answers(answers)   per target line: product id or "", sure, and the M3a
                            translation fields (bottler, distillery, brand, age, edition, kind)
Function calls are forced, so every turn is a tool call and the conversation ends with
submit_answers (or after MAX_TURNS, with no answer).

The model can only name products it was shown: ids are short per-conversation handles
("p3") handed out by the tools, and an id it was never shown is dropped. A named product
then goes through the M3a vetoes with the submitted translation (bottler, age and alias of
another product drop it; an edition word the product lacks only withholds confirm
recommended, since the model saw the product's edition and aliases), and is merged like M3a (`combine`: never exact; confirm
recommended only for one candidate that is new or among the rule candidates, the model
said sure, and no short edition token is unverified). Any failure leaves the line with
its rule result.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any, Protocol
from uuid import UUID

from app.core.normalize import normalize
from app.matching.llm_layer import (
    BASE_STAGES,
    PROMPT_DIR,
    M3Engine,
    ProductMeta,
    combine,
    load_prompt,
)
from app.matching.staged import resolve_product_staged
from app.matching.types import CatalogLookup, ExtractedProduct, ResolutionResult

TOOL_PROMPT = PROMPT_DIR / "tool_prompt_v1.md"
MAX_TURNS = 6
SEARCH_LIMIT = 10
KINDS = ("whisky", "non_whisky", "unclear")
_WORD = re.compile(r"[a-z0-9]+|[가-힣]+")

TOOLS = [
    {"name": "search_catalog",
     "description": "카탈로그에서 이름이 비슷한 상품을 최대 10개 찾는다. 영문 정식 표기(브랜드 또는 병입사 + 증류소 + 연수 + 에디션)가 가장 잘 맞는다.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_product",
     "description": "검색 결과로 받은 상품 하나의 연수, 에디션, 병입사, 별칭을 본다.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]}},
    {"name": "submit_answers",
     "description": "대상 줄마다 답 하나씩, 입력 순서대로 낸다. 한 번만 부른다.",
     "parameters": {"type": "object", "properties": {"answers": {"type": "array", "items": {
         "type": "object",
         "properties": {
             "line": {"type": "integer"},
             "product_id": {"type": "string", "description": "검색 결과의 id, 연결하지 않으면 빈 문자열"},
             "sure": {"type": "boolean"},
             "bottler_en": {"type": "string"}, "distillery_en": {"type": "string"}, "brand_en": {"type": "string"},
             "age": {"type": "integer", "description": "숙성 연수, 없으면 0"},
             "edition_tokens_en": {"type": "array", "items": {"type": "string"}},
             "kind": {"type": "string", "enum": list(KINDS)}},
         "required": ["line", "product_id", "sure", "bottler_en", "distillery_en", "brand_en", "age",
                      "edition_tokens_en", "kind"]}}},
                    "required": ["answers"]}},
]


class ToolLLM(Protocol):
    def step(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        """The model's function calls for the conversation so far: {"calls": [{"name", "args", "sig"}], ...}."""
        ...


def words(text: str) -> list[str]:
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = unicodedata.normalize("NFC", text).lower().replace("'", "").replace("’", "")
    return _WORD.findall(text)


class CatalogSearch:
    """search_catalog / get_product over one catalog (the aliases live in it, so leave-one-bar-out holds)."""

    def __init__(self, catalog: CatalogLookup, products: dict[UUID, ProductMeta]):
        self.catalog = catalog
        self.products = products
        self.entries = []
        for pid in dict.fromkeys(pid for _, pid in catalog.list_normalized_aliases()):
            meta = products.get(pid)
            if meta is None:
                continue
            live = set(catalog.get_normalized_aliases(pid))
            aliases = [a for a in meta.aliases if normalize(a) in live]
            texts = [meta.display_name, meta.edition_name or "", *aliases]
            self.entries.append((pid, {w for t in texts for w in words(t)}, live | {normalize(meta.display_name)}, aliases))

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[UUID]:
        qw = [w for w in dict.fromkeys(words(query))]
        qn = normalize(query) if query else ""
        if not qw:
            return []
        bonus: Counter[UUID] = Counter()
        rules = resolve_product_staged(ExtractedProduct(product_name=query), self.catalog, BASE_STAGES)
        for c in rules.candidates:
            bonus[c.product_id] += 5 if rules.status == "exact_match" else 3
        scored = []
        for pid, ws, norms, _ in self.entries:
            s = float(bonus.get(pid, 0))
            for w in qw:
                if w in ws:
                    s += 1 if w.isdigit() else 2
                elif not w.isdigit() and len(w) >= 2 and any(w in n for n in norms):
                    s += 1
            if qn and len(qn) >= 4 and any(qn in n for n in norms):
                s += 2
            if s > 0 and any(w in ws or (not w.isdigit() and any(w in n for n in norms)) for w in qw
                             if not w.isdigit()) or bonus.get(pid):
                scored.append((-s, self.products[pid].display_name, pid))
        return [pid for _, _, pid in sorted(scored)[:limit]]

    def describe(self, pid: UUID, full: bool = False) -> dict[str, Any]:
        meta = self.products[pid]
        out = {"name": meta.display_name, "age": meta.age_years, "edition": meta.edition_name, "bottler": meta.bottler}
        if full:
            entry = next(e for e in self.entries if e[0] == pid)
            out["aliases"] = entry[3][:15]
        return out


class ToolSession:
    """One photo's conversation."""

    def __init__(self, llm: ToolLLM, search: CatalogSearch, prompt: str, max_turns: int = MAX_TURNS):
        self.llm, self.search, self.prompt, self.max_turns = llm, search, prompt, max_turns
        self.ids: dict[str, UUID] = {}
        self.handles: dict[UUID, str] = {}
        self.stats: Counter[str] = Counter()
        self.history: list[dict] = []

    def _handle(self, pid: UUID) -> str:
        if pid not in self.handles:
            h = f"p{len(self.handles) + 1}"
            self.handles[pid] = h
            self.ids[h] = pid
        return self.handles[pid]

    def _tool(self, name: str, args: dict) -> dict:
        if name == "search_catalog":
            self.stats["search"] += 1
            return {"results": [{"product_id": self._handle(pid), **self.search.describe(pid)}
                                for pid in self.search.search(str(args.get("query", "")))]}
        if name == "get_product":
            self.stats["get"] += 1
            pid = self.ids.get(str(args.get("product_id", "")))
            if pid is None:
                return {"error": "unknown product_id: use an id from search_catalog"}
            return {"product_id": self.handles[pid], **self.search.describe(pid, full=True)}
        self.stats["unknown_tool"] += 1
        return {"error": f"unknown tool {name}"}

    def run(self, names: list[str], targets: set[str]) -> dict[int, dict] | None:
        """Answers by line number, or None when the model never submitted."""
        payload = {"lines": [{"line": i, "name": n, "target": n in targets} for i, n in enumerate(names, start=1)]}
        self.history = [{"role": "user", "text": json.dumps(payload, ensure_ascii=False)}]
        for _ in range(self.max_turns):
            out = self.llm.step(self.prompt, self.history, TOOLS)
            self.stats["turns"] += 1
            calls = out.get("calls") or []
            if not calls:
                self.stats["no_call"] += 1
                return None
            self.history.append({"role": "model", "calls": calls})
            submitted = next((c for c in calls if c["name"] == "submit_answers"), None)
            if submitted is not None:
                return self._answers(submitted["args"].get("answers") or [])
            self.history.append({"role": "tool", "responses": [{"name": c["name"], "response": self._tool(c["name"], c["args"])}
                                                               for c in calls]})
        self.stats["max_turns"] += 1
        return None

    def _answers(self, raw: list) -> dict[int, dict]:
        out = {}
        for a in raw:
            if not isinstance(a, dict) or not isinstance(a.get("line"), int) or a["line"] in out:
                continue
            handle = str(a.get("product_id") or "")
            pid = self.ids.get(handle)
            if handle and pid is None:
                self.stats["invented_id"] += 1
            kind = a.get("kind") if a.get("kind") in KINDS else "unclear"
            out[a["line"]] = {
                "product": pid, "sure": bool(a.get("sure")), "kind": kind,
                "bottler_en": a.get("bottler_en") or None, "distillery_en": a.get("distillery_en") or None,
                "brand_en": a.get("brand_en") or None, "age": a.get("age") or None,
                "edition_tokens_en": [str(t) for t in a.get("edition_tokens_en") or [] if str(t).strip()],
                "expansions": []}
        return out


class ToolEngine:
    """One menu import (mirrors M3Engine: translate per photo, then resolve per line)."""

    def __init__(self, llm: ToolLLM, lines_by_image: dict[str, list[str]], products: dict[UUID, ProductMeta],
                 max_turns: int = MAX_TURNS):
        self.llm = llm
        self.lines = lines_by_image
        self.products = products
        self.max_turns = max_turns
        self.prompt = load_prompt(TOOL_PROMPT)
        self.vetter = M3Engine(None, lines_by_image, products, max_calls=0)  # vetoes only, never calls
        self.stats: Counter[str] = Counter()
        self.sessions: dict[str, ToolSession] = {}
        self._answers: dict[str, dict[str, dict]] = {}
        self._searches: dict[int, CatalogSearch] = {}

    def translate(self, image_id: str, targets: set[str], catalog: CatalogLookup) -> None:
        names = self.lines[image_id]
        self._answers[image_id] = {}
        if not targets:
            return
        key = id(catalog)
        if key not in self._searches:
            self._searches[key] = CatalogSearch(catalog, self.products)
        session = ToolSession(self.llm, self._searches[key], self.prompt, self.max_turns)
        self.sessions[image_id] = session
        try:
            answers = session.run(names, targets)
        except Exception:  # any failure only means no answer
            self.stats["error"] += 1
            return
        if answers is None:
            self.stats["no_answer"] += 1
            return
        self.stats["ok"] += 1
        self._answers[image_id] = {n: answers[i] for i, n in enumerate(names, start=1) if n in targets and i in answers}

    def answer(self, image_id: str, name: str) -> dict | None:
        return self._answers.get(image_id, {}).get(name)

    def resolve(self, image_id: str, name: str, catalog: CatalogLookup, base: ResolutionResult) -> ResolutionResult:
        a = self.answer(image_id, name)
        if a is None or a["kind"] != "whisky" or a["product"] is None:
            return base
        pid = a["product"]
        rules, short = self.vetter._vetoes(name, a, pid, catalog)
        hard = [r for r in rules if r != "edition_mismatch"]
        if hard:
            self.stats["vetoed"] += 1
            return base
        # The model saw the product's edition and aliases before picking it, so an edition word of
        # its own translation the product lacks ("Solist", a series nickname) only withholds
        # confirm recommended; bottler, age and alias-of-another-product still veto.
        if rules:
            self.stats["edition_unverified"] += 1
        confirm_ok = a["sure"] and not rules and not short
        evidence = {pid: {"via": ["tools"], "sure": a["sure"], **({"editionUnverified": True} if rules else {})}}
        return combine(base, [pid], "TOOLS", set() if confirm_ok else {pid}, evidence)
