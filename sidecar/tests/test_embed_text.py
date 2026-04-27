"""Unit tests for _embed_text — heading-prepend at embed time.

Pure-function tests on the helper that produces embedding text from a
chunk. Per hybrid_retrieval_spike (sibling experiments repo), prepending
the section_heading breadcrumb at embed time delivers +0.184 MRR@5 /
+0.150 recall@5; storage of chunk.text remains unchanged.
"""

from chunker import Chunk
from server import _embed_text


def _chunk(text: str, heading: str | None) -> Chunk:
    return Chunk(
        text=text,
        page_start=1,
        page_end=1,
        chunk_type="prose",
        section_heading=heading,
        source_pdf="test.pdf",
        chunker="structure_aware-v1",
        ordinal=0,
    )


def test_prepends_heading_when_present():
    c = _chunk("Goblins attack with crude weapons.", "PART 6: MONSTERS > Goblin")
    assert _embed_text(c) == "PART 6: MONSTERS > Goblin\n\nGoblins attack with crude weapons."


def test_returns_text_unchanged_when_heading_is_none():
    c = _chunk("Some uncategorized prose.", None)
    assert _embed_text(c) == "Some uncategorized prose."


def test_returns_text_unchanged_when_heading_is_empty_string():
    """The Chunk dataclass allows '' as a heading; treat falsy as 'no heading'."""
    c = _chunk("Some prose.", "")
    assert _embed_text(c) == "Some prose."


def test_preserves_chunk_text_verbatim():
    """Body text including markdown markers must pass through untouched."""
    body = "## Inline heading\n\n| col | val |\n|---|---|\n| a | 1 |"
    c = _chunk(body, "Tables")
    embedded = _embed_text(c)
    assert embedded.endswith(body)
    assert embedded.startswith("Tables\n\n")
