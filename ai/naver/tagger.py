# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""Matcher tag for a candidate alias (naver_plan.md, 3절).

The candidate alias is looked up with the adopted matcher S1+S2b+S3 in the catalog
"product is in the DB, its Korean spelling is not": catalog_v1_draft with every alias,
plus every new:* product of match_gold_v1 with its English name as the only alias
(the C1 construction of match_eval.py, for all splits). Tags:
  same           exact match to the input product
  other_product  exact match (or a two-product result) to another product: wrong-alias risk
  ambiguous      candidates, nothing confirmed
  new            no candidate
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))

from app.matching.staged import resolve_product_staged  # noqa: E402
from app.matching.types import ExtractedProduct  # noqa: E402
from match_eval import GOLD, load_catalog  # noqa: E402

MATCHER = "S1+S2b+S3"
STAGES = {"S1", "S2", "S2b", "S3"}
TAGS = ("same", "other_product", "ambiguous", "new")


class MatcherTagger:
    def __init__(self, gold: dict | None = None):
        gold = gold or json.loads(GOLD.read_text(encoding="utf-8"))
        self.new_products = gold["new_products"]
        # bar "" excludes no menu aliases; C1 with every new product
        self.catalog, self.key_to_id = load_catalog("", "C1", self.new_products, set(self.new_products))
        self.id_to_key = {v: k for k, v in self.key_to_id.items()}

    def product_id(self, key: str) -> uuid.UUID:
        """Id of a catalog product key or a new product key ("new:<key>" or bare)."""
        if key in self.key_to_id:
            return self.key_to_id[key]
        return self.key_to_id[f"new:{key}"]

    def describe(self, pid: uuid.UUID) -> dict:
        info = self.catalog.get_product(pid)
        return {"key": self.id_to_key.get(pid), "display_name": info.display_name if info else None,
                "age_years": info.age_years if info else None, "edition_name": info.edition_name if info else None}

    def tag(self, alias: str, input_key: str) -> dict:
        target = self.product_id(input_key)
        r = resolve_product_staged(ExtractedProduct(product_name=alias), self.catalog, STAGES)
        if r.status == "exact_match":
            tag = "same" if r.proposed_product_id == target else "other_product"
            named = [r.proposed_product_id]
        elif r.status == "multi":
            named = [p.proposed_product_id for p in r.parts]
            tag = "same" if set(named) == {target} else "other_product"
        else:
            named = [c.product_id for c in r.candidates]
            tag = "ambiguous" if r.status == "ambiguous" else "new"
        return {
            "tag": tag,
            "matcher": MATCHER,
            "status": r.status,
            "input_among_candidates": target in named,
            "products": [{**self.describe(pid),
                          "evidence": next((c.evidence for c in r.candidates if c.product_id == pid), {})}
                         for pid in named],
        }
