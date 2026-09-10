"""Heading text sanitation — roadmap 2026-09-02 item 1.1, issue #367.

pymupdf4llm's heading lines keep inline markup and, on small-caps display
fonts, pull descender glyphs (g, p, y, q, j) out of their words and append
them: ``S eed p`` for ``Speed``, ``Halfling Halflin Traits g`` for the two
headings ``Halfling`` / ``Halfling Traits``. The page's raw spans
(``server._extract_spans``) still carry the intact text, so they are the
oracle: a run of consecutive spans whose letters are exactly the heading's
letters, in fragment order, replaces the heading.

Pure functions, no I/O. Applied in promote_headings before font
signatures are computed, so a repaired ``Speed`` matches its body-size
span and stops being a level-1 root.
"""
from __future__ import annotations

import re

_MARKUP_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?>|\*+|(?<!\w)_+|_+(?!\w)|`|^#+\s*")
_WS_RE = re.compile(r"\s+")
_MIXED_RE = re.compile(r"[a-z][A-Z]")
_LONE_RE = re.compile(r"(?<![\w'])(?![aAI](?![\w']))[A-Za-z](?![\w'])")
_NON_ALPHA_RE = re.compile(r"[^a-z]")
_MAX_RUN = 4


def strip_markup(text: str) -> str:
    return _WS_RE.sub(" ", _MARKUP_RE.sub("", text or "")).strip()


def normalize_small_caps(text: str) -> str:
    def fix(word: str) -> str:
        if any(ch.isdigit() for ch in word) or not _MIXED_RE.search(word):
            return word
        return word[0].upper() + word[1:].lower()
    return " ".join(fix(w) for w in text.split(" "))


def _letters(s: str) -> str:
    return _NON_ALPHA_RE.sub("", s.lower())


def _is_subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(ch in it for ch in needle)


def _group_by_sig(parts: list[dict]) -> list[tuple[str, tuple[float, bool]]]:
    out: list[tuple[str, tuple[float, bool]]] = []
    for sp in parts:
        sig = (round(float(sp["size"]), 1), bool(sp["bold"]))
        text = _WS_RE.sub(" ", sp["text"]).strip()
        if out and out[-1][1] == sig:
            out[-1] = (f"{out[-1][0]} {text}", sig)
        else:
            out.append((text, sig))
    return out


def repair_from_spans(text: str, spans: list[dict], min_size: float = 0.0):
    if not _LONE_RE.search(text):
        return [(text, None)]
    target = _letters(text)
    kept = _letters(_LONE_RE.sub(" ", text))     # heading minus its stranded letters
    if not target:
        return [(text, None)]
    cands = [sp for sp in spans if _letters(sp.get("text", "")) and float(sp.get("size", 0)) >= min_size]
    for start in range(len(cands)):
        acc = ""
        for end in range(start, min(start + _MAX_RUN, len(cands))):
            acc += _letters(cands[end]["text"])
            if len(acc) > len(target):
                break
            if len(acc) == len(target) and sorted(acc) == sorted(target) and _is_subsequence(kept, acc):
                return _group_by_sig(cands[start:end + 1])
    return [(text, None)]


def sanitize(text: str, spans: list[dict], min_size: float = 0.0):
    clean = strip_markup(text)
    if not clean:
        return []
    out = []
    for part, sig in repair_from_spans(clean, spans, min_size):
        part = _WS_RE.sub(" ", normalize_small_caps(strip_markup(part))).strip()
        if part:
            out.append((part, sig))
    return out
