"""Cross-edition near-dup collapse (roadmap 2.3).

``dup_sections@10`` keys on (filename, breadcrumb), so it never catches
an SRD 5.1/5.2.1 twin — different file, different key. This folds that
user-visible twin into an earlier result's ``also_in`` before packing.
"""
from __future__ import annotations

import difflib
import re

from heading_text import strip_markup

NEAR_DUP_RATIO = 0.9
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_ALSO_IN_FIELDS = (
    "filename", "source", "page_start", "page_end",
    "page_label_start", "page_label_end", "section_id",
)


def leaf_title(section_heading: str) -> str:
    """Last ``>`` breadcrumb segment, stripped, lowercased, normalised."""
    leaf = (section_heading or "").rsplit(" > ", 1)[-1]
    return _NON_ALNUM_RE.sub(" ", strip_markup(leaf).lower()).strip()


def collapse_near_dups(results: list[dict], ratio: float = NEAR_DUP_RATIO) -> list[dict]:
    """Pure; fold a later cross-edition twin into an earlier kept
    result's ``also_in``. Every kept result carries ``also_in`` (maybe []).
    An empty ``leaf_title`` (a normal, un-headed pipeline output) never
    matches — "" == "" is not "same title" — so it neither merges into
    another result nor accepts one."""
    kept: list[dict] = []
    titles: list[str] = []
    for r in results:
        title = leaf_title(r["section_heading"])
        twin = next((k for k, t in zip(kept, titles) if title and t == title
                     and k["filename"] != r["filename"]
                     and difflib.SequenceMatcher(
                         None, k["matched_text"], r["matched_text"]
                     ).ratio() >= ratio), None)
        if twin is not None:
            twin["also_in"].append({f: r[f] for f in _ALSO_IN_FIELDS})
            continue
        kept.append({**r, "also_in": []})
        titles.append(title)
    return kept
