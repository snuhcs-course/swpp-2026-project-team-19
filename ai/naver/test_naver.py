# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""Unit tests for ai/naver with response fixtures. Live API / LLM tests run only with keys.

    python -m pytest ai/naver
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import candidates as cand_mod  # noqa: E402
import client as client_mod  # noqa: E402
import judge as judge_mod  # noqa: E402
from candidates import clean_text, extract_candidates, ko_brand_aliases, edition_brand_aliases  # noqa: E402
from client import ID_HEADER, SECRET_HEADER, NaverSearchClient, NaverSearchError  # noqa: E402
from tagger import MatcherTagger  # noqa: E402

FIXTURES = HERE / "fixtures"
SEED = json.loads((HERE.parents[1] / "ai" / "catalog" / "catalog_v1_draft.json").read_text(encoding="utf-8"))
ARRAN_10 = {"display_name": "Arran 10", "brand": "arran", "age_years": 10, "edition_name": None}
KESTREL = {"display_name": "Kestrel Bottlers Ardbeg 9", "brand": "Kestrel Bottlers", "age_years": 9,
           "edition_name": "Ardbeg"}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def record(endpoint: str, query: str, body: dict) -> dict:
    return {"endpoint": endpoint, "query": query, "fetched_at": "2026-10-13T01:00:00+00:00",
            "total": body["total"], "items": body["items"]}


# --- client -------------------------------------------------------------------------------

@pytest.fixture
def fake_keys(monkeypatch):
    monkeypatch.setattr(client_mod, "load_env", lambda: None)
    monkeypatch.setenv("NAVER_HUB_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_HUB_CLIENT_SECRET", "test-secret")


def test_search_sends_hub_headers_and_caches_without_keys(tmp_path, fake_keys):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("cafearticle_arran10.json"))

    c = NaverSearchClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler), min_interval=0)
    first = c.search("cafearticle", "Arran 10")
    second = c.search("cafearticle", "Arran 10")

    assert len(seen) == 1  # second call served from the cache
    req = seen[0]
    assert req.url.host == "naverapihub.apigw.ntruss.com"
    assert req.url.path == "/search/v1/cafearticle"
    assert req.url.params["query"] == "Arran 10" and req.url.params["display"] == "10"
    assert req.headers[ID_HEADER] == "test-id" and req.headers[SECRET_HEADER] == "test-secret"
    assert first["from_cache"] is False and second["from_cache"] is True
    assert second["fetched_at"] == first["fetched_at"] and len(second["items"]) == 4
    cached = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))
    assert "test-id" not in cached and "test-secret" not in cached
    assert c.stats["api_calls"] == 1 and c.stats["cache_hits"] == 1


def test_search_retries_transient_errors(tmp_path, fake_keys, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    responses = iter([httpx.Response(429, json={"errorCode": "SE99", "errorMessage": "limit"}),
                      httpx.Response(200, json=fixture("blog_kestrel.json"))])
    c = NaverSearchClient(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: next(responses)),
                          min_interval=0)
    assert len(c.search("blog", "Kestrel")["items"]) == 3
    assert c.stats["retries"] == 1 and c.stats["api_calls"] == 2


def test_search_gives_up_with_error_code(tmp_path, fake_keys, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    body = {"error": {"errorCode": "200", "message": "Authentication Failed", "details": "x"}}
    c = NaverSearchClient(cache_dir=tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(401, json=body)),
                          min_interval=0)
    with pytest.raises(NaverSearchError, match="HTTP 401: 200 Authentication Failed"):
        c.search("webkr", "x")
    assert c.stats["api_calls"] == 1  # 401 is not retried


def test_shopping_endpoint_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        NaverSearchClient(cache_dir=tmp_path).search("shop", "x")


# --- candidates ---------------------------------------------------------------------------

def test_clean_text_removes_tags_and_double_entities():
    # "&lt;펌&gt;" becomes a tag-like "<펌>" and is dropped with the tags
    assert clean_text("&lt;펌&gt; <b>Arran</b> &amp;amp; 아란") == "Arran & 아란"
    assert "<b>" not in clean_text("아란<b>10</b>년")


def test_korean_brand_from_catalog():
    assert ko_brand_aliases("arran", SEED) == ["아란"]
    assert ko_brand_aliases("Unknown Bottler", SEED) == []
    assert "아드벡" in edition_brand_aliases(KESTREL, SEED)


def test_candidates_strip_promotion_and_keep_provenance():
    results = [record("cafearticle", "Arran 10 위스키", fixture("cafearticle_arran10.json"))]
    out = extract_candidates(ARRAN_10, results, ["아란"])
    by_norm = {c["normalized"]: c for c in out["candidates"]}
    assert "아란10" in by_norm  # "아란10년", "아란 10년은 ...", "아란 10년 최저가 판매" -> one candidate
    ten = by_norm["아란10"]
    assert ten["result_count"] == 2 and ten["age_years"] == 10
    assert not any(w in c["alias"] for c in out["candidates"] for w in ("최저가", "판매", "후기", "할인"))
    assert "아란10주년기념에디션" in by_norm  # a different product, left for the judge
    ev = ten["evidence"][0]
    assert set(ev) >= {"endpoint", "query", "url", "fetched_at", "title_raw"}
    assert ev["title_raw"].startswith("아란<b>")  # original title kept for provenance


def test_candidates_learn_brand_and_keep_distillery_only_names():
    results = [record("blog", "Kestrel Bottlers Ardbeg 9", fixture("blog_kestrel.json"))]
    out = extract_candidates(KESTREL, results, [], edition_brand_aliases(KESTREL, SEED))
    kinds = {c["alias"]: c["anchor_kind"] for c in out["candidates"]}
    assert {"text": "케스트럴 보틀러스", "kind": "learned"} in out["anchors"]
    assert any(k == "learned" and "아드벡 9년" in a for a, k in kinds.items())
    # "아드벡 9년" without the bottler: kept as a candidate (P18 risk c), tagged as such
    assert kinds.get("아드벡 9년") == "edition_brand"


def test_learned_brand_skips_comma_lists_and_text_before_particles():
    texts = ["고든 앤 맥페일, 디스커버리 부나하벤 10년(Gordon & MacPhail, Discovery Bunnahabhain 10)",
             "독립병입사 고든 앤 맥페일(Gordon & MacPhail) 소개", "고든 앤 맥페일(Gordon & MacPhail)"]
    learned = cand_mod.learn_brand_aliases("Gordon & MacPhail", texts)
    assert "고든 앤 맥페일" in learned and not any("디스커버리" in a for a in learned)
    texts = ["위스키의 원액은 토마틴 12년 (Tomatin 12)", "토마틴 레거시 (Tomatin Legacy)"]
    assert cand_mod.learn_brand_aliases("Tomatin", texts) == ["토마틴"]


def test_quantities_and_detached_particles_end_a_candidate():
    results = [record("blog", "q", {"total": 2, "items": [
        {"title": "토마틴 12년 1병 토마틴 전용잔 1개", "link": "l1", "description": ""},
        {"title": "토마틴12년 과 모듬회", "link": "l2", "description": ""}]})]
    out = extract_candidates({**ARRAN_10, "brand": "Tomatin", "age_years": 12}, results, ["토마틴"])
    aliases = [c["alias"] for c in out["candidates"]]
    assert aliases[0] == "토마틴 12년" and out["candidates"][0]["result_count"] == 2
    assert not any("1병" in a or "모듬회" in a for a in aliases)


def test_bottler_missing_flag():
    anchors = [{"text": "케스트럴 보틀러스", "kind": "learned"}, {"text": "아드벡", "kind": "edition_brand"}]
    assert cand_mod.bottler_missing(True, "아드벡 9년", anchors)
    assert not cand_mod.bottler_missing(True, "케스트럴 보틀러스 아드벡 9년", anchors)
    assert not cand_mod.bottler_missing(False, "아드벡 9년", anchors)


def test_particle_cut_keeps_names_ending_in_i():
    assert cand_mod._trim(["글렌모레이", "12년은", "부드럽다"]) == ["글렌모레이", "12년"]
    assert cand_mod._trim(["글렌모레이"]) == ["글렌모레이"]
    assert cand_mod._trim(["아란", "10년", "위스키"]) == ["아란", "10년"]


# --- matcher tag --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tagger():
    return MatcherTagger()


def test_tags(tagger):
    assert tagger.tag("아란 10년", "arran-10")["tag"] == "same"
    other = tagger.tag("아드벡 10년", "arran-10")
    assert other["tag"] == "other_product" and other["products"][0]["key"] == "ardbeg-10"
    assert tagger.tag("전혀없는이름", "arran-10")["tag"] == "new"


# --- judge --------------------------------------------------------------------------------

class FakeInteractions:
    def __init__(self, texts):
        self.texts = list(texts)
        self.requests = []

    def create(self, timeout=None, **request):
        self.requests.append(request)
        usage = SimpleNamespace(total_input_tokens=100, total_output_tokens=20, total_thought_tokens=5)
        return SimpleNamespace(output_text=self.texts.pop(0), usage=usage)


def fake_judge(*texts, budget=10):
    client = SimpleNamespace(interactions=FakeInteractions(texts))
    return judge_mod.Judge(client=client, budget=budget, min_interval=0), client.interactions


ALIAS_CANDIDATE = {"mode": "alias", "product": ARRAN_10, "alias": "아란 10년",
                   "evidence": [{"endpoint": "blog", "title": "t", "snippet": "s", "url": "u", "fetched_at": "x",
                                 "title_raw": "<b>t</b>", "query": "q"}] * 6,
                   "matcher_tag": {"tag": "same", "status": "exact_match", "products": [{"display_name": "Arran 10"}]}}


def test_judge_parses_verdict_and_records_meta():
    j, api = fake_judge('{"verdict":"same","product_id":null,"confidence":0.93,"reason":"브랜드·연수 일치"}')
    v = j(ALIAS_CANDIDATE)
    assert v["verdict"] == "same" and v["confidence"] == 0.93 and "format_problem" not in v
    assert v["meta"]["model"] == "gemini-3.5-flash-lite" and v["meta"]["prompt_version"] == "v1"
    req = api.requests[0]
    assert req["model"] == "gemini-3.5-flash-lite" and req["store"] is False
    sent = json.loads(req["input"][0]["text"])
    assert len(sent["evidence"]) == judge_mod.MAX_EVIDENCE
    assert "title_raw" not in sent["evidence"][0] and sent["matcher_tag"]["products"] == ["Arran 10"]


def test_judge_match_mode_checks_product_id():
    cand = {"mode": "match", "menu_line": "아란 10년", "evidence": [],
            "options": [{"product_id": "p1", "display_name": "Arran 10", "age_years": 10, "edition_name": None}]}
    j, _ = fake_judge('{"verdict":"same","product_id":"p9","confidence":0.8,"reason":"x"}',
                      '{"verdict":"different","product_id":"new","confidence":0.7,"reason":"x"}')
    assert "format_problem" in j(cand)
    assert "format_problem" not in j(cand)


def test_judge_parse_error_is_unsure_and_budget_is_enforced():
    j, _ = fake_judge("not json", budget=1)
    v = j(ALIAS_CANDIDATE)
    assert v["verdict"] == "unsure" and v["confidence"] == 0.0 and j.stats["parse_errors"] == 1
    with pytest.raises(judge_mod.BudgetExceeded):
        j(ALIAS_CANDIDATE)


# --- live (only with keys) ----------------------------------------------------------------

def _has(*names: str) -> bool:
    client_mod.load_env()
    return all(os.environ.get(n) for n in names)


@pytest.mark.skipif(not _has("NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET"), reason="no NAVER API HUB keys")
def test_live_naver_blog(tmp_path):
    out = NaverSearchClient(cache_dir=tmp_path, use_cache=False).search("blog", "아란 10년", display=3)
    assert out["items"] and {"title", "link", "description"} <= set(out["items"][0])


@pytest.mark.skipif(not _has("GEMINI_API_KEY"), reason="no Gemini key")
def test_live_judge_obvious_same():
    cand = {**ALIAS_CANDIDATE, "evidence": [{"endpoint": "cafearticle", "title": "아란 10년 시음기 Arran 10-year-old",
                                             "snippet": "아란 10년 Arran 10-year-old 아란 증류소 숙성년수 10년", "url": "u"}]}
    v = judge_mod.Judge(budget=2)(cand)
    assert v["verdict"] in ("same", "different", "unsure") and 0 <= v["confidence"] <= 1
