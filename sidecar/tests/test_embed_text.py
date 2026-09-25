"""Unit tests for _embed_text — heading-prepend at embed time.

Pure-function tests on the helper that produces embedding text from an
EmbedUnit. Per hybrid_retrieval_spike (sibling experiments repo),
prepending the section_heading breadcrumb at embed time delivers
+0.184 MRR@5 / +0.150 recall@5; storage of the embed unit text remains
unchanged.
"""

from legend_lore.granularity import EmbedUnit
from legend_lore.service import _embed_text


def _eu(text: str, heading: str | None) -> EmbedUnit:
    return EmbedUnit(
        chunk_id="0",
        text=text,
        parent_id="p_test",
        chunk_type="prose",
        section_heading=heading,
        source_pdf="test.pdf",
        page_start=1,
        page_end=1,
        ordinal=0,
    )


def test_prepends_heading_when_present():
    eu = _eu("Goblins attack with crude weapons.", "PART 6: MONSTERS > Goblin")
    assert _embed_text(eu) == "PART 6: MONSTERS > Goblin\n\nGoblins attack with crude weapons."


def test_returns_text_unchanged_when_heading_is_none():
    eu = _eu("Some uncategorized prose.", None)
    assert _embed_text(eu) == "Some uncategorized prose."


def test_returns_text_unchanged_when_heading_is_empty_string():
    """The dataclass allows '' as a heading; treat falsy as 'no heading'."""
    eu = _eu("Some prose.", "")
    assert _embed_text(eu) == "Some prose."


def test_preserves_text_verbatim():
    """Body text including markdown markers must pass through untouched."""
    body = "## Inline heading\n\n| col | val |\n|---|---|\n| a | 1 |"
    eu = _eu(body, "Tables")
    embedded = _embed_text(eu)
    assert embedded.endswith(body)
    assert embedded.startswith("Tables\n\n")
