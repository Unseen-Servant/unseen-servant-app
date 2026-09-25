"""`max_context_chars` packer (roadmap 2.2, API side).

`pack_results` walks the formatted results in rank order, accumulating
`len(text) + len(section_heading)` under a caller-supplied budget. The
first result that doesn't fit is cut down to its matched unit (if that
narrower text fits) and ends the list; everything already accepted
keeps its full section text. `None` means unlimited — every result
passes through unmodified except for the added `truncated: False` flag.
"""

from legend_lore.service import pack_results
from tests.test_search_sections import _search, section_client  # noqa: F401


def _r(text, matched, heading="H"):
    return {"text": text, "matched_text": matched, "section_heading": heading}


def test_pack_keeps_everything_when_unbudgeted():
    out = pack_results([_r("a" * 100, "a"), _r("b" * 100, "b")], None)
    assert [x["truncated"] for x in out] == [False, False]


def test_pack_truncates_the_last_result_to_its_matched_unit_and_stops():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "bb"), _r("c" * 100, "cc")], 150)
    assert len(out) == 2
    assert out[0]["truncated"] is False and out[1]["truncated"] is True and out[1]["text"] == "bb"


def test_pack_drops_a_result_whose_matched_unit_does_not_fit_either():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "b" * 60)], 110)
    assert len(out) == 1


def test_search_honours_max_context_chars(section_client):
    # The section fixture's single Kraken section (query="kraken", the
    # dedupe target of test_search_sections.py) runs ~181 chars
    # (text + heading), under the brief's suggested budget of 200 — a
    # budget that size would never force truncation here. 100 sits
    # between that full-section cost and the matched-unit fallback cost
    # (~38 chars), so the packer must cut it down instead of passing it
    # through whole.
    body = _search(section_client, query="kraken", rerank=False, max_context_chars=100)
    total = sum(len(r["text"]) + len(r["section_heading"]) for r in body["results"])
    assert total <= 100 and any(r["truncated"] for r in body["results"])
