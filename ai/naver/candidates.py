# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""Korean spelling candidates for a product from Naver search results (naver_plan.md, 3절).

    queries = build_queries(product, ko_brands)
    cands = extract_candidates(product, results, ko_brands)

A product is {display_name, brand, age_years, edition_name}. Results are records from
`NaverSearchClient.search`. Candidates are runs of Hangul / age tokens in the cleaned
title and description that start at an anchor:
  brand          a Korean alias of the product's brand in the catalog ("아란")
  learned        a Hangul run written next to the English brand in the results,
                 "하이랜드 레어드(Highland Laird)" or "Highland Laird(하이랜드 레어드)"
  edition_brand  a Korean alias of another catalog brand named in the edition
                 (the distillery of an independent bottling, "쿨일라" for "... Caol Ila 12").
                 These are kept on purpose: they are the "bottler name missing" risk (P18 c).
HTML tags, entities and sales / promotion words are removed; a promotion word ends a run.
"""

from __future__ import annotations

import html
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.normalize import normalize  # noqa: E402

MAX_TOKENS = 6  # tokens in one candidate, anchor included
MAX_CANDIDATES = 5  # per product, by evidence count
MAX_EVIDENCE = 10  # provenance entries kept per candidate

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_HANGUL = re.compile(r"[가-힣]")
# A token that can be part of a Korean product name: Hangul, digits, a few joiners.
_NAME_TOKEN = re.compile(r"[가-힣0-9][가-힣0-9.&'’]*")
_AGE = re.compile(r"^(\d{1,2})(?:년|y|yo|년산)?$", re.IGNORECASE)
_AGE_IN = re.compile(r"(?<!\d)(\d{1,2})\s*(?:년|y\b|yo\b|years?\b)", re.IGNORECASE)
# Sales / promotion words. A token containing one ends the run (it is not part of a name).
PROMO_WORDS = (
    "최저가", "할인", "특가", "판매", "구매", "구입", "가격", "배송", "이벤트", "쿠폰", "후기", "리뷰",
    "추천", "시음", "테이스팅", "정품", "공식", "쇼핑", "마트", "면세", "데일리샷", "바틀샵", "입고",
    "품절", "예약", "증정", "선물", "세트", "한정판매", "주문", "택배", "픽업", "가성비", "맛집",
    "노트", "후기", "소개", "정보", "리스트", "모음", "총정리", "비교", "차이", "종류", "입문",
)
# Words dropped from the ends of a candidate (they describe the category, not the product).
EDGE_WORDS = frozenset({
    "위스키", "싱글몰트", "싱글", "몰트", "스카치", "버번", "블렌디드", "라이", "증류소", "제품", "신제품",
    "출시", "병", "잔", "한잔", "마셔본", "마신", "오늘", "드디어", "그리고", "및", "등", "의",
})
# Particles that end a noun phrase: a token ending in one ends the candidate (the particle is
# dropped). Kept to particles that rarely end a transliterated name ("이", "가", "로", "와" do:
# 글렌모레이, 하뉴가 ...), so those stay in the token.
_PARTICLE = re.compile(r"(?<=[가-힣0-9]{2})(?:에서|으로|이에요|예요|입니다|이고|하고|까지|부터|을|를|은|는|의|과|에)$")
_SEPARATORS = re.compile(r"[|/\\\[\]{}<>«»\"“”‘’!?~:;,·•■◆▶★☆♥♡#=+*()\-–—_…]")


def clean_text(text: str) -> str:
    """Strip tags and entities (twice: Naver escapes '<' in some titles), collapse spaces."""
    value = html.unescape(html.unescape(text or ""))
    value = _TAG.sub(" ", value)
    return _WS.sub(" ", value).strip()


def has_hangul(text: str) -> bool:
    return bool(_HANGUL.search(text))


def ko_brand_aliases(brand: str, seed: dict) -> list[str]:
    """Korean aliases of the catalog brand for a gold brand name ("arran", "makers-mark", "Kilchoman")."""
    key = normalize(brand.replace("-", " ").replace("_", " "))
    for b in seed["brands"]:
        names = [b["key"].replace("_", " "), b["canonical_name"]] + [a["alias_text"] for a in b["aliases"]]
        if key in {normalize(n) for n in names}:
            return sorted({a["alias_text"] for a in b["aliases"] if has_hangul(a["alias_text"])})
    return []


def edition_brand_aliases(product: dict, seed: dict) -> list[str]:
    """Korean aliases of other catalog brands named in the edition (an independent bottling's distillery)."""
    edition = normalize(product.get("edition_name") or "")
    own = normalize(product["brand"].replace("-", " ").replace("_", " "))
    out = set()
    for b in seed["brands"]:
        english = {normalize(a["alias_text"]) for a in b["aliases"] if not has_hangul(a["alias_text"])}
        english.add(normalize(b["canonical_name"]))
        if own in english:
            continue
        if any(len(e) >= 4 and e in edition for e in english):
            out |= {a["alias_text"] for a in b["aliases"] if has_hangul(a["alias_text"])}
    return sorted(out)


def brand_age_query(product: dict, ko_brand: str, edition_brands: list[str] = ()) -> str | None:
    """"<Korean brand> <age>년"; for an independent bottling also the distillery
    ("고든 앤 맥페일 부나하벤 10년"), since the bottler and age alone match many products."""
    if not product.get("age_years"):
        return None
    middle = f" {edition_brands[0]}" if edition_brands else ""
    return f"{ko_brand}{middle} {product['age_years']}년"


def build_queries(product: dict, ko_brands: list[str], edition_brands: list[str] = ()) -> list[str]:
    """English name; "<Korean brand> <age>년" (only with a Korean brand and an age); English name + 위스키."""
    queries = [product["display_name"]]
    if ko_brands and (q := brand_age_query(product, ko_brands[0], edition_brands)):
        queries.append(q)
    queries.append(f"{product['display_name']} 위스키")
    return queries


def learn_brand_aliases(brand: str, texts: list[str]) -> list[str]:
    """Hangul runs written right next to the English brand: "한글(English" or "English(한글)"."""
    english = re.escape(brand.replace("-", " ").replace("_", " "))
    before = re.compile(r"([가-힣][가-힣 ]{1,24}?)\s*\(\s*" + english, re.IGNORECASE)
    after = re.compile(english + r"\s*\(\s*([가-힣][가-힣 ]{1,24}?)\s*\)", re.IGNORECASE)
    found = set()
    for text in texts:
        for m in list(before.finditer(text)) + list(after.finditer(text)):
            words = m.group(1).split()[-3:]
            alias = " ".join(w for w in words if w not in EDGE_WORDS)
            if len(alias.replace(" ", "")) >= 2:
                found.add(alias)
    return sorted(found)


def _runs(text: str) -> list[list[str]]:
    """Runs of name tokens, split at separators, non-name tokens and promotion words."""
    runs = []
    for segment in _SEPARATORS.split(text):
        run: list[str] = []
        for token in segment.split():
            if _NAME_TOKEN.fullmatch(token) and not any(w in token for w in PROMO_WORDS):
                run.append(token)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
    return runs


def _trim(tokens: list[str]) -> list[str]:
    """Cut at the first token that ends a phrase ("10년은", "위주."), then drop category words at the end."""
    out = []
    for token in tokens:
        stripped = _PARTICLE.sub("", token.rstrip("."))
        out.append(stripped)
        if stripped != token:
            break
    while out and out[-1] in EDGE_WORDS:
        out.pop()
    return [t for t in out if t]


def _from_run(run: list[str], anchors: list[tuple[str, str]]) -> tuple[list[str], str, str] | None:
    """First anchor that a suffix of the run starts with -> (candidate tokens, anchor, kind)."""
    for i in range(len(run)):
        joined = normalize("".join(run[i:]))
        for anchor, kind in anchors:
            a = normalize(anchor)
            if a and joined.startswith(a):
                tokens = _trim(run[i:i + MAX_TOKENS])
                # More than the anchor itself: a bare brand is not a product name.
                if len(normalize("".join(tokens))) > len(a):
                    return tokens, anchor, kind
    return None


def split_attributes(alias: str, anchor: str) -> tuple[int | None, list[str]]:
    """Age and edition tokens of a candidate (the anchor removed)."""
    rest = alias
    if normalize(alias).startswith(normalize(anchor)):
        rest = alias[len(anchor):] if alias.startswith(anchor) else alias
    age_match = _AGE_IN.search(rest)
    age = int(age_match.group(1)) if age_match else None
    if age_match:
        rest = rest[:age_match.start()] + " " + rest[age_match.end():]
    edition = [t for t in rest.split() if t not in EDGE_WORDS and not _AGE.fullmatch(t)]
    return age, edition


def extract_candidates(product: dict, results: list[dict], ko_brands: list[str],
                       edition_brands: list[str] = ()) -> dict:
    """Return {"anchors": [...], "candidates": [...]} (candidates ranked, at most MAX_CANDIDATES)."""
    items = [(r, it) for r in results for it in r["items"]]
    texts = [clean_text(it.get("title", "")) + " | " + clean_text(it.get("description", "")) for _, it in items]
    learned = [a for a in learn_brand_aliases(product["brand"], texts) if normalize(a) not in
               {normalize(b) for b in ko_brands}]
    anchors = ([(a, "brand") for a in ko_brands] + [(a, "learned") for a in learned]
               + [(a, "edition_brand") for a in edition_brands])
    # Longer anchors first so "하이랜드 파크" wins over "하이랜드".
    anchors.sort(key=lambda x: -len(normalize(x[0])))

    found: dict[str, dict] = {}
    links: dict[str, set] = defaultdict(set)
    for (record, item), text in zip(items, texts):
        for run in _runs(text):
            hit = _from_run(run, anchors)
            if hit is None:
                continue
            tokens, anchor, kind = hit
            alias = " ".join(tokens)
            key = normalize(alias)
            cand = found.setdefault(key, {"alias": alias, "normalized": key, "anchor": anchor,
                                          "anchor_kind": kind, "evidence": []})
            link = item.get("link", "")
            if link in links[key]:
                continue
            links[key].add(link)
            if len(cand["evidence"]) < MAX_EVIDENCE:
                cand["evidence"].append({
                    "endpoint": record["endpoint"], "query": record["query"], "url": link,
                    "fetched_at": record["fetched_at"], "title_raw": item.get("title", ""),
                    "title": clean_text(item.get("title", "")),
                    "snippet": clean_text(item.get("description", ""))[:300],
                })
    ranked = sorted(found.values(), key=lambda c: (-len(links[c["normalized"]]),
                                                    c["anchor_kind"] == "edition_brand", c["normalized"]))
    out = []
    for c in ranked[:MAX_CANDIDATES]:
        age, edition = split_attributes(c["alias"], c["anchor"])
        out.append({**c, "result_count": len(links[c["normalized"]]), "age_years": age, "edition_tokens": edition})
    return {"anchors": [{"text": a, "kind": k} for a, k in anchors], "candidate_total": len(found), "candidates": out}
