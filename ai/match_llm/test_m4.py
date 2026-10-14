# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, M4). Reviewed by Jinwoo Park.
"""M4 tests with the made-up Fernhollow products of test_vetoes.py, a fake Naver client and a
fixed judge. No API call. Covers: never exact, vetoes on the pick, "new"/"none" leave the
line as it was, confirm only when there was no candidate or the pick was among them, target rule."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from m3 import M3  # noqa: E402
from m4 import M4, is_target  # noqa: E402
from test_vetoes import FERN_12, FERN_12_CS, FERN_15, GM_FERN_12, META, SIG_FERN_12, FixedLLM, catalog, tr  # noqa: E402
from app.matching.types import Candidate, ResolutionResult  # noqa: E402


class FakeNaver:
    def __init__(self, items=()):
        self.items = list(items)
        self.calls = []
        self.stats = {}

    def search(self, endpoint, query, display=10):
        self.calls.append((endpoint, query))
        return {"items": self.items if endpoint == "blog" else [], "from_cache": True, "fetched_at": "t"}


class FixedJudge:
    prompt_sha256 = "test"

    def __init__(self, verdict, product=None):
        self.verdict, self.product, self.seen = verdict, product, []

    def __call__(self, candidate):
        self.seen.append(candidate)
        pid = str(self.product) if self.product else ("new" if self.verdict == "different" else None)
        return {"verdict": self.verdict, "product_id": pid, "confidence": 0.9, "reason": "test", "meta": {}}


def engine(name, translation, judge, items=()):
    m3 = M3(FixedLLM(translation), {"photo": [name]}, META)
    m3.translate("photo", {name})
    return M4(m3, FakeNaver(items), judge)


def cand(pid, rank, confirm=False):
    return Candidate(product_id=pid, rank=rank, score=0.5, method="alias",
                     evidence={"confirmRecommended": True} if confirm else {})


def ambiguous(*pids, confirm=False):
    return ResolutionResult(status="ambiguous", candidates=tuple(cand(p, i, confirm and i == 1)
                                                                 for i, p in enumerate(pids, start=1)),
                            proposed_product_id=pids[0])


UNMATCHED = ResolutionResult(status="unmatched")


def test_target_rule():
    assert is_target(UNMATCHED)
    assert is_target(ambiguous(FERN_12, FERN_15))
    assert not is_target(ambiguous(FERN_12, FERN_15, confirm=True))
    assert not is_target(ambiguous(FERN_12))  # one candidate: the owner only confirms it
    assert not is_target(ResolutionResult(status="exact_match", proposed_product_id=FERN_12))


def test_pick_on_unmatched_line_is_confirm_recommended_never_exact():
    name = "페른홀로우 12년 스페셜"
    m4 = engine(name, tr(brand_en="Fernhollow", age=12), FixedJudge("same", FERN_12))
    r, info = m4.resolve("photo", name, catalog(), UNMATCHED)
    assert r.status == "ambiguous" and r.candidates[0].product_id == FERN_12
    assert r.candidates[0].method == "llm" and r.candidates[0].evidence.get("confirmRecommended")
    assert info["raised_confirm"] is True
    # options: the brand family (no current candidates); the judge saw only catalog products
    opts = {o["product_id"] for o in m4.judge.seen[0]["options"]}
    assert str(FERN_12) in opts and m4.judge.seen[0]["mode"] == "match"


def test_vetoed_pick_leaves_the_line():
    """Distillery-only line, the judge picks a Signatory bottling: bottler_missing."""
    name = "페른홀로우 12년 스페셜"
    m4 = engine(name, tr(brand_en="Fernhollow", age=12), FixedJudge("same", SIG_FERN_12),
                items=[{"title": "Signatory Vintage Fernhollow 12", "description": "", "link": "u1"}])
    r, info = m4.resolve("photo", name, catalog(), UNMATCHED)
    assert r is UNMATCHED and info["m4"] == "vetoed"
    assert info["vetoed"][0]["rules"] == ["bottler_missing"]


def test_age_veto_on_pick():
    name = "페른홀로우 12년 스페셜"
    m4 = engine(name, tr(brand_en="Fernhollow", age=12), FixedJudge("same", FERN_15))
    r, info = m4.resolve("photo", name, catalog(), UNMATCHED)
    assert r is UNMATCHED and info["vetoed"][0]["rules"] == ["age_mismatch"]


def test_new_and_unsure_change_nothing():
    name = "페른홀로우 12년 스페셜"
    for verdict in ("different", "unsure"):
        m4 = engine(name, tr(brand_en="Fernhollow", age=12), FixedJudge(verdict))
        r, info = m4.resolve("photo", name, catalog(), UNMATCHED)
        assert r is UNMATCHED and info["m4"] == verdict


def test_pick_outside_current_candidates_is_not_confirm_recommended():
    """Current candidates 15 and 12 CS; the judge picks 12 (not among them): rank 1, no confirm."""
    name = "Fernhollow twelve"
    m4 = engine(name, tr(brand_en="Fernhollow", age=12), FixedJudge("same", FERN_12))
    current = ambiguous(FERN_12_CS, GM_FERN_12)
    r, info = m4.resolve("photo", name, catalog(), current)
    assert r.candidates[0].product_id == FERN_12
    assert not r.candidates[0].evidence.get("confirmRecommended") and info["raised_confirm"] is False
    assert [c.product_id for c in r.candidates[1:]] == [FERN_12_CS, GM_FERN_12]


def test_naver_options_need_all_core_tokens_and_the_age():
    name = "페른 12"
    items = [{"title": "Fernhollow 12 Cask Strength review", "description": "", "link": "a"},
             {"title": "Fernhollow 15", "description": "", "link": "b"}]
    m4 = engine(name, tr(age=12), FixedJudge("unsure"), items=items)  # no brand: no family
    _, info = m4.resolve("photo", name, catalog(), UNMATCHED)
    via = {o["product"]: o["via"] for o in info["options"]}
    assert via == {"Fernhollow 12": "naver", "Fernhollow 12 Cask Strength": "naver"}  # 15: age differs


def test_non_whisky_translation_is_skipped():
    name = "페른홀로우 진"
    m4 = engine(name, tr(brand_en="Fernhollow", kind="non_whisky"), FixedJudge("same", FERN_12))
    r, info = m4.resolve("photo", name, catalog(), UNMATCHED)
    assert r is UNMATCHED and info["m4"] == "skipped" and not m4.judge.seen and not m4.naver.calls
