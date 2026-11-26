"""I5-P59: the catalog ages (1a) and the measurement scripts i5_p59_compare.py, i5_p59_with_age.py."""

import json
import sys
from types import SimpleNamespace

import i3_match_eval as h
import i5_p59_compare as cmp
import i5_p59_with_age as wa
import pytest
from test_i3_match_eval import be, files  # noqa: F401 (fixtures)


# ---------- 1a: catalog v2.5 ----------

def test_catalog_v2_5_has_the_current_glenmorangie_ages():
    seed = json.loads((h.REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json").read_text(encoding="utf-8"))
    ages = {p["key"]: p["age_years"] for p in seed["products"] if p["key"].startswith("glenmorangie")}
    assert seed["version"] == "catalog_v2_5_service"
    assert (ages["glenmorangie-original"], ages["glenmorangie-quinta-ruban"], ages["glenmorangie-lasanta"],
            ages["glenmorangie-nectar-dor"]) == (12, 14, 12, 16)
    assert ages["glenmorangie-18"] == 18 and ages["glenmorangie-signet"] is None  # the others as before


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
