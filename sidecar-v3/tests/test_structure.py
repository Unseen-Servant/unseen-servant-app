"""Stage E — section/heading tree (plan §3.2 E). Headings from block-kind +
font clustering + TOC pinning, with junk-heading rejection (R2 fix). Pure logic
over hand-built Blocks — no model, no corpus."""
from domain.models import BBox, Block, BlockKind, FontStats, Section
from ingest.structure import build_sections


def blk(bid, kind, text, page, size=11.0, order=0):
    return Block(
        id=bid, kind=kind, text=text, page=page, bbox=BBox(0, 0, 100, 20),
        reading_order=order, font_stats=FontStats(size=size, bold=(kind is BlockKind.heading)),
    )


def H(bid, text, page, size, order):
    return blk(bid, BlockKind.heading, text, page, size, order)


def P(bid, text, page, order):
    return blk(bid, BlockKind.prose, text, page, 11.0, order)


def test_heading_opens_section_and_content_belongs():
    blocks = [H("h", "Monsters", 0, 18, 0), P("p1", "A goblin has AC 15", 0, 1), P("p2", "more", 1, 2)]
    sections, assign = build_sections(blocks, toc=(), doc_id="d")
    assert len(sections) == 1
    s = sections[0]
    assert s.title == "Monsters" and s.level == 1 and s.parent_id is None
    assert s.page_start == 0 and s.page_end == 1
    assert assign["p1"] == s.id and assign["p2"] == s.id


def test_nested_sections_by_font_size():
    blocks = [H("c", "Chapter", 0, 18, 0), H("s", "Section", 0, 14, 1), P("p", "body", 0, 2)]
    sections, assign = build_sections(blocks, toc=(), doc_id="d")
    chapter = next(s for s in sections if s.title == "Chapter")
    section = next(s for s in sections if s.title == "Section")
    assert chapter.level == 1 and chapter.parent_id is None
    assert section.level == 2 and section.parent_id == chapter.id
    assert assign["p"] == section.id


def test_toc_depth_pins_level_over_font():
    # "Appendix" has a small font (would cluster to level 2) but is a TOC depth-1 entry.
    blocks = [H("t", "Big Title", 0, 20, 0), H("a", "Appendix", 5, 12, 1)]
    sections, _ = build_sections(blocks, toc=((1, "Appendix", 6),), doc_id="d")
    appendix = next(s for s in sections if s.title == "Appendix")
    assert appendix.level == 1 and appendix.parent_id is None


def test_junk_long_sentence_heading_rejected():
    junk = "When a character attacks a creature they must roll below their strength stat to hit them"
    blocks = [H("c", "Combat", 0, 16, 0), H("j", junk, 0, 16, 1), P("p", "body", 0, 2)]
    sections, assign = build_sections(blocks, toc=(), doc_id="d")
    assert len(sections) == 1 and sections[0].title == "Combat"
    assert assign["j"] == sections[0].id  # junk heading demoted to content


def test_junk_stat_line_heading_rejected():
    blocks = [H("g", "Goblin", 0, 14, 0), H("st", "AC 15 HP 7 Speed 30", 0, 11, 1), P("p", "x", 0, 2)]
    sections, _ = build_sections(blocks, toc=(), doc_id="d")
    assert len(sections) == 1 and sections[0].title == "Goblin"


def test_body_size_heading_demoted():
    # PP-DocLayout over-tags bold body-size lead-ins as paragraph_title; a
    # "heading" at the modal body font size (and not TOC-pinned) is a false
    # positive and must not open a section — this is the 364-sections/208pp
    # over-detection that failed the Phase-2 junk-breadcrumb criterion.
    blocks = [
        H("real", "Combat", 0, 16, 0),
        P("p1", "body one", 0, 1), P("p2", "body two", 0, 2), P("p3", "body three", 0, 3),
        H("fake", "Bold lead-in", 0, 11, 4),  # same size as the modal body prose
        P("p4", "body four", 0, 5),
    ]
    sections, assign = build_sections(blocks, toc=(), doc_id="d")
    assert len(sections) == 1 and sections[0].title == "Combat"
    assert assign["fake"] == sections[0].id  # demoted to content, not its own section


def test_toc_pin_survives_body_size_gate():
    # A heading at body size still counts when the TOC names it — an explicit
    # TOC entry is corroboration the font gate must not override.
    blocks = [
        H("c", "Combat", 0, 16, 0),
        P("p1", "body one", 0, 1), P("p2", "body two", 0, 2),
        H("a", "Appendix", 5, 11, 3),  # body size, but in the TOC
    ]
    sections, _ = build_sections(blocks, toc=((1, "Appendix", 6),), doc_id="d")
    assert any(s.title == "Appendix" for s in sections)


def test_content_before_first_heading_has_no_section():
    blocks = [P("intro", "preamble", 0, 0), H("c", "Chapter", 0, 16, 1), P("body", "b", 0, 2)]
    _, assign = build_sections(blocks, toc=(), doc_id="d")
    assert assign["intro"] is None and assign["body"] is not None


def test_section_ids_are_stable_and_prefixed():
    blocks = [H("c", "Chapter", 0, 18, 0)]
    sections, _ = build_sections(blocks, toc=(), doc_id="srd")
    assert sections[0].id.startswith("srd:s")
