"""The tool-calling matching layer (app.matching.tool_layer). No API call: a scripted fake model answers."""

import uuid

import pytest

from app.matching.llm_layer import ProductMeta
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.tool_layer import (
    KINDS,
    MAX_TURNS,
    TOOL_PROMPT,
    TOOLS,
    CatalogSearch,
    ToolEngine,
    ToolSession,
    words,
)
from app.matching.types import Candidate, ProductInfo, ResolutionResult

UNMATCHED = ResolutionResult(status="unmatched")

# Fake distillery "Fernhollow" (페른홀로우) and a real P17 bottler, as in test_llm_layer.py.
B_FERN, B_SIG = uuid.uuid4(), uuid.uuid4()
FERN_12, FERN_15, FERN_12_PX, SIG_12, HIDDEN = (uuid.uuid4() for _ in range(5))
ROWS = {
    FERN_12: ("Fernhollow 12", 12, None, None, B_FERN, ("Fernhollow 12", "페른홀로우 12년")),
    FERN_15: ("Fernhollow 15", 15, None, None, B_FERN, ("Fernhollow 15", "페른홀로우15")),
    FERN_12_PX: ("Fernhollow 12 PX Cask", 12, "PX Cask", None, B_FERN, ("Fernhollow 12 PX Cask",)),
    SIG_12: ("Signatory Vintage Fernhollow 12", 12, "Fernhollow", "Signatory", B_SIG,
             ("Signatory Vintage Fernhollow 12",)),
}
META = {pid: ProductMeta(name, age, edition, bottler, aliases + (("메뉴에만 있는 표기",) if pid == FERN_15 else ()))
        for pid, (name, age, edition, bottler, _, aliases) in ROWS.items()}


def catalog():
    return InMemoryCatalog(
        [ProductInfo(pid, name, age, edition, brand) for pid, (name, age, edition, _, brand, _) in ROWS.items()]
        + [ProductInfo(HIDDEN, "Not In Meta", None, None, B_FERN)],
        [(pid, a) for pid, row in ROWS.items() for a in row[5]] + [(HIDDEN, "Not In Meta")],
        [(B_FERN, "Fernhollow"), (B_FERN, "페른홀로우"), (B_SIG, "Signatory Vintage")],
    )


def call(name, **args):
    return {"name": name, "args": args, "sig": None}


def answer(line=1, product_id="", sure=True, **kw):
    a = {"line": line, "product_id": product_id, "sure": sure, "bottler_en": "", "distillery_en": "",
         "brand_en": "Fernhollow", "age": 0, "edition_tokens_en": [], "kind": "whisky"}
    a.update(kw)
    return a


class Script:
    """Turn i returns steps[i](history); a step may be an exception. Records every history it was given."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.seen = []

    def step(self, system, history, tools):
        self.seen.append([dict(m) for m in history])
        step = self.steps[len(self.seen) - 1]
        if isinstance(step, Exception):
            raise step
        return {"calls": step(history), "usage": {}}


def search_then_submit(query, pick=0, **kw):
    """Search `query`, then submit the `pick`-th result for line 1."""
    def submit(history):
        results = history[-1]["responses"][0]["response"]["results"]
        return [call("submit_answers", answers=[answer(product_id=results[pick]["product_id"], **kw)])]
    return Script(lambda h: [call("search_catalog", query=query)], submit)


def resolve(name, script, base=UNMATCHED):
    engine = ToolEngine(script, {"ph": [name]}, META)
    cat = catalog()
    engine.translate("ph", {name}, cat)
    return engine.resolve("ph", name, cat, base), engine


# --- search ----------------------------------------------------------------------------

def test_words_split_latin_and_hangul():
    assert words("Maker's Mark 46 (메이커스)") == ["makers", "mark", "46", "메이커스"]


def test_search_ranks_rule_hits_first_and_finds_hangul_inside_aliases():
    search = CatalogSearch(catalog(), META)
    assert search.search("Fernhollow 12")[0] == FERN_12
    assert FERN_15 in search.search("페른홀로우")  # inside "페른홀로우15"
    assert search.search("") == [] and search.search("12") == []
    assert len(search.search("Fernhollow", limit=2)) == 2


def test_search_uses_only_aliases_live_in_the_catalog():
    search = CatalogSearch(catalog(), META)
    assert search.search("메뉴에만") == []  # an alias of the product meta that this catalog does not hold
    assert HIDDEN not in search.search("Not In Meta")  # a catalog product without meta is not offered
    assert search.describe(SIG_12) == {"name": "Signatory Vintage Fernhollow 12", "age": 12, "edition": "Fernhollow",
                                       "bottler": "Signatory"}
    assert search.describe(FERN_15, full=True)["aliases"] == ["Fernhollow 15", "페른홀로우15"]


# --- conversation ----------------------------------------------------------------------

def test_session_search_get_and_submit():
    def get(history):
        handle = history[-1]["responses"][0]["response"]["results"][0]["product_id"]
        return [call("get_product", product_id=handle), call("get_product", product_id="p99"), call("frobnicate")]

    def submit(history):
        responses = [r["response"] for r in history[-1]["responses"]]
        assert responses[0]["aliases"] and "error" in responses[1] and "error" in responses[2]
        return [call("submit_answers", answers=[answer(product_id=responses[0]["product_id"], age=12),
                                                answer(product_id="p1"), answer(line=2, product_id="p42"),
                                                "junk", {"line": "x"},
                                                answer(line=3, kind="beer", brand_en="")])]

    script = Script(lambda h: [call("search_catalog", query="Fernhollow 12")], get, submit)
    session = ToolSession(script, CatalogSearch(catalog(), META), "prompt")
    answers = session.run(["Fernhollow 12", "x", "y"], {"Fernhollow 12", "y"})
    assert answers[1]["product"] == FERN_12 and answers[1]["age"] == 12 and answers[1]["sure"]
    assert answers[3]["kind"] == "unclear" and answers[3]["product"] is None and answers[3]["brand_en"] is None
    assert answers[2]["product"] is None  # an id the model was never shown
    assert len(answers) == 3  # the second answer for line 1, "junk" and a non-int line are dropped
    assert session.stats == {"turns": 3, "search": 1, "get": 2, "unknown_tool": 1, "invented_id": 1}
    first = script.seen[0][0]["text"]
    assert '"target": true' in first and '"target": false' in first


def test_no_call_and_too_many_turns_give_no_answer():
    session = ToolSession(Script(lambda h: []), CatalogSearch(catalog(), META), "prompt")
    assert session.run(["a"], {"a"}) is None and session.stats["no_call"] == 1
    endless = Script(*[lambda h: [call("search_catalog", query="Fernhollow")]] * MAX_TURNS)
    session = ToolSession(endless, CatalogSearch(catalog(), META), "prompt")
    assert session.run(["a"], {"a"}) is None and session.stats["max_turns"] == 1


# --- resolving a line -------------------------------------------------------------------

def test_sure_pick_is_confirm_recommended_and_never_exact():
    result, engine = resolve("페른홀로우 12년", search_then_submit("Fernhollow 12", age=12))
    assert result.status == "ambiguous" and result.candidates[0].product_id == FERN_12
    assert result.candidates[0].method == "llm" and result.candidates[0].evidence["confirmRecommended"]
    assert result.candidates[0].evidence["via"] == ["tools"] and engine.stats["ok"] == 1


def test_unsure_pick_is_a_candidate_without_confirm():
    result, _ = resolve("페른홀로우 12년", search_then_submit("Fernhollow 12", age=12, sure=False))
    assert result.candidates[0].product_id == FERN_12
    assert not result.candidates[0].evidence.get("confirmRecommended")


def test_age_veto_drops_the_pick():
    script = search_then_submit("Fernhollow 15", age=12)
    result, engine = resolve("페른홀로우 12년", script)
    assert result is UNMATCHED and engine.stats["vetoed"] == 1


def test_edition_word_missing_in_product_only_withholds_confirm():
    result, engine = resolve("페른홀로우 12 솔리스트", search_then_submit("Fernhollow 12", age=12,
                                                                    edition_tokens_en=["Solist"]))
    assert result.candidates[0].product_id == FERN_12
    assert result.candidates[0].evidence["editionUnverified"]
    assert not result.candidates[0].evidence.get("confirmRecommended") and engine.stats["edition_unverified"] == 1


def test_unverified_short_token_withholds_confirm():
    result, _ = resolve("페른홀로우 12 DR", search_then_submit("Fernhollow 12", age=12, edition_tokens_en=["DR"]))
    assert result.candidates[0].product_id == FERN_12
    assert not result.candidates[0].evidence.get("confirmRecommended")


def test_pick_outside_rule_candidates_is_not_confirm_recommended():
    base = ResolutionResult(status="ambiguous", candidates=(Candidate(FERN_15, 1, 0.6, "edit_distance"),),
                            proposed_product_id=FERN_15)
    result, _ = resolve("페른홀로우 12년", search_then_submit("Fernhollow 12", age=12), base)
    assert [c.product_id for c in result.candidates] == [FERN_12, FERN_15]
    assert not result.candidates[0].evidence.get("confirmRecommended")


@pytest.mark.parametrize("submitted", [answer(), answer(product_id="p1", kind="non_whisky")])
def test_no_product_or_not_whisky_keeps_the_rule_result(submitted):
    script = Script(lambda h: [call("search_catalog", query="Fernhollow")],
                    lambda h: [call("submit_answers", answers=[submitted])])
    result, _ = resolve("페른홀로우", script)
    assert result is UNMATCHED


def test_failures_keep_the_rule_result():
    result, engine = resolve("페른홀로우 12년", Script(RuntimeError("503")))
    assert result is UNMATCHED and engine.stats["error"] == 1
    result, engine = resolve("페른홀로우 12년", Script(lambda h: []))
    assert result is UNMATCHED and engine.stats["no_answer"] == 1


def test_photo_without_targets_makes_no_call_and_catalog_search_is_reused():
    script = Script(lambda h: [call("submit_answers", answers=[answer()])],
                    lambda h: [call("submit_answers", answers=[answer()])])
    engine = ToolEngine(script, {"a": ["x"], "b": ["y"], "c": ["z"]}, META)
    cat = catalog()
    engine.translate("a", set(), cat)
    engine.translate("b", {"y"}, cat)
    engine.translate("c", {"z"}, cat)
    assert len(script.seen) == 2 and len(engine._searches) == 1
    assert engine.answer("a", "x") is None and engine.answer("b", "y")["product"] is None


def test_prompt_and_tool_declarations():
    assert "submit_answers" in TOOL_PROMPT.read_text(encoding="utf-8")
    assert [t["name"] for t in TOOLS] == ["search_catalog", "get_product", "submit_answers"]
    item = TOOLS[2]["parameters"]["properties"]["answers"]["items"]
    assert item["properties"]["kind"]["enum"] == list(KINDS)
