"""Canonical text from a reference file — md/txt direct, html→text, odt→text.

The digital-native references carry no page furniture and real table
structure, so their text is the ground truth the extraction axis verifies
golden specs against (and the retrieval axis verifies anchors against).
Shared by evals/retrieval/verify_anchors.py and evals/extraction/.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path


def _strip_markup(s: str) -> str:
    # The tag name must END at script/style: ODT content.xml is full of
    # <style:style .../> with no </style> closer, and a bare "<style" prefix
    # lazily scanned to EOF for every one of them (9,483 × 3.9 M chars on the
    # BFRPG reference — 27 min per verify run).
    s = re.sub(r"<(script|style)(?![\w:-])[^>]*>[\s\S]*?</\1\s*>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return s


def ref_text(path: Path) -> str:
    """Reference text. md/txt read raw; html/htm stripped of tags; odt is a
    zip whose content.xml holds the body (tables are real table elements)."""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix in {".html", ".htm"}:
        return _strip_markup(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix == ".odt":
        with zipfile.ZipFile(path) as z:
            return _strip_markup(z.read("content.xml").decode("utf-8", "ignore"))
    raise ValueError(f"unsupported reference type: {path}")
