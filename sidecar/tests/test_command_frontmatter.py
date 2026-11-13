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


def test_a_value_shaped_like_a_date_that_is_not_one_reads_as_text():
    """PyYAML raises ValueError building it, which is no YAMLError: one such
    note used to make the whole campaign fail to load."""
    text = "---\nborn: 1021-15-40\nspent: 2026-01-12\nnotes:\n  - \"[[Ismark]]\"\n---\nBody\n"
    meta = fm.load(text)
    assert meta["born"] == "1021-15-40"
    assert meta["notes"] == ["[[Ismark]]"]
    assert fm.spent_value(meta["spent"]) == "2026-01-12"
    assert fm.load_lenient(text) == meta
    # And Command still writes its own keys in such a note.
    assert "spent: 2026-02-01" in fm.set_key(text, "spent", date(2026, 2, 1))


def test_a_read_raises_nothing_but_its_own_error(monkeypatch):
    def broken(*args, **kwargs):
        raise RecursionError("too deep")

    monkeypatch.setattr(fm.yaml, "safe_load", broken)
    monkeypatch.setattr(fm.yaml, "load", broken)
    with pytest.raises(fm.FrontmatterError, match="can't be read"):
        fm.load("---\na: 1\n---\n")
    assert fm.load_lenient("---\na: 1\n---\n") == {}


@pytest.mark.parametrize("entry, target", [
    ("[[Ismark]]", "Ismark"),
    ("[[Ismark|the son]]", "Ismark"),
    ("[[NPCs/Ismark.md#Goals]]", "Ismark"),
    ("Ismark", "Ismark"),
    ([["Ismark"]], "Ismark"),  # `- [[Ismark]]` unquoted
])
def test_link_target(entry, target):
    assert fm.link_target(entry) == target


def test_link_path_keeps_the_folders():
    assert fm.link_path("[[Locations/Svalich Road.md|the road]]") == "Locations/Svalich Road"
    assert fm.entry_text([["NPCs/Ismark"]]) == "[[NPCs/Ismark]]"  # `- [[NPCs/Ismark]]` unquoted


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


def test_set_key_writes_a_whole_number_bare():
    # Foresight's round (Foresight design §3); a bool is no number.
    assert fm.set_key("", "round", 3) == "---\nround: 3\n---\n"
    assert fm.load(fm.set_key("---\nround: 2\n---\n", "round", 12)) == {"round": 12}
    assert fm.set_key("", "turn", "Goblin 2") == '---\nturn: "Goblin 2"\n---\n'


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
