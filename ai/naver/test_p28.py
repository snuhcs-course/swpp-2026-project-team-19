# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P28). Reviewed by Jinwoo Park.
"""Tests for p28_score.py and the quota guard (no API calls)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p28_score  # noqa: E402
import quota  # noqa: E402


def test_cp_upper_matches_plan_value():
    # naver_plan.md 6절 (e): 0 errors in 40 -> 7.2%
    assert p28_score.cp_upper(0, 40) == pytest.approx(1 - 0.05 ** (1 / 40), abs=1e-6)
    assert p28_score.cp_upper(3, 3) == 1.0
    assert p28_score.cp_upper(0, 0) is None


def _write(path: Path, rows: list[dict]) -> None:
    cols = ["row_id", "stratum", "product_key", "product", "candidate", "tag_v1", "tag_v2", "bottler_missing",
            "evidence_titles", "evidence_snippets", "evidence_urls", "llm_verdict", "llm_confidence", "llm_reason",
            "human_verdict", "note"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def test_score_counts_unsure_as_wrong(tmp_path):
    rows = [
        {"row_id": "a#1", "stratum": "official", "product_key": "a", "tag_v1": "new", "llm_verdict": "same",
         "llm_confidence": "0.95", "human_verdict": "same"},
        {"row_id": "a#2", "stratum": "official", "product_key": "a", "tag_v1": "new", "llm_verdict": "same",
         "llm_confidence": "0.9", "human_verdict": "unsure"},
        {"row_id": "b#1", "stratum": "independent", "product_key": "b", "tag_v1": "other_product (X)",
         "llm_verdict": "different", "llm_confidence": "0.9", "human_verdict": "different", "bottler_missing": "yes"},
        {"row_id": "b#2", "stratum": "independent", "product_key": "b", "llm_verdict": "same",
         "llm_confidence": "0.95", "human_verdict": ""},
    ]
    path = tmp_path / "r.csv"
    _write(path, rows)
    loaded, info = p28_score.load_rows(path)
    result = p28_score.score(loaded, info)
    assert info["human_empty"] == 1
    assert result["overall"]["M1_precision"] == 0.5
    assert result["overall"]["M1b_precision_excl_unsure"] == 1.0
    assert result["M6_tag_v1_x_human"]["other_product"] == {"different": 1}
    assert result["M7_bottler_missing"] == {"rows": 1, "human_same": 0, "llm_same": 0}
    assert result["decision"] == "불통과"


def test_quota_error_is_not_retried():
    class E(Exception):
        code = 429
    assert quota.is_quota_error(E("x"))
    assert quota.is_quota_error(RuntimeError("RESOURCE_EXHAUSTED: quota"))
    import judge
    assert judge._is_transient(E("x")) is False
