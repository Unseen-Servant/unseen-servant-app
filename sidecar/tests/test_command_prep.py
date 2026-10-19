"""Beats, sessions and spent notes (command/prep.py, design §4–§5.1).

Membership and plans are frontmatter lists of links, spent is a date on
the note; these pin how each is read back and changed.
"""

from datetime import date

import pytest

from command import prep, vault
from command.vault import Conflict, Invalid


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(prep, "today", lambda: date(2026, 10, 18))


@pytest.fixture
def camp(tmp_path):
    c = tmp_path / "Strahd"
    write(c / "NPCs" / "Ismark.md", "---\nrole: ally\n---\nBrother.\n")
    write(c / "NPCs" / "Ireena.md", "")
    write(c / "Locations" / "Svalich Road.md", "")
    write(c / "Secrets" / "Ravens watch.md", "---\nspent: 2026-10-04\n---\n")
    write(c / "Beats" / "Ambush.md", '---\nnotes:\n  - "[[Ismark|the son]]"\n  - "[[NPCs/Ireena]]"\n  - "[[Wolves]]"\n---\nDusk.\n')
    write(c / "Beats" / "Tser Pool.md", "")
    write(c / "Beats" / "Played.md", "---\nspent: 2026-10-04\n---\n")
    return c


def session(c, name, day, beats):
    links = "".join(f'  - "[[{b}]]"\n' for b in beats)
    write(c / "Sessions" / f"{name}.md", f"---\ndate: {day}\nbeats:\n{links}---\n")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_index_reads_spent_marks(camp):
    notes = {n["path"]: n for n in prep.index(camp)["notes"]}
    assert notes["Secrets/Ravens watch.md"]["spent"] == "2026-10-04"
    assert notes["NPCs/Ismark.md"]["spent"] is None


def test_index_resolves_beat_members_however_they_are_spelled(camp):
    ambush = next(b for b in prep.index(camp)["beats"] if b["name"] == "Ambush")
    assert ambush["notes"] == [
        {"link": "Ismark", "path": "NPCs/Ismark.md"},
        {"link": "Ireena", "path": "NPCs/Ireena.md"},
        {"link": "Wolves", "path": None},
    ]


def test_index_lists_beats_in_the_saved_order_then_by_name(camp):
    vault.save_beat_order(camp, ["Tser Pool", "Gone"])
    assert [b["name"] for b in prep.index(camp)["beats"]] == ["Tser Pool", "Ambush", "Played"]


def test_index_orders_sessions_by_date_then_number(camp):
    session(camp, "Session 10", "2026-10-11", [])
    session(camp, "Session 9", "2026-10-04", [])
    session(camp, "Session 9b", "2026-10-11", [])
    assert [s["name"] for s in prep.index(camp)["sessions"]] == ["Session 9", "Session 9b", "Session 10"]


def test_index_survives_a_note_with_broken_frontmatter(camp):
    write(camp / "NPCs" / "Broken.md", "---\nnotes: [unclosed\n---\n")
    assert any(n["name"] == "Broken" for n in prep.index(camp)["notes"])


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def test_adding_a_member_appends_a_link_and_keeps_the_rest(camp):
    assert prep.set_member(camp, "Beats/Ambush.md", "Locations/Svalich Road.md", True) == [
        "Ismark", "Ireena", "Wolves", "Svalich Road",
    ]
    assert (camp / "Beats" / "Ambush.md").read_text().endswith('  - "[[Svalich Road]]"\n---\nDusk.\n')
    # Adding again changes nothing.
    before = (camp / "Beats" / "Ambush.md").read_text()
    prep.set_member(camp, "Beats/Ambush.md", "Locations/Svalich Road.md", True)
    assert (camp / "Beats" / "Ambush.md").read_text() == before


def test_removing_a_member_drops_every_spelling_of_it(camp):
    write(camp / "Beats" / "Twice.md", '---\nnotes: ["[[Ismark]]", "[[ismark|him]]", "[[Ireena]]"]\n---\n')
    assert prep.set_member(camp, "Beats/Twice.md", "NPCs/Ismark.md", False) == ["Ireena"]


def test_membership_starts_a_bare_beat_and_only_edits_beats(camp):
    assert prep.set_member(camp, "Beats/Tser Pool.md", "NPCs/Ireena.md", True) == ["Ireena"]
    assert (camp / "Beats" / "Tser Pool.md").read_text() == '---\nnotes:\n  - "[[Ireena]]"\n---\n'
    with pytest.raises(Invalid):
        prep.set_member(camp, "NPCs/Ismark.md", "NPCs/Ireena.md", True)


def test_create_beat_makes_beats_folder_holds_notes_and_joins_the_plan(tmp_path):
    c = tmp_path / "Misty Vale"  # started by hand: no Beats/ or Sessions/
    write(c / "NPCs" / "Innkeeper.md", "")
    started = prep.create_session(c)
    rel = prep.create_beat(c, "In town", ["NPCs/Innkeeper.md"], session=started["path"])
    assert rel == "Beats/In town.md"
    beats = prep.index(c)["sessions"][0]["beats"]
    assert beats == [{"link": "In town", "path": "Beats/In town.md"}]
    assert prep.index(c)["beats"][0]["notes"] == [{"link": "Innkeeper", "path": "NPCs/Innkeeper.md"}]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_first_session_starts_empty_and_dated_today(camp):
    made = prep.create_session(camp)
    assert made == {"path": "Sessions/Session 1.md", "name": "Session 1"}
    assert (camp / "Sessions" / "Session 1.md").read_text() == "---\ndate: 2026-10-18\nbeats: []\n---\n"


def test_next_session_plans_nothing(camp):
    # The last session's unplayed beats wait outside the plan, not in it.
    session(camp, "Session 11", "2026-10-04", ["Ambush"])
    session(camp, "Session 12", "2026-10-11", ["Played", "Tser Pool", "Not written yet", "Ambush"])
    made = prep.create_session(camp)
    assert made["name"] == "Session 13"
    assert prep.index(camp)["sessions"][-1]["beats"] == []


def test_session_numbers_skip_names_already_taken(camp):
    session(camp, "Session 2", "2026-10-04", [])
    write(camp / "NPCs" / "Session 3.md", "")
    assert prep.create_session(camp)["name"] == "Session 4"


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

def test_plan_add_move_remove(camp):
    session(camp, "Session 1", "2026-10-11", ["Ambush"])
    s = "Sessions/Session 1.md"
    assert prep.edit_plan(camp, s, "add", beat="Beats/Tser Pool.md") == ["Ambush", "Tser Pool"]
    assert prep.edit_plan(camp, s, "add", beat="Beats/Tser Pool.md") == ["Ambush", "Tser Pool"]
    assert prep.edit_plan(camp, s, "add", beat="Beats/Played.md", to=0) == ["Played", "Ambush", "Tser Pool"]
    assert prep.edit_plan(camp, s, "move", at=2, to=0, expect="Tser Pool") == ["Tser Pool", "Played", "Ambush"]
    assert prep.edit_plan(camp, s, "remove", at=1, expect="played") == ["Tser Pool", "Ambush"]


def test_plan_edit_refuses_when_the_plan_moved_underneath(camp):
    session(camp, "Session 1", "2026-10-11", ["Ambush", "Tser Pool"])
    with pytest.raises(Conflict):
        prep.edit_plan(camp, "Sessions/Session 1.md", "remove", at=0, expect="Tser Pool")
    with pytest.raises(Conflict):
        prep.edit_plan(camp, "Sessions/Session 1.md", "move", at=5, to=0, expect="Ambush")


def test_only_beats_go_in_a_plan(camp):
    session(camp, "Session 1", "2026-10-11", [])
    with pytest.raises(Invalid):
        prep.edit_plan(camp, "Sessions/Session 1.md", "add", beat="NPCs/Ismark.md")


# ---------------------------------------------------------------------------
# Spent
# ---------------------------------------------------------------------------

def test_spending_dates_the_note_and_keeps_its_text(camp):
    assert prep.set_spent(camp, "NPCs/Ismark.md", True) == "2026-10-18"
    assert (camp / "NPCs" / "Ismark.md").read_text() == "---\nrole: ally\nspent: 2026-10-18\n---\nBrother.\n"


def test_spending_twice_keeps_the_first_date_and_unspending_removes_it(camp):
    assert prep.set_spent(camp, "Secrets/Ravens watch.md", True) == "2026-10-04"
    assert prep.set_spent(camp, "Secrets/Ravens watch.md", False) is None
    assert (camp / "Secrets" / "Ravens watch.md").read_text() == ""


def test_any_note_can_be_spent_including_beats(camp):
    assert prep.set_spent(camp, "Beats/Ambush.md", True) == "2026-10-18"
    beat = next(b for b in prep.index(camp)["beats"] if b["name"] == "Ambush")
    assert beat["spent"] == "2026-10-18"
    assert len(beat["notes"]) == 3


def hash_of(c, rel):
    return vault.read_note(c, rel)["hash"]


def test_writing_text_keeps_the_frontmatter_byte_for_byte(camp):
    ismark = camp / "NPCs" / "Ismark.md"
    prep.write_text(camp, "NPCs/Ismark.md", "Elder brother.\n", hash_of(camp, "NPCs/Ismark.md"))
    assert ismark.read_text() == "---\nrole: ally\n---\nElder brother.\n"
    # The frontmatter sent back as read, even requoted, is dropped.
    prep.write_text(camp, "NPCs/Ismark.md", '---\nrole: "ally"\n---\nWary.\n', hash_of(camp, "NPCs/Ismark.md"))
    assert ismark.read_text() == "---\nrole: ally\n---\nWary.\n"
    prep.write_text(camp, "Beats/Ambush.md", "Night falls.\n", hash_of(camp, "Beats/Ambush.md"))
    beat = next(b for b in prep.index(camp)["beats"] if b["name"] == "Ambush")
    assert len(beat["notes"]) == 3
    unclosed = write(camp / "NPCs" / "Doru.md", "---\nrole: thrall\n---")
    prep.write_text(camp, "NPCs/Doru.md", "Hungry.", hash_of(camp, "NPCs/Doru.md"))
    assert unclosed.read_text() == "---\nrole: thrall\n---\nHungry."


def test_writing_text_refuses_a_changed_key_or_a_stale_hash(camp):
    with pytest.raises(Invalid, match="role would change"):
        prep.write_text(camp, "NPCs/Ismark.md", "---\nrole: foe\n---\nTraitor.\n", hash_of(camp, "NPCs/Ismark.md"))
    with pytest.raises(Invalid, match="spent would change"):
        prep.write_text(camp, "NPCs/Ireena.md", "---\nspent: 2026-10-18\n---\nGone.\n", hash_of(camp, "NPCs/Ireena.md"))
    stale = hash_of(camp, "NPCs/Ismark.md")
    prep.write_text(camp, "NPCs/Ismark.md", "Wary.\n", stale)
    with pytest.raises(Conflict) as refused:
        prep.write_text(camp, "NPCs/Ismark.md", "Clobber.\n", stale)
    assert refused.value.current_hash == hash_of(camp, "NPCs/Ismark.md")
    assert (camp / "NPCs" / "Ismark.md").read_text() == "---\nrole: ally\n---\nWary.\n"


def test_renaming_a_beat_rewrites_session_plans(camp):
    session(camp, "Session 1", "2026-10-11", ["Ambush"])
    vault.rename_note(camp, "Beats/Ambush.md", "Ambush on the road")
    assert prep.index(camp)["sessions"][0]["beats"] == [
        {"link": "Ambush on the road", "path": "Beats/Ambush on the road.md"},
    ]


# ---------------------------------------------------------------------------
# Material sent from Legend Lore (design §8)
# ---------------------------------------------------------------------------

SOURCE = "file:///Books/Curse%20of%20Strahd%20(5e).pdf#page=42"


def test_a_hit_arrives_as_a_note_with_its_source(camp):
    path = prep.receive(camp, "NPCs", "Ismark", "Tall and tired.\n", SOURCE, "Curse of Strahd (5e), p.40")
    assert path == "NPCs/Ismark 2.md"
    assert (camp / path).read_text() == (
        f'---\nsource: "{SOURCE}"\n---\n'
        "Tall and tired.\n\n"
        "[Curse of Strahd (5e), p.40](file:///Books/Curse%20of%20Strahd%20%285e%29.pdf#page=42)\n"
    )
    notes = {n["path"]: n for n in prep.index(camp)["notes"]}
    assert notes[path]["source"] == SOURCE
    assert notes["NPCs/Ismark.md"]["source"] is None


def test_a_hit_goes_only_to_a_track(camp):
    with pytest.raises(vault.NotFound):
        prep.receive(camp, "Beats", "X", "text", SOURCE, "")
    with pytest.raises(vault.NotFound):
        prep.receive(camp, "Nowhere", "X", "text", SOURCE, "")


# ---------------------------------------------------------------------------
# The shelf (design §3.6)
# ---------------------------------------------------------------------------

def test_a_hit_sent_without_a_track_lands_on_the_shelf(camp):
    path = prep.receive(camp, None, "Fire Drake", "Breathes fire.", SOURCE, "Monsters, p.3")
    assert path == "Shelf/Fire Drake.md"
    index = prep.index(camp)
    assert "Shelf" not in index["tracks"]
    assert next(n for n in index["notes"] if n["path"] == path)["track"] == "Shelf"


def test_copying_from_another_campaign_leaves_the_spent_mark_behind(camp, tmp_path):
    other = tmp_path / "Tomb"
    write(other / "NPCs" / "Merchant.md", "---\nrole: trader\nspent: 2026-09-01\n---\nSells [[Rope]].\n")
    write(other / "Beats" / "Market.md", "")
    path = prep.copy_in(camp, other, "NPCs/Merchant.md")
    assert path == "Shelf/Merchant.md"
    assert (camp / path).read_text() == "---\nrole: trader\n---\nSells [[Rope]].\n"
    assert (other / "NPCs" / "Merchant.md").read_text().count("spent") == 1
    with pytest.raises(Conflict):
        prep.copy_in(camp, other, "NPCs/Merchant.md")
    with pytest.raises(Invalid):
        prep.copy_in(camp, other, "Beats/Market.md")
    with pytest.raises(Invalid):
        prep.copy_in(camp, camp, "NPCs/Ismark.md")
