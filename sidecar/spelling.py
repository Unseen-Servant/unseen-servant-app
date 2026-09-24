"""Library-derived vocabulary + spell correction for search queries.

Sections A and B + Vocabulary of the typo-tolerance design
(docs/retrieval/2026-07-10-typo-tolerance-design.md): out-of-
vocabulary query tokens are rewritten to the closest in-vocabulary term
before embedding, so a misspelled query returns (approximately) the
results of its corrected form. ``expand()`` (section B, behind the
default-off ``variant_expansion`` search flag — its eval gate failed)
derives spacing-variant queries from the same vocabulary.

The vocabulary is a term → frequency map over the indexed chunks —
lowercased, unstemmed, same ``[A-Za-z0-9]+`` token alphabet as
``lexical.py``. It is a separate pass, not a reuse of the lexical index:
the FTS5 index is porter-stemmed, the wrong surface forms for a spell
dictionary. Terms below ``MIN_VOCAB_FREQ`` are treated as extraction
junk ("byweapon"): they are neither protected from correction nor
loaded into the dictionary as correction targets.
"""
from __future__ import annotations

import math
import re
from importlib.resources import files
from pathlib import Path
from typing import Callable

from symspellpy import SymSpell, Verbosity

from parents_store import count_phrases, open_store

# A term is in-vocab (protected, and a valid correction target) only at
# this frequency or above. Start 3 per the design; tune during eval.
MIN_VOCAB_FREQ = 3

# Variant expansion (section B): at most this many variant queries
# beyond the primary — realistic queries have one or two candidate
# spots; the cap bounds the fan-out.
MAX_VARIANTS = 2

# A split part shorter than this is a tokenization artifact, not a
# word: possessives ("player's") put a bare high-frequency "s" in every
# library vocabulary, which would otherwise split "sword" into "s word".
MIN_SPLIT_PART_LEN = 3

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# Context tie-break (roadmap 3.5): among candidates at the closest edit
# distance, raw frequency sends "thif" to "this" and "muct" to "must".
# The neighbouring words settle it, from two sources: the library's own
# phrases ("thief skill", "chain mail") and, for the question frame
# rulebooks never print ("how does", "what is"), SymSpell's English
# bigram list. Each candidate scores
#   log(1 + freq)
#   + CONTEXT_WEIGHT · Σ log(1 + library units containing the pair)
#   + ENGLISH_CONTEXT_WEIGHT · Σ log(1 + English bigram count / scale)
# over the pairs it would form with the words either side. Only the most
# frequent MAX_CONTEXT_CANDIDATES are scored, bounding the phrase lookups.
CONTEXT_WEIGHT = 2.0
ENGLISH_CONTEXT_WEIGHT = 1.0
ENGLISH_BIGRAM_SCALE = 1e6
MAX_CONTEXT_CANDIDATES = 10

PhraseCounter = Callable[[list[tuple[str, ...]]], dict[tuple[str, ...], int]]

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


_english_bigrams_cache: dict[str, int] | None = None


def _english_bigrams() -> dict[str, int]:
    """SymSpell's English bigrams, keyed "a b", that involve a stopword.

    English context is only there for the question frame ("how does",
    "what is") — content pairs come from the library. Keeping only
    stopword pairs scored identically on the spell bench and holds
    ~12 MB instead of ~53 MB for the full 242k-pair table.
    """
    global _english_bigrams_cache
    if _english_bigrams_cache is None:
        from lexical import _STOPWORDS

        text = files("symspellpy").joinpath(
            "frequency_bigramdictionary_en_243_342.txt"
        ).read_text()
        table = {}
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 3 and (
                parts[0] in _STOPWORDS or parts[1] in _STOPWORDS
            ):
                table[f"{parts[0]} {parts[1]}"] = int(parts[2])
        _english_bigrams_cache = table
    return _english_bigrams_cache


def keyword_tokens(known_systems: dict[str, list[str]]) -> set[str]:
    """Lowercase tokens of every game-system keyword ("dnd", "osric",
    "year", "zero") — the words ``SpellCorrector.correct`` must protect."""
    return {
        t for keywords in known_systems.values() for kw in keywords
        for t in _TOKEN_RE.findall(kw.lower())
    }


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


def build_vocabulary_from_store(data_dir: Path) -> dict[str, int]:
    """Term → frequency over the persisted embed units (``unit_fts``).

    Same counting as ``build_vocabulary``, one SQLite read instead of a
    full Chroma scan: ``unit_fts.text`` is written as ``_embed_text(eu)``,
    i.e. exactly the heading-prepended text ``build_vocabulary``
    reassembles from documents + metadata. Used whenever the store has
    rows; a legacy index predating ``unit_fts`` still needs the Chroma
    path.
    """
    vocab: dict[str, int] = {}
    with open_store(data_dir) as conn:
        for (text,) in conn.execute("SELECT text FROM unit_fts"):
            for token in _TOKEN_RE.findall(text.lower()):
                vocab[token] = vocab.get(token, 0) + 1
    return vocab


class SpellCorrector:
    """Rewrites OOV query tokens to the closest in-vocabulary term."""

    def __init__(
        self,
        vocabulary: dict[str, int],
        min_freq: int = MIN_VOCAB_FREQ,
        phrase_counts: PhraseCounter | None = None,
    ) -> None:
        self._vocab = vocabulary
        self._min_freq = min_freq
        self._phrase_counts = phrase_counts
        self._symspell = SymSpell(max_dictionary_edit_distance=2)
        for term, freq in vocabulary.items():
            if freq >= min_freq:
                self._symspell.create_dictionary_entry(term, freq)

    @classmethod
    def from_collection(cls, collection) -> "SpellCorrector":
        return cls(build_vocabulary(collection))

    @classmethod
    def from_store(cls, data_dir: Path) -> "SpellCorrector":
        """Vocabulary and neighbour-pair context both from ``unit_fts``."""
        return cls(
            build_vocabulary_from_store(data_dir),
            phrase_counts=lambda phrases: count_phrases(data_dir, phrases),
        )

    def correct(
        self, query: str, protected: set[str] | None = None
    ) -> str | None:
        """The corrected query, or ``None`` when nothing was rewritten.

        Only OOV tokens are corrected — in-vocab tokens are never
        rewritten, protecting proper nouns ("Tiamat") and rare but real
        terms. Tokens containing digits ("5e", "d20", "1d6") and tokens
        of length ≤ 2 are skipped, and so are ``protected`` tokens
        (lowercase; the caller passes game-system keywords such as "dnd",
        which the library may never print). Non-ASCII queries are returned
        untouched (consistent with ``_rerank_safe_for_query``; the ASCII
        token regex would otherwise see fragments like "caf" for
        "café"). Corrections are spliced back into the original string,
        leaving punctuation and the casing of untouched tokens intact.
        """
        if not query.isascii():
            return None
        replacements: list[tuple[int, int, str]] = []
        matches = list(_TOKEN_RE.finditer(query))
        for k, match in enumerate(matches):
            token = match.group()
            if len(token) <= 2 or any(c.isdigit() for c in token):
                continue
            if self._vocab.get(token.lower(), 0) >= self._min_freq:
                continue
            if token.lower() in _english_words():
                continue
            if protected and token.lower() in protected:
                continue
            max_distance = 1 if len(token) <= 4 else 2
            suggestions = self._symspell.lookup(
                token,
                Verbosity.CLOSEST,
                max_edit_distance=max_distance,
                transfer_casing=True,
            )
            if not suggestions:
                continue
            left = matches[k - 1].group().lower() if k > 0 else None
            right = matches[k + 1].group().lower() if k + 1 < len(matches) else None
            best = self._best(suggestions, left, right)
            if best.lower() != token.lower():
                replacements.append((match.start(), match.end(), best))
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

    def _best(self, suggestions, left: str | None, right: str | None) -> str:
        """The candidate to use among those at the closest distance.

        SymSpell orders them by frequency; with one candidate, no
        neighbours or no phrase counter, that order stands. Otherwise
        the context score above decides (ties keep frequency order).
        """
        top = suggestions[:MAX_CONTEXT_CANDIDATES]
        if len(top) == 1 or not (left or right):
            return top[0].term
        pairs: dict[str, list[tuple[str, ...]]] = {}
        for s in top:
            term = s.term.lower()
            pairs[s.term] = (
                ([(left, term)] if left else []) + ([(term, right)] if right else [])
            )
        counts = (
            self._phrase_counts([p for ps in pairs.values() for p in ps])
            if self._phrase_counts is not None else {}
        )
        english = _english_bigrams() if ENGLISH_CONTEXT_WEIGHT else {}

        def score(s) -> float:
            lib = sum(math.log1p(counts.get(p, 0)) for p in pairs[s.term])
            eng = sum(
                math.log1p(english.get(" ".join(p), 0) / ENGLISH_BIGRAM_SCALE)
                for p in pairs[s.term]
            )
            return (
                math.log1p(s.count)
                + CONTEXT_WEIGHT * lib
                + ENGLISH_CONTEXT_WEIGHT * eng
            )

        return max(top, key=score).term  # max keeps the first of equals

    def _in_vocab(self, term: str) -> bool:
        return self._vocab.get(term, 0) >= self._min_freq

    def expand(self, query: str) -> list[str]:
        """Spacing-variant queries (section B), each one edit, capped.

        Direct vocabulary checks, no symspell. Join: an adjacent token
        pair separated by pure whitespace whose concatenation is
        in-vocab. Split: a token (in-vocab or not) writable as two
        in-vocab parts — when several boundaries qualify, the one
        maximizing ``min(freq(a), freq(b))`` wins. Variants are
        collected left to right and capped at ``MAX_VARIANTS``.
        """
        if not query.isascii():
            return []
        matches = list(_TOKEN_RE.finditer(query))
        variants: list[str] = []
        for i, match in enumerate(matches):
            token = match.group()
            if i + 1 < len(matches):
                nxt = matches[i + 1]
                gap = query[match.end():nxt.start()]
                if gap.isspace() and self._in_vocab(
                    (token + nxt.group()).lower()
                ):
                    variants.append(query[:match.end()] + query[nxt.start():])
            best_split: tuple[int, int] | None = None  # (min_freq, boundary)
            for k in range(
                MIN_SPLIT_PART_LEN, len(token) - MIN_SPLIT_PART_LEN + 1
            ):
                a, b = token[:k].lower(), token[k:].lower()
                if self._in_vocab(a) and self._in_vocab(b):
                    score = min(self._vocab[a], self._vocab[b])
                    if best_split is None or score > best_split[0]:
                        best_split = (score, k)
            if best_split is not None:
                k = best_split[1]
                variants.append(
                    query[:match.start()]
                    + token[:k] + " " + token[k:]
                    + query[match.end():]
                )
        return variants[:MAX_VARIANTS]
