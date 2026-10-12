"""The session log (command/log.py, design §4): where Command appends, and
how the arrangement reads the section back."""

from datetime import datetime

import pytest

from command import log
from command.vault import Invalid

LINE = "- 19:42 ▶ [[Ambush]]"


@pytest.mark.parametrize(("text", "expected"), [
    ("", f"## Log\n{LINE}\n"),
    ("Prep notes.\n", f"Prep notes.\n\n## Log\n{LINE}\n"),
    ("Prep notes.", f"Prep notes.\n\n## Log\n{LINE}\n"),
    ("Prep notes.\n\n", f"Prep notes.\n\n## Log\n{LINE}\n"),
])
def test_a_note_without_a_log_gets_the_heading_at_the_end(text, expected):
    assert log.add_line(text, LINE) == expected


def test_entries_go_after_the_last_entry_before_the_next_section():
    text = "Prep.\n\n## Log\n- 19:00 ▶ [[Opening]]\n\n## Afterwards\nNotes.\n"
    assert log.add_line(text, LINE) == (
        "Prep.\n\n## Log\n- 19:00 ▶ [[Opening]]\n" + LINE + "\n\n## Afterwards\nNotes.\n"
    )


def test_a_subheading_stays_inside_the_log():
    text = "## Log\n### First hour\n- 19:00 jot\n"
    assert log.add_line(text, LINE) == f"## Log\n### First hour\n- 19:00 jot\n{LINE}\n"


def test_the_last_log_section_is_the_one_written():
    text = "## Log\n- 18:00 old\n## Prep\n## Log\n"
    assert log.add_line(text, LINE) == f"## Log\n- 18:00 old\n## Prep\n## Log\n{LINE}\n"


def test_a_heading_or_entry_without_a_final_break_and_crlf_files():
    assert log.add_line("## Log", LINE) == f"## Log\n{LINE}"
    assert log.add_line("## Log\r\n- 19:00 jot\r\n", LINE) == f"## Log\r\n- 19:00 jot\r\n{LINE}\r\n"
    assert log.add_line("Prep.\r\n", LINE) == f"Prep.\r\n\r\n## Log\r\n{LINE}\r\n"


def test_parse_reads_commands_lines_and_keeps_the_rest_as_jots():
    text = (
        "## Log\n"
        "- 19:42 ▶ [[Ambush on the road|the ambush]]\n"
        "- 20:15 spent [[Secrets/Ravens watch]]\n"
        "- 20:16 unspent [[Ravens watch]]\n"
        "- 20:22 the party insulted the burgomaster\n"
        "\n"
        "- 20:31 captured [[Bildrath's shop]]\n"
        "- remembered later: Ireena's locket\n"
        "Some prose the GM wrote.\n"
        "- 21:00 ▶ [[Ambush]] and then some\n"
    )
    assert [(e["time"], e["kind"], e["link"]) for e in log.parse(text)] == [
        ("19:42", "launch", "Ambush on the road"),
        ("20:15", "spent", "Ravens watch"),
        ("20:16", "unspent", "Ravens watch"),
        ("20:22", "jot", None),
        ("20:31", "captured", "Bildrath's shop"),
        (None, "jot", None),
        (None, "jot", None),
        ("21:00", "jot", None),
    ]
    assert log.parse(text)[3]["text"] == "the party insulted the burgomaster"
    assert log.parse("No log here.\n") == []


def test_append_stamps_the_time_and_keeps_entries_on_one_line(tmp_path, monkeypatch):
    monkeypatch.setattr(log, "now", lambda: datetime(2026, 10, 18, 9, 5))
    camp = tmp_path / "Strahd"
    (camp / "Sessions").mkdir(parents=True)
    note = camp / "Sessions" / "Session 1.md"
    note.write_text("---\ndate: 2026-10-18\n---\n")
    assert log.append(camp, "Sessions/Session 1.md", "  the party\nleft  town ") == "- 09:05 the party left town"
    assert note.read_text() == "---\ndate: 2026-10-18\n---\n\n## Log\n- 09:05 the party left town\n"
    with pytest.raises(Invalid):
        log.append(camp, "Sessions/Session 1.md", " \n ")
