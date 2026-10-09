# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-05, PR #5). Reviewed by Jinwoo Park.
"""Shared string normalization for alias matching (matching flow doc, section 7).

The same function must be used when storing `brand_aliases.normalized_alias` /
`product_aliases.normalized_alias` and when looking up an extracted name. If a
rule changes, every stored normalized alias has to be regenerated in one
migration, so keep the rules here limited to section 7. Spelling variants such
as "Aged 12 Years" are registered as aliases instead of being stripped here.
"""

import re
import unicodedata

# Hyphen, non-breaking hyphen, figure dash, en dash, em dash, horizontal bar, minus sign.
_SPECIAL_DASHES = re.compile(r"[‐‑‒–—―−]")
_WHITESPACE = re.compile(r"\s+")
# Age expression right after a number: 12년, 12年, 12 years old, 12 years, 12 yo, 12y.
# Not applied when a Latin letter follows, so "12yamazaki" or "12ydw" stays as is.
_AGE_SUFFIX = re.compile(r"(?<=\d) ?(?:years? old|years?|yo|y|년|年)(?![a-z])")
# Everything except letters, digits, whitespace, dots and hyphens ("_" counts as \w).
_UNNEEDED_CHARS = re.compile(r"[^\w\s.\-]|_")
# Dots are kept only between digits so "16.1" survives and "No.7" becomes "no7".
_NON_DECIMAL_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")


def normalize(text: str) -> str:
    """Return the comparison key for an alias or extracted name.

    >>> normalize(" 딘스톤 12年 ")
    '딘스톤12'
    """
    value = unicodedata.normalize("NFKC", text)
    value = _SPECIAL_DASHES.sub("-", value)
    value = value.lower()
    value = _WHITESPACE.sub(" ", value).strip()
    value = _AGE_SUFFIX.sub("", value)
    value = _UNNEEDED_CHARS.sub("", value)
    value = _NON_DECIMAL_DOT.sub("", value)
    # Spaces are dropped entirely so "딘스톤 12" and "딘스톤12" compare equal.
    return _WHITESPACE.sub("", value)
