"""Command's vault: folders as the only truth, and writes that touch only
what they mean to (docs/roadmap/2026-10-11-command-design.md §3).

Several tests here pin a failure of the two earlier Command apps (§1): a
note invisible for lacking frontmatter, a save landing on a file that had
changed underneath it, links left pointing at a renamed note.
"""

import json
import os

import pytest

from command import vault
from command.vault import Conflict, Invalid, NotFound


def write(path, text, *, raw: bytes | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "root"
    r.mkdir()
    return r


@pytest.fixture
def camp(root):
    """A campaign shaped like real data: tracks made by hand, no
    presentation file, a note with no frontmatter, Obsidian's own folder."""
    c = root / "Curse of Strahd"
    write(c / "NPCs" / "Ismark.md", "---\nrole: ally\n---\nBrother of [[Ireena]].\n")
    write(c / "NPCs" / "Ireena.md", "Sister of [[Ismark]].\n")
    write(c / "NPCs" / "Vallaki" / "Lady Wachter.md", "")
    write(c / "Locations" / "Village of Barovia.md", "[[Ismark|the burgomaster's son]] lives here.\n")
    write(c / "Beats" / "Ambush.md", '---\nnotes: ["[[Ismark]]", "[[Wolves]]"]\n---\n')
    write(c / "Sessions" / "Session 1.md", "")
    write(c / "Overview.md", "Loose note.\n")
    write(c / "Locations" / "map.png", "", raw=b"\x89PNG")
    write(c / ".obsidian" / "workspace.md", "hidden")
    write(c / "NPCs" / ".draft.md", "hidden")
    return c


# ---------------------------------------------------------------------------
# Names and paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["", "   ", ".hidden", "a/b", "a:b", "x#y", "[[x]]", "a|b", 'say "hi"', "trailing."])
def test_validate_name_refuses(name):
    with pytest.raises(Invalid):
        vault.validate_name(name)


def test_validate_name_strips_and_keeps_apostrophes():
    assert vault.validate_name("  Bildrath's Mercantile ") == "Bildrath's Mercantile"


@pytest.mark.parametrize("rel", ["../outside.md", "/etc/passwd", "NPCs/../../x.md", ".obsidian/workspace.md", "NPCs/.draft.md"])
def test_resolve_refuses_escapes_and_hidden(camp, rel):
    with pytest.raises(Invalid):
        vault.resolve(camp, rel)


def test_resolve_refuses_a_symlink_out_of_the_campaign(camp, tmp_path):
    outside = write(tmp_path / "secret.md", "not yours")
    os.symlink(outside, camp / "NPCs" / "link.md")
    with pytest.raises(Invalid):
        vault.resolve(camp, "NPCs/link.md")


def test_campaign_dir_refuses_hidden_and_missing(root):
    with pytest.raises(Invalid):
        vault.campaign_dir(root, "..")
    with pytest.raises(NotFound):
        vault.campaign_dir(root, "Nope")


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def test_scan_reads_the_folders(camp):
    index = vault.scan(camp)
    by_path = {n["path"]: n for n in index["notes"]}

    # Tracks are the non-reserved folders, alphabetical with no saved order.
    assert index["tracks"] == ["Locations", "NPCs"]
    # A note without frontmatter is a note (unseen-command hid these).
    assert by_path["NPCs/Ireena.md"] == {"name": "Ireena", "path": "NPCs/Ireena.md", "track": "NPCs", "group": None}
    assert by_path["NPCs/Vallaki/Lady Wachter.md"]["group"] == "Vallaki"
    assert by_path["Overview.md"]["track"] is None
    assert by_path["Beats/Ambush.md"]["track"] == "Beats"
    # Hidden files and folders, and non-Markdown files, are not notes.
    assert not any(".obsidian" in p or ".draft" in p or p.endswith(".png") for p in by_path)


def test_scan_flags_names_shared_across_folders(camp):
    write(camp / "Locations" / "ismark.md", "")
    assert vault.scan(camp)["ambiguous"] == ["ismark"]


def test_track_order_keeps_saved_order_then_alphabetical(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"tracks": ["NPCs", "Gone"]}))
    write(camp / "Monsters" / "Wolves.md", "")
    assert vault.track_order(camp) == ["NPCs", "Locations", "Monsters"]


def test_track_order_survives_a_corrupt_presentation_file(camp):
    write(camp / ".unseen" / "command.json", "{not json")
    assert vault.track_order(camp) == ["Locations", "NPCs"]


# ---------------------------------------------------------------------------
# Reading and saving
# ---------------------------------------------------------------------------

def test_read_note_returns_content_and_hash(camp):
    note = vault.read_note(camp, "NPCs/Ireena.md")
    assert note["content"] == "Sister of [[Ismark]].\n"
    assert note["hash"] == vault.content_hash(b"Sister of [[Ismark]].\n")


def test_read_note_refuses_non_utf8(camp):
    write(camp / "NPCs" / "Latin1.md", "", raw="café".encode("latin-1"))
    with pytest.raises(Invalid):
        vault.read_note(camp, "NPCs/Latin1.md")


def test_save_lands_on_the_file_that_was_loaded(camp):
    loaded = vault.read_note(camp, "NPCs/Ireena.md")
    new_hash = vault.write_note(camp, "NPCs/Ireena.md", "Edited.\n", loaded["hash"])
    assert (camp / "NPCs" / "Ireena.md").read_text() == "Edited.\n"
    assert new_hash == vault.content_hash(b"Edited.\n")
    # The other note is untouched: the save went to the path it carried.
    assert (camp / "NPCs" / "Ismark.md").read_text().startswith("---\nrole: ally")


def test_save_refuses_when_the_file_changed_on_disk(camp):
    loaded = vault.read_note(camp, "NPCs/Ireena.md")
    write(camp / "NPCs" / "Ireena.md", "Edited in Obsidian.\n")
    with pytest.raises(Conflict) as err:
        vault.write_note(camp, "NPCs/Ireena.md", "Edited in Command.\n", loaded["hash"])
    assert err.value.current_hash == vault.content_hash(b"Edited in Obsidian.\n")
    assert (camp / "NPCs" / "Ireena.md").read_text() == "Edited in Obsidian.\n"


def test_atomic_write_keeps_mode_and_leaves_no_temp_file(camp):
    path = camp / "NPCs" / "Ireena.md"
    os.chmod(path, 0o600)
    vault.atomic_write(path, b"new")
    assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in path.parent.iterdir()) == [".draft.md", "Ireena.md", "Ismark.md", "Vallaki"]


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------

def test_create_campaign_lays_out_default_tracks(root):
    assert vault.create_campaign(root, " Into the Odd ") == "Into the Odd"
    camp = root / "Into the Odd"
    assert vault.track_order(camp) == list(vault.DEFAULT_TRACKS)
    assert (camp / "Beats").is_dir() and (camp / "Sessions").is_dir()
    with pytest.raises(Conflict):
        vault.create_campaign(root, "into the odd")


def test_create_track_appends_and_refuses_reserved(camp):
    vault.create_track(camp, "Factions")
    assert vault.track_order(camp)[-1] == "Factions"
    with pytest.raises(Invalid):
        vault.create_track(camp, "beats")
    with pytest.raises(Conflict):
        vault.create_track(camp, "npcs")


def test_create_note_refuses_a_name_taken_anywhere_in_the_campaign(camp):
    assert vault.create_note(camp, "Locations", "Tser Pool") == "Locations/Tser Pool.md"
    assert (camp / "Locations" / "Tser Pool.md").read_bytes() == b""
    with pytest.raises(Conflict):
        vault.create_note(camp, "Locations", "ireena")
    with pytest.raises(NotFound):
        vault.create_note(camp, "Nowhere", "X")


# ---------------------------------------------------------------------------
# Link rewriting
# ---------------------------------------------------------------------------

MOVE = [(("Camp", "NPCs", "Ismark"), ("Camp", "NPCs", "Ismark the Lesser"))]


@pytest.mark.parametrize("before, after", [
    ("[[Ismark]]", "[[Ismark the Lesser]]"),
    ("[[ismark]]", "[[Ismark the Lesser]]"),
    ("[[Ismark|the son]]", "[[Ismark the Lesser|the son]]"),
    ("[[Ismark#Goals|goals]]", "[[Ismark the Lesser#Goals|goals]]"),
    ("| [[Ismark\\|son]] |", "| [[Ismark the Lesser\\|son]] |"),
    ("![[Ismark]]", "![[Ismark the Lesser]]"),
    ("[[Ismark.md]]", "[[Ismark the Lesser.md]]"),
    ("[[NPCs/Ismark]]", "[[NPCs/Ismark the Lesser]]"),
    ("[[Vault/Camp/NPCs/Ismark]]", "[[Vault/Camp/NPCs/Ismark the Lesser]]"),
    ("[[Ireena]] and [Ismark](x) and [[Ismarks]]", "[[Ireena]] and [Ismark](x) and [[Ismarks]]"),
    ("[[Locations/Ismark]]", "[[Locations/Ismark]]"),
])
def test_rewrite_links(before, after):
    assert vault.rewrite_links(before, MOVE) == after


def test_rewrite_links_keeps_shape_on_a_move():
    moves = [(("Camp", "NPCs", "Ismark"), ("Camp", "Locations", "Ismark"))]
    text = "[[Ismark]] [[NPCs/Ismark]] [[Camp/NPCs/Ismark|x]]"
    assert vault.rewrite_links(text, moves) == "[[Ismark]] [[Locations/Ismark]] [[Camp/Locations/Ismark|x]]"


def test_rewrite_links_escapes_apostrophes_in_single_quoted_yaml():
    moves = [(("C", "Locations", "Shop"), ("C", "Locations", "Bildrath's Shop"))]
    text = "---\nnotes: ['[[Shop]]', \"[[Shop]]\"]\n---\n[[Shop]] in 'quotes [[Shop]]'\n"
    assert vault.rewrite_links(text, moves) == (
        "---\nnotes: ['[[Bildrath''s Shop]]', \"[[Bildrath's Shop]]\"]\n---\n"
        "[[Bildrath's Shop]] in 'quotes [[Bildrath's Shop]]'\n"
    )


def test_rename_note_rewrites_links_and_nothing_else(camp):
    # CRLF, a BOM and trailing spaces must survive the rewrite byte for byte.
    write(camp / "NPCs" / "Doru.md", "", raw="﻿---\r\nkin: \"[[Ismark]]\"  \r\n---\r\nSee [[Ismark]].  \r\n".encode())
    path, rewritten = vault.rename_note(camp, "NPCs/Ismark.md", "Ismark Kolyanovich")

    assert path == "NPCs/Ismark Kolyanovich.md"
    assert not (camp / "NPCs" / "Ismark.md").exists()
    assert sorted(rewritten) == ["Beats/Ambush.md", "Locations/Village of Barovia.md", "NPCs/Doru.md", "NPCs/Ireena.md"]
    assert (camp / "NPCs" / "Doru.md").read_bytes() == (
        "﻿---\r\nkin: \"[[Ismark Kolyanovich]]\"  \r\n---\r\nSee [[Ismark Kolyanovich]].  \r\n".encode()
    )
    assert (camp / "Beats" / "Ambush.md").read_text() == '---\nnotes: ["[[Ismark Kolyanovich]]", "[[Wolves]]"]\n---\n'
    assert (camp / "Locations" / "Village of Barovia.md").read_text().startswith("[[Ismark Kolyanovich|the burgomaster's son]]")


def test_rename_note_refuses_a_clash_but_allows_a_case_change(camp):
    with pytest.raises(Conflict):
        vault.rename_note(camp, "NPCs/Ismark.md", "IREENA")
    path, _ = vault.rename_note(camp, "NPCs/Ismark.md", "ISMARK")
    assert path == "NPCs/ISMARK.md"
    assert "[[ISMARK]]" in (camp / "NPCs" / "Ireena.md").read_text()


def test_move_note_leaves_name_links_alone(camp):
    write(camp / "Locations" / "Church.md", "[[Ismark]] [[NPCs/Ismark]]")
    path, rewritten = vault.move_note(camp, "NPCs/Ismark.md", "Locations")
    assert path == "Locations/Ismark.md"
    assert rewritten == ["Locations/Church.md"]
    assert (camp / "Locations" / "Church.md").read_text() == "[[Ismark]] [[Locations/Ismark]]"


def test_rename_track_keeps_its_place_and_rewrites_path_links(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"tracks": ["NPCs", "Locations"]}))
    write(camp / "Overview.md", "[[NPCs/Vallaki/Lady Wachter]] [[Ireena]]")
    rewritten = vault.rename_track(camp, "NPCs", "Characters")
    assert vault.track_order(camp) == ["Characters", "Locations"]
    assert rewritten == ["Overview.md"]
    assert (camp / "Overview.md").read_text() == "[[Characters/Vallaki/Lady Wachter]] [[Ireena]]"
    with pytest.raises(Invalid):
        vault.rename_track(camp, "Characters", "Sessions")


def test_rename_campaign_rewrites_only_links_that_spell_it(root, camp):
    write(camp / "Overview.md", "[[Curse of Strahd/NPCs/Ismark]] [[NPCs/Ismark]] [[Ismark]]")
    rewritten = vault.rename_campaign(root, "Curse of Strahd", "Barovia")
    assert rewritten == ["Overview.md"]
    assert (root / "Barovia" / "Overview.md").read_text() == "[[Barovia/NPCs/Ismark]] [[NPCs/Ismark]] [[Ismark]]"
    assert vault.list_campaigns(root) == ["Barovia"]
