"""What a menu line says about a product, in separate parts, for a line the catalog does not settle (I4-P18).

    draft = draft_from_name("글렌알라키(Glenallachie) 15년 셰리 캐스크", catalog)

When a line has no confirmed product, somebody may have to register one. The line already says
most of what the form asks for, so the parts are read out of it with the helpers the rule matcher
uses (staged.py), and nothing else:

  source_text      the spelling on the menu, unchanged
  spellings        that spelling one script at a time when the menu wrote the whole name twice:
                   "제목(English) 나머지" gives "제목 나머지" and "English 나머지", and "A / B" gives
                   A and B when they are in different scripts and carry the same numbers. Alias
                   suggestions. A trailing "(블레어 아쏠)" is not a whole name and gives none, since a
                   partial spelling saved as an alias matches other products of the brand later.
  brand_id         the catalog brand the name starts with, when exactly one fits
  brand_text       the brand as the menu wrote it
  age_years        a number with a unit ("15년", "15Y", "15yo") anywhere, or a bare number of 8 or
                   more right after the brand ("Aberlour 12"). Other bare numbers are batch and
                   series numbers more often than ages ("배치 4", "사부로마루3") and are left in
                   the edition text.
  edition_text     the rest of the name as written
  edition_english  the same in English, when the vocabulary knows every Korean word in it

A draft is a suggestion for a form. It is never a catalog product and never confirms a line:
making the product stays a decision a person submits.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from app.matching.staged import (
    _AGE_WITH_UNIT,
    _BARE_AGE,
    _HANGUL,
    _PARENTHESIZED,
    _VOCABULARY,
    BILINGUAL_SEPARATOR,
    _find_brand,
    _parenthesis_variants,
    _script,
)
from app.matching.types import CatalogLookup
from app.matching.vocabulary import to_english

_SPACES = re.compile(r"\s+")
_NUMBERS = re.compile(r"\d+")
_MIN_BARE_AGE = 8


@dataclass(frozen=True)
class ProductDraft:
    source_text: str
    spellings: tuple[str, ...] = ()
    brand_id: UUID | None = None
    brand_text: str | None = None
    age_years: int | None = None
    edition_text: str | None = None
    edition_english: str | None = None


def _age_and_edition(rest: str) -> tuple[int | None, str | None]:
    """(age, the rest as written without it) of the name after the brand."""
    age = None
    match = _AGE_WITH_UNIT.search(rest)
    words = rest.split()
    if match is not None:
        age = int(match[1])
        rest = f"{rest[: match.start()]} {rest[match.end():]}"
    elif words and _BARE_AGE.match(words[0]) and int(words[0]) >= _MIN_BARE_AGE:
        age = int(words[0])
        rest = " ".join(words[1:])
    return age, _SPACES.sub(" ", rest).strip() or None


def whole_spellings(source: str) -> tuple[str, ...]:
    """The name one script at a time, when the menu wrote the whole name in two scripts."""
    out: list[str] = []
    match = _PARENTHESIZED.match(source)
    if match is not None and match["rest"].strip() and match["title"].strip():
        out += [_SPACES.sub(" ", f"{match[part].strip()} {match['rest'].strip()}") for part in ("title", "inner")]
    sides = [side.strip() for side in source.split(BILINGUAL_SEPARATOR)] if BILINGUAL_SEPARATOR in source else []
    if (len(sides) == 2 and all(sides) and None not in (_script(sides[0]), _script(sides[1]))
            and _script(sides[0]) != _script(sides[1]) and _NUMBERS.findall(sides[0]) == _NUMBERS.findall(sides[1])):
        out += sides
    return tuple(dict.fromkeys(out))


MAX_ALIAS_LENGTH = 200  # ProductAliasInput.aliasText


def alias_suggestions(name: str | None) -> list[str]:
    """Spellings of a menu line worth saving as aliases of its product: one per script when the
    line writes the whole name twice, otherwise the name as written. A partial spelling is never
    suggested (see `spellings` above)."""
    source = _SPACES.sub(" ", name or "").strip()
    if not source:
        return []
    return [text for text in (whole_spellings(source) or (source,)) if len(text) <= MAX_ALIAS_LENGTH]


def draft_from_name(name: str | None, catalog: CatalogLookup) -> ProductDraft | None:
    """The draft for a menu line, or None for a line without a name."""
    source = (name or "").strip()
    if not source:
        return None
    spellings = whole_spellings(source)
    readings = list(dict.fromkeys([*_parenthesis_variants(source), *spellings, source]))
    for variant in readings:
        found = _find_brand(variant, catalog)
        if found is None:
            continue
        brand_ids, _, rest = found
        if not rest and variant != source:
            continue  # this reading is only the brand ("아벨라워" of "Aberlour 12 (아벨라워)")
        age, edition = _age_and_edition(rest)
        english = to_english(edition, _VOCABULARY) if edition and _VOCABULARY is not None else edition
        english = _SPACES.sub(" ", english).strip() if english else None
        return ProductDraft(
            source_text=source, spellings=spellings,
            brand_id=brand_ids[0] if len(brand_ids) == 1 else None,
            brand_text=variant[: len(variant) - len(rest)].strip() if rest else variant,
            age_years=age, edition_text=edition,
            edition_english=english if english != edition and not _HANGUL.search(english or "") else None,
        )
    match = _AGE_WITH_UNIT.search(source)
    return ProductDraft(source_text=source, spellings=spellings, age_years=int(match[1]) if match else None)
