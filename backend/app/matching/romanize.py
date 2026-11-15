"""Hangul to Latin letters for the pick check's embedding query (`app.matching.pick_check`).

Revised Romanization of each syllable on its own, without the sound-change rules between
syllables. The character n-gram embedding has no n-gram shared by Hangul and Latin text, so a
Korean edition ("솔리스트") is otherwise far from every English product name ("Solist"). Close is
enough: "솔리스트" gives "solriseuteu", which shares "sol" and "st" with "solist".
"""

_INITIALS = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_VOWELS = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
           "yu", "eu", "ui", "i")
_FINALS = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
           "ng", "t", "t", "k", "t", "p", "t")
_FIRST, _COUNT = 0xAC00, 11172


def romanize(text: str) -> str:
    """`text` with every Hangul syllable in Latin letters; every other character as it is."""
    out = []
    for char in text:
        code = ord(char) - _FIRST
        if 0 <= code < _COUNT:
            out.append(_INITIALS[code // 588] + _VOWELS[(code % 588) // 28] + _FINALS[code % 28])
        else:
            out.append(char)
    return "".join(out)
