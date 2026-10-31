"""P24: rules vs rules + generated Korean aliases vs rules + embedding candidates, dev bars only.

    # one model per process (clean memory numbers); models are ONNX exports from Hugging Face
    python ai/eval/p24_embedding_compare.py run --model tfidf --out ai/runs/2026-10-30_p24
    python ai/eval/p24_embedding_compare.py run --model e5-small --models-root <dir> --threads 2 \
        --out ai/runs/2026-10-30_p24
    python ai/eval/p24_embedding_compare.py summary --out ai/runs/2026-10-30_p24

Input: the 5 dev bars of ai/eval/i3_match_eval.py (`dev_photos`, label input; it refuses I3 files),
catalog v2.3 built per bar as that harness does:
  eval           (1) rules only: no generated / paren-strip alias unless another bar's menu gives it
  eval_p17       (2) rules + the P17 generated Korean aliases (`service` without paren-strip-only aliases)
  service        the catalog as served (generated and paren-strip aliases)
  eval_dropprod  `eval` without the products seen only at that bar (absent products)
(3) rules + embedding candidates: the rules result of a catalog, then `apply_policy` adds products
ranked by the embedding index of that bar's catalog (only the aliases the harness keeps for that
bar, so a bar's own menu spellings never leak in). Embeddings never confirm: a confirmed rules
result is returned as is and every result built here is "ambiguous", so Top-1 and false merges
equal those of rules; `check_invariants` checks it line by line and the run stops if it fails.

What is embedded (doc sets, one vector per text, a product scores the max over its texts)
  canonical  the product's display name
  aliases    display name + every alias kept for the bar
  korean     the kept aliases written in Hangul
  brand_age  display name + "<brand alias> <edition> <age>" for every kept brand alias
  all        aliases + brand_age

Measured per catalog: answer-in-candidates (recall@1/3/5/10) for the known lines the rules do
not confirm (rules list, embedding list, rules then embedding); per policy the i3_match_eval
numbers (Top-1, FM, wrong confirm recommended, burden kinds); the server LLM layer (M3a, E8
response cache, --cache-only, no API call) with embedding candidates before or after it; CPU
latency per menu photo (embed the photo's lines and search the bar index) and process memory.

No network except the model download done beforehand; no API key; never reads the menu photos.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, Sequence

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

import i3_match_eval as h  # noqa: E402

REPO_ROOT = h.REPO_ROOT
CATALOG_FILE = REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json"
E8_CACHE = REPO_ROOT / "ai" / "runs" / "2026-10-28_e8" / "cache"
CATALOG_VARIANTS = ("eval", "eval_p17", "service", "eval_dropprod")
LLM_CATALOGS = ("eval", "eval_dropprod", "service")
DOCSETS = ("canonical", "aliases", "korean", "brand_age", "all")
KS = (1, 3, 5, 10)
TOP_N = 10
CONFIRMED = h.CONFIRMED
HANGUL = re.compile("[가-힣]")
PAREN_STRIP = "template:paren-strip"

# name -> (Hugging Face repo, revision, pooling, text prefix, ONNX file). Pooling: mean over tokens or
# the model's own "sentence_embedding" output. All vectors are L2-normalized. "-int8": the dynamic int8
# export the model repo ships (model_qint8_avx512_vnni.onnx; runs on any x86-64 CPU, fastest with VNNI).
FP32, INT8 = "model.onnx", "model_qint8_avx512_vnni.onnx"
E5_SMALL = ("intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3")
E5_BASE = ("intfloat/multilingual-e5-base", "d128750597153bb5987e10b1c3493a34e5a4502a")
MODELS = {
    "minilm-l12": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                   "e8f8c211226b894fcb81acc59f3b34ba3efd5f42", "mean", "", FP32),
    "e5-small": (*E5_SMALL, "mean", "query: ", FP32),
    "e5-small-int8": (*E5_SMALL, "mean", "query: ", INT8),
    "e5-base": (*E5_BASE, "mean", "query: ", FP32),
    "e5-base-int8": (*E5_BASE, "mean", "query: ", INT8),
    "bge-m3": ("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181", "sentence_embedding", "", FP32),
}


# ---- embedders ----------------------------------------------------------------------------

class Embedder(Protocol):
    """Text -> vector. `fit` sees the catalog texts first (TF-IDF needs them; models ignore it)."""

    name: str

    def fit(self, docs: Sequence[str]) -> None: ...

    def embed(self, texts: Sequence[str]) -> list: ...

    def similarity(self, queries: list, docs: list) -> list[list[float]]: ...


def dense_similarity(queries: list, docs: list) -> list[list[float]]:
    """Cosine of unit vectors: numpy when available, else plain Python (tests)."""
    if len(queries) == 0 or len(docs) == 0:
        return [[] for _ in range(len(queries))]
    try:
        import numpy as np
    except ModuleNotFoundError:  # pragma: no cover - CI has no numpy; tests take the branch below
        np = None
    if np is not None and not isinstance(queries[0], list):
        return (np.asarray(queries) @ np.asarray(docs).T).tolist()
    return [[sum(a * b for a, b in zip(q, d)) for d in docs] for q in queries]


def unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class CharTfidf:
    """Character n-gram TF-IDF (n = 1..3 over the lowercased text without spaces), fitted on the
    catalog texts; sublinear tf, smooth idf, cosine. The baseline: no model, no download."""

    name = "tfidf"

    def __init__(self, n_min: int = 1, n_max: int = 3):
        self.n_min, self.n_max = n_min, n_max
        self.idf: dict[str, float] = {}

    def grams(self, text: str) -> Counter:
        s = re.sub(r"\s+", "", text.lower())
        return Counter(s[i:i + n] for n in range(self.n_min, self.n_max + 1) for i in range(len(s) - n + 1))

    def fit(self, docs: Sequence[str]) -> None:
        df: Counter = Counter()
        for d in docs:
            df.update(set(self.grams(d)))
        n = len(docs)
        self.idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}

    def embed(self, texts: Sequence[str]) -> list[dict[str, float]]:
        out = []
        for t in texts:
            v = {g: (1 + math.log(c)) * self.idf[g] for g, c in self.grams(t).items() if g in self.idf}
            norm = math.sqrt(sum(x * x for x in v.values()))
            out.append({g: x / norm for g, x in v.items()} if norm else {})
        return out

    def similarity(self, queries: list, docs: list) -> list[list[float]]:
        postings: dict[str, list[tuple[int, float]]] = {}
        for j, d in enumerate(docs):
            for g, x in d.items():
                postings.setdefault(g, []).append((j, x))
        rows = []
        for q in queries:
            row = [0.0] * len(docs)
            for g, x in q.items():
                for j, y in postings.get(g, ()):
                    row[j] += x * y
            rows.append(row)
        return rows


class OnnxEmbedder:
    """A Hugging Face ONNX export run with onnxruntime on CPU (what a small server would run;
    no torch). `model_dir` holds onnx/<onnx_file> (+ model.onnx_data) and tokenizer.json."""

    def __init__(self, name: str, model_dir: Path, pooling: str, prefix: str, threads: int,
                 onnx_file: str = FP32, max_length: int = 64, batch_size: int = 64):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.name, self.pooling, self.prefix, self.batch_size = name, pooling, prefix, batch_size
        tok = model_dir / "tokenizer.json"
        self.tokenizer = Tokenizer.from_file(str(tok if tok.exists() else model_dir / "onnx" / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length)
        self.tokenizer.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_dir / "onnx" / onnx_file), opts,
                                            providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.outputs = [o.name for o in self.session.get_outputs()]

    def fit(self, docs: Sequence[str]) -> None:
        pass

    def embed(self, texts: Sequence[str]):
        import numpy as np
        out = []
        for start in range(0, len(texts), self.batch_size):
            enc = self.tokenizer.encode_batch([self.prefix + t for t in texts[start:start + self.batch_size]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            if self.pooling == "sentence_embedding":
                vec = self.session.run(["sentence_embedding"], feed)[0]
            else:
                hidden = self.session.run([self.outputs[0]], feed)[0]
                if self.pooling == "cls":
                    vec = hidden[:, 0]
                else:
                    m = mask[..., None].astype(hidden.dtype)
                    vec = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            out.append(vec / np.clip(np.linalg.norm(vec, axis=1, keepdims=True), 1e-12, None))
        return np.concatenate(out) if out else np.zeros((0, 1), dtype=np.float32)

    def similarity(self, queries, docs) -> list[list[float]]:
        return dense_similarity(queries, docs)


# ---- catalogs with their raw alias texts -------------------------------------------------------

class RawBackend:
    """h.Backend whose InMemoryCatalog also keeps the raw (product, alias) and (brand, alias)
    texts the harness passed in, i.e. exactly the aliases kept for the bar."""

    def __init__(self, be):
        self.__dict__.update(be.__dict__)
        base = be.InMemoryCatalog

        class RawCatalog(base):
            def __init__(self, products, aliases, brand_aliases=()):
                products, aliases, brand_aliases = list(products), list(aliases), list(brand_aliases)
                super().__init__(products, aliases, brand_aliases)
                self.products, self.raw_aliases, self.raw_brand_aliases = products, aliases, brand_aliases

        self.InMemoryCatalog = RawCatalog

    def resolve(self, name, catalog):
        return self.resolve_staged(self.ExtractedProduct(product_name=name), catalog, h.STAGES)


def without_paren_strip(seed: dict) -> dict:
    """The seed without aliases whose only source is the paren-strip template (eval_p17)."""
    out = json.loads(json.dumps(seed))
    for p in out["products"]:
        p["aliases"] = [a for a in p["aliases"] if set(a.get("sources", [])) != {PAREN_STRIP}]
    return out


def build_catalogs(be, seed: dict, bars: list[str], variants=CATALOG_VARIANTS) -> dict[str, dict]:
    built = {}
    for variant in variants:
        if variant == "eval_p17":
            built[variant] = {bar: h.build_catalog(be, bar, "service", without_paren_strip(seed)) for bar in bars}
        else:
            built[variant] = {bar: h.build_catalog(be, bar, variant, seed) for bar in bars}
    return built


def doc_entries(catalog, docset: str) -> list[tuple[str, object]]:
    """(text, product id) to embed for one bar catalog (see the module docstring)."""
    out: dict[tuple[str, object], None] = {}
    if docset in ("canonical", "aliases", "brand_age", "all"):
        for p in catalog.products:
            out[(p.display_name, p.product_id)] = None
    if docset in ("aliases", "korean", "all"):
        for pid, text in catalog.raw_aliases:
            if docset != "korean" or HANGUL.search(text):
                out[(text, pid)] = None
    if docset in ("brand_age", "all"):
        brand_texts: dict[object, list[str]] = {}
        for bid, text in catalog.raw_brand_aliases:
            brand_texts.setdefault(bid, []).append(text)
        for p in catalog.products:
            if p.age_years is None and not p.edition_name:
                continue  # the brand name alone would tie every product of the brand
            for b in brand_texts.get(p.brand_id, []):
                age = f"{p.age_years}{'년' if HANGUL.search(b) else ''}" if p.age_years is not None else None
                out[(" ".join(x for x in (b, p.edition_name, age) if x), p.product_id)] = None
    return list(out)


# ---- ranking and the embedding policy --------------------------------------------------------

def rank_products(scores: Sequence[float], entries: list[tuple[str, object]],
                  top_n: int = TOP_N) -> list[tuple[object, float, str]]:
    """(product id, best score, text that gave it), best first; ties by text for stability."""
    best: dict[object, tuple[float, str]] = {}
    for s, (text, pid) in zip(scores, entries):
        if pid not in best or s > best[pid][0]:
            best[pid] = (s, text)
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    return [(pid, s, text) for pid, (s, text) in ranked[:top_n]]


@dataclass(frozen=True)
class Policy:
    """How embedding candidates join a rules result.
      k               at most k embedding candidates on an unmatched line
      floor           no embedding candidate below this similarity (None: always)
      fill_ambiguous  also append to ambiguous lines without confirm recommended, up to fill_k in all
      fill_k          the cap for fill_ambiguous (None: k); 0 adds nothing (with rerank: only reorder)
      rerank          ambiguous lines without confirm recommended: the candidates in embedding order
                      (rule candidates the embedding does not rank keep their order, after the others)
      cr_threshold    confirmRecommended on the rank-1 embedding candidate of an unmatched line when
                      its similarity >= threshold and it leads rank 2 by cr_margin (None: never)"""

    name: str
    k: int = 5
    floor: float | None = None
    fill_ambiguous: bool = False
    fill_k: int | None = None
    rerank: bool = False
    cr_threshold: float | None = None
    cr_margin: float = 0.0


POLICIES = (Policy("unmatched_k5"), Policy("unmatched_k3", k=3), Policy("fill_k5", fill_ambiguous=True),
            Policy("rerank_k5", fill_ambiguous=True, rerank=True),
            Policy("unmatched_k5+rerank_only", fill_ambiguous=True, fill_k=0, rerank=True))


def embedding_candidate(Candidate, pid, rank: int, score: float, text: str, model: str, cr: bool = False):
    ev = {"rule": "embedding", "similarity": round(float(score), 4), "matchedText": text, "model": model}
    if cr:
        ev["confirmRecommended"] = True
    return Candidate(product_id=pid, rank=rank, score=round(float(score), 4), method="embedding", evidence=ev)


def apply_policy(base, ranking: list[tuple[object, float, str]], policy: Policy, model: str, types):
    """Rules result + embedding candidates. Never returns a confirmed status for an unconfirmed
    line and returns a confirmed one unchanged (the invariant behind "Top-1/FM = rules")."""
    if base.status in CONFIRMED:
        return base
    have = {c.product_id for c in base.candidates}
    picks = [(pid, s, t) for pid, s, t in ranking
             if pid not in have and (policy.floor is None or s >= policy.floor)]
    if base.status == "unmatched":
        picks = picks[:policy.k]
        if not picks:
            return base
        cr = (policy.cr_threshold is not None and picks[0][1] >= policy.cr_threshold
              and (len(ranking) < 2 or ranking[0][1] - ranking[1][1] >= policy.cr_margin)
              and ranking[0][0] == picks[0][0])
        cands = tuple(embedding_candidate(types.Candidate, pid, i, s, t, model, cr and i == 1)
                      for i, (pid, s, t) in enumerate(picks, start=1))
        return types.ResolutionResult(status="ambiguous", candidates=cands, proposed_product_id=cands[0].product_id)
    if not policy.fill_ambiguous or any(c.evidence.get("confirmRecommended") for c in base.candidates):
        return base
    room = max(0, (policy.k if policy.fill_k is None else policy.fill_k) - len(base.candidates))
    n = len(base.candidates)
    extra = tuple(embedding_candidate(types.Candidate, pid, n + i, s, t, model)
                  for i, (pid, s, t) in enumerate(picks[:room], start=1))
    if not policy.rerank:
        return replace(base, candidates=base.candidates + extra) if extra else base
    order = {pid: i for i, (pid, _, _) in enumerate(ranking)}
    pool = sorted(base.candidates + extra, key=lambda c: order.get(c.product_id, len(order)))  # stable
    cands = tuple(replace(c, rank=i) for i, c in enumerate(pool, start=1))
    return replace(base, candidates=cands, proposed_product_id=cands[0].product_id)


def check_invariants(rules_rows: list[dict], rows: list[dict], rules_res: dict, res: dict) -> dict:
    """Embedding candidates must not change what is confirmed: line by line and in the totals."""
    new_confirmed = sum(1 for key, r in res.items()
                        if r.status in CONFIRMED and rules_res[key].status not in CONFIRMED)
    changed_confirmed = sum(1 for key, b in rules_res.items() if b.status in CONFIRMED and (
        res[key].status != b.status or res[key].proposed_product_id != b.proposed_product_id
        or res[key].parts != b.parts))
    top1 = lambda rs: sum(r["outcome"] == "correct" for r in rs if r["kind"] == "known")
    fm = lambda rs: sum(r["outcome"] in ("false_merge", "overconfident") for r in rs)
    out = {"new_confirmed_lines": new_confirmed, "changed_confirmed_lines": changed_confirmed,
           "top1_correct": [top1(rules_rows), top1(rows)], "false_merges": [fm(rules_rows), fm(rows)]}
    out["holds"] = (new_confirmed == 0 and changed_confirmed == 0 and out["top1_correct"][0] == out["top1_correct"][1]
                    and out["false_merges"][0] == out["false_merges"][1])
    if not out["holds"]:
        raise AssertionError(f"embedding changed a confirmed result: {out}")
    return out


# ---- recall ---------------------------------------------------------------------------------

def gold_ids_of(be, graw: str, key_to_id: dict) -> tuple[str, set]:
    """(kind, gold product ids) of a line in the bar catalog's terms."""
    g = h.gold_for(be, graw, key_to_id, dev=True)
    if g in ("unknown", "non_whisky"):
        return g, set()
    refs = be.gold_refs(g)
    kind = "known" if all(r in key_to_id for r in refs) else "absent"
    return kind, {key_to_id[r] for r in refs if r in key_to_id}


def recall_at(lists: list[list], golds: list[set], ks=KS) -> dict:
    n = len(golds)
    return {f"@{k}": (sum(bool(set(lst[:k]) & g) for lst, g in zip(lists, golds)) / n if n else None) for k in ks}


def merged(first: list, second: list) -> list:
    return list(dict.fromkeys([*first, *second]))


# ---- one model ------------------------------------------------------------------------------

def rss_mb() -> float | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:  # pragma: no cover - not Linux
        return None
    return None  # pragma: no cover


def peak_rss_mb() -> float | None:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:  # pragma: no cover - not Unix
        return None


def evaluate(embedder: Embedder, be, seed: dict, photos: list, *, variants=CATALOG_VARIANTS,
             docsets=DOCSETS, policies=POLICIES, llm_factory=None, llm_catalogs=LLM_CATALOGS,
             cr_docset: str = "all", latency_docset: str = "all") -> dict:
    """Everything for one embedder. `llm_factory(layer)` returns a MatchingLLM (the E8 cache) or None."""
    rbe = RawBackend(be)
    types = sys.modules[be.ExtractedProduct.__module__]
    bars = list(dict.fromkeys(p.bar for p in photos))
    catalogs = build_catalogs(rbe, seed, bars, variants)

    # rules
    base = {v: {(p.photo_id, n): rbe.resolve(n, catalogs[v][p.bar].catalog) for p in photos for n, _ in p.lines}
            for v in variants}

    def rows_for(v, resolved, targets=None):
        return [h.score_line(be, p, n, g, resolved[(p.photo_id, n)], base[v][(p.photo_id, n)], catalogs[v][p.bar],
                             True, bool(targets and n in targets[p.photo_id])) for p in photos for n, g in p.lines]

    # embed every text once
    entries = {(v, d, bar): doc_entries(catalogs[v][bar].catalog, d) for v in variants for d in docsets for bar in bars}
    doc_texts = list(dict.fromkeys(t for es in entries.values() for t, _ in es))
    queries = list(dict.fromkeys(n for p in photos for n, _ in p.lines))
    t0 = time.perf_counter()
    embedder.fit(doc_texts)
    doc_vecs = embedder.embed(doc_texts)
    t_docs = time.perf_counter() - t0
    t0 = time.perf_counter()
    q_vecs = embedder.embed(queries)
    t_queries = time.perf_counter() - t0
    doc_index = {t: i for i, t in enumerate(doc_texts)}
    q_index = {t: i for i, t in enumerate(queries)}

    def pick(vecs, idx):
        return vecs[idx] if not isinstance(vecs, list) else [vecs[i] for i in idx]

    rankings: dict[tuple[str, str], dict] = {}
    for v in variants:
        for d in docsets:
            out = {}
            for bar in bars:
                es = entries[(v, d, bar)]
                names = [n for p in photos if p.bar == bar for n, _ in p.lines
                         if base[v][(p.photo_id, n)].status not in CONFIRMED]
                names = list(dict.fromkeys(names))
                if not names:
                    continue
                sims = embedder.similarity(pick(q_vecs, [q_index[n] for n in names]),
                                           pick(doc_vecs, [doc_index[t] for t, _ in es]))
                for n, row in zip(names, sims):
                    out[(bar, n)] = rank_products(row, es)
            rankings[(v, d)] = out

    result = {"embedder": embedder.name, "doc_texts": len(doc_texts), "queries": len(queries),
              "embed_seconds": {"catalog_texts": round(t_docs, 3), "line_names": round(t_queries, 3)},
              "index_size": {d: {bar: len(entries[("service" if "service" in variants else variants[0], d, bar)])
                                 for bar in bars} for d in docsets},
              "catalogs": {}}

    for v in variants:
        rules_rows = rows_for(v, base[v])
        vres = {"rules": {**h.summarize(rules_rows, photos)["all"]}, "catalog_digest": h.catalog_digest(catalogs[v]),
                "recall": {}, "policies": {}, "cr_calibration": {}}
        # answer-in-candidates on the known lines rules do not confirm
        lines = []
        for p in photos:
            key_to_id = catalogs[v][p.bar].key_to_id
            for n, graw in p.lines:
                b = base[v][(p.photo_id, n)]
                kind, gold = gold_ids_of(be, graw, key_to_id)
                if b.status not in CONFIRMED:
                    lines.append((p, n, b, kind, gold))
        known = [x for x in lines if x[1] and x[3] == "known"]
        rule_lists = [[c.product_id for c in b.candidates] for _, _, b, _, _ in known]
        golds = [g for *_, g in known]
        vres["recall"]["lines"] = {"not_confirmed": len(lines), "known": len(known),
                                   "known_unmatched": sum(b.status == "unmatched" for _, _, b, _, _ in known)}
        vres["recall"]["rules"] = recall_at(rule_lists, golds)
        for d in docsets:
            emb = [[pid for pid, _, _ in rankings[(v, d)].get((p.bar, n), [])] for p, n, *_ in known]
            unm = [i for i, (_, _, b, _, _) in enumerate(known) if b.status == "unmatched"]
            vres["recall"][d] = {
                "embedding": recall_at(emb, golds),
                "rules_then_embedding": recall_at([merged(r, e) for r, e in zip(rule_lists, emb)], golds),
                "embedding_on_rules_unmatched": recall_at([emb[i] for i in unm], [golds[i] for i in unm]),
            }
        # policies
        for d in docsets:
            for pol in policies:
                res = {(p.photo_id, n): apply_policy(base[v][(p.photo_id, n)], rankings[(v, d)].get((p.bar, n), []),
                                                     pol, embedder.name, types) for p in photos for n, _ in p.lines}
                rows = rows_for(v, res)
                inv = check_invariants(rules_rows, rows, base[v], res)
                s = h.summarize(rows, photos)
                shown = [[c.product_id for c in res[(p.photo_id, n)].candidates] for p, n, *_ in known]
                vres["policies"][f"{d}/{pol.name}"] = {**extra_stats(rows, res), **s["all"],
                                                       "hard_under_5_photo_rate": s["hard_under_5_photo_rate"],
                                                       "recall_shown": recall_at(shown, golds), "invariants": inv}
        # confirm-recommended calibration: rank-1 embedding candidate on the lines rules leave unmatched
        vres["cr_calibration"] = calibrate(
            [(rankings[(v, cr_docset)].get((p.bar, n), []), kind, gold) for p, n, b, kind, gold in lines
             if b.status == "unmatched"]) if cr_docset in docsets else None
        # per line rules leave unmatched: [rank-1 similarity, kind, rank of the gold or None] (floor sweep)
        vres["unmatched_top"] = [
            [round(float(rk[0][1]), 4), kind, next((i for i, (pid, _, _) in enumerate(rk, 1) if pid in gold), None)]
            for p, n, b, kind, gold in lines if b.status == "unmatched"
            for rk in [rankings[(v, cr_docset)].get((p.bar, n), [])] if rk] if cr_docset in docsets else None
        result["catalogs"][v] = vres

    # server LLM layer (M3a, merge, M3b off) with embedding candidates after it / before it
    if llm_factory is not None:
        result["llm"] = run_llm(be, rbe, embedder.name, seed, photos, catalogs, base, rankings, rows_for, types,
                                llm_factory, [v for v in llm_catalogs if v in variants], docsets)

    # latency per menu photo: embed the photo's lines and rank them against the bar index
    if latency_docset in docsets:
        v = "service" if "service" in variants else variants[0]
        mats = {bar: pick(doc_vecs, [doc_index[t] for t, _ in entries[(v, latency_docset, bar)]]) for bar in bars}
        per_photo = []
        embedder.embed([photos[0].lines[0][0]] if photos and photos[0].lines else ["warm up"])
        for p in photos:
            names = [n for n, _ in p.lines]
            if not names:
                continue
            t0 = time.perf_counter()
            sims = embedder.similarity(embedder.embed(names), mats[p.bar])
            for row in sims:
                rank_products(row, entries[(v, latency_docset, p.bar)])
            per_photo.append((time.perf_counter() - t0) * 1000)
        per_photo.sort()
        result["latency_ms_per_photo"] = {
            "photos": len(per_photo), "lines_mean": statistics.mean(len(p.lines) for p in photos if p.lines),
            "mean": round(statistics.mean(per_photo), 2), "p50": round(statistics.median(per_photo), 2),
            "p95": round(per_photo[max(0, -(-95 * len(per_photo) // 100) - 1)], 2), "max": round(per_photo[-1], 2),
            "docset": latency_docset, "catalog": v}
    return result


def extra_stats(rows: list[dict], res: dict) -> dict:
    emb_cr = [r for r in rows if r["confirm_recommended"] and r["rank1_method"] == "embedding"]
    return {"cr_by_rank1_method": dict(Counter(r["rank1_method"] for r in rows if r["confirm_recommended"])),
            "cr_embedding": {"n": len(emb_cr), "correct": sum(r["rank1_gold"] for r in emb_cr)},
            "lines_with_embedding_candidate": sum(any(c.method == "embedding" for c in r.candidates)
                                                  for r in res.values())}


def calibrate(items: list[tuple[list, str, set]]) -> dict:
    """Precision of "rank 1 is gold" against a similarity threshold, over the lines rules leave
    unmatched (absent / unknown lines count as wrong: any confirm recommended there is wrong)."""
    scored = sorted(((r[0][1], (r[0][1] - r[1][1]) if len(r) > 1 else r[0][1], r[0][0] in gold)
                     for r, kind, gold in items if r), key=lambda x: -x[0])
    out = {"lines": len(items), "with_ranking": len(scored), "rank1_gold": sum(x[2] for x in scored), "points": []}
    for target in (0.9, 0.95, 0.98, 1.0):
        best = None
        hits = 0
        for i, (s, _, ok) in enumerate(scored, start=1):
            hits += ok
            if hits / i >= target and (i == len(scored) or scored[i][0] < s):
                best = {"threshold": round(s, 4), "n": i, "correct": hits}
        out["points"].append({"precision_at_least": target, **(best or {"threshold": None, "n": 0, "correct": 0})})
    return out


def run_llm(be, rbe, model_name, seed, photos, catalogs, base, rankings, rows_for, types, llm_factory,
            variants, docsets) -> dict:
    layer = h.load_llm_layer()
    llm = llm_factory(layer)
    pmeta = h.product_meta(layer, seed, None)
    pol = POLICIES[0]
    out = {}
    for v in variants:
        bars = list(dict.fromkeys(p.bar for p in photos))
        targets = {p.photo_id: {n for n, _ in p.lines if base[v][(p.photo_id, n)].status not in CONFIRMED}
                   for p in photos}
        engines = {bar: layer.M3Engine(llm, {p.photo_id: [n for n, _ in p.lines] for p in photos if p.bar == bar},
                                       pmeta, max_calls=h.BAR_CALL_CAP) for bar in bars}
        misses = llm.counts["cache_miss"] if hasattr(llm, "counts") else 0
        for p in photos:
            engines[p.bar].translate(p.photo_id, targets[p.photo_id])
        missed = (llm.counts["cache_miss"] if hasattr(llm, "counts") else 0) - misses
        if missed:
            out[v] = {"skipped": f"{missed} M3a cache misses (no API call is made)"}
            continue

        def m3(p, n, b):
            return b if b.status in CONFIRMED else engines[p.bar].resolve(p.photo_id, n, catalogs[v][p.bar].catalog,
                                                                          b, use_m3b=False)

        l0 = {(p.photo_id, n): m3(p, n, base[v][(p.photo_id, n)]) for p in photos for n, _ in p.lines}
        l0_rows = rows_for(v, l0, targets)
        vout = {"rules+M3a": {**h.summarize(l0_rows, photos)["all"], **extra_stats(l0_rows, l0)}, "docsets": {}}
        known = [(p, n) for p in photos for n, g in p.lines
                 if base[v][(p.photo_id, n)].status not in CONFIRMED
                 and gold_ids_of(be, g, catalogs[v][p.bar].key_to_id)[0] == "known"]
        golds = [gold_ids_of(be, dict(p.lines)[n], catalogs[v][p.bar].key_to_id)[1] for p, n in known]
        l0_lists = [[c.product_id for c in l0[(p.photo_id, n)].candidates] for p, n in known]
        vout["recall_known_not_confirmed"] = {"rules+M3a": recall_at(l0_lists, golds)}
        for d in docsets:
            rk = rankings[(v, d)]
            # after: the LLM layer first, then embedding candidates on the lines still unmatched
            after = {(p.photo_id, n): apply_policy(l0[(p.photo_id, n)], rk.get((p.bar, n), []), pol, model_name, types)
                     for p in photos for n, _ in p.lines}
            # before: rules + embedding is the base the LLM layer merges into (an LLM pick on a line rules
            # left unmatched is then confirm recommended only when it is among the embedding candidates)
            before = {}
            for p in photos:
                for n, _ in p.lines:
                    b = apply_policy(base[v][(p.photo_id, n)], rk.get((p.bar, n), []), pol, model_name, types)
                    before[(p.photo_id, n)] = m3(p, n, b)
            vd = {}
            for label, res in (("M3a_then_embedding", after), ("embedding_then_M3a", before)):
                rows = rows_for(v, res, targets)
                check_invariants(rows_for(v, base[v]), rows, base[v], res)
                vd[label] = {**h.summarize(rows, photos)["all"], **extra_stats(rows, res)}
            emb_lists = [[pid for pid, _, _ in rk.get((p.bar, n), [])] for p, n in known]
            vd["recall_known_not_confirmed"] = {
                "M3a_then_embedding": recall_at([merged(a, e) for a, e in zip(l0_lists, emb_lists)], golds),
                "embedding_then_M3a": recall_at(
                    [[c.product_id for c in before[(p.photo_id, n)].candidates] for p, n in known], golds)}
            vout["docsets"][d] = vd
        out[v] = vout
    return out


# ---- CLI ------------------------------------------------------------------------------------

def make_embedder(name: str, models_root: Path | None, threads: int) -> Embedder:
    if name == "tfidf":
        return CharTfidf()
    repo, _, pooling, prefix, onnx_file = MODELS[name]
    if models_root is None:
        raise SystemExit(f"--models-root is needed for {name} (a folder per model: {repo.replace('/', '--')})")
    return OnnxEmbedder(name, models_root / repo.replace("/", "--"), pooling, prefix, threads, onnx_file)


def cached_llm_factory(cache_dir: Path):
    def factory(layer):
        from app.adapters.matching_llm import MODEL, THINKING_LEVEL
        kinds = {h.sha256_bytes(layer.load_prompt(layer.TRANSLATE_PROMPT).encode("utf-8")): "m3a"}
        return h.CachedMatchingLLM(None, cache_dir, [E8_CACHE], model=MODEL, thinking=THINKING_LEVEL, kinds=kinds,
                                   cache_only=True, max_calls=0, min_interval=0.0)
    return factory


def model_info(name: str, models_root: Path | None) -> dict:
    if name == "tfidf":
        return {"model": "char n-gram TF-IDF (n=1..3), fitted on the catalog texts", "files_mb": 0}
    repo, rev, pooling, prefix, onnx_file = MODELS[name]
    d = models_root / repo.replace("/", "--") / "onnx"
    files = [d / onnx_file, d / f"{onnx_file}_data"]
    size = sum(f.stat().st_size for f in files if f.is_file()) / 2**20
    return {"model": repo, "revision": rev, "pooling": pooling, "prefix": prefix,
            "onnx_file": f"onnx/{onnx_file}", "files_mb": round(size, 1)}


def cmd_run(args) -> dict:
    be = h.Backend(REPO_ROOT)
    seed = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    photos, _ = h.dev_photos()  # the 5 dev bars; refuses any I3 file
    rss0 = rss_mb()
    t0 = time.perf_counter()
    embedder = make_embedder(args.model, args.models_root, args.threads)
    load_s = time.perf_counter() - t0
    rss1 = rss_mb()
    with tempfile.TemporaryDirectory() as cache:  # the harness copies seed-cache hits here; thrown away
        result = evaluate(embedder, be, seed, photos,
                          llm_factory=None if args.no_llm else cached_llm_factory(Path(cache)))
    rss2 = rss_mb()
    result.update({
        "harness": "ai/eval/p24_embedding_compare.py", "set": "dev", "input": "label",
        "info": model_info(args.model, args.models_root), "threads": args.threads,
        "catalog_file": CATALOG_FILE.name, "catalog_file_sha256": h.sha256_file(CATALOG_FILE),
        "gold_sha256": {g: h.sha256_file(REPO_ROOT / g) for g in sorted(set(h.DEV_GOLD.values()))},
        "labels_sha256": {g: h.sha256_file(REPO_ROOT / g) for g in sorted(set(h.DEV_LABELS.values()))},
        "repo_head": h.git_head(REPO_ROOT), "photos": len(photos), "lines": sum(len(p.lines) for p in photos),
        "load_seconds": round(load_s, 3),
        "memory_mb": {"rss_before_model": rss0, "model_load_delta": round(rss1 - rss0, 1) if rss0 else None,
                      "rss_after_run": rss2, "peak_rss": peak_rss_mb()},
    })
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"model_{args.model}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"{args.model}: wrote {path}")
    return result


def cmd_summary(args) -> dict:
    runs = {json.loads(p.read_text(encoding="utf-8"))["embedder"]: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(args.out.glob("model_*.json"))}
    if not runs:
        raise SystemExit(f"no model_*.json in {args.out}")
    first = next(iter(runs.values()))
    summary = {"models": {}, "rules": {v: first["catalogs"][v]["rules"] for v in first["catalogs"]},
               "catalog_file_sha256": first["catalog_file_sha256"], "gold_sha256": first["gold_sha256"]}
    for name, r in runs.items():
        summary["models"][name] = {
            "info": r["info"], "memory_mb": r["memory_mb"], "latency_ms_per_photo": r.get("latency_ms_per_photo"),
            "embed_seconds": r["embed_seconds"], "doc_texts": r["doc_texts"],
            "recall": {v: c["recall"] for v, c in r["catalogs"].items()},
            "policies": {v: {k: {x: p[x] for x in ("top1", "fm", "wrong_cr", "totals", "hard_per_photo",
                                                    "known_register", "absent_wrong", "cr_embedding", "recall_shown",
                                                    "invariants")}
                             for k, p in c["policies"].items()} for v, c in r["catalogs"].items()},
            "cr_calibration": {v: c["cr_calibration"] for v, c in r["catalogs"].items()},
            "floor_sweep": {v: floor_sweep(c.get("unmatched_top")) for v, c in r["catalogs"].items()},
            "llm": r.get("llm"),
        }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n",
                                           encoding="utf-8")
    print_tables(summary)
    return summary


def floor_sweep(top: list | None, k: int = 5, keep=(1.0, 0.95, 0.9, 0.8)) -> list[dict] | None:
    """Similarity floors for the lines rules leave unmatched: the floor that still gives candidates to
    `keep` of the known lines whose gold is in the top k, and what else gets candidates at that floor."""
    if top is None:
        return None
    useful = sorted((s for s, kind, rank in top if kind == "known" and rank is not None and rank <= k), reverse=True)
    out = []
    for share in keep:
        floor = useful[max(0, math.ceil(share * len(useful)) - 1)] if useful else None
        kept = [(kind, rank) for s, kind, rank in top if floor is None or s >= floor]
        out.append({"keep_useful": share, "floor": floor, "useful_kept": sum(
            kind == "known" and rank is not None and rank <= k for kind, rank in kept), "useful": len(useful),
            "known_gold_not_in_top_k_kept": sum(kind == "known" and (rank is None or rank > k) for kind, rank in kept),
            "absent_or_unknown_kept": sum(kind != "known" for kind, _ in kept),
            "absent_or_unknown": sum(kind != "known" for _, kind, _ in top)})
    return out


def fmt(x, d=3) -> str:
    return "-" if x is None else f"{x:.{d}f}"


def print_tables(s: dict) -> None:
    print("| catalog | Top-1 | FM | wrong CR | confirm / choose / register / wrong | hard/photo |")
    print("|---|---|---|---|---|---|")
    for v, r in s["rules"].items():
        t = r["totals"]
        print(f"| {v} | {fmt(r['top1'])} ({r['correct']}/{r['known']}) | {r['fm']} | {r['wrong_cr']} | "
              f"{t['confirm']} / {t['choose']} / {t['register']} / {t['wrong']} | {fmt(r['hard_per_photo'], 2)} |")
    for v in ("eval", "service", "eval_dropprod"):
        print(f"\nrecall, known lines rules do not confirm ({v}): rules / embedding / rules then embedding")
        print("| model | doc set | rules @1/3/5/10 | emb @1/3/5/10 | rules+emb @1/3/5/10 | emb on unmatched @1/5/10 |")
        print("|---|---|---|---|---|---|")
        for name, m in s["models"].items():
            rec = m["recall"].get(v)
            if not rec:
                continue
            for d in DOCSETS:
                if d not in rec:
                    continue
                f = lambda x, ks=KS: "/".join(fmt(x[f"@{k}"], 2) for k in ks)
                print(f"| {name} | {d} | {f(rec['rules'])} | {f(rec[d]['embedding'])} | "
                      f"{f(rec[d]['rules_then_embedding'])} | {f(rec[d]['embedding_on_rules_unmatched'], (1, 5, 10))} |")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="evaluate one embedder on the dev bars")
    run.add_argument("--model", required=True, choices=("tfidf", *MODELS))
    run.add_argument("--models-root", type=Path, help="folder with one <owner>--<name> ONNX snapshot per model")
    run.add_argument("--threads", type=int, default=2, help="onnxruntime intra-op threads (2 vCPU server)")
    run.add_argument("--no-llm", action="store_true", help="skip the M3a combinations")
    run.add_argument("--out", type=Path, required=True)
    summ = sub.add_parser("summary", help="merge model_*.json into summary.json and print tables")
    summ.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_summary(args)


if __name__ == "__main__":
    main()
