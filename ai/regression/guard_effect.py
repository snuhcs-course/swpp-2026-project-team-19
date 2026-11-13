"""What the incomplete-name guard would change on an evaluation set (I4-P38). Rules only, no API call.

    python ai/regression/guard_effect.py dev service
    python ai/regression/guard_effect.py i3 asis
    python ai/regression/guard_effect.py i3 full

Runs ai/eval/i3_match_eval.py twice on the set, without and with
`apply_linking_guards(..., incomplete_names=True)` after the rule matcher, and prints totals:
lines per owner burden, false merges, wrong recommendations, and how many lines lost their
confirmation and whether they had been right. It prints no line of the set, so running it on the
frozen I3 set shows nothing that could be tuned to.
"""

from __future__ import annotations

import collections
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import i3_match_eval as harness  # noqa: E402

BURDENS = ("confirmed", "confirm", "choose", "register", "wrong")


def totals(rows: list[dict]) -> dict:
    burden = collections.Counter(r["burden"] for r in rows)
    return {**{b: burden[b] for b in BURDENS},
            "false_merge": sum(r["outcome"] in ("false_merge", "overconfident") for r in rows),
            "wrong_recommendation": sum(r["confirm_recommended"] and not r["rank1_gold"] for r in rows)}


def measure(set_: str, catalog: str) -> dict:
    from app.matching.linking_guards import apply_linking_guards

    resolve = harness.Backend.resolve
    rows = {}
    try:
        for guard in (False, True):
            def guarded(self, name, cat, guard=guard):
                result = resolve(self, name, cat)
                return apply_linking_guards(name, result, cat, incomplete_names=True) if guard else result

            harness.Backend.resolve = guarded
            with tempfile.TemporaryDirectory() as tmp:
                rows[guard] = harness.main(["--set", set_, "--catalog", catalog, "--json", f"{tmp}/out.json"])["rules"]["rows"]
    finally:
        harness.Backend.resolve = resolve
    moved = [before for before, after in zip(rows[False], rows[True]) if before["status"] != after["status"]]
    return {"set": set_, "catalog": catalog, "lines": len(rows[False]),
            "without": totals(rows[False]), "with": totals(rows[True]),
            "lost_confirmation": len(moved),
            "of_them_right": sum(r["outcome"] == "correct" for r in moved),
            "of_them_false_merge": sum(r["outcome"] in ("false_merge", "overconfident") for r in moved)}


def main(argv=None) -> int:
    set_, catalog = (argv or sys.argv[1:])[:2]
    result = measure(set_, catalog)
    print(f"{set_}/{catalog}: {result['lines']} lines")
    for key in ("without", "with"):
        print(f"  {key:7} guard: " + "  ".join(f"{k} {v}" for k, v in result[key].items()))
    print(f"  lost confirmation: {result['lost_confirmation']} (right product {result['of_them_right']}, "
          f"false merge {result['of_them_false_merge']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
