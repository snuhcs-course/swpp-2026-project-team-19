"""I5-P59: the catalog ages (1a) and the measurement scripts i5_p59_compare.py, i5_p59_with_age.py."""

import json
import sys
import uuid
from types import SimpleNamespace

import i3_match_eval as h
import i5_p59_compare as cmp
import i5_p59_with_age as wa
import pytest
from test_i3_match_eval import be, files  # noqa: F401 (fixtures)


# ---------- 1a: catalog v2.5, v2.6 ----------

def test_catalog_v2_7_has_the_current_glenmorangie_ages_and_names():
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    ages = {p["key"]: p["age_years"] for p in seed["products"] if p["key"].startswith("glenmorangie")}
    assert seed["version"] == "catalog_v2_7_service"
    # v2.6: Lasanta 12 -> 15 (the bottle changed in 2025)
    assert (ages["glenmorangie-original"], ages["glenmorangie-quinta-ruban"], ages["glenmorangie-lasanta"],
            ages["glenmorangie-nectar-dor"]) == (12, 14, 15, 16)
    assert ages["glenmorangie-18"] == 18 and ages["glenmorangie-signet"] is None  # the others as before
    # v2.7: Nectar D'Or under the current bottle name; the old name stays an alias
    nectar = next(p for p in seed["products"] if p["key"] == "glenmorangie-nectar-dor")
    assert (nectar["display_name"], nectar["edition_name"]) == ("Glenmorangie The Nectar", "The Nectar")
    assert {"Glenmorangie Nectar D'Or", "Glenmorangie The Nectar"} <= {a["alias_text"] for a in nectar["aliases"]}


# ---------- accepted ages in the harness (v2.6) ----------

def test_the_harness_catalog_has_the_accepted_ages_of_the_rules_code(be):  # noqa: F811
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    bc = h.build_catalog(be, "테스트바", "service", seed)
    ages = {key: bc.catalog.get_product(bc.key_to_id[key]).accepted_ages for key in
            ("glenmorangie-original", "glenmorangie-lasanta", "glenmorangie-quinta-ruban", "glenmorangie-nectar-dor")}
    assert ages == {"glenmorangie-original": (10,), "glenmorangie-lasanta": (12,),
                    "glenmorangie-quinta-ruban": (12,), "glenmorangie-nectar-dor": ()}
    r = be.resolve("글렌모렌지 12", bc.catalog)
    assert r.status == "ambiguous"
    assert {c.product_id for c in r.candidates} == {bc.key_to_id[k] for k in (
        "glenmorangie-original", "glenmorangie-lasanta", "glenmorangie-quinta-ruban", "glenmorangie-12-calvados")}
    r = be.resolve("Glenmorangie 15yr", bc.catalog)
    assert [c.product_id for c in r.candidates] == [bc.key_to_id["glenmorangie-lasanta"]]


def test_the_harness_builds_products_without_accepted_ages_for_older_rules_code(be):  # noqa: F811
    older = SimpleNamespace(ProductInfo=lambda *args, **kwargs: (args, kwargs), accepted_ages=None)
    assert h.product_info(older, "pid", "X 12", 12, None, "bid") == (("pid", "X 12", 12, None, "bid"), {})
    bare = SimpleNamespace(ProductInfo=older.ProductInfo)  # no accepted_ages attribute at all
    assert h.product_info(bare, "pid", "X", None, None, None) == (("pid", "X", None, None, None), {})
    assert h.product_info(be, uuid.uuid4(), "X", None, None, None).accepted_ages == ()  # a product not in the table


def test_brand_and_age_now_reach_the_edition_product_of_that_age(be):  # noqa: F811
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    bc = h.build_catalog(be, "테스트바", "service", seed)
    r = be.resolve("Glenmorangie 14", bc.catalog)
    assert r.status == "ambiguous" and [c.product_id for c in r.candidates] == [bc.key_to_id["glenmorangie-quinta-ruban"]]
    assert r.candidates[0].evidence.get("confirmRecommended") is True


# ---------- i5_p59_compare.py ----------

def row(photo, name, status="exact_match", outcome="correct", burden="confirmed", cands="A", cr=False):
    return {"photo_id": photo, "name": name, "gold": "g", "status": status, "outcome": outcome, "burden": burden,
            "cands": cands, "confirm_recommended": cr}


def section(rows):
    return {"all": {"correct": sum(r["outcome"] == "correct" for r in rows), "known": len(rows), "fm": 0,
                    "wrong_cr": 0, "hard_per_photo": 1.0}, "rows": rows}


def test_compare_pairs_repeated_names_by_order_and_lists_lost_and_new_confirmations(tmp_path):
    before = {"rules": section([row("p", "a"), row("p", "a", status="ambiguous", outcome="ambiguous_ok", burden="choose"),
                                row("p", "b", status="unmatched", outcome="unmatched", burden="register", cands="")])}
    after = {"rules": section([row("p", "a", status="ambiguous", outcome="ambiguous_ok", burden="confirm", cr=True),
                               row("p", "a", status="ambiguous", outcome="ambiguous_ok", burden="choose"),
                               row("p", "b")])}
    out = cmp.compare(before, after, ["rules", "server"])
    assert list(out) == ["rules"]  # a section missing from the files is skipped
    r = out["rules"]
    assert [(c["name"], c["before"]["status"]) for c in r["changed"]] == [("a", "exact_match"), ("b", "unmatched")]
    assert [c["name"] for c in r["lost_correct_confirmations"]] == ["a"]
    assert [c["name"] for c in r["new_correct_confirmations"]] == ["b"]
    assert r["before"]["confirm/choose/register/wrong"] == "0/1/1/0" and r["after"]["confirmed"] == 1
    md = cmp.to_md(out, "t")
    assert "| p | a | g | exact_match / correct / confirmed: A | ambiguous / ambiguous_ok / confirm CR: A |" in md
    b, a = tmp_path / "b.json", tmp_path / "a.json"
    b.write_text(json.dumps(before), encoding="utf-8")
    a.write_text(json.dumps(after), encoding="utf-8")
    assert cmp.main([str(b), str(a), "--md", str(tmp_path / "d.md")])["rules"]["lines"] == 3
    assert (tmp_path / "d.md").read_text(encoding="utf-8") == md.replace("# t", f"# b.json -> a.json", 1)


def test_compare_stops_when_the_lines_differ():
    with pytest.raises(SystemExit, match="same lines"):
        cmp.compare({"rules": section([row("p", "a")])}, {"rules": section([row("p", "b")])}, ["rules"])


# ---------- i5_p59_with_age.py ----------

def test_with_age_passes_the_age_read_from_the_name_and_restores_the_harness(be, monkeypatch):  # noqa: F811
    seen = []
    fake = SimpleNamespace(ExtractedProduct=be.ExtractedProduct,
                           resolve_staged=lambda item, catalog, stages: seen.append(item.age_years))

    def fake_main(argv):
        h.Backend.resolve(fake, "글렌모렌지 오리지날 10년", None)
        h.Backend.resolve(fake, "Glenmorangie 14yr", None)
        h.Backend.resolve(fake, "글렌모렌지 시그넷", None)
        return {"argv": argv}

    original = h.Backend.resolve
    monkeypatch.setattr(h, "main", fake_main)
    assert "app.matching.staged" in sys.modules
    assert wa.main(["--set", "i3"]) == {"argv": ["--set", "i3"]}
    assert seen == [10, 14, None]
    assert h.Backend.resolve is original


def test_with_age_runs_the_harness(files, tmp_path):  # noqa: F811
    gold, labels, cat = files
    result = wa.main(["--set", "i3", "--catalog", "asis", "--catalog-file", str(cat), "--gold", str(gold),
                      "--labels", str(labels), "--no-gold-sha-check", "--json", str(tmp_path / "r.json")])
    names = {r["name"]: r for r in result["rules"]["rows"]}
    assert names["글렌피딕 12년"]["status"] == "exact_match"  # alias with the same age: still confirmed


# ---------- 1b: --missing-age-guard ----------

def guard_files(tmp_path):
    import copy
    from test_i3_match_eval import GOLD, SEED, alias
    seed, gold = copy.deepcopy(SEED), copy.deepcopy(GOLD)
    seed["products"][1]["aliases"].append(alias("글렌피딕 에이틴", "standard"))  # glenfiddich-18, no age on it
    gold["photos"][1]["items"].append({"raw_name": "글렌피딕 에이틴", "unit": "glass", "pour_ml": None,
                                       "gold": "glenfiddich-18"})
    paths = {}
    for name, data in (("gold", gold), ("catalog", seed), ("labels", {"photos": [
            {"photo_id": p["photo_id"], "items": [{"raw_name": i["raw_name"], "unit": i["unit"], "price_krw": 1}
                                                  for i in p["items"]]} for p in gold["photos"]]})):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ["--set", "i3", "--catalog", "asis", "--catalog-file", str(paths["catalog"]), "--gold", str(paths["gold"]),
            "--labels", str(paths["labels"]), "--no-gold-sha-check", "--server-steps"]


def test_missing_age_guard_turns_a_confirmation_without_an_age_into_a_recommendation(tmp_path):
    args = guard_files(tmp_path)
    off = h.main([*args, "--json", str(tmp_path / "off.json")])
    on = h.main([*args, "--missing-age-guard", "--json", str(tmp_path / "on.json")])
    rows = lambda r: {x["name"]: x for x in r["server"]["rows"]}
    assert rows(off)["글렌피딕 에이틴"]["status"] == "exact_match"
    assert rows(on)["글렌피딕 에이틴"]["status"] == "ambiguous" and rows(on)["글렌피딕 에이틴"]["confirm_recommended"]
    assert rows(on)["Glenfiddich 18"]["status"] == "exact_match"  # the age is on the line
    assert on["server"]["missing_age_guard"] is True and off["server"]["missing_age_guard"] is False
    assert on["server"]["changed"]["guard_missing_age"] == 1 and "guard_missing_age" not in off["server"]["changed"]
    assert on["rules"]["rows"] == off["rules"]["rows"]  # the guard is a server step only


def test_missing_age_guard_needs_the_server_steps(capsys):
    with pytest.raises(SystemExit):
        h.parse_args(["--set", "i3", "--catalog", "full", "--missing-age-guard", "--json", "x.json"])
    assert "--missing-age-guard needs --server-steps" in capsys.readouterr().err


# ---------- 1c: i5_p59_age_only.py ----------

def test_age_only_scan_reads_brand_and_age_lines_and_flags_a_missing_candidate(files, tmp_path, be):  # noqa: F811
    import i5_p59_age_only as ao
    gold, labels, cat = files
    out = tmp_path / "r.json"
    h.main(["--set", "i3", "--catalog", "asis", "--catalog-file", str(cat), "--gold", str(gold),
            "--labels", str(labels), "--no-gold-sha-check", "--json", str(out)])
    result = json.loads(out.read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in ao.scan(result, be, ao.catalogs_for(result, be, cat))}
    # 글렌피딕 12년: brand + age only, one product of that age, confirmed (the brand's plain 12)
    assert rows["글렌피딕 12년"]["same_age"] == ["Glenfiddich 12"] and not rows["글렌피딕 12년"]["one_product_not_offered"]
    assert rows["글렌피딕 12년"]["confirmed_edition"] is False
    # Glenfiddich 15 is not in the asis catalog: no product of that age, so not a 1c case
    assert rows["Glenfiddich 15"]["same_age"] == [] and not rows["Glenfiddich 15"]["one_product_not_offered"]
    assert "하우스 위스키" not in rows and "Signatory Vintage Macduff 13" not in rows  # not brand + age only
    md_path = tmp_path / "a.md"
    assert ao.main([str(out), "--catalog-file", str(cat), "--md", str(md_path)])["r.json"]
    md = md_path.read_text(encoding="utf-8")
    assert "브랜드 + 연수만 적힌 줄" in md and "그중 후보로 안 나온 줄 0" in md


def test_age_only_scan_flags_the_one_product_left_out(be):  # noqa: F811
    import i5_p59_age_only as ao
    from test_i3_match_eval import SEED
    bc = h.build_catalog(be, "바B", "asis", SEED)
    result = {"rules": {"rows": [{"bar": "바B", "photo_id": "p", "name": "글렌피딕 18년", "gold": "glenfiddich-18",
                                  "status": "unmatched", "outcome": "unmatched", "cands": ""}]}}
    [row] = ao.scan(result, be, {"바B": bc})
    assert row["age"] == 18 and row["same_age"] == ["Glenfiddich 18"] and row["one_product_not_offered"] is True
    assert "**예**" in ao.to_md("x", [row])


# ---------- review fixes (PR #222) ----------

def test_age_only_scan_counts_the_products_that_take_an_older_age(be):  # noqa: F811
    import i5_p59_age_only as ao
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    bc = h.build_catalog(be, "바B", "service", seed)
    result = {"rules": {"rows": [{"bar": "바B", "photo_id": "p", "name": "글렌모렌지 12", "gold": "glenmorangie-original",
                                  "status": "ambiguous", "outcome": "ambiguous_ok",
                                  "cands": "Glenmorangie 12 Calvados Cask Finish || Glenmorangie Lasanta"}]}}
    [row] = ao.scan(result, be, {"바B": bc})
    # Lasanta (15) and Quinta Ruban (14) take 12 as an older age, as the brand + age step reads them
    assert row["same_age"] == ["Glenmorangie 12 Calvados Cask Finish", "Glenmorangie Lasanta",
                               "Glenmorangie Quinta Ruban", "Glenmorangie The Original"]
    assert row["one_product_not_offered"] is False
    # rules code before accepted ages: the product's age only
    assert ao.fits_age(SimpleNamespace(age_years=12), 12) and not ao.fits_age(SimpleNamespace(age_years=15), 12)


def test_compare_escapes_pipes_in_table_cells():
    gold = {"gold": "both:x|y"}
    before = {"server": section([{**row("p", "a", cands="A || B"), **gold}])}
    after = {"server": section([{**row("p", "a", status="ambiguous", outcome="ambiguous_ok", burden="choose",
                                       cands="A || B"), **gold}])}
    md = cmp.to_md(cmp.compare(before, after, ["server"]), "t")
    [line] = [x for x in md.splitlines() if x.startswith("| p |")]
    assert r"both:x\|y" in line and r"A \|\| B" in line
    assert line.replace(r"\|", "").count("|") == 6  # five cells


def test_kind_table_takes_the_rules_only_server_row_only_where_the_llm_kept_the_rule_result():
    import i5_kind_table as kt
    base = {"bar": "b", "photo_id": "p", "gold": "g", "kind": "known", "llm_target": True, "rank1_gold": False}
    rules = [{**base, "name": "kept", "status": "unmatched", "n_cand": 0, "cands": ""},
             {**base, "name": "changed", "status": "unmatched", "n_cand": 0, "cands": ""}]
    llm = [dict(rules[0]), {**rules[1], "status": "ambiguous", "n_cand": 1, "cands": "X"}]
    served = [{**rules[0], "status": "ambiguous", "n_cand": 2, "cands": "E1 || E2"},
              {**rules[1], "status": "ambiguous", "n_cand": 2, "cands": "E3 || E4"}]
    result = {"set": "dev", "catalog": "service", "input": "label", "lines": 2,
              "rules": {"rows": rules}, "llm": {"rows": llm, "photo_runs": [], "cache": "none"}}
    kept, changed = kt.joined_rows(result, {"server": {"rows": served}})
    assert (kept["served_status"], kept["served_n"], kept["served_cands"]) == ("ambiguous", 2, "E1 || E2")
    assert (changed["served_status"], changed["served_n"], changed["served_cands"]) == (None, None, "")
    md = kt.md_report("x", result, [kept, changed])
    assert "**changed** | gold `g` | llm `missing` | rule: unmatched 0; after embedding: not known" in md
    assert "after embedding: ambiguous 2 [E1 || E2]" in md
