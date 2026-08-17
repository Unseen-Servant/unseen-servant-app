"""Phase 3 rung 6 — system/game boost (plan §3.4). Pure keyword→source detection
+ stable soft-boost. The keyword map is data (eval: manifest+defaults; production:
the user's tag keyword lists) — this logic is agnostic to its source."""
from query.boost import boost_order, detect_sources

KMAP = {
    "osric": {"OSRIC.pdf"},
    "basic fantasy": {"BFRPG.pdf"},
    "cairn": {"Cairn.pdf"},
    "dnd": {"srd1.pdf", "srd2.pdf"},
    "5e": {"srd1.pdf", "srd2.pdf"},
}


def test_detect_single_system():
    assert detect_sources("osric falling damage distance dice", KMAP) == {"OSRIC.pdf"}


def test_detect_multiword_keyword():
    assert detect_sources("basic fantasy chain mail cost", KMAP) == {"BFRPG.pdf"}


def test_detect_none_when_no_system_named():
    assert detect_sources("how much falling damage do you take", KMAP) == set()


def test_detect_multi_file_system_unions_sources():
    assert detect_sources("dnd 5e magic missile", KMAP) == {"srd1.pdf", "srd2.pdf"}


def test_single_token_needs_word_boundary():
    assert detect_sources("cairngorm mountains", KMAP) == set()  # 'cairn' must not fire inside a word


def test_boost_moves_matched_to_front_stable():
    ranked = ["u1", "u2", "u3", "u4"]
    src = {"u1": "A.pdf", "u2": "B.pdf", "u3": "B.pdf", "u4": "A.pdf"}
    assert boost_order(ranked, src, {"B.pdf"}) == ["u2", "u3", "u1", "u4"]  # B first, order preserved


def test_boost_is_soft_keeps_unmatched_as_fallback():
    ranked = ["u1", "u2"]
    out = boost_order(ranked, {"u1": "A.pdf", "u2": "B.pdf"}, {"B.pdf"})
    assert set(out) == {"u1", "u2"} and out[0] == "u2"  # unmatched kept, not filtered


def test_boost_noop_when_nothing_detected():
    ranked = ["u1", "u2"]
    assert boost_order(ranked, {"u1": "A", "u2": "B"}, set()) == ["u1", "u2"]
