"""I3 matching evaluation (P10, ai/docs/i3_eval_freeze.md 4장) and its dev pre-run check.

    # pre-run check on the 5 dev bars (E8 C2 numbers), no Gemini call
    python ai/eval/i3_match_eval.py --set dev --catalog eval --json <out>
    python ai/eval/i3_match_eval.py --set dev --catalog eval_dropprod --llm --cache <E8 cache> --cache-only --json <out>
    # I3 test, label input (rules once; rules+LLM once per run r1-r3, each run its own empty cache)
    python ai/eval/i3_match_eval.py --set i3 --catalog full --json <out>
    python ai/eval/i3_match_eval.py --set i3 --catalog asis --llm --cache ai/runs/<date>_p10/cache_r1 --json <out>
    # end-to-end input: P30 hybrid extraction run i (lines = extracted names, paired to the labels)
    python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction <P30 run dir> --run 1 --json <out>
    # C0 / C1: the rules code (and by default the catalog) of another checkout, rules only
    python ai/eval/i3_match_eval.py --set i3 --catalog asis --rules-repo <worktree at 952db5c> \
        [--catalog-file <v2.3 catalog>] --json <out>

Lines are the menu line names of a photo in order, glass/bottle rows once (label input:
the layer-1 gold raw_name; end-to-end: the extracted raw_name, paired to the label items as
e2e_match.py does). Rules = resolve_product_staged with S1+S2+S2b+S3, as menu import runs
it. The LLM layer is the server's (`app.matching.llm_layer.M3Engine`, #68): one M3a call per
photo for the lines the rules did not confirm in that catalog, merge, M3b off, call cap 30
per bar (one bar = one menu import). Scoring uses match_eval.judge / burden_kind.

Catalogs (built per bar; aliases whose only sources are that bar's own menu are dropped)
  dev  eval           no generated / paren-strip alias unless another bar's menu gives it (E8)
       eval_dropprod  eval without the products seen only at that bar
       service        all aliases (generated and paren-strip kept)
  i3   asis           the catalog file as served (aliases as in service); I3-only products absent
       full           asis + every new:<key> product the gold refers to, with its standard English
                      name as the only alias (a new brand gets its English name as the only alias)

Gemini responses are cached by (model, thinking level, prompt SHA-256, input JSON), the
key and file format of ai/match_llm/llm.py, so the E8 cache answers the dev check. A run
stops cleanly (result marked incomplete) at --max-calls API calls or on a quota error; a
rerun with the same cache only sends the missing requests.

Never reads the menu photos; never reads I3 files with --set dev; never prints the API key.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import statistics
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "ai" / "eval"

I3_GOLD = REPO_ROOT / "eval" / "match_gold_i3_v1.json"
I3_GOLD_SHA256 = "281437a00d4f0c1141621c0fcd57af42c0920612ceeec214131433fc06f53721"
I3_LABELS = REPO_ROOT / "eval" / "labels_i3_v1.json"
DEV_GOLD = {"위스키복춘": "eval/match_gold_v1_1.json", "서로상": "eval/match_gold_v1_1.json",
            "미라보": "eval/match_gold_v1_1.json", "수이": "eval/match_gold_final_v1.json",
            "오드비": "eval/match_gold_final_v1.json"}
DEV_LABELS = {"위스키복춘": "eval/labels_v1_1.json", "서로상": "eval/labels_v1_1.json",
              "미라보": "eval/labels_heldout_v1_1.json", "수이": "eval/labels_final_v1.json",
              "오드비": "eval/labels_final_v1.json"}
CATALOGS = {"dev": ("eval", "eval_dropprod", "service"), "i3": ("full", "asis")}
STAGES = frozenset({"S1", "S2", "S2b", "S3"})
CONFIRMED = ("exact_match", "multi")
NEW_NS = uuid.UUID("6f1d3f0e-6c8a-4d5e-9b1a-2b7c3d4e5f60")  # match_eval.NEW_NS: ids of new:<key> products
BAR_CALL_CAP = 30  # backend DEFAULT_MAX_CALLS: model requests per menu import
BURDEN_KINDS = ("confirm", "choose", "register", "wrong")
PAREN = re.compile(r"\s*\([^()]*\)")
I3_NAME = re.compile(r"i3", re.IGNORECASE)
QUOTA = re.compile(r"RESOURCE_EXHAUSTED|quota|429", re.IGNORECASE)


# ---- backend (rules code of --rules-repo) -----------------------------------------------

class Backend:
    """The matching modules of one checkout. Imported before match_eval so that match_eval's
    `from app.matching... import` binds to the same (already imported) `app` package."""

    def __init__(self, rules_repo: Path):
        sys.path.insert(0, str(rules_repo / "backend"))
        sys.path.insert(0, str(EVAL_DIR))
        self.normalize = importlib.import_module("app.core.normalize").normalize
        self.InMemoryCatalog = importlib.import_module("app.matching.memory_catalog").InMemoryCatalog
        self.resolve_staged = importlib.import_module("app.matching.staged").resolve_product_staged
        types = importlib.import_module("app.matching.types")
        self.ExtractedProduct, self.ProductInfo = types.ExtractedProduct, types.ProductInfo
        match_eval = importlib.import_module("match_eval")
        self.judge, self.burden_kind, self.gold_refs = match_eval.judge, match_eval.burden_kind, match_eval.gold_refs

    def resolve(self, name: str, catalog):
        return self.resolve_staged(self.ExtractedProduct(product_name=name), catalog, STAGES)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_head(repo: Path) -> str | None:
    head = repo / ".git" / "HEAD"
    if not head.is_file():
        return None
    ref = head.read_text(encoding="utf-8").strip()
    if ref.startswith("ref: "):
        path = repo / ".git" / ref[5:]
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        packed = repo / ".git" / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref[5:]):
                    return line.split()[0]
        return None
    return ref


# ---- photos, lines and gold ---------------------------------------------------------------

@dataclass
class Photo:
    bar: str
    photo_id: str
    lines: list[tuple[str, str | None]]  # (line name, gold or None for an unpaired extracted line)
    missed: list[tuple[str, str]] = field(default_factory=list)  # (gold line, gold) not extracted (end-to-end)


def read_repo_json(rel: str, allow_i3: bool):
    if not allow_i3 and I3_NAME.search(rel):
        raise SystemExit(f"refusing to read an I3 file with --set dev: {rel}")
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def label_lines(items: list[dict]) -> list[tuple[str, str]]:
    """Menu lines of one photo in order (glass/bottle rows once) with the gold of the first row."""
    seen: dict[str, str] = {}
    for item in items:
        seen.setdefault(item["raw_name"], item["gold"])
    return list(seen.items())


def check_gold_names(gold: dict, labels: dict[str, list[dict]], name: str) -> None:
    for photo in gold["photos"]:
        if [i["raw_name"] for i in photo["items"]] != [i["raw_name"] for i in labels[photo["photo_id"]]]:
            raise SystemExit(f"{photo['photo_id']}: gold names differ from {name}")


def dev_photos() -> tuple[list[Photo], dict]:
    photos = []
    for bar, gpath in DEV_GOLD.items():
        gold = read_repo_json(gpath, allow_i3=False)
        labels = {p["photo_id"]: p["items"] for p in read_repo_json(DEV_LABELS[bar], allow_i3=False)["photos"]}
        for photo in gold["photos"]:
            if photo["bar"] != bar:
                continue
            if [i["raw_name"] for i in labels[photo["photo_id"]]] != [i["raw_name"] for i in photo["items"]]:
                raise SystemExit(f"{photo['photo_id']}: gold names differ from {DEV_LABELS[bar]}")
            photos.append(Photo(bar, photo["photo_id"], label_lines(photo["items"])))
    return photos, {}


def i3_gold(path: Path, expect_sha: str | None) -> dict:
    digest = sha256_file(path)
    if expect_sha and digest != expect_sha:
        raise SystemExit(f"{path.name}: SHA-256 {digest} is not the frozen {expect_sha} (i3_eval_freeze.md 4.2)")
    return json.loads(path.read_text(encoding="utf-8"))


def i3_photos(gold: dict, labels_path: Path) -> list[Photo]:
    labels = {p["photo_id"]: p["items"] for p in json.loads(labels_path.read_text(encoding="utf-8"))["photos"]}
    check_gold_names(gold, labels, labels_path.name)
    return [Photo(p["bar"], p["photo_id"], label_lines(p["items"])) for p in gold["photos"]]


def e2e_photos(gold: dict, labels_path: Path, run_dir: Path, run: int) -> list[Photo]:
    """Lines of P30 extraction run `run`, each with the gold of the first label item it pairs with."""
    import e2e_match  # score.py pairing; imported only here (needs ai/extract on the path)
    labels = {p["photo_id"]: p["items"] for p in json.loads(labels_path.read_text(encoding="utf-8"))["photos"]}
    check_gold_names(gold, labels, labels_path.name)
    extracted = e2e_match.load_run(run_dir, run, "i3")
    built = e2e_match.build_lines(gold, labels, extracted, [p["photo_id"] for p in gold["photos"]])
    photos = []
    for photo in gold["photos"]:
        b = built[photo["photo_id"]]
        photos.append(Photo(photo["bar"], photo["photo_id"], [(r["name"], r["gold"]) for r in b["lines"]],
                            [(g["name"], g["gold"]) for g in b["gold_lines"] if not g["extracted"]]))
    return photos


# ---- catalogs -----------------------------------------------------------------------------

@dataclass
class BarCatalog:
    catalog: object
    key_to_id: dict
    display: dict  # product id -> display name (every seed product and every added new product)
    digest: str


def build_catalog(be: Backend, bar: str, variant: str, seed: dict, new_products: dict | None = None,
                  eval_filter: str = "only-generated") -> BarCatalog:
    """One bar's catalog (see the module docstring). `new_products`: added for "full"."""
    own = {f"menu:{bar}"}
    drop_prod = set()
    if variant == "eval_dropprod":
        drop_prod = {p["key"] for p in seed["products"] if set(p.get("sources", [])) == own}

    def keep(a, product=None) -> bool:
        src = set(a.get("sources", []))
        if src and src <= own:
            return False
        if variant in ("eval", "eval_dropprod"):
            if eval_filter == "any-generated":
                if any(s.startswith("generated") for s in src) or "template:paren-strip" in src:
                    return False
            else:
                real = {s for s in src if not s.startswith("generated") and s != "template:paren-strip"}
                if src and not (real - own):
                    return False
        if variant != "eval" and variant != "eval_dropprod" and "template:paren-strip" in src and product:
            n = be.normalize(a["alias_text"])
            parents = [b for b in product["aliases"] if "(" in b["alias_text"]
                       and be.normalize(PAREN.sub("", b["alias_text"])) == n]
            if parents and all(set(b.get("sources", [])) <= own for b in parents):
                return False
        return True

    products, aliases, brand_aliases = [], [], []
    key_to_id, display = {}, {}
    live_brands = {p["brand_id"] for p in seed["products"] if p["key"] not in drop_prod}
    for b in seed["brands"]:
        if b["id"] in live_brands:
            brand_aliases += [(uuid.UUID(b["id"]), a["alias_text"]) for a in b["aliases"] if keep(a)]
    for p in seed["products"]:
        pid = uuid.UUID(p["id"])
        display[pid] = p["display_name"]
        if p["key"] in drop_prod:
            continue
        key_to_id[p["key"]] = pid
        products.append(be.ProductInfo(pid, p["display_name"], p.get("age_years"), p.get("edition_name"),
                                       uuid.UUID(p["brand_id"])))
        aliases += [(pid, a["alias_text"]) for a in p["aliases"] if keep(a, p)]
    if new_products:
        brand_ids = {b["key"]: uuid.UUID(b["id"]) for b in seed["brands"]}
        for key, p in sorted(new_products.items()):
            pid = uuid.uuid5(NEW_NS, key)
            brand_id = brand_ids.get(p["brand"].replace("-", "_"))
            if brand_id is None:
                brand_id = uuid.uuid5(NEW_NS, f"brand:{p['brand']}")
                alias = (brand_id, p.get("brand_name") or p["brand"])
                if alias not in brand_aliases:
                    brand_aliases.append(alias)
            key_to_id[f"new:{key}"] = pid
            display[pid] = p["display_name"]
            products.append(be.ProductInfo(pid, p["display_name"], p["age_years"], p["edition_name"], brand_id))
            aliases.append((pid, p["display_name"]))
    canonical = json.dumps({
        "products": sorted([str(x.product_id), x.display_name, x.age_years, x.edition_name, str(x.brand_id)]
                           for x in products),
        "aliases": sorted([str(pid), text] for pid, text in aliases),
        "brand_aliases": sorted([str(bid), text] for bid, text in brand_aliases),
    }, ensure_ascii=False, sort_keys=True)
    return BarCatalog(be.InMemoryCatalog(products, aliases, brand_aliases), key_to_id, display,
                      sha256_bytes(canonical.encode("utf-8")))


def catalog_digest(bar_catalogs: dict[str, BarCatalog]) -> str:
    return sha256_bytes("\n".join(f"{bar}\t{c.digest}" for bar, c in sorted(bar_catalogs.items())).encode("utf-8"))


def refs_of(be: Backend, gold: str | None) -> list[str]:
    return [] if gold in (None, "unknown", "non_whisky") else be.gold_refs(gold)


def gold_for(be: Backend, g: str | None, key_to_id: dict, dev: bool) -> str | None:
    """The gold in the catalog's terms: a ref the catalog lacks is written new:<key>."""
    if g in (None, "unknown", "non_whisky"):
        return g
    refs = [r.removeprefix("new:") for r in be.gold_refs(g)]
    if dev and refs == ["jack-daniels-apple"]:  # E8: a flavoured whiskey liqueur, out of scope
        return "non_whisky"
    refs = [r if r in key_to_id else f"new:{r}" for r in refs]
    return ("both:" if g.startswith("both:") else "") + "|".join(refs)


def coverage(be: Backend, photos: list[Photo], bar_catalogs: dict[str, BarCatalog], dev: bool) -> dict:
    """Product lines whose gold products are all in that bar's catalog (an input property, no matching)."""
    product_lines = covered = 0
    for photo in photos:
        key_to_id = bar_catalogs[photo.bar].key_to_id
        for _, graw in photo.lines:
            g = gold_for(be, graw, key_to_id, dev)
            if g in (None, "unknown", "non_whisky"):
                continue
            product_lines += 1
            covered += all(r in key_to_id for r in be.gold_refs(g))
    return {"product_lines": product_lines, "covered": covered,
            "rate": covered / product_lines if product_lines else None}


# ---- LLM ----------------------------------------------------------------------------------

class CacheMiss(Exception):
    pass


class StopRun(Exception):
    """The run cannot go on today (call cap or quota). M3Engine turns any exception into "no
    answer", so the wrapper also keeps the reason in `stopped` and the harness stops there."""


class CachedMatchingLLM:
    """`MatchingLLM` for the harness: the server adapter behind a response cache with the
    ai/match_llm/llm.py key and record format, a minimum interval between API calls, up to
    3 more requests after an API error, and a stop at the call cap or on a quota error."""

    def __init__(self, inner, cache_dir: Path, seed_dirs: list[Path], *, model: str, thinking: str,
                 kinds: dict[str, str], cache_only: bool, max_calls: int, min_interval: float,
                 retries: int = 3):
        self.inner, self.cache_dir, self.seed_dirs = inner, cache_dir, seed_dirs
        self.model, self.thinking, self.kinds = model, thinking, kinds
        self.cache_only, self.max_calls, self.min_interval, self.retries = cache_only, max_calls, min_interval, retries
        self.api_calls = 0
        self.counts: Counter[str] = Counter()
        self.latency_ms: dict[str, int | None] = {}  # cache key -> latency of the request behind it
        self.stopped: str | None = None
        self._last = 0.0

    def key(self, prompt: str, payload: dict) -> str:
        input_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        prompt_sha = sha256_bytes(prompt.encode("utf-8"))
        return sha256_bytes(json.dumps([self.model, self.thinking, prompt_sha, input_json],
                                       ensure_ascii=False).encode("utf-8"))

    def generate_json(self, prompt: str, payload: dict, response_schema: dict) -> str:
        if self.stopped:
            raise StopRun(self.stopped)
        key = self.key(prompt, payload)
        path = self.cache_dir / f"{key}.json"
        record = None
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            self.counts["cache_hit"] += 1
        else:
            for seed in self.seed_dirs:
                if (seed / f"{key}.json").exists():
                    record = json.loads((seed / f"{key}.json").read_text(encoding="utf-8"))
                    self._write(path, record)
                    self.counts["seed_hit"] += 1
                    break
        if record is None:
            if self.cache_only:
                self.counts["cache_miss"] += 1
                raise CacheMiss(key[:12])
            record = self._request(prompt, payload, response_schema, key)
            self._write(path, record)
        self.latency_ms[key] = record["meta"].get("latency_ms")
        return record["output_text"]

    def _write(self, path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    def _request(self, prompt: str, payload: dict, schema: dict, key: str) -> dict:
        attempts = 0
        while True:
            if self.api_calls >= self.max_calls:
                self.stopped = f"call cap {self.max_calls} reached"
                raise StopRun(self.stopped)
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            attempts += 1
            self.api_calls += 1
            self._last = time.monotonic()
            started_at = datetime.now(timezone.utc).isoformat()
            t0 = time.perf_counter()
            try:
                text = self.inner.generate_json(prompt, payload, schema)
                break
            except Exception as error:  # the adapter raises MatchingLLMError for API errors
                if QUOTA.search(str(error)):
                    self.stopped = f"quota: {type(error).__name__}"
                    raise StopRun(self.stopped) from None
                self.counts["api_error"] += 1
                if attempts > self.retries:
                    self.counts["no_answer"] += 1
                    raise
                print(f"    LLM retry {attempts}/{self.retries}: {type(error).__name__}", file=sys.stderr, flush=True)
        self.counts["fresh"] += 1
        prompt_sha = sha256_bytes(prompt.encode("utf-8"))
        return {"key": key, "kind": self.kinds.get(prompt_sha, "?"), "input": payload, "output_text": text,
                "meta": {"model": self.model, "thinking_level": self.thinking, "prompt_sha256": prompt_sha,
                         "started_at": started_at, "latency_ms": round((time.perf_counter() - t0) * 1000),
                         "attempts": attempts, "source": "i3_match_eval (server adapter)",
                         "input_tokens": None, "output_tokens": None, "thought_tokens": None}}


def load_llm_layer():
    try:
        return importlib.import_module("app.matching.llm_layer")
    except ModuleNotFoundError as error:
        raise SystemExit(f"--llm needs the server LLM layer (#68) in the rules checkout: {error}") from None


def product_meta(layer, seed: dict, new_products: dict | None) -> dict:
    """ProductMeta as the server builds it (CatalogSnapshot): bottler from the brand's canonical name."""
    brands = {b["id"]: b for b in seed["brands"]}
    out = {}
    for row in seed["products"]:
        out[uuid.UUID(row["id"])] = layer.ProductMeta(
            row["display_name"], row.get("age_years"), row.get("edition_name"),
            layer.bottler_of(brands[row["brand_id"]]["canonical_name"]), tuple(a["alias_text"] for a in row["aliases"]))
    for key, p in (new_products or {}).items():
        out[uuid.uuid5(NEW_NS, key)] = layer.ProductMeta(
            p["display_name"], p["age_years"], p["edition_name"], layer.bottler_of(p.get("brand_name") or p["brand"]),
            (p["display_name"],))
    return out


def make_llm(args, layer):
    from app.adapters.matching_llm import MODEL, THINKING_LEVEL
    inner = None
    if not args.cache_only:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set (use --cache-only to score from the cache)")
        from app.adapters.gemini_matching_llm import GeminiMatchingLLM
        inner = GeminiMatchingLLM(key)
    kinds = {sha256_bytes(layer.load_prompt(layer.TRANSLATE_PROMPT).encode("utf-8")): "m3a",
             sha256_bytes(layer.load_prompt(layer.PICK_PROMPT).encode("utf-8")): "m3b"}
    return CachedMatchingLLM(inner, args.cache, args.seed_cache, model=MODEL, thinking=THINKING_LEVEL, kinds=kinds,
                             cache_only=args.cache_only, max_calls=args.max_calls, min_interval=args.min_interval)


# ---- scoring ------------------------------------------------------------------------------

def score_line(be: Backend, photo: Photo, name: str, graw: str, r, b, bc: BarCatalog, dev: bool,
               target: bool) -> dict:
    g = gold_for(be, graw, bc.key_to_id, dev)
    if g is None:  # end-to-end: an extracted line paired with no label item
        cr = r.status == "ambiguous" and bool(r.candidates[0].evidence.get("confirmRecommended"))
        return {"bar": photo.bar, "photo_id": photo.photo_id, "name": name, "gold": None, "kind": "unpaired",
                "status": r.status, "outcome": None, "burden": None, "confirm_recommended": cr, "cr_source": None,
                "rank1_gold": False, "n_cand": len(r.candidates), "base_status": b.status, "llm_target": target,
                "cands": " || ".join(bc.display.get(c.product_id, "?") for c in r.candidates[:4])}
    in_cat = lambda ref: ref in bc.key_to_id
    outcome = be.judge(g, r, bc.key_to_id, in_cat)
    kind = ("non_whisky" if g == "non_whisky" else "unknown" if g == "unknown"
            else "known" if all(in_cat(x) for x in be.gold_refs(g)) else "absent")
    gold_ids = {bc.key_to_id[x] for x in refs_of(be, g) if x in bc.key_to_id}
    rank1_gold = bool(r.candidates) and r.candidates[0].product_id in gold_ids
    burden = be.burden_kind(g, r, outcome, rank1_gold) if r.status not in CONFIRMED else "confirmed"
    cr = r.status == "ambiguous" and bool(r.candidates[0].evidence.get("confirmRecommended"))
    source = None
    if cr:
        by_rule = r.candidates[0].method != "llm" or (
            b.status == "ambiguous" and len(b.candidates) == 1
            and b.candidates[0].product_id == r.candidates[0].product_id
            and bool(b.candidates[0].evidence.get("confirmRecommended")))
        source = "rule" if by_rule else "llm"
    row = {"bar": photo.bar, "photo_id": photo.photo_id, "name": name, "gold": g, "kind": kind,
           "status": r.status, "outcome": outcome, "burden": burden, "confirm_recommended": cr, "cr_source": source,
           "rank1_gold": rank1_gold, "n_cand": len(r.candidates),
           "rank1_method": r.candidates[0].method if r.candidates else None,
           "rule": r.candidates[0].evidence.get("rule") if r.candidates else "",
           "cands": " || ".join(bc.display.get(c.product_id, "?") for c in r.candidates[:4]),
           "gold_display": " | ".join(bc.display[bc.key_to_id[x]] for x in refs_of(be, g) if x in bc.key_to_id),
           "base_status": b.status, "llm_target": target}
    if r is not b and r.candidates and r.candidates[0].method == "llm":
        ev = r.candidates[0].evidence
        row["llm"] = {"english_name": ev.get("englishName"), "via": ev.get("via"),
                      "vetoed": ev.get("vetoed"), "short_unverified": ev.get("shortUnverified")}
    return row


def stats(rows: list[dict], photos: int) -> dict:
    """E8 report columns (e8_driver.stats), one set of rows."""
    known = [r for r in rows if r["kind"] == "known"]
    fm = [r for r in rows if r["outcome"] in ("false_merge", "overconfident")]
    wrong_cr = [r for r in rows if r["confirm_recommended"] and not r["rank1_gold"]]
    accept = len(fm) + sum(1 for r in wrong_cr if r["outcome"] not in ("false_merge", "overconfident"))
    b = Counter(r["burden"] for r in rows)
    cr = {s: [r for r in rows if r["cr_source"] == s] for s in ("rule", "llm")}
    correct = sum(r["outcome"] == "correct" for r in known)
    return {
        "lines": len(rows), "photos": photos, "known": len(known), "correct": correct,
        "top1": correct / len(known) if known else None,
        "fm": len(fm), "fm_rate": len(fm) / len(rows) if rows else None, "fm_names": [r["name"] for r in fm],
        "wrong_cr": len(wrong_cr),
        "wrong_cr_names": [f"{r['name']} -> {r['cands'].split(' || ')[0]}" for r in wrong_cr],
        "accept_err_rate": accept / len(rows) if rows else None,
        "totals": {k: b[k] for k in BURDEN_KINDS},
        "per_photo": {k: b[k] / photos for k in BURDEN_KINDS} if photos else {},
        "owner_per_photo": sum(b[k] for k in BURDEN_KINDS) / photos if photos else None,
        "hard_per_photo": sum(b[k] for k in ("choose", "register", "wrong")) / photos if photos else None,
        "cr_rule": {"n": len(cr["rule"]), "correct": sum(r["rank1_gold"] for r in cr["rule"])},
        "cr_llm": {"n": len(cr["llm"]), "correct": sum(r["rank1_gold"] for r in cr["llm"])},
        "llm_targets": sum(r["llm_target"] for r in rows),
        "from_register": sum(1 for r in rows if r["base_status"] == "unmatched" and r["status"] != "unmatched"),
        "from_register_gold_in": sum(1 for r in rows if r["base_status"] == "unmatched"
                                     and r["status"] != "unmatched" and r["outcome"] == "ambiguous_ok"),
    }


def hard_photos_under(rows: list[dict], photo_ids: list[str], limit: int = 5) -> float | None:
    hard = Counter(r["photo_id"] for r in rows if r["burden"] in ("choose", "register", "wrong"))
    return sum(hard[p] < limit for p in photo_ids) / len(photo_ids) if photo_ids else None


def summarize(rows: list[dict], photos: list[Photo], missed_known: int = 0) -> dict:
    """Lines with a gold are scored. End-to-end extras: unpaired lines (no gold) and missed gold
    lines; `missed_known`: missed lines whose gold products are all in the catalog."""
    scored = [r for r in rows if r["gold"] is not None]
    menu_photos = [p for p in photos if p.lines or p.missed]  # per-photo numbers: photos with menu lines (E8)
    photo_ids = [p.photo_id for p in menu_photos]
    out = {"all": stats(scored, len(menu_photos)), "hard_under_5_photo_rate": hard_photos_under(scored, photo_ids),
           "by_bar": {bar: stats([r for r in scored if r["bar"] == bar], sum(p.bar == bar for p in menu_photos))
                      for bar in dict.fromkeys(p.bar for p in menu_photos)}}
    unpaired = [r for r in rows if r["gold"] is None]
    missed = sum(len(p.missed) for p in photos)
    if unpaired or missed:
        a = out["all"]
        out["e2e"] = {"unpaired_lines": len(unpaired),
                      "unpaired_by_status": dict(Counter(r["status"] for r in unpaired)),
                      "unpaired_confirmed_or_cr": sum(r["status"] in CONFIRMED or r["confirm_recommended"]
                                                      for r in unpaired),
                      "missed_gold_lines": missed,
                      "missed_known_lines": missed_known,
                      "top1_missed_as_fail": (a["correct"] / (a["known"] + missed_known)
                                              if a["known"] + missed_known else None)}
    return out


# ---- main ---------------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", dest="set_", choices=("dev", "i3"), required=True)
    ap.add_argument("--catalog", required=True, help="dev: eval | eval_dropprod | service; i3: full | asis")
    ap.add_argument("--rules-repo", type=Path, default=REPO_ROOT,
                    help="checkout whose backend/app/matching (and catalog by default) is used")
    ap.add_argument("--catalog-file", type=Path, help="default: <rules-repo>/ai/catalog/catalog_v2_service.json")
    ap.add_argument("--gold", type=Path, default=I3_GOLD)
    ap.add_argument("--no-gold-sha-check", action="store_true", help="tests only")
    ap.add_argument("--labels", type=Path, default=I3_LABELS)
    ap.add_argument("--extraction", type=Path, help="P30 extraction run dir (end-to-end input)")
    ap.add_argument("--run", type=int, help="extraction run number for --extraction")
    ap.add_argument("--eval-filter", choices=("only-generated", "any-generated"), default="only-generated")
    ap.add_argument("--llm", action="store_true", help="rules + the server LLM layer (M3a, merge, M3b off)")
    ap.add_argument("--cache", type=Path, help="response cache of this run (one per run r1-r3)")
    ap.add_argument("--seed-cache", type=Path, action="append", default=[], help="read-only caches to reuse")
    ap.add_argument("--cache-only", action="store_true", help="score from the cache; a miss is an error")
    ap.add_argument("--max-calls", type=int, default=250, help="API calls per command before a clean stop")
    ap.add_argument("--min-interval", type=float, default=4.5, help="seconds between API calls")
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.catalog not in CATALOGS[args.set_]:
        ap.error(f"--catalog for --set {args.set_}: {', '.join(CATALOGS[args.set_])}")
    if args.llm and args.cache is None:
        ap.error("--llm needs --cache")
    if (args.extraction is None) != (args.run is None):
        ap.error("--extraction and --run go together")
    if args.extraction and args.set_ != "i3":
        ap.error("--extraction is for --set i3")
    return args


def main(argv=None) -> dict:
    args = parse_args(argv)
    rules_repo = args.rules_repo.resolve()
    be = Backend(rules_repo)
    catalog_file = (args.catalog_file or rules_repo / "ai" / "catalog" / "catalog_v2_service.json").resolve()
    seed = json.loads(catalog_file.read_text(encoding="utf-8"))
    dev = args.set_ == "dev"

    gold_sha = None
    new_products = None
    if dev:
        photos, _ = dev_photos()
    else:
        gold = i3_gold(args.gold, None if args.no_gold_sha_check else I3_GOLD_SHA256)
        gold_sha = sha256_file(args.gold)
        if args.catalog == "full":
            used = {r.removeprefix("new:") for p in gold["photos"] for i in p["items"]
                    for r in refs_of(be, i["gold"]) if r.startswith("new:")}
            new_products = {k: v for k, v in gold["new_products"].items() if k in used}
        photos = (e2e_photos(gold, args.labels, args.extraction, args.run) if args.extraction
                  else i3_photos(gold, args.labels))

    bars = list(dict.fromkeys(p.bar for p in photos))
    bar_catalogs = {bar: build_catalog(be, bar, args.catalog, seed, new_products, args.eval_filter) for bar in bars}

    # rules
    base, targets = {}, {}
    for photo in photos:
        catalog = bar_catalogs[photo.bar].catalog
        targets[photo.photo_id] = set()
        for name, _ in photo.lines:
            r = be.resolve(name, catalog)
            base[(photo.photo_id, name)] = r
            if r.status not in CONFIRMED:
                targets[photo.photo_id].add(name)

    def rows_for(resolved) -> list[dict]:
        return [score_line(be, p, name, graw, resolved[(p.photo_id, name)], base[(p.photo_id, name)],
                           bar_catalogs[p.bar], dev, name in targets[p.photo_id])
                for p in photos for name, graw in p.lines]

    rules_rows = rows_for(base)
    missed_known = 0
    for p in photos:
        key_to_id = bar_catalogs[p.bar].key_to_id
        for _, graw in p.missed:
            g = gold_for(be, graw, key_to_id, dev)
            missed_known += g not in ("unknown", "non_whisky") and all(r in key_to_id for r in be.gold_refs(g))
    result = {
        "harness": "ai/eval/i3_match_eval.py", "set": args.set_, "catalog": args.catalog,
        "input": f"extraction {args.extraction.as_posix()} r{args.run}" if args.extraction else "label",
        "rules_repo_head": git_head(rules_repo), "catalog_file": catalog_file.name,
        "catalog_version": seed.get("version"), "catalog_file_sha256": sha256_file(catalog_file),
        "catalog_digest": catalog_digest(bar_catalogs), "gold_sha256": gold_sha,
        "new_products_added": len(new_products or {}), "eval_filter": args.eval_filter if dev else None,
        "coverage": coverage(be, photos, bar_catalogs, dev),
        "photos": len(photos), "lines": sum(len(p.lines) for p in photos),
        "rules": {**summarize(rules_rows, photos, missed_known), "rows": rules_rows},
    }

    if args.llm:
        layer = load_llm_layer()
        llm = make_llm(args, layer)
        pmeta = product_meta(layer, seed, new_products)
        engines, photo_runs, stop = {}, [], None
        for bar in bars:
            bar_photos = [p for p in photos if p.bar == bar]
            engines[bar] = layer.M3Engine(llm, {p.photo_id: [n for n, _ in p.lines] for p in bar_photos}, pmeta,
                                          max_calls=BAR_CALL_CAP)
        misses_before = 0
        for photo in photos:
            rec = {"photo_id": photo.photo_id, "bar": photo.bar, "targets": len(targets[photo.photo_id])}
            if stop is not None:
                rec["status"] = "not_run"
            elif not targets[photo.photo_id]:
                engines[photo.bar].translate(photo.photo_id, set())
                rec["status"] = "no_targets"
            else:
                engine = engines[photo.bar]
                before = (Counter(engine.stats), llm.counts["fresh"])
                payload = {"lines": [{"line": i, "name": n, "target": n in targets[photo.photo_id]}
                                     for i, n in enumerate([n for n, _ in photo.lines], start=1)]}
                key = llm.key(engine.translate_prompt, payload)
                engine.translate(photo.photo_id, targets[photo.photo_id])
                new = Counter(engine.stats) - before[0]
                if llm.stopped:
                    stop = llm.stopped
                    rec["status"] = "not_run"
                else:
                    rec["status"] = ("fresh" if llm.counts["fresh"] > before[1] else
                                     "miss" if llm.counts["cache_miss"] > misses_before else "cached")
                    rec["outcome"] = next(iter(new), None)  # ok | parse_error | error | cap_reached
                    rec["latency_ms"] = llm.latency_ms.get(key)
                    rec["cache_key"] = key
                misses_before = llm.counts["cache_miss"]
            photo_runs.append(rec)
        resolved = {}
        for photo in photos:
            for name, _ in photo.lines:
                b = base[(photo.photo_id, name)]
                resolved[(photo.photo_id, name)] = (b if b.status in CONFIRMED else engines[photo.bar].resolve(
                    photo.photo_id, name, bar_catalogs[photo.bar].catalog, b, use_m3b=False))
        llm_rows = rows_for(resolved)
        lat = [p["latency_ms"] for p in photo_runs if p.get("latency_ms") is not None]
        result["llm"] = {
            **summarize(llm_rows, photos, missed_known), "rows": llm_rows, "photo_runs": photo_runs,
            "complete": stop is None and llm.counts["cache_miss"] == 0,
            "stop_reason": stop, "cache": args.cache.as_posix(), "api_calls": llm.api_calls,
            "counts": dict(llm.counts),
            "engine_stats": {bar: dict(e.stats) for bar, e in engines.items()},
            "latency_s": ({"n": len(lat), "mean": statistics.mean(lat) / 1000, "p50": statistics.median(lat) / 1000,
                           "p95": sorted(lat)[max(0, -(-95 * len(lat) // 100) - 1)] / 1000} if lat else None),
            "translate_prompt_sha256": sha256_bytes(layer.load_prompt(layer.TRANSLATE_PROMPT).encode("utf-8")),
            "llm_layer_sha256": sha256_file(Path(layer.__file__)),
        }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print_summary(result)
    if args.llm and args.cache_only and result["llm"]["counts"].get("cache_miss"):
        raise SystemExit(f"{result['llm']['counts']['cache_miss']} cache misses with --cache-only")
    return result


def fmt(x, digits=3) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def print_summary(result: dict) -> None:
    cov = result["coverage"]
    print(f"{result['set']}/{result['catalog']} ({result['input']}): {result['photos']} photos, {result['lines']} lines,"
          f" catalog {result['catalog_version']} digest {result['catalog_digest'][:12]},"
          f" coverage {cov['covered']}/{cov['product_lines']}")
    for matcher in ("rules", "llm"):
        if matcher not in result:
            continue
        a = result[matcher]["all"]
        print(f"  {matcher:5s} Top-1 {fmt(a['top1'])} ({a['correct']}/{a['known']})  FM {a['fm']}"
              f"  wrong CR {a['wrong_cr']}  accept-err {fmt(a['accept_err_rate'], 4)}"
              f"  hard/photo {fmt(a['hard_per_photo'], 2)}  CR rule {a['cr_rule']['correct']}/{a['cr_rule']['n']}"
              f"  CR LLM {a['cr_llm']['correct']}/{a['cr_llm']['n']}")
    if "llm" in result:
        llm = result["llm"]
        print(f"  LLM complete={llm['complete']} api_calls={llm['api_calls']} counts={llm['counts']}"
              + (f" stop: {llm['stop_reason']}" if llm["stop_reason"] else ""))


if __name__ == "__main__":
    main()
