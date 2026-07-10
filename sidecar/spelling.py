"""Library-derived vocabulary + spell correction for search queries.

Section A + Vocabulary of the typo-tolerance design
(docs/specs/retrieval/2026-07-10-typo-tolerance-design.md): out-of-
vocabulary query tokens are rewritten to the closest in-vocabulary term
before embedding, so a misspelled query returns (approximately) the
results of its corrected form.

The vocabulary is a term → frequency map over the indexed chunks —
lowercased, unstemmed, same ``[A-Za-z0-9]+`` token alphabet as
``lexical.py``. It is a separate pass, not a reuse of ``LexicalIndex``:
the FTS5 index is porter-stemmed, the wrong surface forms for a spell
dictionary. Terms below ``MIN_VOCAB_FREQ`` are treated as extraction
junk ("byweapon"): they are neither protected from correction nor
loaded into the dictionary as correction targets.
"""
from __future__ import annotations

import re
from importlib.resources import files

from symspellpy import SymSpell, Verbosity

# A term is in-vocab (protected, and a valid correction target) only at
# this frequency or above. Start 3 per the design; tune during eval.
MIN_VOCAB_FREQ = 3

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# General-English protection (2026-07-10 eval finding): query words the
# library never prints ("stats", "flag") are real words, not typos —
# without this list they get rewritten to library terms ("starts",
# "flat") and clean queries stop being a no-op. English words are only
# protected, never correction targets.
_english_words_cache: frozenset[str] | None = None


def _english_words() -> frozenset[str]:
    global _english_words_cache
    if _english_words_cache is None:
        text = files("symspellpy").joinpath(
            "frequency_dictionary_en_82_765.txt"
        ).read_text()
        _english_words_cache = frozenset(
            line.split()[0] for line in text.splitlines() if line.strip()
        )
    return _english_words_cache


def build_vocabulary(collection, batch_size: int = 1000) -> dict[str, int]:
    """Term → frequency over every chunk in a ChromaDB collection.

    Counts the heading-prepended view of each chunk — the same text the
    embedder, reranker, and lexical index see — so section-heading terms
    (monster names above stat blocks) are correction targets too.
    """
    vocab: dict[str, int] = {}
    offset = 0
    while True:
        batch = collection.get(
            include=["documents", "metadatas"],
            limit=batch_size,
            offset=offset,
        )
        if not batch["ids"]:
            break
        for doc, meta in zip(batch["documents"], batch["metadatas"]):
            heading = (meta or {}).get("section_heading") or ""
            text = f"{heading}\n\n{doc}" if heading else doc
            for token in _TOKEN_RE.findall(text.lower()):
                vocab[token] = vocab.get(token, 0) + 1
        offset += len(batch["ids"])
    return vocab


class SpellCorrector:
    """Rewrites OOV query tokens to the closest in-vocabulary term."""

    def __init__(
        self, vocabulary: dict[str, int], min_freq: int = MIN_VOCAB_FREQ
    ) -> None:
        self._vocab = vocabulary
        self._min_freq = min_freq
        self._symspell = SymSpell(max_dictionary_edit_distance=2)
        for term, freq in vocabulary.items():
            if freq >= min_freq:
                self._symspell.create_dictionary_entry(term, freq)

    @classmethod
    def from_collection(cls, collection) -> "SpellCorrector":
        return cls(build_vocabulary(collection))

    def correct(self, query: str) -> str | None:
        """The corrected query, or ``None`` when nothing was rewritten.

        Only OOV tokens are corrected — in-vocab tokens are never
        rewritten, protecting proper nouns ("Tiamat") and rare but real
        terms. Tokens containing digits ("5e", "d20", "1d6") and tokens
        of length ≤ 2 are skipped. Non-ASCII queries are returned
        untouched (consistent with ``_rerank_safe_for_query``; the ASCII
        token regex would otherwise see fragments like "caf" for
        "café"). Corrections are spliced back into the original string,
        leaving punctuation and the casing of untouched tokens intact.
        """
        if not query.isascii():
            return None
        replacements: list[tuple[int, int, str]] = []
        for match in _TOKEN_RE.finditer(query):
            token = match.group()
            if len(token) <= 2 or any(c.isdigit() for c in token):
                continue
            if self._vocab.get(token.lower(), 0) >= self._min_freq:
                continue
            if token.lower() in _english_words():
                continue
            max_distance = 1 if len(token) <= 4 else 2
            suggestions = self._symspell.lookup(
                token,
                Verbosity.TOP,
                max_edit_distance=max_distance,
                transfer_casing=True,
            )
            if suggestions and suggestions[0].term.lower() != token.lower():
                replacements.append(
                    (match.start(), match.end(), suggestions[0].term)
                )
        if not replacements:
            return None
        out: list[str] = []
        prev = 0
        for start, end, replacement in replacements:
            out.append(query[prev:start])
            out.append(replacement)
            prev = end
        out.append(query[prev:])
        return "".join(out)
