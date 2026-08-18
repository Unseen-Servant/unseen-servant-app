"""Library-vocabulary spell correction (plan §3.4, ladder rung 7).

Norvig-style edit-distance correction against KNOWN terms — never an error list.
A query token that isn't in the library vocab is replaced by the nearest vocab
term (edit distance 1, then 2), preferring higher frequency; known tokens, short
tokens, and uncorrectable unknowns pass through unchanged. Building the dictionary
from the user's own library (store.build_vocab) means domain terms — thac0,
shillelagh, bugbear, OSRIC — are known-correct, so they're fixed-toward, never
mangled the way a stock English checker would. No import from sidecar/.
"""
from __future__ import annotations

import re
from typing import Callable

_WORD = re.compile(r"[A-Za-z0-9]+")
_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
MIN_LEN = 4  # don't correct 1-3 char tokens (ac, hp, 1d6) — too ambiguous


def _edits1(word: str) -> set[str]:
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [a + b[1:] for a, b in splits if b]
    transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
    replaces = [a + c + b[1:] for a, b in splits if b for c in _ALPHABET]
    inserts = [a + c + b for a, b in splits for c in _ALPHABET]
    return set(deletes + transposes + replaces + inserts)


def correct(query: str, freq: Callable[[str], int]) -> str:
    """Return the query with unknown tokens corrected to the nearest vocab term.
    `freq(term)` gives the library frequency (0 if unknown)."""
    def fix(m: re.Match) -> str:
        token = m.group(0)
        low = token.lower()
        if len(low) < MIN_LEN or freq(low) > 0:
            return token
        cands = [c for c in _edits1(low) if freq(c) > 0]
        if not cands:
            cands = [c for e in _edits1(low) for c in _edits1(e) if freq(c) > 0]
        return max(cands, key=freq) if cands else token

    return _WORD.sub(fix, query)
