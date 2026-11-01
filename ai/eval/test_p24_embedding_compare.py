"""p24_embedding_compare.py on a made-up catalog and made-up photos with a fake embedder (no model,
no numpy, no dev or I3 file, no network)."""

import json
import re
import uuid

import i3_match_eval as h
import p24_embedding_compare as p24
import pytest

BRAND_GF, BRAND_MC = str(uuid.uuid4()), str(uuid.uuid4())
P12, P18, PMC = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def alias(text, *sources):
    return {"alias_text": text, "sources": list(sources)}


SEED = {
    "version": "test_catalog",
    "brands": [
        {"id": BRAND_GF, "key": "glenfiddich", "canonical_name": "Glenfiddich",
         "aliases": [alias("Glenfiddich", "standard"), alias("글렌피딕", "menu:바B")]},
        {"id": BRAND_MC, "key": "macallan", "canonical_name": "The Macallan",
         "aliases": [alias("Macallan", "standard"), alias("맥캘란", "standard")]},
    ],
    "products": [
        {"id": P12, "key": "glenfiddich-12", "brand_id": BRAND_GF, "display_name": "Glenfiddich 12",
         "age_years": 12, "edition_name": None,
         "aliases": [alias("Glenfiddich 12", "standard"), alias("글렌피딕 12년", "menu:바A"),
                     alias("그렌피딕 12", "generated:p17"), alias("Glenfiddich 12 (Our Original)", "menu:바B"),
                     alias("Glenfiddich 12", "template:paren-strip")]},
        {"id": P18, "key": "glenfiddich-18", "brand_id": BRAND_GF, "display_name": "Glenfiddich 18",
         "age_years": 18, "edition_name": None, "sources": ["menu:바B"],
         "aliases": [alias("Glenfiddich 18", "menu:바B"), alias("글렌피딕 18년", "generated:p17")]},
        {"id": PMC, "key": "macallan-12-double-cask", "brand_id": BRAND_MC, "display_name": "Macallan 12 Double Cask",
         "age_years": 12, "edition_name": "Double Cask",
         "aliases": [alias("Macallan 12 Double Cask", "standard"), alias("맥캘란 12 더블캐스크", "generated:p17")]},
    ],
}
PHOTOS = [
    h.Photo("바A", "a_01", [("Glenfiddich 12", "glenfiddich-12"), ("그랜피딕 12", "glenfiddich-12"),
                           ("맥켈란 12년 더블 캐스크", "macallan-12-double-cask"), ("하우스 위스키", "unknown"),
                           ("헤네시 VSOP", "non_whisky")]),
    h.Photo("바B", "b_01", [("글렌피딕 18", "glenfiddich-18"), ("맥캘란 12 더블캐스크", "macallan-12-double-cask")]),
]


class FakeEmbedder:
    """Unit vectors of character counts over a fixed alphabet: close spellings are close."""

    name = "fake"
    ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789글렌피딕그랜맥캘켈란더블캐스크년하우헤네시"

    def __init__(self):
        self.fitted = None

    def fit(self, docs):
        self.fitted = len(docs)

    def embed(self, texts):
        return [p24.unit([float(t.lower().count(ch)) for ch in self.ALPHABET]) for t in texts]

    def similarity(self, queries, docs):
        return p24.dense_similarity(queries, docs)


class FakeLLM:
    """M3a: every target line is Glenfiddich of the age written on the line."""

    def generate_json(self, prompt, payload, schema):
        items = []
        for line in payload["lines"]:
            if line["target"]:
                age = re.search(r"\d+", line["name"])
                items.append({"line": line["line"], "bottler_en": None, "distillery_en": "Glenfiddich",
                              "brand_en": None, "age": int(age.group()) if age else None, "edition_tokens_en": [],
                              "kind": "whisky"})
        return json.dumps({"items": items})


@pytest.fixture(scope="module")
def be():
    return h.Backend(h.REPO_ROOT)


@pytest.fixture(scope="module")
def types(be):
    import sys
    return sys.modules[be.ExtractedProduct.__module__]


def catalogs(be, variants=p24.CATALOG_VARIANTS):
    return p24.build_catalogs(p24.RawBackend(be), SEED, ["바A", "바B"], variants)


# ---------- embedders ----------

def test_tfidf_ranks_the_closest_spelling_first():
    tf = p24.CharTfidf()
    docs = ["글렌피딕 12", "맥캘란 12 더블캐스크", "Glenfiddich 18"]
    tf.fit(docs)
    sims = tf.similarity(tf.embed(["그랜피딕 12년", "macallan"]), tf.embed(docs))
    assert max(range(3), key=lambda j: sims[0][j]) == 0
    assert all(0.0 <= s <= 1.0 + 1e-9 for row in sims for s in row)
    assert tf.embed(["%%%"]) == [{}]  # no known n-gram: an empty vector, similarity 0


class RecordingTfidf(p24.CharTfidf):
    def __init__(self, calls=None):
        super().__init__()
        self.calls = [] if calls is None else calls

    def fitted(self, docs):
        self.calls.append(list(docs))
        return super().fitted(docs)


def test_tfidf_is_fitted_per_bar_index_so_a_bars_own_spellings_never_weigh_in(be):
    tf = RecordingTfidf()
    result = p24.evaluate(tf, be, SEED, PHOTOS)
    catalogs = p24.build_catalogs(p24.RawBackend(be), SEED, ["바A", "바B"])
    expected = {(v, d, bar): [t for t, _ in p24.doc_entries(catalogs[v][bar].catalog, d)]
                for v in p24.CATALOG_VARIANTS for d in p24.DOCSETS for bar in ("바A", "바B")}
    assert sorted(map(tuple, tf.calls)) == sorted(map(tuple, expected.values()))
    # 바A's own menu spelling is an alias only in 바B's catalog: no alias fit for 바A sees it (brand_age
    # builds the same string from brand + age, so that doc set is not the leak this guards against)
    a_fits = [docs for key, docs in expected.items() if key[2] == "바A" and key[1] == "aliases"]
    assert a_fits and all("글렌피딕 12년" not in docs for docs in a_fits)
    assert any("글렌피딕 12년" in docs for key, docs in expected.items() if key[2] == "바B" and key[1] == "aliases")
    assert result["fit"] == "per bar index"
    for c in result["catalogs"].values():
        assert all(pol["invariants"]["holds"] for pol in c["policies"].values())
        assert all(len(row) == 4 for row in c["unmatched_top"])


def test_dense_similarity_handles_empty_inputs():
    assert p24.dense_similarity([], [[1.0]]) == []
    assert p24.dense_similarity([[1.0]], []) == [[]]
    assert p24.dense_similarity([[1.0, 0.0]], [[0.0, 1.0], [1.0, 0.0]]) == [[0.0, 1.0]]
    assert p24.unit([0.0, 0.0]) == [0.0, 0.0]


def test_make_embedder_and_model_info():
    assert isinstance(p24.make_embedder("tfidf", None, 2), p24.CharTfidf)
    with pytest.raises(SystemExit):
        p24.make_embedder("e5-small", None, 2)
    assert p24.model_info("tfidf", None)["files_mb"] == 0


def test_model_info_reads_the_onnx_folder(tmp_path):
    d = tmp_path / "intfloat--multilingual-e5-small" / "onnx"
    d.mkdir(parents=True)
    (d / "model.onnx").write_bytes(b"x" * 2**20)
    (d / "tokenizer.json").write_bytes(b"x" * 2**20)  # not counted
    info = p24.model_info("e5-small", tmp_path)
    assert info["model"] == "intfloat/multilingual-e5-small" and info["files_mb"] == 1.0 and info["revision"]
    assert info["onnx_file"] == "onnx/model.onnx"
    assert p24.model_info("e5-small-int8", tmp_path)["files_mb"] == 0  # its file is not there


# ---------- what is embedded ----------

def test_doc_sets_hold_only_the_aliases_kept_for_the_bar(be):
    built = catalogs(be)
    at_a_eval = built["eval"]["바A"].catalog
    texts = {t for t, _ in p24.doc_entries(at_a_eval, "aliases")}
    assert "글렌피딕 12년" not in texts  # bar A's own menu spelling never leaks into its index
    assert "그렌피딕 12" not in texts  # generated alias: not in the eval catalog
    assert "Glenfiddich 12" in texts and "Macallan 12 Double Cask" in texts
    at_a_service = {t for t, _ in p24.doc_entries(built["service"]["바A"].catalog, "aliases")}
    assert "그렌피딕 12" in at_a_service and "글렌피딕 12년" not in at_a_service
    assert {t for t, _ in p24.doc_entries(at_a_eval, "canonical")} == {
        "Glenfiddich 12", "Glenfiddich 18", "Macallan 12 Double Cask"}
    korean = {t for t, _ in p24.doc_entries(built["service"]["바A"].catalog, "korean")}
    assert korean and all(p24.HANGUL.search(t) for t in korean)
    brand_age = {t for t, _ in p24.doc_entries(built["eval"]["바A"].catalog, "brand_age")}
    # brand aliases kept for bar A (its own "글렌피딕" brand spelling is bar B's, so it is kept here)
    assert {"글렌피딕 12년", "Glenfiddich 12", "Macallan Double Cask 12", "맥캘란 Double Cask 12년"} <= brand_age
    at_b = {t for t, _ in p24.doc_entries(built["eval"]["바B"].catalog, "brand_age")}
    assert "글렌피딕 18년" not in at_b  # bar B's own brand spelling is dropped there
    every = {t for t, _ in p24.doc_entries(built["eval"]["바A"].catalog, "all")}
    assert texts | brand_age == every


def test_eval_p17_is_service_without_paren_strip_only_aliases(be):
    seed = p24.without_paren_strip(SEED)
    texts = [a["sources"] for a in seed["products"][0]["aliases"]]
    assert ["template:paren-strip"] not in texts and len(texts) == 4
    assert len(SEED["products"][0]["aliases"]) == 5  # the input is not changed
    built = catalogs(be, ("eval_p17", "eval_dropprod"))
    assert "glenfiddich-18" not in built["eval_dropprod"]["바B"].key_to_id
    assert "glenfiddich-18" in built["eval_p17"]["바B"].key_to_id


def test_rank_products_keeps_the_best_text_per_product():
    a, b = uuid.uuid4(), uuid.uuid4()
    ranked = p24.rank_products([0.2, 0.9, 0.5], [("x", a), ("y", a), ("z", b)], top_n=5)
    assert ranked == [(a, 0.9, "y"), (b, 0.5, "z")]
    assert p24.rank_products([0.2, 0.9], [("x", a), ("z", b)], top_n=1) == [(b, 0.9, "z")]


# ---------- the policy never confirms ----------

def ranking(*pids):
    return [(pid, 0.9 - 0.1 * i, f"text{i}") for i, pid in enumerate(pids)]


def test_confirmed_results_are_returned_unchanged(types):
    a, b = uuid.uuid4(), uuid.uuid4()
    c = types.Candidate(product_id=a, rank=1, score=1.0, method="alias")
    exact = types.ResolutionResult(status="exact_match", candidates=(c,), proposed_product_id=a)
    for pol in (*p24.POLICIES, p24.Policy("cr", cr_threshold=0.0)):
        assert p24.apply_policy(exact, ranking(b, a), pol, "fake", types) is exact
    multi = types.ResolutionResult(status="multi", parts=(exact, exact))
    assert p24.apply_policy(multi, ranking(b), p24.POLICIES[0], "fake", types) is multi


def test_unmatched_lines_get_embedding_candidates_but_stay_ambiguous(types):
    pids = [uuid.uuid4() for _ in range(6)]
    none = types.ResolutionResult(status="unmatched")
    r = p24.apply_policy(none, ranking(*pids), p24.Policy("k5"), "fake", types)
    assert r.status == "ambiguous" and [c.product_id for c in r.candidates] == pids[:5]
    assert all(c.method == "embedding" and not c.evidence.get("confirmRecommended") for c in r.candidates)
    assert [c.rank for c in r.candidates] == [1, 2, 3, 4, 5] and r.proposed_product_id == pids[0]
    assert r.candidates[0].evidence == {"rule": "embedding", "similarity": 0.9, "matchedText": "text0", "model": "fake"}
    assert len(p24.apply_policy(none, ranking(*pids), p24.Policy("k3", k=3), "fake", types).candidates) == 3
    # below the floor: still unmatched (register)
    assert p24.apply_policy(none, ranking(*pids), p24.Policy("f", floor=0.95), "fake", types) is none
    assert p24.apply_policy(none, [], p24.Policy("k5"), "fake", types) is none


def test_confirm_recommended_hint_needs_threshold_and_margin(types):
    a, b = uuid.uuid4(), uuid.uuid4()
    none = types.ResolutionResult(status="unmatched")
    hint = p24.apply_policy(none, ranking(a, b), p24.Policy("cr", cr_threshold=0.85, cr_margin=0.05), "fake", types)
    assert hint.status == "ambiguous" and hint.candidates[0].evidence["confirmRecommended"] is True
    assert "confirmRecommended" not in hint.candidates[1].evidence
    close = p24.apply_policy(none, ranking(a, b), p24.Policy("cr", cr_threshold=0.85, cr_margin=0.2), "fake", types)
    assert not close.candidates[0].evidence.get("confirmRecommended")
    low = p24.apply_policy(none, ranking(a, b), p24.Policy("cr", cr_threshold=0.95), "fake", types)
    assert not low.candidates[0].evidence.get("confirmRecommended")


def test_fill_appends_after_the_rule_candidates_only_without_confirm_recommended(types):
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rule = types.Candidate(product_id=a, rank=1, score=0.8, method="alias", evidence={"rule": "S2"})
    amb = types.ResolutionResult(status="ambiguous", candidates=(rule,), proposed_product_id=a)
    filled = p24.apply_policy(amb, ranking(a, b, c), p24.Policy("fill", k=2, fill_ambiguous=True), "fake", types)
    assert [x.product_id for x in filled.candidates] == [a, b] and filled.candidates[1].rank == 2
    assert filled.status == "ambiguous" and filled.candidates[0] is rule
    assert p24.apply_policy(amb, ranking(b), p24.Policy("k5"), "fake", types) is amb  # fill off
    full = p24.Policy("fill", k=1, fill_ambiguous=True)
    assert p24.apply_policy(amb, ranking(b), full, "fake", types) is amb  # no room
    assert p24.apply_policy(amb, ranking(a), p24.Policy("fill", fill_ambiguous=True), "fake", types) is amb
    cr = types.ResolutionResult(status="ambiguous", proposed_product_id=a, candidates=(
        types.Candidate(product_id=a, rank=1, score=0.8, method="alias", evidence={"confirmRecommended": True}),))
    assert p24.apply_policy(cr, ranking(b), p24.Policy("fill", fill_ambiguous=True), "fake", types) is cr


def test_check_invariants_raises_when_a_line_becomes_confirmed(types):
    a = uuid.uuid4()
    none = types.ResolutionResult(status="unmatched")
    exact = types.ResolutionResult(status="exact_match", proposed_product_id=a, candidates=(
        types.Candidate(product_id=a, rank=1, score=1.0, method="embedding"),))
    rows = [{"kind": "known", "outcome": "unmatched"}]
    assert p24.check_invariants(rows, rows, {"k": none}, {"k": none})["holds"]
    with pytest.raises(AssertionError):
        p24.check_invariants(rows, [{"kind": "known", "outcome": "correct"}], {"k": none}, {"k": exact})
    with pytest.raises(AssertionError):  # a confirmed rules result that changes
        p24.check_invariants(rows, rows, {"k": exact}, {"k": none})


# ---------- metrics ----------

def test_recall_merged_and_calibration():
    a, b, c = "a", "b", "c"
    assert p24.recall_at([[b, a], [c], []], [{a}, {a}, {a}], ks=(1, 2)) == {"@1": 0.0, "@2": 1 / 3}
    assert p24.recall_at([], [], ks=(1,)) == {"@1": None}
    assert p24.merged([a, b], [b, c]) == [a, b, c]
    items = [([(a, 0.9, ""), (b, 0.5, "")], "known", {a}), ([(b, 0.8, "")], "absent", set()),
             ([(c, 0.7, ""), (a, 0.6, "")], "known", {c}), ([], "known", {a})]
    cal = p24.calibrate(items)
    assert cal["lines"] == 4 and cal["with_ranking"] == 3 and cal["rank1_gold"] == 2
    by = {p["precision_at_least"]: p for p in cal["points"]}
    assert by[1.0] == {"precision_at_least": 1.0, "threshold": 0.9, "n": 1, "correct": 1}
    assert by[0.9]["threshold"] == 0.9


# ---------- whole run on the made-up photos ----------

def test_evaluate_keeps_top1_and_false_merges_of_rules_and_reports_everything(be, tmp_path):
    emb = FakeEmbedder()
    result = p24.evaluate(emb, be, SEED, PHOTOS, llm_factory=lambda layer: FakeLLM())
    assert emb.fitted == result["doc_texts"]
    for v in p24.CATALOG_VARIANTS:
        c = result["catalogs"][v]
        assert set(c["recall"]) == {"lines", "rules", *p24.DOCSETS}
        for name, pol in c["policies"].items():
            assert pol["invariants"]["holds"], name
            assert pol["top1"] == c["rules"]["top1"] and pol["fm"] == c["rules"]["fm"]
    ev = result["catalogs"]["eval"]
    assert ev["rules"]["totals"]["register"] > 0  # some lines rules leave unmatched ...
    assert ev["policies"]["all/unmatched_k5"]["totals"]["register"] == 0  # ... get embedding candidates
    assert result["latency_ms_per_photo"]["photos"] == 2
    assert result["llm"]["eval"]["rules+M3a"]["top1"] == ev["rules"]["top1"]
    for d in p24.DOCSETS:
        for label in ("M3a_then_embedding", "embedding_then_M3a"):
            assert result["llm"]["eval"]["docsets"][d][label]["top1"] == ev["rules"]["top1"]

    # summary over a model file
    out = tmp_path / "runs"
    out.mkdir()
    result.update({"info": p24.model_info("tfidf", None), "memory_mb": {}, "catalog_file_sha256": "x",
                   "gold_sha256": {}})
    (out / "model_fake.json").write_text(json.dumps(result, default=str), encoding="utf-8")
    summary = p24.main(["summary", "--out", str(out)])
    assert summary["models"]["fake"]["policies"]["eval"]["all/unmatched_k5"]["invariants"]["holds"]
    assert (out / "summary.json").exists()
    with pytest.raises(SystemExit):
        p24.main(["summary", "--out", str(tmp_path)])


def test_llm_cache_misses_skip_the_catalog(be):
    class Missing(FakeLLM):
        def __init__(self):
            from collections import Counter
            self.counts = Counter()

        def generate_json(self, prompt, payload, schema):
            self.counts["cache_miss"] += 1
            raise h.CacheMiss("x")

    result = p24.evaluate(FakeEmbedder(), be, SEED, PHOTOS, variants=("eval",), docsets=("aliases",),
                          llm_factory=lambda layer: Missing(), latency_docset="none")
    assert "skipped" in result["llm"]["eval"] and "latency_ms_per_photo" not in result
    assert result["catalogs"]["eval"]["cr_calibration"] is None  # cr_docset "all" not evaluated


def test_cached_llm_factory_reads_only_the_cache(tmp_path):
    layer = h.load_llm_layer()
    llm = p24.cached_llm_factory(tmp_path)(layer)
    assert llm.cache_only and llm.inner is None and llm.seed_dirs == [p24.E8_CACHE]


def test_floor_sweep_keeps_a_line_only_when_its_gold_candidate_reaches_the_floor():
    # [rank-1 similarity, kind, gold rank, gold similarity]
    top = [[0.9, "known", 1, 0.9], [0.8, "known", 3, 0.62], [0.7, "absent", None, None], [0.6, "known", 2, 0.55],
           [0.5, "known", None, None], [0.4, "unknown", None, None]]
    sweep = {p["keep_useful"]: p for p in p24.floor_sweep(top, k=5, keep=(1.0, 0.6))}
    # the lowest gold similarity is 0.55, not the rank-1 0.6 of that line
    assert sweep[1.0] == {"keep_useful": 1.0, "floor": 0.55, "useful_kept": 3, "useful": 3,
                          "known_gold_not_in_top_k_kept": 0, "absent_or_unknown_kept": 1, "absent_or_unknown": 2}
    # floor 0.62: the 0.8 line still gets candidates, and its gold (0.62) survives; the 0.6 line's gold
    # (0.55) does not, although a rank-1 floor test would have said the 0.8 line keeps a useful candidate either way
    assert sweep[0.6]["floor"] == 0.62 and sweep[0.6]["useful_kept"] == 2
    assert sweep[0.6]["absent_or_unknown_kept"] == 1
    # a rank-1 score above the floor is not enough when the gold candidate is below it
    one = p24.floor_sweep([[0.95, "known", 2, 0.5], [0.9, "known", 1, 0.9]], keep=(0.5,))[0]
    assert one["floor"] == 0.9 and one["useful_kept"] == 1
    assert p24.floor_sweep(None) is None
    assert p24.floor_sweep([[0.3, "absent", None, None]])[0]["floor"] is None
    assert p24.floor_sweep([[0.9, "known", 1]]) is None  # a run before the gold similarity was recorded


def test_rerank_orders_an_ambiguous_line_by_embedding_without_confirming(types):
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    rules = tuple(types.Candidate(product_id=x, rank=i, score=0.8, method="alias", evidence={"rule": "S2"})
                  for i, x in enumerate((a, b, d), start=1))
    amb = types.ResolutionResult(status="ambiguous", candidates=rules, proposed_product_id=a)
    r = p24.apply_policy(amb, ranking(c, b, a), p24.Policy("rerank", k=4, fill_ambiguous=True, rerank=True), "f", types)
    assert [x.product_id for x in r.candidates] == [c, b, a, d]  # d: not ranked by the embedding, kept last
    assert [x.rank for x in r.candidates] == [1, 2, 3, 4] and r.proposed_product_id == c and r.status == "ambiguous"
    assert not any(x.evidence.get("confirmRecommended") for x in r.candidates)
    full = p24.apply_policy(amb, ranking(c, b), p24.Policy("rerank", k=3, fill_ambiguous=True, rerank=True), "f", types)
    assert [x.product_id for x in full.candidates] == [b, a, d]  # no room for c: only the rule candidates reordered


def test_rerank_only_reorders_without_adding(types):
    a, b, c = (uuid.uuid4() for _ in range(3))
    rules = tuple(types.Candidate(product_id=x, rank=i, score=0.8, method="alias") for i, x in enumerate((a, b), 1))
    amb = types.ResolutionResult(status="ambiguous", candidates=rules, proposed_product_id=a)
    pol = p24.Policy("ro", fill_ambiguous=True, fill_k=0, rerank=True)
    r = p24.apply_policy(amb, ranking(c, b, a), pol, "f", types)
    assert [x.product_id for x in r.candidates] == [b, a] and r.proposed_product_id == b
    one = types.ResolutionResult(status="ambiguous", candidates=rules[:1], proposed_product_id=a)
    assert [x.product_id for x in p24.apply_policy(one, ranking(c, a), pol, "f", types).candidates] == [a]
    none = types.ResolutionResult(status="unmatched")
    assert len(p24.apply_policy(none, ranking(c, b, a), pol, "f", types).candidates) == 3  # k=5 for unmatched


def test_provenance_records_the_commit_uncommitted_changes_and_harness_hashes():
    prov = p24.provenance()
    assert set(prov) == {"commit", "uncommitted_changes", "checked_paths", "harness_sha256"}
    assert set(prov["harness_sha256"]) == {"ai/eval/p24_embedding_compare.py", "ai/eval/i3_match_eval.py"}
    assert prov["harness_sha256"]["ai/eval/p24_embedding_compare.py"] == h.sha256_file(p24.Path(p24.__file__))


@pytest.mark.parametrize("changes", [[" M ai/eval/p24_embedding_compare.py"], None])
def test_run_refuses_uncommitted_or_unknown_state_unless_allowed(monkeypatch, tmp_path, changes):
    monkeypatch.setattr(p24, "provenance", lambda: {"commit": "abc", "uncommitted_changes": changes})
    monkeypatch.setattr(p24.h, "Backend", lambda repo: (_ for _ in ()).throw(AssertionError("ran")))
    with pytest.raises(SystemExit) as stop:
        p24.main(["run", "--model", "tfidf", "--out", str(tmp_path)])
    assert "ran" not in str(stop.value) and not list(tmp_path.iterdir())
    with pytest.raises(AssertionError, match="ran"):  # --allow-dirty goes on to the run
        p24.main(["run", "--model", "tfidf", "--allow-dirty", "--out", str(tmp_path)])
