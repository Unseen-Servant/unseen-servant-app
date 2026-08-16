"""Stage F (chunking) — structure-aware boundaries: heading/table walls,
~1000-char soft cap, no overlap, atomic tables (plan §3.2 F). Pure over Blocks."""
from domain.models import BBox, Block, BlockKind, ChunkKind
from ingest.chunk import chunk_blocks, SOFT_CAP


def blk(bid, kind, text, page=0, order=0):
    return Block(id=bid, kind=kind, text=text, page=page,
                 bbox=BBox(0, order * 20, 100, order * 20 + 18), reading_order=order, font_stats=None)


def test_prose_accumulates_into_one_chunk():
    blocks = [blk("p1", BlockKind.prose, "first para", 0, 0), blk("p2", BlockKind.prose, "second para", 0, 1)]
    chunks = chunk_blocks(blocks, {"p1": "s1", "p2": "s1"}, "d")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.kind is ChunkKind.prose and c.section_id == "s1"
    assert "first para" in c.text and "second para" in c.text


def test_soft_cap_splits_prose():
    body = "x " * (SOFT_CAP // 3)  # ~SOFT_CAP*2/3 chars per block; 3 blocks -> 2 chunks
    blocks = [blk(f"p{i}", BlockKind.prose, body, 0, i) for i in range(3)]
    chunks = chunk_blocks(blocks, {b.id: "s" for b in blocks}, "d")
    assert len(chunks) == 2


def test_heading_is_a_wall_not_a_chunk():
    blocks = [blk("a", BlockKind.prose, "before", 0, 0),
              blk("h", BlockKind.heading, "Title", 0, 1),
              blk("b", BlockKind.prose, "after", 0, 2)]
    chunks = chunk_blocks(blocks, {"a": "s0", "h": "s1", "b": "s1"}, "d")
    assert len(chunks) == 2
    assert all("Title" not in c.text for c in chunks)  # heading text isn't a chunk


def test_table_is_atomic_chunk():
    blocks = [blk("a", BlockKind.prose, "intro", 0, 0),
              blk("t", BlockKind.table, "Club 1d4\nDagger 1d6", 0, 1),
              blk("b", BlockKind.prose, "outro", 0, 2)]
    chunks = chunk_blocks(blocks, {"a": "s", "t": "s", "b": "s"}, "d")
    assert [c.kind for c in chunks] == [ChunkKind.prose, ChunkKind.table, ChunkKind.prose]
    assert chunks[1].text == "Club 1d4\nDagger 1d6"


def test_artifact_and_image_skipped():
    blocks = [blk("a", BlockKind.prose, "aaa", 0, 0),
              blk("f", BlockKind.artifact, "Page 42 footer", 0, 1),
              blk("i", BlockKind.image, "", 0, 2),
              blk("b", BlockKind.prose, "bbb", 0, 3)]
    chunks = chunk_blocks(blocks, {b.id: "s" for b in blocks}, "d")
    assert len(chunks) == 1
    assert "aaa" in chunks[0].text and "bbb" in chunks[0].text and "footer" not in chunks[0].text


def test_chunk_carries_section_pages_bbox_and_ordinal():
    blocks = [blk("p1", BlockKind.prose, "a", 0, 0), blk("p2", BlockKind.prose, "b", 1, 1)]
    c = chunk_blocks(blocks, {"p1": "s7", "p2": "s7"}, "d")[0]
    assert c.section_id == "s7" and c.ordinal == 0 and c.id == "d:c0"
    assert c.page_start == 0 and c.page_end == 1
    assert len(c.bbox_spans) == 2 and c.bbox_spans[1].page == 1
