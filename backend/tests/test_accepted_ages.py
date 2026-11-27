"""Older ages a product is also known by (I5-P59, catalog v2.6, app/matching/accepted_ages.py)."""

import json
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from app.matching.accepted_ages import ACCEPTED_AGES, accepted_ages
from app.matching.db_catalog import CatalogSnapshot, DbCatalog
from app.matching.linking_guards import incomplete_name
from app.matching.llm_layer import M3Engine, ProductMeta
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.pick_check import _family, check_pick
from app.matching.staged import resolve_product_staged
from app.matching.types import ExtractedProduct, ProductInfo
from scripts.seed_catalog import seed

ALL_STAGES = {"S1", "S2", "S2b", "S3"}  # menu import
SEED = Path(__file__).resolve().parents[2] / "ai" / "catalog" / "catalog_v2_service.json"


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


GM = _id(400)
ORIGINAL, LASANTA, QUINTA, NECTAR, CALVADOS, SIGNET = (_id(n) for n in range(401, 407))
# catalog v2.6: the current age, and the older ages accepted for it
PRODUCTS = [
    ProductInfo(ORIGINAL, "Glenmorangie The Original", 12, "The Original", GM, accepted_ages=(10,)),
    ProductInfo(LASANTA, "Glenmorangie Lasanta", 15, "Lasanta", GM, accepted_ages=(12,)),
    ProductInfo(QUINTA, "Glenmorangie Quinta Ruban", 14, "Quinta Ruban", GM, accepted_ages=(12,)),
    ProductInfo(NECTAR, "Glenmorangie Nectar D'Or", 16, "Nectar D'Or", GM),
    ProductInfo(CALVADOS, "Glenmorangie 12 Calvados Cask Finish", 12, "Calvados Cask Finish", GM),
    ProductInfo(SIGNET, "Glenmorangie Signet", None, "Signet", GM),
]
ALIASES = [(p.product_id, p.display_name) for p in PRODUCTS] + [
    (ORIGINAL, "글렌모렌지 오리지날"), (LASANTA, "글렌모렌지 라산타"), (NECTAR, "글렌모렌지 넥타도르"),
]
BRANDS = [(GM, "Glenmorangie"), (GM, "글렌모렌지")]


def make_catalog(products=PRODUCTS) -> InMemoryCatalog:
    have = {p.product_id for p in products}
    return InMemoryCatalog(products, [(pid, text) for pid, text in ALIASES if pid in have], BRANDS)


@pytest.fixture
def catalog():
    return make_catalog()


@pytest.fixture
def without_accepted():
    """The same catalog with no accepted ages (matching before v2.6, with the v2.6 ages)."""
    return make_catalog([replace(p, accepted_ages=()) for p in PRODUCTS])


def match(name, catalog, age=None):
    return resolve_product_staged(ExtractedProduct(product_name=name, age_years=age), catalog, ALL_STAGES)


def ids(result):
    return [c.product_id for c in result.candidates]


def test_fits_age():
    original, nectar, signet = PRODUCTS[0], PRODUCTS[3], PRODUCTS[5]
    assert original.fits_age(12) and original.fits_age(10) and not original.fits_age(11)
    assert nectar.fits_age(16) and not nectar.fits_age(15)
    assert not signet.fits_age(12)


# ---- the age extraction passed (menu import: extracted_age_years) ----

@pytest.mark.parametrize("age, evidence", [(10, {"ageAccepted": 10}), (12, {"ageExact": True})])
def test_an_alias_match_with_an_accepted_or_the_current_age_is_confirmed(catalog, age, evidence):
    result = match("글렌모렌지 오리지날", catalog, age)
    assert result.status == "exact_match" and result.proposed_product_id == ORIGINAL
    [c] = result.candidates
    assert {k: c.evidence[k] for k in evidence} == evidence
    assert "ageConflict" not in c.evidence and ("ageExact" in c.evidence) is (age == 12)


def test_an_age_that_is_neither_is_still_a_conflict(catalog):
    result = match("글렌모렌지 오리지날", catalog, 11)
    assert result.status != "exact_match"
    assert result.candidates[0].evidence.get("ageConflict") is True


def test_an_extracted_age_only_also_narrows_by_the_accepted_ages(catalog):
    # no age on the line: S2 takes the extracted one, and Lasanta (15) is found by its older 12
    result = match("글렌모렌지 Lasanta", catalog, 12)
    assert result.status == "exact_match" and result.proposed_product_id == LASANTA
    assert result.candidates[0].evidence["ageMatch"] == 12 and result.candidates[0].evidence["ageAccepted"] == 12
    assert match("글렌모렌지 Lasanta", catalog, 13).status != "exact_match"


# ---- the age on the line ----

@pytest.mark.parametrize("name, product, accepted", [
    ("글렌모렌지 오리지날 10년", ORIGINAL, 10),
    ("글렌모렌지 12 라산타", LASANTA, 12),
    ("글렌모렌지 라산타 15Y", LASANTA, None),  # the current age
])
def test_a_line_with_an_accepted_or_the_current_age_is_confirmed(catalog, name, product, accepted):
    result = match(name, catalog)
    assert result.status == "exact_match" and result.proposed_product_id == product
    assert result.candidates[0].evidence.get("ageAccepted") == accepted


def test_the_same_lines_with_the_age_also_extracted(catalog):
    for name, age, product in (("글렌모렌지 오리지날 10년", 10, ORIGINAL), ("글렌모렌지 라산타 15Y", 15, LASANTA)):
        assert match(name, catalog, age).proposed_product_id == product


def test_brand_and_age_offer_every_product_that_takes_that_age(catalog):
    result = match("글렌모렌지 12", catalog)
    assert result.status == "ambiguous"
    assert set(ids(result)) == {ORIGINAL, LASANTA, QUINTA, CALVADOS}
    accepted = {c.product_id for c in result.candidates if c.evidence.get("ageAccepted") == 12}
    assert accepted == {LASANTA, QUINTA}  # Original and Calvados are 12 now


@pytest.mark.parametrize("name, product", [
    ("글렌모렌지 15년 / Glenmorangie 15yr", LASANTA),
    ("Glenmorangie 15", LASANTA),
    ("글렌모렌지 10", ORIGINAL),
])
def test_brand_and_an_age_one_product_takes_give_that_product_unconfirmed(catalog, name, product):
    result = match(name, catalog)
    assert result.status == "ambiguous" and ids(result) == [product]


def test_an_age_no_product_takes_finds_nothing_by_brand_and_age(catalog):
    assert match("글렌모렌지 11년", catalog).status == "unmatched"


@pytest.mark.parametrize("name, age", [
    ("글렌모렌지 16년", None), ("Glenmorangie 16yr", None), ("글렌모렌지 넥타도르", 16), ("글렌모렌지 넥타도르", 15),
    ("글렌모렌지 18", None), ("Glenmorangie Signet", 12),
])
def test_lines_of_products_without_accepted_ages_are_as_before(catalog, without_accepted, name, age):
    assert match(name, catalog, age) == match(name, without_accepted, age)


# ---- the reviewer's pick (pick_check) ----

def no_similarities(query):
    return {}


def test_a_pick_with_an_accepted_age_is_no_age_conflict(catalog):
    assert check_pick("글렌모렌지 오리지날 10년", 10, ORIGINAL, catalog, no_similarities).fits
    conflict = check_pick("글렌모렌지 오리지날 11년", 11, ORIGINAL, catalog, no_similarities)
    assert conflict.reasons == ("ageConflict",) and conflict.evidence == {"lineAge": 11, "productAge": 12}


def test_the_pick_family_has_the_products_that_take_the_line_age(catalog):
    family = {p.product_id for p in _family(PRODUCTS[1], 12, catalog)}
    assert family == {ORIGINAL, LASANTA, QUINTA, CALVADOS, SIGNET}  # Signet has no age


# ---- incompleteName (linking_guards, measurement only) ----

def test_age_only_counts_a_sibling_that_takes_the_age():
    two = [PRODUCTS[0], PRODUCTS[1]]  # Original 12, Lasanta 15 (also 12)
    assert incomplete_name("글렌모렌지 12", PRODUCTS[0], make_catalog(two)) == "age_only"
    assert incomplete_name("글렌모렌지 12", PRODUCTS[0], make_catalog([replace(p, accepted_ages=()) for p in two])) is None


# ---- LLM layer vetoes ----

META = {p.product_id: ProductMeta(p.display_name, p.age_years, p.edition_name, None) for p in PRODUCTS}


def tr(**kw):
    return {"bottler_en": None, "distillery_en": None, "brand_en": None, "age": None, "edition_tokens_en": [],
            "expansions": [], "kind": "whisky", **kw}


def test_the_llm_layer_takes_an_accepted_age_and_still_vetoes_another(catalog):
    engine = M3Engine(None, {}, META, max_calls=0)
    lasanta = tr(brand_en="Glenmorangie", age=12, edition_tokens_en=["Lasanta"])
    assert "age_mismatch" not in engine._vetoes("글렌모렌지 라산타 12년", lasanta, LASANTA, catalog)[0]
    assert "age_mismatch" in engine._vetoes("글렌모렌지 라산타 13년", {**lasanta, "age": 13}, LASANTA, catalog)[0]
    assert "age_mismatch" in engine._vetoes("글렌모렌지 시그넷 12년", tr(brand_en="Glenmorangie", age=12), SIGNET, catalog)[0]
    _, _, found, _ = engine.m3a_candidates("글랜모랜지 라산타 12년", lasanta, catalog)
    assert "tokens" in found[LASANTA]  # the token match takes the accepted age too


# ---- the table and the catalog ----

def test_the_seed_catalog_gets_the_accepted_ages_of_the_table():
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    rows = {uuid.UUID(p["id"]): p for p in seed["products"]}
    names = {rows[pid]["key"]: (rows[pid]["age_years"], ages) for pid, ages in ACCEPTED_AGES.items()}
    assert names == {"glenmorangie-original": (12, (10,)), "glenmorangie-lasanta": (15, (12,)),
                     "glenmorangie-quinta-ruban": (14, (12,))}
    loaded = InMemoryCatalog.from_seed(SEED)
    for pid, ages in ACCEPTED_AGES.items():
        assert loaded.get_product(pid).accepted_ages == ages == accepted_ages(pid)
    nectar = next(pid for pid, p in rows.items() if p["key"] == "glenmorangie-nectar-dor")
    assert loaded.get_product(nectar).accepted_ages == () == accepted_ages(nectar)


@pytest.mark.skipif(not SEED.exists(), reason="ai/catalog seed is not checked out")
def test_the_database_catalogs_get_the_accepted_ages_by_product_id(db_session):
    bars = SEED.parent / "bars_v2.json"
    seed(db_session.connection(), json.loads(SEED.read_text(encoding="utf-8")), json.loads(bars.read_text(encoding="utf-8")))
    from_db, snapshot = DbCatalog(db_session), CatalogSnapshot(db_session)
    for pid, ages in ACCEPTED_AGES.items():
        assert from_db.get_product(pid).accepted_ages == ages == snapshot.get_product(pid).accepted_ages
    assert from_db.get_product(PRODUCTS[0].product_id) is None  # not a seed product
