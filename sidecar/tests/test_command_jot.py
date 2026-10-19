"""A jot (command/jot.py, design §5.2): where it lands in the session note."""

import pytest

from command import jot
from command.vault import Invalid

JOT = "- the party insulted the burgomaster"


@pytest.mark.parametrize(("text", "expected"), [
    ("", f"{JOT}\n"),
    ("---\ndate: 2026-10-18\n---\n", f"---\ndate: 2026-10-18\n---\n\n{JOT}\n"),
    ("Prep notes.", f"Prep notes.\n\n{JOT}\n"),
    ("Prep notes.\n\n", f"Prep notes.\n\n{JOT}\n\n"),
    ("- earlier\n", f"- earlier\n{JOT}\n"),
    ("Prep.\r\n", f"Prep.\r\n\r\n{JOT}\r\n"),
])
def test_a_jot_goes_at_the_end_of_the_text(text, expected):
    assert jot.add_jot(text, JOT) == expected


def test_an_old_log_heading_is_just_text():
    # Command wrote a ## Log until 2026-10-18; a jot no longer goes above it.
    assert jot.add_jot("Prep.\n\n## Log\n- 19:42 ▶ [[Ambush]]\n", JOT) == (
        f"Prep.\n\n## Log\n- 19:42 ▶ [[Ambush]]\n{JOT}\n"
    )


def test_jot_writes_one_line_without_a_time(tmp_path):
    camp = tmp_path / "Strahd"
    (camp / "Sessions").mkdir(parents=True)
    note = camp / "Sessions" / "Session 1.md"
    note.write_text("---\ndate: 2026-10-18\n---\n")
    assert jot.jot(camp, "Sessions/Session 1.md", "  the party\nleft  town ") == "- the party left town"
    assert note.read_text() == "---\ndate: 2026-10-18\n---\n\n- the party left town\n"
    with pytest.raises(Invalid):
        jot.jot(camp, "Sessions/Session 1.md", " \n ")
