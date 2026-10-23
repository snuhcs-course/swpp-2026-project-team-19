"""Build eval/match_gold_v1_1.json: match_gold_v1 with the v1.1 menu line names.

    python ai/eval/build_match_gold_v1_1.py

match_gold_v1 stores each line's raw_name (the matcher input in match_eval.py),
so it depends on the label text. match_gold_v1 and its builder are frozen
(eval_plan.md, P22), so this does not rebuild it: each gold item is aligned
with the label item at the same photo and position, and only raw_name is
replaced where labels v1.1 changed it. `review` keys (notes keyed by name) are
renamed the same way. Checks: every gold item lines up with a v1 label item
(same raw_name, unit, pour_ml), every gold link ("gold") is identical to v1,
and nothing else differs.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_V1 = REPO_ROOT / "eval" / "match_gold_v1.json"
GOLD_V1_SHA256 = "9b1b0794ecd05e866ace44b80e32c0452a59ed4d45f349909c69096c6da2bbdf"  # frozen (P22)
OUT = REPO_ROOT / "eval" / "match_gold_v1_1.json"
PAIRS = [  # (v1 labels, v1.1 labels)
    (REPO_ROOT / "eval" / "labels_v1.json", REPO_ROOT / "eval" / "labels_v1_1.json"),
    (REPO_ROOT / "eval" / "labels_heldout_v1.json", REPO_ROOT / "eval" / "labels_heldout_v1_1.json"),
]


def label_items(path: Path) -> dict[str, list[dict]]:
    return {p["photo_id"]: p["items"] for p in json.loads(path.read_text(encoding="utf-8"))["photos"]}


def main() -> None:
    raw = GOLD_V1.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == GOLD_V1_SHA256, "match_gold_v1.json changed"
    gold = json.loads(raw.decode("utf-8"))
    old, new = {}, {}
    for a, b in PAIRS:
        old.update(label_items(a))
        new.update(label_items(b))

    out = copy.deepcopy(gold)
    out["version"] = "match_gold_v1.1"
    out["created"] = "2026-10-14"
    out["labeling"] = (gold["labeling"] + ". v1.1: raw_name from labels v1.1 (menu print, "
                       "eval/labels_changelog.md); gold links unchanged from match_gold_v1")
    renamed = {}
    changed = []
    for p, q in zip(gold["photos"], out["photos"]):
        pid = p["photo_id"]
        assert len(p["items"]) == len(old[pid]) == len(new[pid]), pid
        for i, (g, lab_old, lab_new) in enumerate(zip(q["items"], old[pid], new[pid])):
            assert (g["raw_name"], g["unit"], g["pour_ml"]) == \
                (lab_old["raw_name"], lab_old["unit"], lab_old["pour_ml"]), f"{pid}#{i} not aligned"
            if lab_new["raw_name"] != g["raw_name"]:
                renamed.setdefault(g["raw_name"], set()).add(lab_new["raw_name"])
                changed.append((f"{pid}#{i}", g["raw_name"], lab_new["raw_name"], g["gold"]))
                g["raw_name"] = lab_new["raw_name"]
    for name, targets in renamed.items():
        assert len(targets) == 1, f"{name} renamed two ways: {targets}"
    out["review"] = {next(iter(renamed[k])) if k in renamed else k: v for k, v in gold["review"].items()}

    # the product links must not move by a single line
    for p, q in zip(gold["photos"], out["photos"]):
        assert [i["gold"] for i in p["items"]] == [i["gold"] for i in q["items"]], p["photo_id"]
        for a, b in zip(p["items"], q["items"]):
            assert {k: v for k, v in a.items() if k != "raw_name"} == {k: v for k, v in b.items() if k != "raw_name"}
    assert out["new_products"] == gold["new_products"] and out["split"] == gold["split"]
    assert list(out["review"].values()) == list(gold["review"].values())

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    n = sum(len(p["items"]) for p in gold["photos"])
    print(f"{len(changed)} of {n} gold items renamed; gold links identical to v1 ({n}/{n})")
    print(f"review keys renamed: {sum(k in renamed for k in gold['review'])}")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}  sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
