"""Seeded typing-error model for the spell-correction evals (roadmap 3.5).

One edit per corrupted word, drawn from the error types that dominate
real typing: a neighbouring key hit instead of the right one, a dropped
letter, an extra neighbouring key, two adjacent letters swapped, a letter
doubled. The first letter is spared most of the time — first-letter
errors are rare in real typing, and sparing them keeps the set honest
about what a corrector can reasonably recover.

Every word of every query is a candidate, stopwords included: a natural-
language query is full of them ("how does…"), and a corrector that fixes
content words by breaking stopwords is not an improvement.
"""
from __future__ import annotations

import random
import re

_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_POS = {c: (r, i) for r, row in enumerate(_ROWS) for i, c in enumerate(row)}

# Relative frequency of each error type.
_OPS = [("substitute", 35), ("delete", 30), ("insert", 15), ("swap", 15), ("double", 5)]

FIRST_LETTER_P = 0.1
MIN_WORD_LEN = 3

_WORD_RE = re.compile(r"[A-Za-z]+")


def neighbours(ch: str) -> list[str]:
    """Keys physically adjacent to ``ch`` on a QWERTY keyboard."""
    pos = _POS.get(ch.lower())
    if pos is None:
        return []
    r, i = pos
    out = []
    for dr in (-1, 0, 1):
        row = r + dr
        if not 0 <= row < len(_ROWS):
            continue
        for j in (i - 1, i, i + 1):
            if (dr, j) != (0, i) and 0 <= j < len(_ROWS[row]):
                out.append(_ROWS[row][j])
    return out


def typo(word: str, rng: random.Random) -> str:
    """``word`` with one realistic typing error; never returns ``word``."""
    lo = 0 if rng.random() < FIRST_LETTER_P else 1
    for _ in range(20):
        op = rng.choices([o for o, _ in _OPS], weights=[w for _, w in _OPS])[0]
        i = rng.randrange(lo, len(word))
        c = word[i]
        if op == "substitute" and neighbours(c):
            out = word[:i] + rng.choice(neighbours(c)) + word[i + 1:]
        elif op == "delete":
            out = word[:i] + word[i + 1:]
        elif op == "insert" and neighbours(c):
            out = word[:i + 1] + rng.choice(neighbours(c)) + word[i + 1:]
        elif op == "swap" and i + 1 < len(word):
            out = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        elif op == "double":
            out = word[:i + 1] + c + word[i + 1:]
        else:
            continue
        if out.lower() != word.lower():
            return out
    return word[:lo] + word[lo + 1:]  # fall back to a deletion


def typo_query(query: str, rng: random.Random) -> tuple[str, str]:
    """``query`` with one eligible word corrupted, and that word."""
    words = [m for m in _WORD_RE.finditer(query) if len(m.group()) >= MIN_WORD_LEN]
    m = rng.choice(words)
    return query[:m.start()] + typo(m.group(), rng) + query[m.end():], m.group()
