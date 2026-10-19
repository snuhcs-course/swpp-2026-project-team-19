# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-17, P47). Reviewed by Jinwoo Park.
"""P47 dry run: load everything the final run needs, without any API call (ai/docs/p47_plan.md).

    python ai/eval/p47_preflight.py [--json ai/runs/2026-10-17_p47/preflight.json]

Checks the 14 photos' CLOVA caches (table-off) and rebuilt line counts, the label and gold
files, both catalog v2 snapshots, and counts the M3a calls the label-input baseline needs
(photos with at least one line S1+S2b+S3 leaves unconfirmed). The hybrid run's M3a calls depend
on its output and are at most one per photo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "ocr"))

import e2e_match  # noqa: E402
import match_eval  # noqa: E402
from hybrid import ocr_lines  # noqa: E402
from clova import set_photos  # noqa: E402
from match_eval import CONFIRMED, M3_BASE, MATCHERS, gold_lines, gold_refs, load_catalog  # noqa: E402
from score import load_labels, load_photo_map  # noqa: E402

from app.matching.types import ExtractedProduct  # noqa: E402

FINAL_MENUS = {"menu:수이", "menu:오드비"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    from extract import data_dir

    out = {"files": {}, "photos": {}, "catalogs": {}}
    for f in ("eval/labels_final_v1.json", "eval/match_gold_final_v1.json",
              "ai/catalog/catalog_v2_eval_5bars.json", "ai/catalog/catalog_v2_eval_5bars_drop_products.json",
              "ai/ocr/hybrid_prompt_v1.md", "ai/match_llm/translate_prompt_v3.md"):
        out["files"][f] = sha(REPO_ROOT / f)

    labels = load_labels("final")  # SHA-256 pinned in score.py
    stem_to_id = load_photo_map(data_dir(), "final")
    photos = set_photos("final")
    for p in photos:
        lines, size, meta = ocr_lines(p.stem)  # raises when a cache is missing
        pid = stem_to_id[p.stem]
        out["photos"][p.name] = {"photo_id": pid, "ocr_lines": len(lines), "ocr_latency_ms": meta["latency_ms"],
                                 "label_items": len(labels[pid]),
                                 "label_lines": len(dict.fromkeys(i["raw_name"] for i in labels[pid]))}

    for name, path in e2e_match.FINAL_CATALOGS.items():
        match_eval.SEED = path
        gold = e2e_match.final_gold(path)
        e2e_match.check_labels_final(gold, labels)
        cat = json.loads(path.read_text(encoding="utf-8"))
        kinds, targets, n_target_lines = Counter(), {}, 0
        for photo in gold["photos"]:
            catalog = load_catalog(photo["bar"], "C0", gold["new_products"], set())[0]
            seen = {}
            for item in photo["items"]:
                seen.setdefault(item["raw_name"], item["gold"])
            for g in seen.values():
                kinds["non_whisky" if g == "non_whisky" else "unknown" if g == "unknown"
                      else "absent" if any(r.startswith("new:") for r in gold_refs(g)) else "known"] += 1
            t = [n for n in gold_lines(gold, "final")[photo["photo_id"]]
                 if MATCHERS[M3_BASE](ExtractedProduct(product_name=n), catalog).status not in CONFIRMED]
            targets[photo["photo_id"]] = len(t)
            n_target_lines += len(t)
        out["catalogs"][name] = {
            "products": len(cat["products"]),
            "product_aliases": sum(len(p["aliases"]) for p in cat["products"]),
            "final_only_product_aliases": sum(bool(a.get("sources")) and set(a["sources"]) <= FINAL_MENUS
                                              for p in cat["products"] for a in p["aliases"]),
            "final_only_brand_aliases": [a["alias_text"] for b in cat["brands"] for a in b["aliases"]
                                         if a.get("sources") and set(a["sources"]) <= FINAL_MENUS],
            "gold_line_kinds": dict(kinds),
            "label_m3a_target_lines": n_target_lines,
            "label_m3a_calls": sum(n > 0 for n in targets.values()),
            "label_m3a_targets_per_photo": targets,
        }

    ph = out["photos"].values()
    out["totals"] = {"photos": len(photos), "ocr_lines": sum(p["ocr_lines"] for p in ph),
                     "label_items": sum(p["label_items"] for p in ph),
                     "label_lines": sum(p["label_lines"] for p in ph)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
