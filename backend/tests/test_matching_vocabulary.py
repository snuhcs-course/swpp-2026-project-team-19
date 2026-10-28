import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.matching.vocabulary import VOCABULARY_PATH, Vocabulary, load_vocabulary, to_english

CATALOG = Path(__file__).resolve().parents[2] / "ai" / "catalog" / "catalog_v2_service.json"


@pytest.fixture(scope="module")
def vocabulary():
    return load_vocabulary()


def test_the_shipped_vocabulary_loads(vocabulary):
    assert vocabulary.english["셰리"] == vocabulary.english["쉐리"] == "sherry"
    assert vocabulary.english["스트렝스"] == vocabulary.english["스트랭스"] == "strength"
    data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    assert data["version"] and data["about"]


@pytest.mark.parametrize(
    ("word", "terms"),
    [
        ("더블우드", ["double", "wood"]),
        ("캐스크스트렝스", ["cask", "strength"]),
        ("셰리오크", ["sherry", "oak"]),
        ("쿨일라", ["caol ila"]),
        ("글렌피딕", None),  # a brand name is not covered
        ("셰리글렌", None),  # covered only in part
    ],
)
def test_words_are_split_by_longest_match(vocabulary, word, terms):
    assert vocabulary.split(word) == terms


def test_to_english_rewrites_only_covered_hangul_words(vocabulary):
    assert to_english("킬호만(Kilchoman) 소테른 캐스크", vocabulary) == "킬호만(Kilchoman) sauternes cask"
    assert to_english("발베니 12년 더블우드", vocabulary) == "발베니 12년 double wood"
    assert to_english("시그나토리 쿨일라13", vocabulary) == "시그나토리 caol ila 13"
    # Nothing to rewrite: the name comes back unchanged, spacing included.
    assert to_english("글렌피딕  12년", vocabulary) == "글렌피딕  12년"
    assert to_english("Macallan 12 Sherry Oak", vocabulary) == "Macallan 12 Sherry Oak"


@pytest.mark.parametrize(
    "terms",
    [
        {"sherry": ["셰리"], "cherry": ["셰리"]},  # one spelling, two English terms
        {"sherry": ["sherry"]},  # not Hangul
        {"sherry": ["셰 리"]},
        {"Sherry": ["셰리"]},  # English must be lowercase
        {"": ["셰리"]},
    ],
)
def test_invalid_vocabularies_are_rejected(terms):
    with pytest.raises(ValueError):
        Vocabulary(terms)


def test_the_same_spelling_twice_for_one_term_is_fine():
    assert Vocabulary({"sherry": ["셰리", "셰리"]}).split("셰리") == ["sherry"]


@pytest.mark.skipif(not CATALOG.exists(), reason="ai/catalog seed is not checked out")
def test_every_english_term_comes_from_the_catalog(vocabulary):
    """The build rule in the vocabulary's "about": words in the edition name of 2 or more
    products, or in the display name of 2 or more products and in no brand name."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    def words(text):
        return {w.lower().replace("’", "'") for w in re.findall(r"[A-Za-z][A-Za-z'’]*", text or "")}

    brand_words = set().union(*(words(b["canonical_name"]) for b in catalog["brands"]))
    in_edition = Counter(w for p in catalog["products"] for w in words(p.get("edition_name")))
    in_name = Counter(w for p in catalog["products"] for w in words(p["display_name"]))
    allowed = {w for w in in_edition if in_edition[w] >= 2} | {
        w for w in in_name if in_name[w] >= 2 and w not in brand_words
    }

    for term in set(vocabulary.english.values()):
        assert set(term.split()) <= allowed, term
