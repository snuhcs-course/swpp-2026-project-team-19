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
from dataclasses import dataclass, replace
from uuid import UUID

from app.core.normalize import normalize
from app.matching.staged import (
    _AGE_WITH_UNIT,
    _BARE_AGE,
    _HANGUL,
    _LATIN,
    _PARENTHESIZED,
    _VOCABULARY,
    BILINGUAL_SEPARATOR,
    _find_brand,
    _script,
)
from app.matching.types import CatalogLookup
from app.matching.vocabulary import to_english

_SPACES = re.compile(r"\s+")
_PARENTHESES = re.compile(r"[()]")
_NUMBERS = re.compile(r"\d+")
_LATIN_WORD = re.compile(r"[a-z']+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")  # "DoubleWood" is read as "Double Wood"
_KOREAN_SPELLINGS: dict[str, list[str]] = {}
for _korean, _english in (_VOCABULARY.english.items() if _VOCABULARY is not None else ()):
    _KOREAN_SPELLINGS.setdefault(_english, []).append(_korean)
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
    # brackets that are not a second spelling hold part of the name: "12 (Sherry Oak)", "(12년) 셰리 오크"
    return age, _SPACES.sub(" ", _PARENTHESES.sub(" ", rest)).strip() or None


def _says_more(title: str, inner: str) -> bool:
    """Whether brackets in the other script say something the title does not: a number, or a
    whisky word of the vocabulary. "발베니 (12Y DoubleWood)" and "Balvenie 14y (럼 캐스크)" do;
    "포트샬롯(Port Charlotte)" and "Balvenie 16y French Oak (프렌치 오크)" only repeat the title."""
    if not set(_NUMBERS.findall(inner)) <= set(_NUMBERS.findall(title)):
        return True
    if _VOCABULARY is None:
        return False
    if _HANGUL.search(title):  # Latin brackets: an English term none of whose Korean spellings is in the title
        latin = f" {' '.join(_LATIN_WORD.findall(_CAMEL.sub(' ', inner).lower()))} "
        return any(f" {english} " in latin and not any(korean in title for korean in spellings)
                   for english, spellings in _KOREAN_SPELLINGS.items())
    # Hangul brackets: a Korean spelling, as a word of its own, whose English is not in the title. Inside
    # a longer word it is not that term: "라이" (rye) in 클라이넬리쉬, "몰트" (malt) in 몰트락.
    plain = "".join(_LATIN_WORD.findall(title.lower()))
    return any(english.replace(" ", "") not in plain and _has_word(inner, korean)
               for korean, english in _VOCABULARY.english.items())


def _has_word(text: str, korean: str) -> bool:
    start = text.find(korean)
    while start >= 0:
        end = start + len(korean)
        if not (start and _HANGUL.match(text[start - 1])) and not (end < len(text) and _HANGUL.match(text[end])):
            return True
        start = text.find(korean, start + 1)
    return False


def _other_script_brackets(source: str) -> re.Match | None:
    """The match of "제목(Title) 나머지" when the text before the brackets is in one script and the
    brackets have the other one."""
    match = _PARENTHESIZED.match(source)
    if match is None:
        return None
    other = {"hangul": _LATIN, "latin": _HANGUL}.get(_script(match["title"]))
    return match if other is not None and other.search(match["inner"]) else None


def _second_spelling(source: str) -> re.Match | None:
    """The match of "제목(Title) 나머지" when the brackets hold the same words in the other script.

    The text before the brackets must be in one script and the brackets must have the other one:
    "글렌알라키(Glenallachie) 15년", "Yamazaki Dr (야마자키 Dr)". Brackets in the same script are part
    of the name ("Macallan 12 (Sherry Oak)", "맥캘란 (12년) 셰리 오크") and give no second spelling.

    The other script alone is not enough: "발베니 (12Y DoubleWood)" and "발베니 (Caribbean Cask) 14년"
    put the age and the edition in the brackets, not the name again. Brackets with a number or a
    whisky word the title does not have are part of the name too (_says_more).
    """
    match = _other_script_brackets(source)
    return match if match is not None and not _says_more(match["title"], match["inner"]) else None


def _edition_reading(source: str, catalog: CatalogLookup) -> str | None:
    """"아드벡 (Uigeadail) 나머지" read as "아드벡 Uigeadail 나머지" when the brackets, in the other
    script after a name that starts with a brand, hold an edition the catalog has for that brand.

    Such brackets pass _says_more when the edition is not a vocabulary word. Only an edition the
    catalog knows is taken: menus also write the brand again in brackets in spellings the catalog
    does not have ("맥캘란(Maccallan)", "산토리(Santory)", "더 위스키 에이전시(TWA)"), and those
    must stay second spellings.
    """
    match = _other_script_brackets(source)
    if match is None:
        return None
    title, inner = match["title"].strip(), match["inner"].strip()
    brand = _find_brand(title, catalog)
    if brand is None or len(brand[0]) != 1:
        return None
    wanted = normalize(inner)  # never empty: the brackets have a letter of the other script
    for product_id in catalog.get_brand_product_ids(brand[0][0]):
        product = catalog.get_product(product_id)
        if product is not None and product.edition_name and normalize(product.edition_name) == wanted:
            return _SPACES.sub(" ", f"{title} {inner} {match['rest']}").strip()
    return None


def _bracket_readings(source: str, catalog: CatalogLookup) -> list[str]:
    match = _second_spelling(source)
    if match is None:
        # brackets that say more than the title are still the name again when they start with the
        # title's brand: "맥캘란 (Macallan 12) 셰리 오크". Each side is read on its own then, so the
        # other spelling of the brand is not taken for the edition.
        match = _other_script_brackets(source)
        if match is None:
            return []
        title, inner = (_find_brand(match[part].strip(), catalog) for part in ("title", "inner"))
        if title is None or inner is None or not set(title[0]) & set(inner[0]):
            return []
    rest = match["rest"].strip()
    return list(dict.fromkeys(f"{match[part].strip()} {rest}".strip() for part in ("title", "inner")))


def whole_spellings(source: str) -> tuple[str, ...]:
    """The name one script at a time, when the menu wrote the whole name in two scripts."""
    out: list[str] = []
    match = _second_spelling(source)
    if match is not None and match["rest"].strip():
        out += [_SPACES.sub(" ", f"{match[part].strip()} {match['rest'].strip()}") for part in ("title", "inner")]
    sides = [side.strip() for side in source.split(BILINGUAL_SEPARATOR)] if BILINGUAL_SEPARATOR in source else []
    if (len(sides) == 2 and all(sides) and None not in (_script(sides[0]), _script(sides[1]))
            and _script(sides[0]) != _script(sides[1]) and _NUMBERS.findall(sides[0]) == _NUMBERS.findall(sides[1])):
        out += sides
    return tuple(dict.fromkeys(out))


def draft_from_name(name: str | None, catalog: CatalogLookup) -> ProductDraft | None:
    """The draft for a menu line, or None for a line without a name."""
    source = _SPACES.sub(" ", name or "").strip()  # OCR text can have double spaces
    if not source:
        return None
    with_edition = _edition_reading(source, catalog)
    spellings = () if with_edition else whole_spellings(source)
    # the line as a whole is read only when it has no second spelling: with one, the other
    # spelling would be taken for the edition ("발베니 17년 / Balvenie 17Y")
    bracketed = [with_edition] if with_edition else _bracket_readings(source, catalog)
    readings = list(dict.fromkeys([*bracketed, *spellings])) or [source]
    best: ProductDraft | None = None
    drafts: list[ProductDraft] = []
    brand_alone: tuple[UUID | None, str] | None = None
    for variant in readings:
        found = _find_brand(variant, catalog)
        if found is None:
            continue
        brand_ids, alias, rest = found
        if not rest and variant != source:
            # this reading is only the brand ("아벨라워" of "Aberlour 12 (아벨라워)")
            brand_alone = brand_alone or (brand_ids[0] if len(brand_ids) == 1 else None, variant)
            continue
        age, edition = _age_and_edition(rest)
        english = to_english(edition, _VOCABULARY) if edition and _VOCABULARY is not None else edition
        english = _SPACES.sub(" ", english).strip() if english else None
        # the brand as written is the reading without its rest; `rest` is rebuilt by the matcher,
        # so when it is not the reading's tail the matched alias stands in
        brand_text = variant[: len(variant) - len(rest)].strip() if variant.endswith(rest) else alias
        draft = ProductDraft(
            source_text=source, spellings=spellings,
            brand_id=brand_ids[0] if len(brand_ids) == 1 else None,
            brand_text=brand_text if rest else variant,
            age_years=age, edition_text=edition,
            edition_english=english if english != edition and not _HANGUL.search(english or "") else None,
        )
        # two spellings of one line can say different amounts ("발베니 16년 / Balvenie 16 French Oak"):
        # the reading with more parts wins, the first one on a tie
        drafts.append(draft)
        if best is None or _parts(draft) > _parts(best):
            best = draft
    if best is not None:
        return _with_parts_of_the_other_readings(best, drafts)
    match = _AGE_WITH_UNIT.search(source)
    age = int(match[1]) if match else None
    if brand_alone is not None:
        # "아드벡 (Corryvreckan)": the other reading has no brand the catalog knows (an edition it
        # does not have, or the brand in another spelling). The brand is still the brand.
        return ProductDraft(source_text=source, spellings=spellings, brand_id=brand_alone[0],
                            brand_text=brand_alone[1], age_years=age)
    return ProductDraft(source_text=source, spellings=spellings, age_years=age)


def _with_parts_of_the_other_readings(best: ProductDraft, drafts: list[ProductDraft]) -> ProductDraft:
    """The readings of one line can each say a part the other lacks: "발베니 14년 (Balvenie Caribbean
    Cask)" has the age on one side and the edition on the other. A part the chosen reading lacks
    is taken from another reading of the same brand; a part it has is never replaced."""
    for other in drafts:
        if other is best or best.brand_id is None or other.brand_id != best.brand_id:
            continue
        if best.age_years is None and other.age_years is not None:
            best = replace(best, age_years=other.age_years)
        if best.edition_text is None and other.edition_text is not None:
            best = replace(best, edition_text=other.edition_text, edition_english=other.edition_english)
    return best


def _parts(draft: ProductDraft) -> int:
    return (draft.age_years is not None) + (draft.edition_text is not None)
