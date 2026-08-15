"""The skeleton's one guarantee: the typed IR imports and every retrieval-
bearing model carries bbox + page + section (constitution #6)."""
from domain.models import BBox, BBoxSpan, Chunk, ChunkKind, Document, SCHEMA_VERSION


def test_chunk_carries_bbox_page_section():
    c = Chunk(
        id="c1", doc_id="srd_5_1", section_id="s1", ordinal=0,
        kind=ChunkKind.prose, text="a goblin has AC 15",
        page_start=314, page_end=315,
        bbox_spans=(BBoxSpan(page=314, bbox=BBox(0, 0, 100, 20)),),
        lang="en",
    )
    assert c.section_id == "s1"
    assert c.page_start == 314 and c.page_end == 315
    assert c.bbox_spans[0].bbox.x1 == 100


def test_document_is_immutable_and_versioned():
    d = Document(id="srd_5_1", path="/x.pdf", title="SRD", page_count=403)
    assert SCHEMA_VERSION >= 1
    try:
        d.title = "nope"  # frozen
    except AttributeError:
        return
    raise AssertionError("Document should be frozen")
