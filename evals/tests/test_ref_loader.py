"""Reference-text loader (evals/extraction/ref_loader.py)."""
import time

from evals.extraction.ref_loader import _strip_markup


def test_strips_script_and_style_blocks_but_keeps_body_text():
    html = "<style>p {color: red}</style><script>alert(1)</script><p>Falling damage is 1d6</p>"
    assert _strip_markup(html).split() == ["Falling", "damage", "is", "1d6"]


def test_odt_style_namespace_tags_do_not_trigger_a_scan_to_end_of_file():
    # ODT content.xml carries thousands of <style:style .../> tags and no
    # </style> closer; a bare "<(script|style)" lazily scanned to EOF for each
    # one (9,483 tags × 3.9 M chars on the BFRPG reference = 27 min per run).
    tags = '<style:style style:name="P1" style:family="paragraph"/>' * 1500
    xml = tags + "<text:p>Cloud dragon armor class 22</text:p>" + tags
    t0 = time.perf_counter()
    out = _strip_markup(xml)
    assert time.perf_counter() - t0 < 2.0
    assert "Cloud dragon armor class 22" in out
