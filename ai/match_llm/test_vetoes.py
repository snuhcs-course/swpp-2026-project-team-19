"""Veto tests for the M3 layer with made-up products that are not in the eval set or catalog.

Fake distillery "Fernhollow" (페른홀로우) and its products; the independent bottler is a real
P17 bottler name (bottler detection uses the fixed list), the products are not real.
Covers: bottler_missing in both directions, age_mismatch, alias_of_other, edition_mismatch,
and the short-token rule (kept, no confirm recommended). No API call.
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from m3 import M3, ProductMeta  # noqa: E402
from app.matching.memory_catalog import InMemoryCatalog  # noqa: E402
from app.matching.types import ProductInfo, ResolutionResult  # noqa: E402

B_FERN, B_SIG, B_GM = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FERN_12 = uuid.uuid4()  # official
FERN_12_CS = uuid.uuid4()  # official, edition
FERN_15 = uuid.uuid4()  # official
SIG_FERN_12 = uuid.uuid4()  # Signatory Vintage bottling of Fernhollow
GM_FERN_12 = uuid.uuid4()  # Gordon & MacPhail bottling of Fernhollow

PRODUCTS = {
    FERN_12: ("Fernhollow 12", 12, None, None, B_FERN, ("Fernhollow 12", "페른홀로우 12년")),
    FERN_12_CS: ("Fernhollow 12 Cask Strength", 12, "Cask Strength", None, B_FERN, ("Fernhollow 12 Cask Strength",)),
    FERN_15: ("Fernhollow 15", 15, None, None, B_FERN, ("Fernhollow 15",)),
    SIG_FERN_12: ("Signatory Vintage Fernhollow 12", 12, "Fernhollow", "Signatory", B_SIG,
                  ("Signatory Vintage Fernhollow 12",)),
    GM_FERN_12: ("Gordon & MacPhail Fernhollow 12", 12, "Fernhollow", "Gordon & MacPhail", B_GM,
                 ("Gordon & MacPhail Fernhollow 12",)),
}
META = {pid: ProductMeta(name, age, edition, bottler, aliases)
        for pid, (name, age, edition, bottler, _, aliases) in PRODUCTS.items()}


def catalog(drop=()):
    products = [ProductInfo(pid, name, age, edition, brand)
                for pid, (name, age, edition, _, brand, _) in PRODUCTS.items() if pid not in drop]
    aliases = [(pid, a) for pid, row in PRODUCTS.items() if pid not in drop for a in row[5]]
    brands = [(B_FERN, "Fernhollow"), (B_FERN, "페른홀로우"), (B_SIG, "Signatory Vintage"), (B_GM, "Gordon & MacPhail")]
    return InMemoryCatalog(products, aliases, brands)


def tr(**kw):
    return {"bottler_en": None, "distillery_en": None, "brand_en": None, "age": None, "edition_tokens_en": [],
            "expansions": [], "kind": "whisky", **kw}


class FixedLLM:
    def __init__(self, translation):
        self.translation = translation

    def call(self, kind, prompt, payload, schema):
        assert kind == "m3a"
        return {"items": [{"line": 1, **self.translation}]}, {"key": "fixed"}


def run(name, translation, drop=(), base=ResolutionResult(status="unmatched")):
    m = M3(FixedLLM(translation), {"photo": [name]}, META)
    m.translate("photo", {name})
    return m.resolve("photo", name, catalog(drop), base)


def ids(r):
    return [c.product_id for c in r.candidates]


def vetoed(info):
    return {META_NAME[v["product"]]: v["rules"] for v in info["vetoed"]}


META_NAME = {meta.display_name: pid for pid, meta in META.items()}


# --- bottler_missing, both directions ------------------------------------------------

def veto_rules(name, translation, pid, drop=()):
    m = M3(FixedLLM(translation), {"photo": [name]}, META)
    return m._vetoes(name, translation, pid, catalog(drop))[0]


def test_official_line_vetoes_independent_bottlings():
    """Distillery name only on the menu: any bottling offered (here checked directly; with brand =
    bottler in the catalog, relookup and the token rule do not surface it) is vetoed."""
    t = tr(brand_en="Fernhollow", age=12)
    assert veto_rules("페른할로우 12년", t, SIG_FERN_12) == ["bottler_missing"]
    assert veto_rules("페른할로우 12년", t, GM_FERN_12) == ["bottler_missing"]
    assert veto_rules("페른할로우 12년", t, FERN_12) == []
    r, info = run("페른할로우 12년", t)
    assert ids(r) == [FERN_12] and r.candidates[0].evidence.get("confirmRecommended")


def test_official_line_with_only_bottlings_in_catalog_gets_nothing():
    """The P18 c false merge: the official 12 is not in the catalog, only bottlings of it."""
    r, _ = run("페른할로우 12년", tr(brand_en="Fernhollow", age=12), drop={FERN_12, FERN_12_CS})
    assert r.status == "unmatched"


def test_wrong_bottler_is_vetoed():
    t = tr(bottler_en="G&M", distillery_en="Fernhollow", age=12)
    assert veto_rules("G&M 페른할로우 12", t, SIG_FERN_12) == ["bottler_missing"]
    assert veto_rules("G&M 페른할로우 12", t, GM_FERN_12) == []


def test_bottler_line_never_reaches_official_product():
    """Bottler on the menu (reverse): the official product is vetoed, the other bottler too."""
    t = tr(bottler_en="Signatory Vintage", distillery_en="Fernhollow", age=12)
    r, info = run("시그나토리 페른홀로우 12년", t)
    assert ids(r) == [SIG_FERN_12] and r.candidates[0].evidence.get("confirmRecommended")
    assert vetoed(info)[FERN_12] == ["bottler_missing (reverse)"]  # found by the token rule


def test_bottler_line_with_only_official_in_catalog_gets_nothing():
    t = tr(bottler_en="Signatory", distillery_en="Fernhollow", age=12)
    r, info = run("시그나토리 페른홀로우 12년", t, drop={SIG_FERN_12, GM_FERN_12})
    assert r.status == "unmatched"
    assert vetoed(info)[FERN_12] == ["bottler_missing (reverse)"]


# --- age_mismatch -------------------------------------------------------------------

def test_printed_age_beats_the_translation():
    """The translation says 15, the menu prints 12: the 15 found from the translation is vetoed."""
    r, info = run("페른할로우 12yo", tr(brand_en="Fernhollow", age=15))  # not an alias spelling
    assert FERN_15 not in ids(r)
    assert vetoed(info)[FERN_15] == ["age_mismatch"]


def test_age_on_menu_and_product_without_age():
    nas = uuid.uuid4()
    PRODUCTS[nas] = ("Fernhollow Founders", None, "Founders", None, B_FERN, ("Fernhollow Founders",))
    META[nas] = ProductMeta("Fernhollow Founders", None, "Founders", None, ("Fernhollow Founders",))
    META_NAME["Fernhollow Founders"] = nas
    try:
        t = tr(brand_en="Fernhollow", age=10, edition_tokens_en=["Founders"])
        assert veto_rules("페른홀로우 파운더스 10년", t, nas) == ["age_mismatch"]
        assert veto_rules("페른홀로우 파운더스", tr(brand_en="Fernhollow", edition_tokens_en=["Founders"]), nas) == []
    finally:
        del PRODUCTS[nas], META[nas], META_NAME["Fernhollow Founders"]


# --- alias_of_other -----------------------------------------------------------------

def test_line_that_is_another_products_alias():
    """"페른홀로우 12년" is a registered alias of Fernhollow 12; a translation pointing at 15 is vetoed."""
    _, info = run("페른홀로우 12년", tr(brand_en="Fernhollow", age=15))
    assert "alias_of_other" in vetoed(info)[FERN_15]


# --- edition_mismatch and short tokens ----------------------------------------------

def test_edition_on_menu_missing_in_product():
    """Menu "Cask Strength", catalog without it: the plain 12 must not be offered."""
    t = tr(brand_en="Fernhollow", age=12, edition_tokens_en=["Cask", "Strength"])
    r, info = run("페른홀로우 12 캐스크 스트렝스", t, drop={FERN_12_CS})
    assert r.status == "unmatched"
    assert vetoed(info)[FERN_12] == ["edition_mismatch"]
    r, _ = run("페른홀로우 12 캐스크 스트렝스", t)
    assert ids(r) == [FERN_12_CS] and r.candidates[0].evidence.get("confirmRecommended")


def test_neutral_words_are_not_evidence_either_way():
    """"Oak" / "Cask" alone do not veto the plain product."""
    r, info = run("페른홀로우 12 오크", tr(brand_en="Fernhollow", age=12, edition_tokens_en=["Oak"]))
    assert FERN_12 in ids(r) and FERN_12 not in vetoed(info)


def test_short_token_keeps_candidate_without_confirm():
    t = tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"])
    r, info = run("페른홀로우 15 SB", t)
    assert ids(r) == [FERN_15] and "confirmRecommended" not in r.candidates[0].evidence
    assert info["short_unverified"] == {"Fernhollow 15": ["sb"]}


def test_short_token_with_expansion():
    sb = uuid.uuid4()
    PRODUCTS[sb] = ("Fernhollow 15 Small Batch", 15, "Small Batch", None, B_FERN, ("Fernhollow 15 Small Batch",))
    META[sb] = ProductMeta("Fernhollow 15 Small Batch", 15, "Small Batch", None, ("Fernhollow 15 Small Batch",))
    META_NAME["Fernhollow 15 Small Batch"] = sb
    try:
        t = tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"],
               expansions=[{"token": "SB", "expansion": "Small Batch"}])
        r, info = run("페른홀로우 15 SB", t)
        # Small Batch fits through the expansion; the plain 15 lacks "SB" but is only kept without
        # confirm -> two LLM candidates, the owner chooses (no confirm recommended)
        assert set(ids(r)) == {sb, FERN_15}
        assert not any(c.evidence.get("confirmRecommended") for c in r.candidates)
        assert info["short_unverified"] == {"Fernhollow 15": ["sb"]}
    finally:
        del PRODUCTS[sb], META[sb], META_NAME["Fernhollow 15 Small Batch"]


def test_short_token_with_expansion_only_product():
    sb = uuid.uuid4()
    PRODUCTS[sb] = ("Fernhollow 15 Small Batch", 15, "Small Batch", None, B_FERN, ("Fernhollow 15 Small Batch",))
    META[sb] = ProductMeta("Fernhollow 15 Small Batch", 15, "Small Batch", None, ("Fernhollow 15 Small Batch",))
    META_NAME["Fernhollow 15 Small Batch"] = sb
    try:
        t = tr(brand_en="Fernhollow", age=15, edition_tokens_en=["SB"],
               expansions=[{"token": "SB", "expansion": "Small Batch"}])
        r, _ = run("페른홀로우 15 SB", t, drop={FERN_15})
        assert ids(r) == [sb] and r.candidates[0].evidence.get("confirmRecommended")
    finally:
        del PRODUCTS[sb], META[sb], META_NAME["Fernhollow 15 Small Batch"]
