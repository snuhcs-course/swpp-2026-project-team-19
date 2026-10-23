"""Offline tests for the M3 layer (no API call: a fake LLM returns fixed outputs)."""

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from m3 import M3, ProductMeta, bottler_of, combine, core_tokens, english_name, tokens  # noqa: E402
from app.matching.memory_catalog import InMemoryCatalog  # noqa: E402
from app.matching.types import Candidate, ProductInfo, ResolutionResult  # noqa: E402

from llm import CacheMiss, CachedLLM  # noqa: E402

B_CAOL, B_SIG = uuid.uuid4(), uuid.uuid4()
P_CAOL12, P_SIG10, P_CAOL18 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
META = {
    P_CAOL12: ProductMeta("Caol Ila 12", 12, None, None),
    P_CAOL18: ProductMeta("Caol Ila 18", 18, None, None),
    P_SIG10: ProductMeta("Signatory Vintage 100 Proof Caol Ila 10", 10, "100 Proof Caol Ila", "Signatory"),
}


def catalog():
    products = [ProductInfo(P_CAOL12, "Caol Ila 12", 12, None, B_CAOL), ProductInfo(P_CAOL18, "Caol Ila 18", 18, None, B_CAOL),
                ProductInfo(P_SIG10, "Signatory Vintage 100 Proof Caol Ila 10", 10, "100 Proof Caol Ila", B_SIG)]
    aliases = [(P_CAOL12, "Caol Ila 12"), (P_CAOL12, "쿨일라 12년"), (P_CAOL18, "Caol Ila 18"),
               (P_SIG10, "Signatory Vintage 100 Proof Caol Ila 10")]
    return InMemoryCatalog(products, aliases, [(B_CAOL, "Caol Ila"), (B_SIG, "Signatory Vintage")])


class FakeLLM:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def call(self, kind, prompt, payload, schema):
        self.calls.append((kind, payload))
        return self.outputs[kind](payload), {"key": "fake"}


def tr(**kw):
    base = {"bottler_en": None, "distillery_en": None, "brand_en": None, "age": None, "edition_tokens_en": [],
            "kind": "whisky"}
    return {**base, **kw}


def test_tokens_and_names():
    assert tokens("Maker's Mark 46") == ["makers", "mark", "46"]
    assert tokens("Octomore 13.1") == ["octomore", "13.1"]
    assert tokens("Bunnahabhain Cruach-Mhòna") == ["bunnahabhain", "cruach", "mhona"]
    assert core_tokens(ProductMeta("The Balvenie 12 DoubleWood", 12, "DoubleWood", None)) == ["balvenie", "doublewood"]
    assert english_name(tr(brand_en="Caol Ila", age=12)) == "Caol Ila 12"
    assert english_name(tr(bottler_en="Signatory Vintage", distillery_en="Caol Ila", age=10,
                           edition_tokens_en=["100", "Proof"])) == "Signatory Vintage Caol Ila 10 100 Proof"
    assert bottler_of("signatory") == bottler_of("Signatory Vintage") == "Signatory"
    assert bottler_of("Caol Ila") is None


def engine(translation, pick=None):
    llm = FakeLLM({"m3a": lambda p: {"items": [{"line": 1, **translation}]},
                   "m3b": pick or (lambda p: {"choice": "unsure", "reason": ""})})
    m = M3(llm, {"ph": ["NAME"]}, META)
    m.translate("ph", {"NAME"})
    return m, llm


def resolve(m, name="NAME", base=ResolutionResult(status="unmatched"), **kw):
    m.lines["ph"] = [name]
    m._translations["ph"] = {name: m._translations["ph"]["NAME"]}
    return m.resolve("ph", name, catalog(), base, **kw)


def test_m3a_finds_official_product_as_confirm_recommended():
    m, _ = engine(tr(brand_en="Caol Ila", age=12))
    r, info = resolve(m, "꿀일라 12")
    assert r.status == "ambiguous" and [c.product_id for c in r.candidates] == [P_CAOL12]
    assert r.candidates[0].method == "llm" and r.candidates[0].evidence["confirmRecommended"]
    assert info["vetoed"] == []


def test_bottler_missing_vetoes_independent_bottling():
    m, _ = engine(tr(brand_en="Caol Ila", age=10))
    assert m._vetoes("쿨일라 10년 100프루프", tr(brand_en="Caol Ila", age=10), P_SIG10, catalog())[0] == ["bottler_missing"]
    with_bottler = tr(bottler_en="Signatory", distillery_en="Caol Ila", age=10)
    assert m._vetoes("시그나토리 쿨일라 10년", with_bottler, P_SIG10, catalog()) == ([], [])


def test_m3b_pick_and_none():
    m, llm = engine(tr(brand_en="Caol Ila", edition_tokens_en=["Secret"]), pick=lambda p: {"choice": "2", "reason": ""})
    r, info = resolve(m, "꿀일라 18", use_m3b=True)  # M3a: unknown edition -> nothing
    assert [o["name"] for o in llm.calls[-1][1]["options"]] == ["Caol Ila 12", "Caol Ila 18"]
    # the pick lacks the line's edition token -> edition_mismatch drops it
    assert info["stage"] == "M3b" and info["picked"] == "Caol Ila 18" and r.status == "unmatched"
    assert info["vetoed"] == [{"product": "Caol Ila 18", "via": ["m3b"], "rules": ["edition_mismatch"]}]
    m, _ = engine(tr(brand_en="Caol Ila", edition_tokens_en=["Secret"]), pick=lambda p: {"choice": "none", "reason": ""})
    r, info = resolve(m, "꿀일라 시크릿", use_m3b=True)
    assert info["m3b"] == "none" and r.status == "unmatched"


def test_reverse_bottler_and_age_vetoes():
    m, _ = engine(tr(bottler_en="Signatory Vintage", distillery_en="Caol Ila", age=12))
    r, info = resolve(m, "시그나토리 쿨일라 12년")
    rules = {v["product"]: v["rules"] for v in info["vetoed"]}
    assert rules["Caol Ila 12"] == ["bottler_missing (reverse)"]
    assert r.status == "unmatched"
    m, _ = engine(tr(brand_en="Caol Ila", age=18))
    r, info = resolve(m, "꿀일라 12년")  # printed age wins over the translated one
    assert info["vetoed"][0]["rules"] == ["age_mismatch"]


def test_alias_of_other():
    m, _ = engine(tr(brand_en="Caol Ila", age=18))
    _, info = resolve(m, "쿨일라 12년")
    assert "alias_of_other" in info["vetoed"][0]["rules"]


def test_non_whisky_is_skipped():
    m, llm = engine(tr(kind="non_whisky"))
    base = ResolutionResult(status="unmatched")
    r, info = resolve(m, base=base, use_m3b=True)
    assert r is base and info["skipped"] == "non_whisky" and [k for k, _ in llm.calls] == ["m3a"]


def test_combine_merge_and_replace():
    other = uuid.uuid4()
    base = ResolutionResult(status="ambiguous", candidates=(
        Candidate(other, 1, 0.8, "alias", {"brandMatch": "x"}), Candidate(P_CAOL12, 2, 0.8, "alias", {})),
        proposed_product_id=other)
    merged = combine(base, [P_CAOL12], "merge", "M3a")
    assert [c.product_id for c in merged.candidates] == [P_CAOL12, other]
    assert merged.candidates[0].evidence["confirmRecommended"]  # the LLM pick is inside the S1-S3 candidates
    outside = combine(base, [P_CAOL18], "merge", "M3a")
    assert len(outside.candidates) == 3 and "confirmRecommended" not in outside.candidates[0].evidence
    replaced = combine(base, [P_CAOL18], "replace", "M3a")
    assert [c.product_id for c in replaced.candidates] == [P_CAOL18] and replaced.candidates[0].evidence[
        "confirmRecommended"]


def test_edition_check():
    from m3 import edition_check
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
    m, _ = engine(tr(brand_en="Caol Ila", age=12, edition_tokens_en=["SR"]))
    r, info = resolve(m, "꿀일라 12 SR")
    assert [c.product_id for c in r.candidates] == [P_CAOL12]
    assert "confirmRecommended" not in r.candidates[0].evidence and info["short_unverified"] == {"Caol Ila 12": ["sr"]}


def test_cache_only_never_calls(tmp_path):
    llm = CachedLLM(tmp_path, cache_only=True)
    from m3 import Pick
    with pytest.raises(CacheMiss):
        llm.call("m3b", "prompt", {"a": 1}, Pick)
    assert llm.api_calls == 0


def test_cache_hit(tmp_path):
    from m3 import Pick

    class Client:
        class interactions:
            @staticmethod
            def create(**kw):
                class Usage:
                    total_input_tokens, total_output_tokens, total_thought_tokens = 10, 5, 0

                class R:
                    output_text = json.dumps({"choice": "1", "reason": "r"})
                    usage = Usage()
                return R()

    llm = CachedLLM(tmp_path, min_interval=0, client=Client())
    first, _ = llm.call("m3b", "prompt", {"a": 1}, Pick)
    again = CachedLLM(tmp_path, cache_only=True)
    second, _ = again.call("m3b", "prompt", {"a": 1}, Pick)
    assert first == second == {"choice": "1", "reason": "r"} and llm.api_calls == 1 and again.api_calls == 0
