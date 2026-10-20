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
    assert by_path["NPCs/Ireena.md"] == {"name": "Ireena", "path": "NPCs/Ireena.md", "track": "NPCs", "group": None, "type": "note"}
    assert by_path["NPCs/Vallaki/Lady Wachter.md"]["group"] == "Vallaki"
    assert by_path["Overview.md"]["track"] is None
    assert by_path["Beats/Ambush.md"]["track"] == "Beats"
    # Hidden files and folders are not notes.
    assert not any(".obsidian" in p or ".draft" in p for p in by_path)


def test_scan_lists_a_tracks_images_as_clips_named_with_their_extension(camp):
    # Images design §3.1: a track's or the shelf's image is a clip, a loose
    # one too; one among the sessions is an attachment, and no list's.
    write(camp / "Shelf" / "Crest.webp", "", raw=b"")
    write(camp / "Sessions" / "handout.png", "", raw=b"")
    write(camp / "Locations" / "notes.txt", "")
    clips = {n["path"]: n for n in vault.scan(camp)["notes"] if n["type"] == "image"}
    assert clips == {
        "Locations/map.png": {"name": "map.png", "path": "Locations/map.png", "track": "Locations", "group": None, "type": "image"},
        "Shelf/Crest.webp": {"name": "Crest.webp", "path": "Shelf/Crest.webp", "track": "Shelf", "group": None, "type": "image"},
    }
    assert vault.find_notes(camp, "crest")[0]["path"] == "Shelf/Crest.webp"
    vault.clip_path(camp, "Locations/map.png")
    with pytest.raises(Invalid):
        vault.clip_path(camp, "Sessions/handout.png")
    with pytest.raises(Invalid):
        vault.clip_path(camp, "Locations/notes.txt")


def test_scan_lists_the_images_wherever_they_sit(camp):
    # For the app to resolve a note's embeds against (#407): a track's, an
    # attachment folder's, a session's; never a hidden one.
    write(camp / "attachments" / "Crest.JPG", "", raw=b"")
    write(camp / "Sessions" / "handout.webp", "", raw=b"")
    write(camp / ".obsidian" / "icon.png", "", raw=b"")
    assert vault.scan(camp)["images"] == ["Locations/map.png", "Sessions/handout.webp", "attachments/Crest.JPG"]


def test_scan_flags_names_shared_within_a_kind(camp):
    # Two notes named Ismark make a link to it ambiguous; a beat named after
    # a note doesn't, since a beat's links and a note's are read apart.
    write(camp / "Locations" / "ismark.md", "")
    write(camp / "Beats" / "Ireena.md", "")
    assert vault.scan(camp)["ambiguous"] == ["Locations/ismark.md", "NPCs/Ismark.md"]


def test_track_order_keeps_saved_order_then_alphabetical(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"tracks": ["NPCs", "Gone"]}))
    write(camp / "Monsters" / "Wolves.md", "")
    assert vault.track_order(camp) == ["NPCs", "Locations", "Monsters"]


def test_track_order_survives_a_corrupt_presentation_file(camp):
    write(camp / ".unseen" / "command.json", "{not json")
    assert vault.track_order(camp) == ["Locations", "NPCs"]


def test_saving_the_track_order_answers_with_the_tracks_on_disk(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"version": 1, "beats": ["Ambush"]}))
    assert vault.save_track_order(camp, ["Locations", "Gone"]) == ["Locations", "NPCs"]
    assert vault.beat_order(camp) == ["Ambush"]


def test_saving_the_beat_order_keeps_the_track_order(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"version": 1, "tracks": ["NPCs", "Locations"]}))
    vault.save_beat_order(camp, ["Ambush"])
    assert vault.track_order(camp) == ["NPCs", "Locations"]
    assert vault.beat_order(camp) == ["Ambush"]
    assert json.loads((camp / ".unseen" / "command.json").read_text()) == {
        "version": 1, "tracks": ["NPCs", "Locations"], "beats": ["Ambush"],
    }


def test_saving_a_folders_note_order_keeps_the_rest(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"version": 1, "tracks": ["NPCs"], "notes": {"Locations": ["Church"]}}))
    assert vault.save_note_order(camp, "NPCs", ["Ismark", "Ireena"]) == ["Ismark", "Ireena"]
    assert vault.note_order(camp) == {"Locations": ["Church"], "NPCs": ["Ismark", "Ireena"]}
    assert vault.track_order(camp)[0] == "NPCs"
    assert vault.scan(camp)["note_order"] == {"Locations": ["Church"], "NPCs": ["Ismark", "Ireena"]}


def test_note_order_ignores_what_it_cant_read(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"notes": {"NPCs": ["Ismark", 3], "Locations": "Church"}}))
    assert vault.note_order(camp) == {"NPCs": ["Ismark"]}
    write(camp / ".unseen" / "command.json", json.dumps({"notes": ["Ismark"]}))
    assert vault.note_order(camp) == {}


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
    assert vault.track_pigments(camp) == vault.DEFAULT_PIGMENTS
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


def test_create_note_refuses_a_name_another_note_has(camp):
    assert vault.create_note(camp, "Locations", "Tser Pool") == "Locations/Tser Pool.md"
    assert (camp / "Locations" / "Tser Pool.md").read_bytes() == b""
    with pytest.raises(Conflict):
        vault.create_note(camp, "Locations", "ireena")
    with pytest.raises(NotFound):
        vault.create_note(camp, "Nowhere", "X")


def test_a_name_is_unique_among_its_kind_only(camp):
    # A beat may be named after its place, never after another beat: in
    # Beats/, in a rename, or for a note moved in among the beats.
    assert vault.create_note(camp, "Beats", "Ismark") == "Beats/Ismark.md"
    assert vault.create_note(camp, "Locations", "Ambush") == "Locations/Ambush.md"
    with pytest.raises(Conflict, match="A beat named 'ambush' already exists"):
        vault.create_note(camp, "Beats", "ambush")
    assert vault.rename_note(camp, "Beats/Ambush.md", "Ireena")[0] == "Beats/Ireena.md"
    with pytest.raises(Conflict, match="A beat named 'Ismark' already exists"):
        vault.rename_note(camp, "Beats/Ireena.md", "Ismark")
    write(camp / "Beats" / "Act 1" / "Overview.md", "")
    with pytest.raises(Conflict, match="A beat named 'Overview' already exists"):
        vault.move_note(camp, "Overview.md", "Beats")


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


def test_rename_note_leaves_links_another_note_also_answers_to(camp):
    # Two Ismarks, the second made outside Command: a bare [[Ismark]] is
    # ambiguous (scan flags it), so it may be meant for either, and renaming
    # one must not claim it. A link only the renamed note answers to follows.
    write(camp / "Locations" / "Ismark.md", "An inn.\n")
    write(camp / "Overview.md", "[[Ismark]] [[NPCs/Ismark]] [[Locations/Ismark]]")
    _, rewritten = vault.rename_note(camp, "NPCs/Ismark.md", "Ismark Kolyanovich")

    assert rewritten == ["Overview.md"]
    assert (camp / "Overview.md").read_text() == "[[Ismark]] [[NPCs/Ismark Kolyanovich]] [[Locations/Ismark]]"
    assert "[[Ismark]]" in (camp / "NPCs" / "Ireena.md").read_text()
    assert (camp / "Beats" / "Ambush.md").read_text() == '---\nnotes: ["[[Ismark]]", "[[Wolves]]"]\n---\n'


# A beat named after its note: a beat's notes name notes, a session's
# beats name beats, and a link anywhere else a note first (design §3.3).
NAMED_ALIKE = {
    "Beats/Ismark.md": '---\nnotes: ["[[Ismark]]"]\n---\nIsmark pleads.\n',
    "Sessions/Session 1.md": '---\nbeats:\n- "[[Ismark]]"\n---\nAsk [[Ismark]].\n',
}


def test_renaming_a_beat_named_after_its_note_rewrites_what_names_the_beat(camp):
    for rel, text in NAMED_ALIKE.items():
        write(camp / rel, text)
    _, rewritten = vault.rename_note(camp, "Beats/Ismark.md", "Plea")
    assert rewritten == ["Sessions/Session 1.md"]
    assert (camp / "Sessions" / "Session 1.md").read_text() == '---\nbeats:\n- "[[Plea]]"\n---\nAsk [[Ismark]].\n'


def test_renaming_the_note_a_beat_is_named_after_rewrites_what_names_the_note(camp):
    for rel, text in NAMED_ALIKE.items():
        write(camp / rel, text)
    vault.save_beat_order(camp, ["Ismark", "Ambush"])
    vault.rename_note(camp, "NPCs/Ismark.md", "Ismark Kolyanovich")
    assert (camp / "Beats" / "Ismark.md").read_text() == '---\nnotes: ["[[Ismark Kolyanovich]]"]\n---\nIsmark pleads.\n'
    assert (camp / "Sessions" / "Session 1.md").read_text() == (
        '---\nbeats:\n- "[[Ismark]]"\n---\nAsk [[Ismark Kolyanovich]].\n'
    )
    assert vault.beat_order(camp) == ["Ismark", "Ambush"]  # the beat's name, not the note's


def test_move_note_leaves_a_path_link_another_note_also_answers_to(camp):
    write(camp / "Locations" / "Vallaki" / "Lady Wachter.md", "")
    write(camp / "Overview.md", "[[Vallaki/Lady Wachter]] [[NPCs/Vallaki/Lady Wachter]]")
    _, rewritten = vault.move_note(camp, "NPCs/Vallaki/Lady Wachter.md", "NPCs")

    assert rewritten == ["Overview.md"]
    # The path link keeps its three parts, so it now spells the campaign.
    assert (camp / "Overview.md").read_text() == "[[Vallaki/Lady Wachter]] [[Curse of Strahd/NPCs/Lady Wachter]]"


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


def test_move_note_into_and_out_of_a_tracks_subfolder(camp):
    assert vault.move_note(camp, "NPCs/Ismark.md", "NPCs/Vallaki")[0] == "NPCs/Vallaki/Ismark.md"
    assert vault.move_note(camp, "NPCs/Vallaki/Lady Wachter.md", "NPCs")[0] == "NPCs/Lady Wachter.md"


def test_a_moved_note_heads_its_new_folder(camp):
    write(camp / "Locations" / "Church.md", "")
    write(camp / "Locations" / "Tser Pool.md", "")
    vault.save_note_order(camp, "Locations", ["Tser Pool", "Village of Barovia"])
    vault.move_note(camp, "NPCs/Ismark.md", "Locations")
    assert vault.note_order(camp)["Locations"] == ["Ismark", "Tser Pool", "Village of Barovia"]
    # Whatever its name, and whatever spot an earlier stay left it.
    vault.move_note(camp, "NPCs/Ireena.md", "Locations")
    vault.move_note(camp, "Locations/Ismark.md", "NPCs")
    vault.move_note(camp, "NPCs/Ismark.md", "Locations")
    assert vault.note_order(camp)["Locations"] == ["Ismark", "Ireena", "Tser Pool", "Village of Barovia"]
    assert vault.note_order(camp)["NPCs"] == []


def test_a_note_dropped_between_rows_lands_in_its_place(camp):
    vault.save_note_order(camp, "Locations", ["Village of Barovia"])
    vault.move_note(camp, "NPCs/Ismark.md", "Locations", ["Village of Barovia", "Ismark"])
    assert vault.note_order(camp)["Locations"] == ["Village of Barovia", "Ismark"]


def test_rename_note_keeps_a_beat_in_its_place(camp):
    write(camp / "Beats" / "Tser Pool.md", "")
    vault.save_beat_order(camp, ["Tser Pool", "Ambush"])
    vault.rename_note(camp, "Beats/Ambush.md", "Road ambush")
    assert vault.beat_order(camp) == ["Tser Pool", "Road ambush"]


def test_rename_note_keeps_its_place_among_its_folders_notes(camp):
    vault.save_note_order(camp, "NPCs", ["Ismark", "Ireena"])
    vault.rename_note(camp, "NPCs/Ismark.md", "Ismark the Lesser")
    assert vault.note_order(camp) == {"NPCs": ["Ismark the Lesser", "Ireena"]}


def test_rename_track_keeps_the_order_of_its_notes(camp):
    vault.save_note_order(camp, "NPCs", ["Ismark", "Ireena"])
    vault.save_note_order(camp, "NPCs/Vallaki", ["Lady Wachter"])
    vault.save_note_order(camp, "NPCs Extra", ["Doru"])
    vault.rename_track(camp, "NPCs", "Characters")
    assert vault.note_order(camp) == {
        "Characters": ["Ismark", "Ireena"],
        "Characters/Vallaki": ["Lady Wachter"],
        "NPCs Extra": ["Doru"],
    }


def test_a_track_takes_a_pigment_and_gives_it_back(camp):
    vault.save_track_order(camp, ["NPCs", "Locations"])
    assert vault.save_track_pigment(camp, "NPCs", "#d07c87") == {"NPCs": "#d07c87"}
    assert vault.save_track_pigment(camp, "Locations", "#6b9ad0") == {"NPCs": "#d07c87", "Locations": "#6b9ad0"}
    assert vault.save_track_pigment(camp, "NPCs", None) == {"Locations": "#6b9ad0"}
    assert vault.scan(camp)["pigments"] == {"Locations": "#6b9ad0"}
    assert vault.track_order(camp) == ["NPCs", "Locations"]
    with pytest.raises(NotFound):
        vault.save_track_pigment(camp, "Gone", "#d07c87")
    with pytest.raises(Invalid):
        vault.save_track_pigment(camp, "NPCs", "red")


def test_track_pigments_ignore_what_isnt_one(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"pigments": {"NPCs": "#d07c87", "Locations": "red", "Monsters": 3}}))
    assert vault.track_pigments(camp) == {"NPCs": "#d07c87"}
    write(camp / ".unseen" / "command.json", json.dumps({"pigments": ["NPCs"]}))
    assert vault.track_pigments(camp) == {}


def test_rename_track_keeps_its_pigment(camp):
    vault.save_track_pigment(camp, "NPCs", "#d07c87")
    vault.save_track_pigment(camp, "Locations", "#6b9ad0")
    vault.rename_track(camp, "NPCs", "Characters")
    assert vault.track_pigments(camp) == {"Characters": "#d07c87", "Locations": "#6b9ad0"}


def test_rename_track_keeps_its_place_and_rewrites_path_links(camp):
    write(camp / ".unseen" / "command.json", json.dumps({"tracks": ["NPCs", "Locations"]}))
    write(camp / "Overview.md", "[[NPCs/Vallaki/Lady Wachter]] [[Ireena]]")
    rewritten = vault.rename_track(camp, "NPCs", "Characters")
    assert vault.track_order(camp) == ["Characters", "Locations"]
    assert rewritten == ["Overview.md"]
    assert (camp / "Overview.md").read_text() == "[[Characters/Vallaki/Lady Wachter]] [[Ireena]]"
    with pytest.raises(Invalid):
        vault.rename_track(camp, "Characters", "Sessions")


def test_a_track_rename_carries_the_links_that_spell_an_image(camp):
    # An image moves with its track, so an embed spelling its path follows,
    # its width kept; one naming it alone needs nothing (#407).
    write(camp / "Overview.md", "![[Locations/map.png|300]] ![[map.png]] [[Locations/Village of Barovia]]")
    vault.rename_track(camp, "Locations", "Places")
    assert (camp / "Overview.md").read_text() == "![[Places/map.png|300]] ![[map.png]] [[Places/Village of Barovia]]"


def test_an_image_renames_and_moves_as_a_note_does_keeping_its_extension(camp):
    write(camp / "Overview.md", "![[map.png|300]] and [[Locations/map.png]]")
    # The field edits the stem; the whole name with its extension works too.
    path, rewritten = vault.rename_note(camp, "Locations/map.png", "Village map")
    assert path == "Locations/Village map.png"
    assert (camp / "Overview.md").read_text() == "![[Village map.png|300]] and [[Locations/Village map.png]]"
    assert rewritten == ["Overview.md"]
    assert vault.rename_note(camp, path, "Old map.png")[0] == "Locations/Old map.png"
    # Two images can't share a name, wherever they are; an image named
    # after a note (Ismark.png beside Ismark) can.
    write(camp / "NPCs" / "Ireena.png", "", raw=b"")
    write(camp / "Shelf" / "Ismark.png", "", raw=b"")
    with pytest.raises(Conflict):
        vault.rename_note(camp, "NPCs/Ireena.png", "ismark")
    assert vault.rename_note(camp, "Shelf/Ismark.png", "Ismark portrait")[0] == "Shelf/Ismark portrait.png"
    moved, _ = vault.move_note(camp, "Locations/Old map.png", "NPCs")
    assert moved == "NPCs/Old map.png"
    # An image goes in a track or on the shelf.
    with pytest.raises(Invalid):
        vault.move_note(camp, moved, "Beats")


def test_add_image_names_it_after_the_file_and_numbers_a_clash(camp):
    assert vault.add_image(camp, "Locations", "Map.PNG", b"\x89PNG") == "Locations/Map 2.PNG"
    assert vault.add_image(camp, "NPCs", "Ismark: portrait?.webp", b"x") == "NPCs/Ismark portrait.webp"
    assert (camp / "Locations" / "Map 2.PNG").read_bytes() == b"\x89PNG"
    # A name can't reach out of the folder, nor hide the file.
    assert vault.add_image(camp, "NPCs", "../../.evil.png", b"x") == "NPCs/evil.png"
    with pytest.raises(Invalid):
        vault.add_image(camp, "NPCs", "notes.md", b"x")


def test_rename_campaign_rewrites_only_links_that_spell_it(root, camp):
    write(camp / "Overview.md", "[[Curse of Strahd/NPCs/Ismark]] [[NPCs/Ismark]] [[Ismark]]")
    rewritten = vault.rename_campaign(root, "Curse of Strahd", "Barovia")
    assert rewritten == ["Overview.md"]
    assert (root / "Barovia" / "Overview.md").read_text() == "[[Barovia/NPCs/Ismark]] [[NPCs/Ismark]] [[Ismark]]"
    assert vault.list_campaigns(root) == ["Barovia"]


# ---------------------------------------------------------------------------
# Notes made with content, free names, finding notes (design §8)
# ---------------------------------------------------------------------------

def test_a_note_can_start_with_content(camp):
    path = vault.create_note(camp, "NPCs", "Doru", "Ismark's friend.\n")
    assert (camp / path).read_text() == "Ismark's friend.\n"


def test_free_name_cleans_a_heading_and_steps_past_a_clash(camp):
    assert vault.free_name(camp, "  **Fire / Drake**: notes ") == "Fire Drake notes"
    assert vault.free_name(camp, "Ismark") == "Ismark 2"
    vault.create_note(camp, "NPCs", "Ismark 2")
    assert vault.free_name(camp, "ismark") == "ismark 3"
    assert vault.free_name(camp, "#[]") == "Untitled"


def test_find_notes_puts_names_before_text_and_quotes_the_text(camp):
    found = vault.find_notes(camp, "ismark")
    assert [n["name"] for n in found] == ["Ismark", "Ambush", "Village of Barovia", "Ireena"]
    assert found[3]["snippet"] == "Sister of [[Ismark]]."
    # The line comes from the text, though the frontmatter is searched.
    assert [n["snippet"] for n in vault.find_notes(camp, "ally")] == ["Brother of [[Ireena]]."]
    assert vault.find_notes(camp, "wachter")[0]["snippet"] == ""
    assert vault.find_notes(camp, "wolves")[0]["snippet"] == ""
    assert [n["name"] for n in vault.find_notes(camp, "ISMARK", track="Locations")] == ["Village of Barovia"]
    assert vault.find_notes(camp, "  ") == []


def test_the_shelf_is_reserved(root, camp):
    with pytest.raises(Invalid):
        vault.create_track(camp, "shelf")
    vault.create_campaign(root, "Tomb")
    assert (root / "Tomb" / "Shelf").is_dir()
    assert "Shelf" not in vault.track_order(root / "Tomb")


# ---------------------------------------------------------------------------
# The untitled campaign
# ---------------------------------------------------------------------------

def test_untitled_names_are_the_ones_command_gives():
    assert vault.is_untitled("Untitled") and vault.is_untitled("Untitled 12")
    for name in ("untitled", "Untitled 0", "Untitled 2a", "Untitled Tomb", "My Untitled"):
        assert not vault.is_untitled(name)


def test_open_untitled_makes_one_then_reuses_it_while_blank(root):
    assert vault.open_untitled(root) == "Untitled"
    assert vault.track_order(root / "Untitled") == list(vault.DEFAULT_TRACKS)
    (root / "Untitled" / "NPCs" / ".DS_Store").write_bytes(b"")
    assert vault.open_untitled(root) == "Untitled"


def test_open_untitled_passes_over_one_in_use_and_a_file_in_the_way(root):
    vault.open_untitled(root)
    write(root / "Untitled" / "NPCs" / "Ismark.md", "")
    (root / "Untitled 2").write_text("a file, not a campaign")
    assert vault.open_untitled(root) == "Untitled 3"


def test_open_untitled_reuses_the_lowest_blank_one(root):
    for name in ("Untitled", "Untitled 2", "Untitled 10"):
        vault.create_campaign(root, name)
    write(root / "Untitled" / "Beats" / "Ambush.md", "")
    assert vault.open_untitled(root) == "Untitled 2"


def test_blank_means_nothing_the_gm_made(root):
    vault.open_untitled(root)
    camp = root / "Untitled"
    assert vault.is_blank(camp)
    vault.create_track(camp, "Factions")  # a folder, and the order file
    assert vault.is_blank(camp)
    write(camp / ".obsidian" / "app.json", "{}")
    assert not vault.is_blank(camp)


def test_a_symlink_is_not_blank(root, tmp_path):
    vault.open_untitled(root)
    (tmp_path / "elsewhere").mkdir()
    (root / "Untitled" / "Linked").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert not vault.is_blank(root / "Untitled")


def test_discard_removes_a_blank_untitled_and_nothing_else(root):
    vault.open_untitled(root)
    (root / "Untitled" / "PCs" / ".DS_Store").write_bytes(b"")
    assert vault.discard_if_blank(root, "Untitled")
    assert not (root / "Untitled").exists()
    assert not vault.discard_if_blank(root, "Untitled")  # already gone

    vault.create_campaign(root, "Tomb")  # named, and just as empty
    assert not vault.discard_if_blank(root, "Tomb")
    vault.open_untitled(root)
    write(root / "Untitled" / "Shelf" / "Hunch.md", "")
    assert not vault.discard_if_blank(root, "Untitled")
    assert (root / "Untitled" / "Shelf" / "Hunch.md").exists()
    assert sorted(vault.list_campaigns(root)) == ["Tomb", "Untitled"]
