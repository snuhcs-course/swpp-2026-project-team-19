"""i3_match_eval.py on a made-up catalog and gold (never the I3 files), and its LLM cache."""

import json
import sys
import uuid

import i3_match_eval as h
import pytest

BRAND_GF, BRAND_SV = str(uuid.uuid4()), str(uuid.uuid4())
P12, P18, PSV = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def alias(text, *sources):
    return {"alias_text": text, "sources": list(sources)}


SEED = {
    "version": "test_catalog",
    "brands": [
        {"id": BRAND_GF, "key": "glenfiddich", "canonical_name": "Glenfiddich",
         "aliases": [alias("Glenfiddich", "standard"), alias("글렌피딕", "menu:바A")]},
        {"id": BRAND_SV, "key": "signatory", "canonical_name": "Signatory Vintage",
         "aliases": [alias("Signatory Vintage", "standard"), alias("시그나토리", "menu:바A")]},
    ],
    "products": [
        {"id": P12, "key": "glenfiddich-12", "brand_id": BRAND_GF, "display_name": "Glenfiddich 12",
         "age_years": 12, "edition_name": None,
         "aliases": [alias("Glenfiddich 12", "standard"), alias("글렌피딕 12년", "menu:바A"),
                     alias("그렌피딕 12", "generated:p17")]},
        {"id": P18, "key": "glenfiddich-18", "brand_id": BRAND_GF, "display_name": "Glenfiddich 18",
         "age_years": 18, "edition_name": None, "sources": ["menu:바B"],
         "aliases": [alias("Glenfiddich 18", "menu:바B")]},
        {"id": PSV, "key": "signatory-macduff-13", "brand_id": BRAND_SV,
         "display_name": "Signatory Vintage Macduff 13", "age_years": 13, "edition_name": None,
         "aliases": [alias("Signatory Vintage Macduff 13", "standard")]},
    ],
}
NEW_PRODUCTS = {
    "hart-brothers-glenfarclas-12": {"display_name": "Hart Brothers Glenfarclas 12", "brand": "hart-brothers",
                                     "brand_name": "Hart Brothers", "age_years": 12, "edition_name": None},
    "glenfiddich-15": {"display_name": "Glenfiddich 15", "brand": "glenfiddich", "brand_name": "Glenfiddich",
                       "age_years": 15, "edition_name": None},
}


def item(name, gold, unit="glass"):
    return {"raw_name": name, "unit": unit, "pour_ml": None, "gold": gold}


GOLD = {
    "version": "test_gold", "new_products": NEW_PRODUCTS,
    "photos": [
        {"photo_id": "t_01", "bar": "바B", "split": "test", "items": [
            item("글렌피딕 12년", "glenfiddich-12"), item("글렌피딕 12년", "glenfiddich-12", "bottle"),
            item("Glenfiddich 15", "new:glenfiddich-15"),
            item("Hart Brothers Glenfarclas 12", "new:hart-brothers-glenfarclas-12"),
            item("하우스 위스키", "unknown"), item("헤네시 VSOP", "non_whisky")]},
        {"photo_id": "t_02", "bar": "바C", "split": "test", "items": [
            item("Signatory Vintage Macduff 13", "signatory-macduff-13"), item("Glenfiddich 18", "glenfiddich-18")]},
    ],
}


@pytest.fixture(scope="module")
def be():
    return h.Backend(h.REPO_ROOT)


@pytest.fixture
def files(tmp_path):
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"photos": [
        {"photo_id": p["photo_id"], "items": [{"raw_name": i["raw_name"], "unit": i["unit"], "price_krw": 10000}
                                              for i in p["items"]]} for p in GOLD["photos"]]},
        ensure_ascii=False), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(SEED, ensure_ascii=False), encoding="utf-8")
    return gold, labels, catalog


def run(files, tmp_path, catalog):
    gold, labels, cat = files
    return h.main(["--set", "i3", "--catalog", catalog, "--catalog-file", str(cat), "--gold", str(gold),
                   "--labels", str(labels), "--no-gold-sha-check", "--json", str(tmp_path / f"{catalog}.json")])


# ---------- catalogs ----------

def test_full_adds_gold_new_products_with_their_english_name_only(be):
    full = h.build_catalog(be, "바B", "full", SEED, NEW_PRODUCTS)
    asis = h.build_catalog(be, "바B", "asis", SEED)
    new_id = full.key_to_id["new:hart-brothers-glenfarclas-12"]
    assert full.catalog.get_normalized_aliases(new_id) == [be.normalize("Hart Brothers Glenfarclas 12")]
    assert "new:hart-brothers-glenfarclas-12" not in asis.key_to_id
    # a new brand gets its English name; an existing brand key is reused
    assert full.catalog.find_brand_ids_by_alias(be.normalize("Hart Brothers"))
    assert full.catalog.get_product(full.key_to_id["new:glenfiddich-15"]).brand_id == uuid.UUID(BRAND_GF)
    assert full.digest != asis.digest


def test_own_bar_menu_aliases_are_dropped_and_generated_aliases_kept_outside_dev_eval(be):
    at_a = h.build_catalog(be, "바A", "asis", SEED)
    at_b = h.build_catalog(be, "바B", "asis", SEED)
    pid = uuid.UUID(P12)
    assert be.normalize("글렌피딕 12년") not in at_a.catalog.get_normalized_aliases(pid)
    assert be.normalize("글렌피딕 12년") in at_b.catalog.get_normalized_aliases(pid)
    assert be.normalize("그렌피딕 12") in at_b.catalog.get_normalized_aliases(pid)
    dev_eval = h.build_catalog(be, "바B", "eval", SEED)
    assert be.normalize("그렌피딕 12") not in dev_eval.catalog.get_normalized_aliases(pid)


def test_eval_dropprod_drops_the_products_only_that_bar_has(be):
    assert "glenfiddich-18" not in h.build_catalog(be, "바B", "eval_dropprod", SEED).key_to_id
    assert "glenfiddich-18" in h.build_catalog(be, "바C", "eval_dropprod", SEED).key_to_id


def test_gold_for_writes_refs_the_catalog_lacks_as_new(be):
    full = h.build_catalog(be, "바B", "full", SEED, NEW_PRODUCTS)
    asis = h.build_catalog(be, "바B", "asis", SEED)
    assert h.gold_for(be, "new:glenfiddich-15", full.key_to_id, dev=False) == "new:glenfiddich-15"
    assert h.gold_for(be, "both:glenfiddich-12|new:glenfiddich-15", asis.key_to_id, dev=False) == \
        "both:glenfiddich-12|new:glenfiddich-15"
    # no dev exception for the flavoured whiskey since 2026-11-21: a product ref like any other
    assert h.gold_for(be, "jack-daniels-apple", asis.key_to_id, dev=True) == "new:jack-daniels-apple"
    assert h.gold_for(be, "unknown", asis.key_to_id, dev=False) == "unknown"


# ---------- whole runs on the made-up gold ----------

def test_full_and_asis_runs(files, tmp_path):
    full = run(files, tmp_path, "full")
    asis = run(files, tmp_path, "asis")
    assert full["lines"] == asis["lines"] == 7  # glass/bottle rows of one line count once
    assert full["coverage"] == {"product_lines": 5, "covered": 5, "rate": 1.0}
    assert asis["coverage"]["covered"] == 3
    assert full["new_products_added"] == 2 and asis["new_products_added"] == 0
    rows = {r["name"]: r for r in full["rules"]["rows"]}
    assert rows["글렌피딕 12년"]["outcome"] == "correct"
    assert rows["Glenfiddich 15"]["outcome"] == "correct"  # its English name is in the full catalog
    assert rows["헤네시 VSOP"]["kind"] == "non_whisky"
    a_rows = {r["name"]: r for r in asis["rules"]["rows"]}
    assert a_rows["Glenfiddich 15"]["kind"] == "absent"
    assert a_rows["Glenfiddich 15"]["outcome"] in ("unmatched", "ambiguous_bad")
    assert full["rules"]["all"]["fm"] == asis["rules"]["all"]["fm"] == 0
    assert set(full["rules"]["by_bar"]) == {"바B", "바C"}


def test_gold_hash_is_checked(files, tmp_path):
    gold, labels, cat = files
    with pytest.raises(SystemExit, match="SHA-256"):
        h.main(["--set", "i3", "--catalog", "asis", "--catalog-file", str(cat), "--gold", str(gold),
                "--labels", str(labels), "--json", str(tmp_path / "x.json")])


def test_gold_names_must_be_the_label_names(files, tmp_path):
    _, labels, _ = files
    data = json.loads(labels.read_text(encoding="utf-8"))
    data["photos"][0]["items"][0]["raw_name"] = "다른 이름"
    labels.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="gold names differ"):
        run(files, tmp_path, "asis")


def test_dev_set_refuses_i3_files():
    with pytest.raises(SystemExit, match="I3 file"):
        h.read_repo_json("eval/labels_i3_v1.json", allow_i3=False)


@pytest.mark.parametrize("argv, message", [
    (["--set", "dev", "--catalog", "full"], "--catalog for --set dev"),
    (["--set", "i3", "--catalog", "asis", "--llm"], "--llm needs --cache"),
    (["--set", "i3", "--catalog", "asis", "--run", "1"], "go together"),
])
def test_bad_arguments(argv, message, capsys):
    with pytest.raises(SystemExit):
        h.parse_args([*argv, "--json", "x.json"])
    assert message in capsys.readouterr().err


# ---------- LLM cache ----------

class FakeInner:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def generate_json(self, prompt, payload, schema):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def cached(tmp_path, inner, seed_dirs=(), **kw):
    options = {"model": "m", "thinking": "low", "kinds": {}, "cache_only": False, "max_calls": 10,
               "min_interval": 0.0}
    options.update(kw)
    return h.CachedMatchingLLM(inner, tmp_path / "cache", list(seed_dirs), **options)


def test_cache_key_is_the_m3_experiment_key(tmp_path):
    sys.path.insert(0, str(h.REPO_ROOT / "ai" / "match_llm"))
    from llm import MODEL, THINKING_LEVEL, sha256_text  # the M3 experiment's cache (ai/match_llm/llm.py)
    payload = {"lines": [{"line": 1, "name": "글렌피딕 12년", "target": True}]}
    llm = cached(tmp_path, FakeInner([]), model=MODEL, thinking=THINKING_LEVEL)
    input_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    expected = sha256_text(json.dumps([MODEL, THINKING_LEVEL, sha256_text("prompt"), input_json], ensure_ascii=False))
    assert llm.key("prompt", payload) == expected


def test_a_response_is_cached_and_reused(tmp_path):
    inner = FakeInner(['{"items": []}'])
    llm = cached(tmp_path, inner)
    assert llm.generate_json("p", {"a": 1}, {}) == '{"items": []}'
    assert llm.generate_json("p", {"a": 1}, {}) == '{"items": []}'
    assert inner.calls == 1 and llm.counts["fresh"] == 1 and llm.counts["cache_hit"] == 1
    record = json.loads(next((tmp_path / "cache").glob("*.json")).read_text(encoding="utf-8"))
    assert record["output_text"] == '{"items": []}' and record["meta"]["attempts"] == 1


def test_seed_cache_hit_is_copied_and_cache_only_miss_raises(tmp_path):
    seed = tmp_path / "seed"
    writer = cached(tmp_path, FakeInner(['{"x": 1}']))
    writer.cache_dir = seed
    writer.generate_json("p", {"a": 1}, {})
    reader = cached(tmp_path, FakeInner([]), seed_dirs=[seed], cache_only=True)
    assert reader.generate_json("p", {"a": 1}, {}) == '{"x": 1}'
    assert reader.counts["seed_hit"] == 1
    with pytest.raises(h.CacheMiss):
        reader.generate_json("p", {"a": 2}, {})
    assert reader.counts["cache_miss"] == 1


def test_api_errors_are_retried_then_raised(tmp_path):
    inner = FakeInner([RuntimeError("503"), '{"ok": true}'])
    assert cached(tmp_path, inner).generate_json("p", {}, {}) == '{"ok": true}'
    failing = FakeInner([RuntimeError("503")] * 4)
    llm = cached(tmp_path, failing)
    with pytest.raises(RuntimeError):
        llm.generate_json("p", {"b": 1}, {})
    assert failing.calls == 4 and llm.counts["no_answer"] == 1 and llm.stopped is None


def test_quota_error_and_call_cap_stop_the_run(tmp_path):
    llm = cached(tmp_path, FakeInner([RuntimeError("429 RESOURCE_EXHAUSTED")]))
    with pytest.raises(h.StopRun):
        llm.generate_json("p", {}, {})
    assert llm.stopped.startswith("quota")
    with pytest.raises(h.StopRun):  # nothing more is sent once stopped
        llm.generate_json("p", {"c": 1}, {})
    capped = cached(tmp_path, FakeInner(['{}']), max_calls=0)
    with pytest.raises(h.StopRun):
        capped.generate_json("p", {"d": 1}, {})
    assert capped.stopped == "call cap 0 reached" and capped.api_calls == 0


# ---------- end-to-end input ----------

def test_end_to_end_lines_are_paired_to_the_labels(files, tmp_path, monkeypatch):
    import e2e_match
    extracted = {
        "t_01": [{"raw_name": "글렌피딕 12년", "unit": "glass", "price_krw": 10000},  # paired
                 {"raw_name": "Glenfiddich 15", "unit": "glass", "price_krw": 10000},  # paired
                 {"raw_name": "코카콜라", "unit": "glass", "price_krw": 3000}],  # unpaired
        "t_02": [],  # both gold lines missed
    }
    monkeypatch.setattr(e2e_match, "load_run", lambda run_dir, run, label_set: extracted)
    gold, labels, cat = files
    out = h.main(["--set", "i3", "--catalog", "full", "--catalog-file", str(cat), "--gold", str(gold),
                  "--labels", str(labels), "--no-gold-sha-check", "--extraction", str(tmp_path), "--run", "1",
                  "--json", str(tmp_path / "e2e.json")])
    e2e = out["rules"]["e2e"]
    assert out["input"].endswith("r1")
    assert e2e["unpaired_lines"] == 1
    assert e2e["missed_gold_lines"] == 5  # t_01: Hart Brothers, unknown, non_whisky; t_02: both lines
    assert e2e["missed_known_lines"] == 3  # Hart Brothers (in the full catalog) and both t_02 lines
    a = out["rules"]["all"]
    assert (a["correct"], a["known"]) == (2, 2)
    assert e2e["top1_missed_as_fail"] == 2 / 5


# ---------- I4-P46: bar groups, the ops catalog, the server steps ----------

ADDITIONS = {
    "version": "test_additions", "brands": [],
    "products": [
        {"id": str(uuid.uuid4()), "key": "glenfiddich-15", "brand_id": BRAND_GF, "display_name": "Glenfiddich 15",
         "age_years": 15, "edition_name": None,
         "aliases": [alias("Glenfiddich 15", "standard"), alias("글렌피딕 15", "menu:바B"),
                     alias("글렌피딕 15년산", "generated:test")]},
    ],
}
# The I3 catalogs as P10 recorded them (c2_{asis,full}_rules.json, 2026-10-29): bar groups and the
# ops catalog must leave them as they were.
I3_BARS = ("테일오브테일즈", "연림 서울대입구역점", "연림 봉천역점", "리틀 갤러리", "청춘위스키 봉천", "쏘댓page2", "네스트",
           "무용의 유용")
I3_ASIS_DIGEST = "7c65fa51c4c8370b"


def test_a_group_of_bars_shares_its_own_menu_aliases(be, monkeypatch):
    pid = uuid.UUID(P12)
    assert be.normalize("글렌피딕 12년") in h.build_catalog(be, "바B", "asis", SEED).catalog.get_normalized_aliases(pid)
    monkeypatch.setattr(h, "BAR_GROUPS", (frozenset({"바A", "바B"}),))
    assert h.own_bars("바B") == {"바A", "바B"} and h.own_bars("바C") == {"바C"}
    assert be.normalize("글렌피딕 12년") not in h.build_catalog(be, "바B", "asis", SEED).catalog.get_normalized_aliases(pid)
    assert be.normalize("글렌피딕 12년") in h.build_catalog(be, "바C", "asis", SEED).catalog.get_normalized_aliases(pid)


def test_embedded_entries_keep_one_alias_per_normalized_value_like_the_database(be):
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    entries = h.build_catalog(be, "바C", "asis", seed).entries
    keys = [(pid, be.normalize(text)) for text, pid in entries]
    products = {pid for _, pid in entries}
    names = {p.display_name for p in h.build_catalog(be, "바C", "asis", seed).catalog._products.values()}
    alias_keys = [k for (text, _), k in zip(entries, keys) if text not in names]
    assert len(alias_keys) == len(set(alias_keys)) and products
    ardbeg = [text for text, _ in entries if be.normalize(text) == be.normalize("Ardbeg 10")]
    assert len(ardbeg) <= 2  # the display name and at most one stored alias


V2_4_ASIS_DIGEST = "b82cacac24493d0f"
V2_5_ASIS_DIGEST = "541fb3d457e8d5da"
V2_6_ASIS_DIGEST = "7f96c66ad6e70e19"
V2_7_ASIS_DIGEST = "1a4e2469c48baa82"


def test_the_i3_asis_catalogs_are_the_recorded_ones(be):
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    digest = h.catalog_digest({bar: h.build_catalog(be, bar, "asis", seed) for bar in I3_BARS})
    # catalog v2.4 (2026-11-21, I5: Jack Daniel's Tennessee Apple added) no longer gives the asis
    # catalogs I3 and P46 ran with (I3_ASIS_DIGEST, catalog v2.3): numbers from here on are not theirs.
    # v2.5 (2026-11-27, I5-P59: Glenmorangie ages) is not v2.4 either (V2_4_ASIS_DIGEST, 11/21 runs),
    # nor is v2.6 (Lasanta 12 -> 15) v2.5 (V2_5_ASIS_DIGEST, the 11/27 night runs), nor v2.7 (The Nectar) v2.6
    assert not digest.startswith(I3_ASIS_DIGEST)
    assert not digest.startswith(V2_4_ASIS_DIGEST)
    assert not digest.startswith(V2_5_ASIS_DIGEST)
    assert not digest.startswith(V2_6_ASIS_DIGEST)
    assert digest.startswith(V2_7_ASIS_DIGEST)


def test_ops_is_the_catalog_with_the_additions_minus_own_menu_aliases(files, tmp_path):
    gold, labels, cat = files
    additions = tmp_path / "additions.json"
    additions.write_text(json.dumps(ADDITIONS, ensure_ascii=False), encoding="utf-8")
    result = h.main(["--set", "i3", "--catalog", "ops", "--catalog-file", str(cat), "--additions-file", str(additions),
                     "--gold", str(gold), "--labels", str(labels), "--no-gold-sha-check",
                     "--json", str(tmp_path / "ops.json")])
    assert result["new_products_added"] == 0 and result["additions_file_sha256"]
    assert result["coverage"]["covered"] == 4  # glenfiddich-15 is now a catalog product
    rows = {r["name"]: r for r in result["rules"]["rows"]}
    assert rows["Glenfiddich 15"]["kind"] == "known" and rows["Glenfiddich 15"]["outcome"] == "correct"
    merged = h.with_additions(SEED, ADDITIONS)
    at_b = h.build_catalog(h.Backend(h.REPO_ROOT), "바B", "ops", merged)
    aliases = at_b.catalog.get_normalized_aliases(at_b.key_to_id["glenfiddich-15"])
    assert h.Backend(h.REPO_ROOT).normalize("글렌피딕 15") not in aliases  # 바B's own menu spelling
    assert h.Backend(h.REPO_ROOT).normalize("글렌피딕 15년산") in aliases
    with pytest.raises(SystemExit, match="both the catalog and the additions"):
        h.with_additions(merged, ADDITIONS)


def test_server_steps_add_candidates_and_never_confirm(files, tmp_path):
    gold, labels, cat = files
    result = h.main(["--set", "i3", "--catalog", "asis", "--catalog-file", str(cat), "--gold", str(gold),
                     "--labels", str(labels), "--no-gold-sha-check", "--server-steps",
                     "--json", str(tmp_path / "server.json")])
    rules = {r["name"]: r for r in result["rules"]["rows"]}
    server = {r["name"]: r for r in result["server"]["rows"]}
    assert result["server"]["after"] == "rules" and result["server"]["embedding_model"] == "tfidf-char"
    # "Glenfiddich 15" is not in the catalog: the rules offer nothing, the embedding step offers its siblings
    assert rules["Glenfiddich 15"]["status"] == "unmatched" and server["Glenfiddich 15"]["status"] == "ambiguous"
    assert server["Glenfiddich 15"]["rank1_method"] == "embedding"
    assert result["server"]["changed"]["embedding_filled"] >= 1
    for name, row in rules.items():  # the steps never add or change a confirmation
        if row["status"] in h.CONFIRMED:
            assert server[name]["status"] == row["status"] and server[name]["cands"] == row["cands"]
        else:
            assert server[name]["status"] not in h.CONFIRMED
    assert result["server"]["all"]["correct"] == result["rules"]["all"]["correct"]
    assert result["server"]["all"]["fm"] == result["rules"]["all"]["fm"]


def test_server_steps_are_not_for_the_tool_layer(capsys):
    with pytest.raises(SystemExit):
        h.parse_args(["--set", "i3", "--catalog", "asis", "--llm", "--llm-mode", "tools", "--cache", "c",
                      "--server-steps", "--json", "x.json"])
    assert "--server-steps is for rules or rules + M3a" in capsys.readouterr().err


# ---------- the "not a whisky" note (I5) ----------

def nw_row(kind, llm_kind, base_n=0, n=0, hint=None, target=True, burden="register"):
    return {"photo_id": "p", "name": f"{kind}-{llm_kind}-{base_n}-{n}", "gold": kind, "kind": kind,
            "llm_target": target, "llm_kind": llm_kind, "base_n_cand": base_n, "n_cand": n, "kind_hint": hint,
            "status": "unmatched" if n == 0 else "ambiguous", "burden": burden, "cands": ""}


def test_not_whisky_stats_count_the_note_and_the_three_variants_by_gold_class():
    rows = [
        nw_row("non_whisky", "non_whisky", hint="non_whisky"),               # cognac: flagged
        nw_row("non_whisky", "non_whisky", n=1, hint="non_whisky", burden="wrong"),  # embedding added a candidate
        nw_row("non_whisky", "whisky"),                                      # the LLM missed it
        nw_row("known", "non_whisky", base_n=1, n=1, burden="confirm"),      # a whisky the rules had a candidate for
        nw_row("absent", "non_whisky", hint="non_whisky"),                   # a whisky flagged by mistake
        nw_row("unknown", "unclear"),
        nw_row("known", None, target=False, n=1, burden="confirmed"),        # confirmed by the rules: never asked
    ]
    s = h.not_whisky_stats(rows)
    assert s["llm_targets"] == {"non_whisky": 3, "whisky": 2, "unknown": 1, "unpaired": 0}
    assert s["flagged"] == {"non_whisky": 2, "whisky": 1, "unknown": 0, "unpaired": 0}
    assert s["variant_A"] == {"non_whisky": 2, "whisky": 2, "unknown": 0, "unpaired": 0}
    assert s["variant_B"] == {"non_whisky": 2, "whisky": 1, "unknown": 0, "unpaired": 0}
    assert s["variant_C"] == {"non_whisky": 1, "whisky": 1, "unknown": 0, "unpaired": 0}
    assert s["flagged_by_burden"] == {"register": 2, "wrong": 1}
    assert (s["no_candidate"], s["no_candidate_not_flagged"]) == (4, 2)
    assert [x["name"] for x in s["said_not_flagged_lines"]] == ["known-non_whisky-1-1"]
    assert [x["llm_kind"] for x in s["non_whisky_gold_not_said"]] == ["whisky"]
