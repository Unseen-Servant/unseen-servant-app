"""Frontmatter for Command's own keys (command/frontmatter.py): every write
touches only its key's lines, and is parsed back before it's accepted."""

from datetime import date

import pytest

from command import frontmatter as fm
from command.frontmatter import FrontmatterError


def test_split_finds_the_fences_and_leaves_the_body():
    parts = fm.split("---\nrole: ally\n---\n# Ismark\n")
    assert (parts.block, parts.body) == ("role: ally\n", "# Ismark\n")
    assert fm.split("# No frontmatter\n---\n").block is None
    assert fm.split("---\nunclosed: yes\n").block is None


def test_load_reads_keys_and_refuses_broken_yaml():
    assert fm.load("---\nspent: 2026-10-18\n---\n") == {"spent": date(2026, 10, 18)}
    assert fm.load("no frontmatter") == {}
    with pytest.raises(FrontmatterError):
        fm.load("---\nnotes: [unclosed\n---\n")
    assert fm.load_lenient("---\nnotes: [unclosed\n---\n") == {}


@pytest.mark.parametrize("entry, target", [
    ("[[Ismark]]", "Ismark"),
    ("[[Ismark|the son]]", "Ismark"),
    ("[[NPCs/Ismark.md#Goals]]", "Ismark"),
    ("Ismark", "Ismark"),
    ([["Ismark"]], "Ismark"),  # `- [[Ismark]]` unquoted
])
def test_link_target(entry, target):
    assert fm.link_target(entry) == target


def test_set_key_adds_frontmatter_to_a_bare_note():
    out = fm.set_key("Dusk. The wolves come.\n", "notes", ["[[Ismark]]", "[[Wolves]]"])
    assert out == '---\nnotes:\n  - "[[Ismark]]"\n  - "[[Wolves]]"\n---\nDusk. The wolves come.\n'


def test_set_key_touches_only_its_own_lines():
    text = (
        "---\n"
        "# hand-written comment\n"
        "role:   ally   # spacing kept\n"
        "notes: ['[[Old]]']\n"
        "tags:\n"
        "- npc\n"
        "- barovia\n"
        "---\n"
        "Body [[Old]].\n"
    )
    out = fm.set_key(text, "notes", ["[[Ismark]]"])
    assert out == (
        "---\n"
        "# hand-written comment\n"
        "role:   ally   # spacing kept\n"
        "notes:\n"
        '  - "[[Ismark]]"\n'
        "tags:\n"
        "- npc\n"
        "- barovia\n"
        "---\n"
        "Body [[Old]].\n"
    )


def test_set_key_replaces_a_block_list_and_keeps_what_follows():
    text = '---\nnotes:\n  - "[[A]]"\n\n  - "[[B]]"\n\nrole: ally\n---\n'
    assert fm.set_key(text, "notes", []) == "---\nnotes: []\n\nrole: ally\n---\n"


def test_set_key_appends_a_new_key_at_the_end():
    out = fm.set_key("---\nrole: ally\n---\nBody\n", "spent", date(2026, 10, 18))
    assert out == "---\nrole: ally\nspent: 2026-10-18\n---\nBody\n"


def test_removing_the_only_key_drops_the_block():
    assert fm.set_key("---\nspent: 2026-10-18\n---\nBody\n", "spent", None) == "Body\n"
    assert fm.set_key("---\nrole: ally\nspent: yes\n---\nB", "spent", None) == "---\nrole: ally\n---\nB"
    assert fm.set_key("Body\n", "spent", None) == "Body\n"


def test_set_key_keeps_bom_crlf_and_the_fence_style():
    text = "﻿---\r\nrole: ally\r\n...\r\nBody\r\n"
    out = fm.set_key(text, "spent", date(2026, 10, 18))
    assert out == "﻿---\r\nrole: ally\r\nspent: 2026-10-18\r\n...\r\nBody\r\n"


def test_set_key_quotes_names_yaml_would_misread():
    out = fm.set_key("", "notes", ["[[Bildrath's Shop]]", "[[Ismark: the Lesser]]", '[[He said "no"]]'])
    assert fm.load(out)["notes"] == ["[[Bildrath's Shop]]", "[[Ismark: the Lesser]]", '[[He said "no"]]']


def test_set_key_refuses_broken_frontmatter_and_duplicate_keys():
    with pytest.raises(FrontmatterError):
        fm.set_key("---\nnotes: [unclosed\n---\n", "spent", date(2026, 10, 18))
    with pytest.raises(FrontmatterError):
        fm.set_key("---\nnotes: []\nnotes: []\n---\n", "notes", ["[[A]]"])


def test_spent_and_date_values():
    assert fm.spent_value(date(2026, 10, 18)) == "2026-10-18"
    assert fm.spent_value(True) == "yes"
    assert fm.spent_value(False) is None
    assert fm.spent_value(None) is None
    assert fm.date_value("someday") == "someday"
