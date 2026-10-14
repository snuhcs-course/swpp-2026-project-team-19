# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""Fix the P28 evaluation sample of new products (naver_plan.md, 2절).

    python ai/naver/sample.py          # writes eval/naver_sample_v1.json, prints counts only

The sample is not opened during P17: this script prints no product names.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "eval" / "match_gold_v1.json"
OUT = REPO_ROOT / "eval" / "naver_sample_v1.json"
SEED = 20261013
PER_STRATUM = 20

# Independent bottlers: brands that sell other distilleries' spirit under their own name.
# Fixed before sampling. Compared case-insensitively with new_products[*].brand.
IB_BOTTLERS = frozenset(b.casefold() for b in (
    "Signatory", "Gordon & MacPhail", "Douglas Laing", "Hunter Laing", "La Maison du Whisky",
    "The Whisky Agency", "Samaroli", "Wilson & Morgan", "Highland Laird", "Elements of Islay",
    "Port Askaig", "Blackadder",
))


def is_independent(product: dict) -> bool:
    return product["brand"].casefold() in IB_BOTTLERS


def strata(gold: dict) -> dict[str, list[str]]:
    """New product keys by stratum, sorted (so the draw depends only on the seed)."""
    out = {"independent": [], "official": []}
    for key, product in gold["new_products"].items():
        out["independent" if is_independent(product) else "official"].append(key)
    return {k: sorted(v) for k, v in out.items()}


def draw(keys: list[str], n: int, rng: random.Random) -> list[str]:
    return sorted(rng.sample(keys, n))


def main() -> None:
    raw = GOLD.read_bytes()
    gold = json.loads(raw.decode("utf-8"))
    by_stratum = strata(gold)
    rng = random.Random(SEED)
    sample = {name: draw(keys, PER_STRATUM, rng) for name, keys in by_stratum.items()}
    OUT.write_text(json.dumps({
        "version": "naver_sample_v1",
        "created": "2026-10-13",
        "purpose": "P28 evaluation of Naver candidates + LLM judge. Not run or opened during P17.",
        "source": "eval/match_gold_v1.json new_products",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "seed": SEED,
        "rule": "independent = brand in ai/naver/sample.py IB_BOTTLERS; official = the rest",
        "population": {k: len(v) for k, v in by_stratum.items()},
        "sample": sample,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("population", {k: len(v) for k, v in by_stratum.items()},
          "sample", {k: len(v) for k, v in sample.items()}, "->", OUT.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
