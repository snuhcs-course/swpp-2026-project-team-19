"""Korean -> English whisky word vocabulary for staged matching (I3-A4, E2).

    vocabulary = load_vocabulary()            # vocab_ko_en.json next to this module
    to_english("킬호만 소테른캐스크", vocabulary)  # -> "킬호만 sauternes cask"

The catalog stores edition names in English, while Korean menus spell them in Hangul
(셰리, 캐스크 스트렝스, 더블우드). `to_english` rewrites each Hangul word that the
vocabulary covers completely, splitting compounds by longest match (더블우드 ->
double wood); a word with any part not in the vocabulary (brand names such as 글렌피딕)
is left as it is. How the vocabulary was built is recorded in its "about" field.
"""

import json
import re
from pathlib import Path

VOCABULARY_PATH = Path(__file__).with_name("vocab_ko_en.json")

_HANGUL_WORD = re.compile(r"[가-힣]+")
_HANGUL_ONLY = re.compile(r"^[가-힣]+$")


class Vocabulary:
    """Korean spelling -> English term, with the spellings tried longest first."""

    def __init__(self, terms: dict[str, list[str]]) -> None:
        self.english: dict[str, str] = {}
        for english, spellings in terms.items():
            if not english or english != english.strip().lower():
                raise ValueError(f"English term must be lowercase and trimmed: {english!r}")
            for korean in spellings:
                if not _HANGUL_ONLY.match(korean):
                    raise ValueError(f"Korean spelling must be Hangul syllables only: {korean!r}")
                if self.english.get(korean, english) != english:
                    raise ValueError(f"{korean!r} is listed for both {self.english[korean]!r} and {english!r}")
                self.english[korean] = english
        self._longest_first = sorted(self.english, key=len, reverse=True)

    def split(self, word: str) -> list[str] | None:
        """English terms for a Hangul word covered completely by the vocabulary, else None."""
        terms, start = [], 0
        while start < len(word):
            for korean in self._longest_first:
                if word.startswith(korean, start):
                    terms.append(self.english[korean])
                    start += len(korean)
                    break
            else:
                return None
        return terms


def load_vocabulary(path: Path = VOCABULARY_PATH) -> Vocabulary:
    return Vocabulary(json.loads(path.read_text(encoding="utf-8"))["terms"])


def to_english(name: str, vocabulary: Vocabulary) -> str:
    """Rewrite the Hangul words the vocabulary covers; other text is kept.

    Rewritten words are surrounded by spaces so "쿨일라13" becomes "caol ila 13".
    """

    rewritten = False

    def rewrite(match: re.Match[str]) -> str:
        nonlocal rewritten
        terms = vocabulary.split(match.group())
        if terms is None:
            return match.group()
        rewritten = True
        return f" {' '.join(terms)} "

    result = _HANGUL_WORD.sub(rewrite, name)
    return " ".join(result.split()) if rewritten else name
