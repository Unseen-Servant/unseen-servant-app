"""Half-typed queries for the typing-vs-committing evals.

The app searches as the GM types (a 300 ms debounce), so most queries the
sidecar sees end in an unfinished word. This turns a suite query into what
the search box holds partway through its last word: the word cut to a
fixed share of its length, with trailing punctuation not yet typed.

Deterministic, unlike ``typos.py``: a prefix has no randomness worth
sampling, and one fixed cut per query keeps runs comparable.
"""
from __future__ import annotations

import math
import re

# A last word shorter than this is left whole: cutting "ac" or "5e" says
# nothing about completion, and FTS5 prefix matching needs a few letters.
MIN_CUT_WORD_LEN = 5
MIN_PREFIX_LEN = 3

_LAST_WORD_RE = re.compile(r"([A-Za-z]+)[^A-Za-z0-9]*$")


def prefix_query(query: str, frac: float) -> tuple[str, bool]:
    """``query`` as typed up to ``frac`` of its last word.

    Returns ``(text, cut)``; ``cut`` is False when the last word is too
    short to cut, in which case the text is the query minus trailing
    punctuation.
    """
    m = _LAST_WORD_RE.search(query)
    if m is None:
        return query.rstrip(), False
    word = m.group(1)
    head = query[: m.start(1)]
    if len(word) < MIN_CUT_WORD_LEN:
        return head + word, False
    keep = max(MIN_PREFIX_LEN, math.ceil(len(word) * frac))
    if keep >= len(word):
        return head + word, False
    return head + word[:keep], True
