"""I4-P19: Korean and English names of one bottle, and its ages and editions (name_cases.py)."""

import name_cases
import pytest

RESULT = name_cases.run()


def test_enough_names_were_made_and_most_are_confirmed():
    counts = RESULT["counts"]
    assert counts["names"] >= 1000 and counts["absent_age_names"] >= 500 and counts["brand_alone_names"] >= 400
    assert counts["confirmed"] + counts["not_confirmed"] == counts["names"]
    assert counts["confirmed"] / counts["names"] >= 0.95


@pytest.mark.parametrize("kind", ["false_merge", "false_split", "lost", "absent_age"])
def test_no_violation(kind):
    rows = RESULT["violations"].get(kind, [])
    assert not rows, f"{len(rows)} {kind}: {rows[:5]}"


def test_names_that_say_less_than_their_product_are_known():
    # Confirmed today because one bar's menu spelling is an alias of that product. The
    # incomplete-name guard would hand them to a person; menu import leaves it off (see
    # app/matching/linking_guards.py for the measurement). A new entry here is a new alias of this kind.
    incomplete = {kind: sorted({product for _, product in rows}) for kind, rows in RESULT["incomplete"].items()}
    assert incomplete == {
        "age_only": ["BenRiach The Twelve", "The Balvenie 12 DoubleWood", "The Balvenie 14 Caribbean Cask"],
        "brand_only": ["Jack Daniel's Old No.7", "Royal Brackla 12"],
    }


def test_spellings_and_brand_names():
    assert name_cases.spellings("글렌피딕", 12, None, "ko") == ["글렌피딕 12년"]
    assert name_cases.spellings("Glenfiddich", 12, "Sherry Cask", "en") == [
        "Glenfiddich 12y Sherry Cask", "Glenfiddich 12 Years Sherry Cask", "Glenfiddich 12 Sherry Cask"]
    brand = {"canonical_name": "Glenfiddich", "aliases": [{"alias_text": "글렌피딕"}, {"alias_text": "Glenfiddich"}]}
    assert name_cases.brand_names(brand) == {"ko": "글렌피딕", "en": "Glenfiddich"}
    assert name_cases.brand_names({"canonical_name": "X", "aliases": []}) == {"en": "X"}


def test_a_broken_catalog_shows_up_as_violations(capsys, monkeypatch):
    # Glenfiddich 15's names moved onto Glenfiddich 12: "Glenfiddich 15y" is now confirmed as the 12
    seed = name_cases.regression.load_seed()
    by_key = {p["key"]: p for p in seed["products"]}
    twelve, fifteen = by_key["glenfiddich-12"], by_key["glenfiddich-15"]
    twelve["aliases"] = twelve["aliases"] + fifteen["aliases"]
    fifteen["aliases"] = []
    result = name_cases.run(seed)
    assert any("Glenfiddich 12" in row[1] for row in result["violations"]["false_merge"])
    monkeypatch.setattr(name_cases, "run", lambda: result)
    assert name_cases.main() == 1 and "VIOLATION false_merge" in capsys.readouterr().out


def test_main_passes_on_the_catalog(capsys, monkeypatch):
    monkeypatch.setattr(name_cases, "run", lambda: RESULT)
    assert name_cases.main() == 0
    assert "confirmed although the name is incomplete (age_only): 4" in capsys.readouterr().out
