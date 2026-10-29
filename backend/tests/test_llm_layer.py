"""The M3 matching LLM layer (app.matching.llm_layer). No API call: a fake `MatchingLLM` answers.

Ported from ai/match_llm/test_m3.py and test_vetoes.py (the frozen M3), plus the server parts:
failed, invalid and capped calls, and the evidence stored with each candidate. When ai/ is
checked out, the last tests run the frozen m3.py on the same cases and compare.
"""

import json
import sys
import uuid
from pathlib import Path

import pytest

from app.matching.llm_layer import (
    BASE_STAGES,
    CONTEXT_LINES,
    GENERIC_TOKENS,
    IB_BOTTLERS,
    LLM_SCORE,
    NEUTRAL_TOKENS,
    PICK_PROMPT,
    PROMPT_SHA256,
    TRANSLATE_PROMPT,
    M3Engine,
    Pick,
    ProductMeta,
    SHORT_LATIN,
    Translation,
    bottler_of,
    combine,
    core_tokens,
    edition_check,
    english_name,
    load_prompt,
    prompt_sha256,
    tokens,
)
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.types import Candidate, ProductInfo, ResolutionResult

AI_MATCH_LLM = Path(__file__).resolve().parents[2] / "ai" / "match_llm"
UNMATCHED = ResolutionResult(status="unmatched")


class FakeLLM:
    """Answers M3a with `translate(payload)` and M3b with `pick(payload)`: a dict (sent back as JSON),
    a str (sent back as is) or an exception (raised). Records every payload."""

    def __init__(self, translate=None, pick=None):
        self.translate = translate
        self.pick = pick or (lambda payload: {"choice": "unsure", "reason": ""})
        self.calls = []

    def generate_json(self, prompt, payload, response_schema):
        kind = "m3a" if "lines" in payload else "m3b"
        self.calls.append((kind, prompt, payload, response_schema))
        answer = (self.translate if kind == "m3a" else self.pick)(payload)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


def tr(**kw):
    return {"bottler_en": None, "distillery_en": None, "brand_en": None, "age": None, "edition_tokens_en": [],
            "expansions": [], "kind": "whisky", **kw}


def one_line(translation):
    """M3a answer translating line 1 as `translation`."""
    return lambda payload: {"items": [{"line": 1, **translation}]}


def ids(result):
    return [c.product_id for c in result.candidates]


# --- Caol Ila catalog (test_m3.py) ------------------------------------------------------

B_CAOL, B_SIG = uuid.uuid4(), uuid.uuid4()
P_CAOL12, P_SIG10, P_CAOL18 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
CAOL_META = {
    P_CAOL12: ProductMeta("Caol Ila 12", 12, None, None),
    P_CAOL18: ProductMeta("Caol Ila 18", 18, None, None),
    P_SIG10: ProductMeta("Signatory Vintage 100 Proof Caol Ila 10", 10, "100 Proof Caol Ila", "Signatory"),
}


def caol_catalog():
    products = [ProductInfo(P_CAOL12, "Caol Ila 12", 12, None, B_CAOL), ProductInfo(P_CAOL18, "Caol Ila 18", 18, None, B_CAOL),
                ProductInfo(P_SIG10, "Signatory Vintage 100 Proof Caol Ila 10", 10, "100 Proof Caol Ila", B_SIG)]
    aliases = [(P_CAOL12, "Caol Ila 12"), (P_CAOL12, "쿨일라 12년"), (P_CAOL18, "Caol Ila 18"),
               (P_SIG10, "Signatory Vintage 100 Proof Caol Ila 10")]
    return InMemoryCatalog(products, aliases, [(B_CAOL, "Caol Ila"), (B_SIG, "Signatory Vintage")])


def caol(name, translation, pick=None, base=UNMATCHED, use_m3b=False, max_calls=30):
    llm = FakeLLM(one_line(translation), pick)
    engine = M3Engine(llm, {"ph": [name]}, CAOL_META, max_calls=max_calls)
    engine.translate("ph", {name})
    return engine.resolve("ph", name, caol_catalog(), base, use_m3b=use_m3b), engine, llm


def test_tokens_and_names():
    assert tokens("Maker's Mark 46") == ["makers", "mark", "46"]
    assert tokens("Octomore 13.1") == ["octomore", "13.1"]
    assert tokens("Bunnahabhain Cruach-Mhòna") == ["bunnahabhain", "cruach", "mhona"]
    assert core_tokens(ProductMeta("The Balvenie 12 DoubleWood", 12, "DoubleWood", None)) == ["balvenie", "doublewood"]
    assert english_name(tr(brand_en="Caol Ila", age=12)) == "Caol Ila 12"
    assert english_name(tr(bottler_en="Signatory Vintage", distillery_en="Caol Ila", age=10,
                           edition_tokens_en=["100", "Proof"])) == "Signatory Vintage Caol Ila 10 100 Proof"
    assert english_name(tr()) is None
    assert bottler_of("signatory") == bottler_of("Signatory Vintage") == "Signatory"
    assert bottler_of("Caol Ila") is None and bottler_of(None) is None


def test_m3a_finds_official_product_as_confirm_recommended():
    r, _, llm = caol("꿀일라 12", tr(brand_en="Caol Ila", age=12))

    assert r.status == "ambiguous" and ids(r) == [P_CAOL12] and r.proposed_product_id == P_CAOL12
    [c] = r.candidates
    assert (c.rank, c.score, c.method) == (1, 0.5, "llm")
    assert c.evidence == {"rule": "M3a", "via": ["relookup", "tokens"], "englishName": "Caol Ila 12",
                          "confirmRecommended": True}
    # One M3a request with the whole photo, the target marked.
    [(kind, prompt, payload, schema)] = llm.calls
    assert (kind, payload) == ("m3a", {"lines": [{"line": 1, "name": "꿀일라 12", "target": True}]})
    assert prompt == load_prompt(TRANSLATE_PROMPT) and schema == Translation.model_json_schema()


def test_bottler_missing_vetoes_independent_bottling():
    _, engine, _ = caol("x", tr())
    assert engine._vetoes("쿨일라 10년 100프루프", tr(brand_en="Caol Ila", age=10), P_SIG10, caol_catalog())[0] == [
        "bottler_missing"]
    with_bottler = tr(bottler_en="Signatory", distillery_en="Caol Ila", age=10)
    assert engine._vetoes("시그나토리 쿨일라 10년", with_bottler, P_SIG10, caol_catalog()) == ([], [])


def test_m3b_pick_vetoed_and_none():
    t = tr(brand_en="Caol Ila", edition_tokens_en=["Secret"])
    r, engine, llm = caol("꿀일라 18", t, pick=lambda p: {"choice": "2", "reason": ""}, use_m3b=True)
    # M3a finds nothing for an unknown edition; M3b gets the brand's products in name order.
    kind, prompt, payload, schema = llm.calls[-1]
    assert (kind, prompt, schema) == ("m3b", load_prompt(PICK_PROMPT), Pick.model_json_schema())
    assert payload["menu_line"] == "꿀일라 18" and payload["context_lines"] == []
    assert payload["options"] == [{"no": "1", "name": "Caol Ila 12", "age": 12, "edition": None},
                                  {"no": "2", "name": "Caol Ila 18", "age": 18, "edition": None}]
    # The pick lacks the line's edition token -> edition_mismatch drops it; the line keeps its rule result.
    assert r is UNMATCHED
    assert engine.m3b("ph", "꿀일라 18", t, caol_catalog())[1] == [
        {"productId": str(P_CAOL18), "displayName": "Caol Ila 18", "via": ["m3b"], "rules": ["edition_mismatch"]}]

    r, _, llm = caol("꿀일라 시크릿", t, pick=lambda p: {"choice": "none", "reason": ""}, use_m3b=True)
    assert r is UNMATCHED and [k for k, *_ in llm.calls] == ["m3a", "m3b"]


def test_m3b_pick_becomes_a_candidate():
    t = tr(brand_en="Caol Ila", age=18)
    llm = FakeLLM(lambda p: {"items": [{"line": 2, **t}]}, lambda p: {"choice": "2", "reason": "연수 18"})
    engine = M3Engine(llm, {"ph": ["Caol Ila", "깔일라 열여덟"]}, CAOL_META, max_calls=30)
    engine.translate("ph", {"깔일라 열여덟"})
    m3a_vetoed = [{"productId": str(P_SIG10), "displayName": "x", "via": ["tokens"], "rules": ["age_mismatch"]}]
    engine.m3a_candidates = lambda name, t, catalog: ([], m3a_vetoed, {}, "Caol Ila 18")  # M3a found nothing

    r = engine.resolve("ph", "깔일라 열여덟", caol_catalog(), UNMATCHED, use_m3b=True)

    assert ids(r) == [P_CAOL18] and r.status == "ambiguous"
    assert r.candidates[0].evidence == {"rule": "M3b", "via": ["m3b"], "englishName": "Caol Ila 18",
                                        "vetoed": m3a_vetoed, "confirmRecommended": True}
    assert llm.calls[-1][2]["context_lines"] == ["Caol Ila"]


@pytest.mark.parametrize("choice", ["unsure", "0", "3", "x1"])
def test_m3b_without_a_valid_pick_keeps_the_rule_result(choice):
    t = tr(brand_en="Caol Ila", edition_tokens_en=["Secret"])
    r, _, _ = caol("꿀일라", t, pick=lambda p: {"choice": choice, "reason": ""}, use_m3b=True)
    assert r is UNMATCHED


def test_m3b_without_brand_products_makes_no_call():
    r, _, llm = caol("뭔가 시크릿", tr(brand_en="Nowhere", edition_tokens_en=["Secret"]), use_m3b=True)
    assert r is UNMATCHED and [k for k, *_ in llm.calls] == ["m3a"]


def test_reverse_bottler_and_age_vetoes():
    _, engine, _ = caol("x", tr())
    kept, vetoed, _, _ = engine.m3a_candidates("시그나토리 쿨일라 12년",
                                               tr(bottler_en="Signatory Vintage", distillery_en="Caol Ila", age=12),
                                               caol_catalog())
    assert kept == [] and {v["displayName"]: v["rules"] for v in vetoed}["Caol Ila 12"] == ["bottler_missing (reverse)"]
    r, _, _ = caol("시그나토리 쿨일라 12년", tr(bottler_en="Signatory Vintage", distillery_en="Caol Ila", age=12))
    assert r is UNMATCHED
    _, vetoed, _, _ = engine.m3a_candidates("꿀일라 12년", tr(brand_en="Caol Ila", age=18), caol_catalog())
    assert vetoed[0]["rules"] == ["age_mismatch"]  # the printed age wins over the translated one


def test_alias_of_other():
    _, engine, _ = caol("x", tr())
    _, vetoed, _, _ = engine.m3a_candidates("쿨일라 12년", tr(brand_en="Caol Ila", age=18), caol_catalog())
    assert "alias_of_other" in vetoed[0]["rules"]


@pytest.mark.parametrize("kind", ["non_whisky", "unclear"])
def test_lines_that_are_not_whisky_are_skipped(kind):
    r, _, llm = caol("하이볼", tr(kind=kind), use_m3b=True)
    assert r is UNMATCHED and [k for k, *_ in llm.calls] == ["m3a"]


def test_combine_merge():
    other = uuid.uuid4()
    base = ResolutionResult(status="ambiguous", candidates=(
        Candidate(other, 1, 0.8, "alias", {"brandMatch": "x", "confirmRecommended": True}),
        Candidate(P_CAOL12, 2, 0.8, "alias", {})), proposed_product_id=other)
    merged = combine(base, [P_CAOL12], "M3a")
    assert [(c.product_id, c.rank, c.method) for c in merged.candidates] == [(P_CAOL12, 1, "llm"), (other, 2, "alias")]
    assert merged.candidates[0].evidence == {"rule": "M3a", "confirmRecommended": True}  # inside the rule candidates
    assert merged.candidates[1].evidence == {"brandMatch": "x"}  # the rule's own recommendation is dropped
    assert (merged.status, merged.proposed_product_id) == ("ambiguous", P_CAOL12)
    outside = combine(base, [P_CAOL18], "M3a")
    assert len(outside.candidates) == 3 and "confirmRecommended" not in outside.candidates[0].evidence
    two = combine(UNMATCHED, [P_CAOL12, P_CAOL18], "M3a")
    assert not any("confirmRecommended" in c.evidence for c in two.candidates)
    assert "confirmRecommended" not in combine(UNMATCHED, [P_CAOL12], "M3a", {P_CAOL12}).candidates[0].evidence


def test_edition_check():
    plain = ProductMeta("Laphroaig 10", 10, None, None, ("Laphroaig 10", "라프로익 10년"))
    cs = tr(brand_en="Laphroaig", age=10, edition_tokens_en=["Cask", "Strength"])
    assert edition_check(cs, plain, ["laphroaig10"]) == (["strength"], [])  # "cask" is neutral
    qc = ProductMeta("Arran Bodega Sherry Cask", None, "Bodega Sherry Cask", None)
    assert edition_check(tr(edition_tokens_en=["Quarter", "Cask"]), qc, [])[0] == ["quarter"]
    px = ProductMeta("The Balvenie 18 Pedro Ximenez Cask", 18, "Pedro Ximenez Cask", None)
    base18 = ProductMeta("The Balvenie 18", 18, None, None)
    line = tr(edition_tokens_en=["PX"])
    assert edition_check(line, base18, []) == ([], ["px"])  # short token missing: kept, no confirm
    assert edition_check(line, px, []) == ([], ["px"])  # "px" is not a word of "Pedro Ximenez"
    with_exp = tr(edition_tokens_en=["PX"], expansions=[{"token": "PX", "expansion": "Pedro Ximenez"}])
    assert edition_check(with_exp, px, []) == ([], [])
    assert edition_check(tr(edition_tokens_en=["DR"]), ProductMeta("Hakushu DRY", None, None, None), []) == ([], ["dr"])
    sherry = ProductMeta("The Macallan 12 Sherry Oak", 12, "Sherry Oak", None)
    assert edition_check(tr(edition_tokens_en=["Sherry", "Cask"]), sherry, []) == ([], [])


def test_short_token_blocks_confirm():
    r, _, _ = caol("꿀일라 12 SR", tr(brand_en="Caol Ila", age=12, edition_tokens_en=["SR"]))
    assert ids(r) == [P_CAOL12]
    assert r.candidates[0].evidence == {"rule": "M3a", "via": ["relookup", "tokens"], "englishName": "Caol Ila 12 SR",
                                        "shortUnverified": ["sr"]}


# --- failures and the call cap ------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "stat"),
    [
        (RuntimeError("API down"), "error"),
        (TimeoutError(), "error"),
        ("not json", "parse_error"),
        ('{"items": [{"line": 1}]}', "parse_error"),  # valid JSON, wrong shape
        ("", "parse_error"),
    ],
)
def test_failed_or_invalid_m3a_keeps_the_rule_result(answer, stat, caplog):
    base = ResolutionResult(status="ambiguous", candidates=(Candidate(P_CAOL18, 1, 0.6, "alias", {"rule": "S3"}),),
                            proposed_product_id=P_CAOL18)
    llm = FakeLLM(lambda payload: answer)
    engine = M3Engine(llm, {"ph": ["꿀일라 12"]}, CAOL_META, max_calls=30)
    engine.translate("ph", {"꿀일라 12"})

    assert engine.resolve("ph", "꿀일라 12", caol_catalog(), base) is base
    assert engine.stats == {stat: 1}
    assert "API down" not in caplog.text  # only the exception type is logged


def test_failed_m3b_keeps_the_rule_result():
    r, engine, _ = caol("꿀일라", tr(brand_en="Caol Ila", edition_tokens_en=["Secret"]),
                        pick=lambda p: RuntimeError("down"), use_m3b=True)
    assert r is UNMATCHED and engine.stats == {"ok": 1, "error": 1}


def test_cap_stops_further_calls():
    names = {"p1": ["꿀일라 12"], "p2": ["꿀일라 12"]}
    llm = FakeLLM(one_line(tr(brand_en="Caol Ila", age=12)))
    engine = M3Engine(llm, names, CAOL_META, max_calls=1)
    engine.translate("p1", {"꿀일라 12"})
    engine.translate("p2", {"꿀일라 12"})

    assert len(llm.calls) == 1 and engine.calls == 1 and engine.stats == {"ok": 1, "cap_reached": 1}
    assert ids(engine.resolve("p1", "꿀일라 12", caol_catalog(), UNMATCHED)) == [P_CAOL12]
    assert engine.resolve("p2", "꿀일라 12", caol_catalog(), UNMATCHED) is UNMATCHED


def test_cap_applies_to_m3b():
    r, engine, llm = caol("꿀일라", tr(brand_en="Caol Ila", edition_tokens_en=["Secret"]), use_m3b=True, max_calls=1)
    assert r is UNMATCHED and [k for k, *_ in llm.calls] == ["m3a"] and engine.stats == {"ok": 1, "cap_reached": 1}


def test_photo_without_targets_makes_no_call():
    llm = FakeLLM(lambda payload: pytest.fail("no call expected"))
    engine = M3Engine(llm, {"ph": ["Caol Ila 12"]}, CAOL_META, max_calls=30)
    engine.translate("ph", set())
    assert engine.translation("ph", "Caol Ila 12") is None and engine.calls == 0


# --- vetoes with made-up products (test_vetoes.py) ------------------------------------------
# Fake distillery "Fernhollow" (페른홀로우); the independent bottlers are real P17 names.

B_FERN, B_FSIG, B_GM = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FERN_12, FERN_12_CS, FERN_15, SIG_FERN_12, GM_FERN_12 = (uuid.uuid4() for _ in range(5))
FERN_NAS, FERN_15_SB = uuid.uuid4(), uuid.uuid4()
FERN = {
    FERN_12: ("Fernhollow 12", 12, None, None, B_FERN, ("Fernhollow 12", "페른홀로우 12년")),
    FERN_12_CS: ("Fernhollow 12 Cask Strength", 12, "Cask Strength", None, B_FERN, ("Fernhollow 12 Cask Strength",)),
    FERN_15: ("Fernhollow 15", 15, None, None, B_FERN, ("Fernhollow 15",)),
    SIG_FERN_12: ("Signatory Vintage Fernhollow 12", 12, "Fernhollow", "Signatory", B_FSIG,
                  ("Signatory Vintage Fernhollow 12",)),
    GM_FERN_12: ("Gordon & MacPhail Fernhollow 12", 12, "Fernhollow", "Gordon & MacPhail", B_GM,
                 ("Gordon & MacPhail Fernhollow 12",)),
}
EXTRA = {
    FERN_NAS: ("Fernhollow Founders", None, "Founders", None, B_FERN, ("Fernhollow Founders",)),
    FERN_15_SB: ("Fernhollow 15 Small Batch", 15, "Small Batch", None, B_FERN, ("Fernhollow 15 Small Batch",)),
}


def fern(extra=(), drop=()):
    rows = {**FERN, **{pid: EXTRA[pid] for pid in extra}}
    rows = {pid: row for pid, row in rows.items() if pid not in drop}
    meta = {pid: ProductMeta(name, age, edition, bottler, aliases)
            for pid, (name, age, edition, bottler, _, aliases) in rows.items()}
    catalog = InMemoryCatalog(
        [ProductInfo(pid, name, age, edition, brand) for pid, (name, age, edition, _, brand, _) in rows.items()],
        [(pid, a) for pid, row in rows.items() for a in row[5]],
        [(B_FERN, "Fernhollow"), (B_FERN, "페른홀로우"), (B_FSIG, "Signatory Vintage"), (B_GM, "Gordon & MacPhail")],
    )
    return meta, catalog


def run(name, translation, extra=(), drop=()):
    """(result, vetoed by product name) for one line through M3a."""
    meta, catalog = fern(extra, drop)
    engine = M3Engine(FakeLLM(one_line(translation)), {"photo": [name]}, meta, max_calls=30)
    engine.translate("photo", {name})
    _, vetoed, _, _ = engine.m3a_candidates(name, engine.translation("photo", name), catalog)
    return engine.resolve("photo", name, catalog, UNMATCHED), {v["displayName"]: v["rules"] for v in vetoed}


def veto_rules(name, translation, pid, extra=()):
    meta, catalog = fern(extra)
    engine = M3Engine(FakeLLM(), {"photo": [name]}, meta, max_calls=30)
    return engine._vetoes(name, translation, pid, catalog)[0]


def confirmed(result):
    return result.candidates[0].evidence.get("confirmRecommended")


def test_official_line_vetoes_independent_bottlings():
    t = tr(brand_en="Fernhollow", age=12)
    assert veto_rules("페른할로우 12년", t, SIG_FERN_12) == ["bottler_missing"]
    assert veto_rules("페른할로우 12년", t, GM_FERN_12) == ["bottler_missing"]
    assert veto_rules("페른할로우 12년", t, FERN_12) == []
    r, _ = run("페른할로우 12년", t)
    assert ids(r) == [FERN_12] and confirmed(r)


def test_official_line_with_only_bottlings_in_catalog_gets_nothing():
    r, _ = run("페른할로우 12년", tr(brand_en="Fernhollow", age=12), drop={FERN_12, FERN_12_CS})
    assert r is UNMATCHED


def test_wrong_bottler_is_vetoed():
    t = tr(bottler_en="G&M", distillery_en="Fernhollow", age=12)
    assert veto_rules("G&M 페른할로우 12", t, SIG_FERN_12) == ["bottler_missing"]
    assert veto_rules("G&M 페른할로우 12", t, GM_FERN_12) == []


def test_bottler_line_never_reaches_official_product():
    r, vetoed = run("시그나토리 페른홀로우 12년", tr(bottler_en="Signatory Vintage", distillery_en="Fernhollow", age=12))
    assert ids(r) == [SIG_FERN_12] and confirmed(r)
    assert vetoed["Fernhollow 12"] == ["bottler_missing (reverse)"]
    assert {"productId": str(FERN_12), "displayName": "Fernhollow 12", "via": ["tokens"],
            "rules": ["bottler_missing (reverse)"]} in r.candidates[0].evidence["vetoed"]


def test_bottler_line_with_only_official_in_catalog_gets_nothing():
    t = tr(bottler_en="Signatory", distillery_en="Fernhollow", age=12)
    r, vetoed = run("시그나토리 페른홀로우 12년", t, drop={SIG_FERN_12, GM_FERN_12})
    assert r is UNMATCHED and vetoed["Fernhollow 12"] == ["bottler_missing (reverse)"]


def test_printed_age_beats_the_translation():
    r, vetoed = run("페른할로우 12yo", tr(brand_en="Fernhollow", age=15))
    assert FERN_15 not in ids(r) and vetoed["Fernhollow 15"] == ["age_mismatch"]


def test_age_on_menu_and_product_without_age():
    t = tr(brand_en="Fernhollow", age=10, edition_tokens_en=["Founders"])
    assert veto_rules("페른홀로우 파운더스 10년", t, FERN_NAS, extra={FERN_NAS}) == ["age_mismatch"]
    assert veto_rules("페른홀로우 파운더스", tr(brand_en="Fernhollow", edition_tokens_en=["Founders"]), FERN_NAS,
                      extra={FERN_NAS}) == []


def test_line_that_is_another_products_alias():
    _, vetoed = run("페른홀로우 12년", tr(brand_en="Fernhollow", age=15))
    assert "alias_of_other" in vetoed["Fernhollow 15"]


def test_edition_on_menu_missing_in_product():
    t = tr(brand_en="Fernhollow", age=12, edition_tokens_en=["Cask", "Strength"])
    r, vetoed = run("페른홀로우 12 캐스크 스트렝스", t, drop={FERN_12_CS})
    assert r is UNMATCHED and vetoed["Fernhollow 12"] == ["edition_mismatch"]
    r, _ = run("페른홀로우 12 캐스크 스트렝스", t)
    assert ids(r) == [FERN_12_CS] and confirmed(r)


def test_neutral_words_are_not_evidence_either_way():
    r, vetoed = run("페른홀로우 12 오크", tr(brand_en="Fernhollow", age=12, edition_tokens_en=["Oak"]))
    assert FERN_12 in ids(r) and "Fernhollow 12" not in vetoed


def test_short_token_keeps_candidate_without_confirm():
    r, _ = run("페른홀로우 15 SB", tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"]))
    assert ids(r) == [FERN_15] and not confirmed(r)
    assert r.candidates[0].evidence["shortUnverified"] == ["sb"]


def test_short_token_with_expansion():
    t = tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"], expansions=[{"token": "SB", "expansion": "Small Batch"}])
    r, _ = run("페른홀로우 15 SB", t, extra={FERN_15_SB})
    # Small Batch fits through the expansion; the plain 15 lacks "SB" but is only kept without confirm.
    assert set(ids(r)) == {FERN_15_SB, FERN_15}
    assert not any(c.evidence.get("confirmRecommended") for c in r.candidates)
    r, _ = run("페른홀로우 15 SB", t, extra={FERN_15_SB}, drop={FERN_15})
    assert ids(r) == [FERN_15_SB] and confirmed(r)


# --- the copies of the frozen prompts, and parity with ai/match_llm/m3.py ------------------


def test_prompts_are_the_frozen_m3_prompts():
    for path in (TRANSLATE_PROMPT, PICK_PROMPT):
        assert prompt_sha256(load_prompt(path)) == PROMPT_SHA256[path.name]


@pytest.fixture
def m3():
    if not (AI_MATCH_LLM / "m3.py").exists():
        pytest.skip("ai/match_llm is not checked out")
    sys.path.insert(0, str(AI_MATCH_LLM))
    try:
        import m3

        yield m3
    finally:
        sys.path.remove(str(AI_MATCH_LLM))


def test_prompts_and_schemas_match_ai_match_llm(m3):
    for path in (TRANSLATE_PROMPT, PICK_PROMPT):
        assert load_prompt(path) == (AI_MATCH_LLM / path.name).read_text(encoding="utf-8")
    assert m3.TRANSLATE_PROMPT.name == TRANSLATE_PROMPT.name and m3.PICK_PROMPT.name == PICK_PROMPT.name
    assert Translation.model_json_schema() == m3.Translation.model_json_schema()
    assert Pick.model_json_schema() == m3.Pick.model_json_schema()
    assert (m3.LLM_SCORE, m3.CONTEXT_LINES, m3.SHORT_LATIN, m3.BASE_STAGES) == (
        LLM_SCORE, CONTEXT_LINES, SHORT_LATIN, BASE_STAGES)
    assert (m3.IB_BOTTLERS, m3.GENERIC_TOKENS, m3.NEUTRAL_TOKENS) == (IB_BOTTLERS, GENERIC_TOKENS, NEUTRAL_TOKENS)


PARITY_CASES = [
    # (lines, line resolved, translation, pick choice, use M3b, extra, drop)
    (["페른할로우 12년"], "페른할로우 12년", tr(brand_en="Fernhollow", age=12), None, False, (), ()),
    (["시그나토리 페른홀로우 12년"], "시그나토리 페른홀로우 12년",
     tr(bottler_en="Signatory Vintage", distillery_en="Fernhollow", age=12), None, False, (), ()),
    (["페른할로우 12yo"], "페른할로우 12yo", tr(brand_en="Fernhollow", age=15), None, False, (), ()),
    (["페른홀로우 12 캐스크 스트렝스"], "페른홀로우 12 캐스크 스트렝스",
     tr(brand_en="Fernhollow", age=12, edition_tokens_en=["Cask", "Strength"]), None, False, (), ()),
    (["페른홀로우 15 SB"], "페른홀로우 15 SB",
     tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"], expansions=[{"token": "SB", "expansion": "Small Batch"}]),
     None, False, {FERN_15_SB}, ()),
    (["페른홀로우", "페른 시크릿"], "페른 시크릿",  # M3b picks Fernhollow 15, vetoed (edition_mismatch)
     tr(brand_en="Fernhollow", edition_tokens_en=["Secret"]), "3", True, (), ()),
    (["페른 파운더스"], "페른 파운더스",
     tr(brand_en="Fernhollow", edition_tokens_en=["Founder"]), "1", True, {FERN_NAS}, ()),
    (["하이볼"], "하이볼", tr(kind="non_whisky"), None, True, (), ()),
]


@pytest.mark.parametrize(("lines", "name", "translation", "choice", "use_m3b", "extra", "drop"), PARITY_CASES)
def test_same_result_and_requests_as_m3(m3, lines, name, translation, choice, use_m3b, extra, drop):
    meta, catalog = fern(extra, drop)
    line_no = lines.index(name) + 1
    answers = {"m3a": {"items": [{"line": line_no, **translation}]},
               "m3b": {"choice": choice or "unsure", "reason": ""}}
    base = ResolutionResult(status="ambiguous", candidates=(Candidate(FERN_15, 1, 0.8, "alias", {"rule": "S2"}),),
                            proposed_product_id=FERN_15)

    class OldLLM:
        calls = []

        def call(self, kind, prompt, payload, schema):
            self.calls.append((kind, prompt, payload, schema.model_json_schema()))
            return answers[kind], {"key": "fake"}

    old_llm = OldLLM()
    old = m3.M3(old_llm, {"ph": lines}, {pid: m3.ProductMeta(*vars_of(m)) for pid, m in meta.items()})
    old.translate("ph", {name})
    old_result, info = old.resolve("ph", name, catalog, base, "merge", use_m3b)

    new_llm = FakeLLM(lambda p: answers["m3a"], lambda p: answers["m3b"])
    new = M3Engine(new_llm, {"ph": lines}, meta, max_calls=30)
    new.translate("ph", {name})
    new_result = new.resolve("ph", name, catalog, base, use_m3b=use_m3b)

    assert [(k, p, payload, s) for k, p, payload, s in new_llm.calls] == old_llm.calls
    assert (new_result.status, new_result.proposed_product_id) == (old_result.status, old_result.proposed_product_id)
    def summary(result):
        return [(c.product_id, c.rank, c.score, c.method, c.evidence.get("confirmRecommended")) for c in result.candidates]

    assert summary(new_result) == summary(old_result)
    for new_c, old_c in zip(new_result.candidates, old_result.candidates, strict=True):
        if old_c.method != "llm":
            assert new_c.evidence == old_c.evidence
            continue
        assert new_c.evidence["rule"] == old_c.evidence["m3"] == info["stage"]
        assert [(v["displayName"], v["via"], v["rules"]) for v in new_c.evidence.get("vetoed", [])] == [
            (v["product"], v["via"], v["rules"]) for v in info["vetoed"]]
        assert new_c.evidence["englishName"] == info["english_name"]
        short = info.get("short_unverified", {}).get(meta[new_c.product_id].display_name)
        assert new_c.evidence.get("shortUnverified") == short


def vars_of(meta):
    return meta.display_name, meta.age_years, meta.edition_name, meta.bottler, meta.aliases
