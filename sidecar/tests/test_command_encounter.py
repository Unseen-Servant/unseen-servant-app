"""Foresight's encounters (command/encounter.py, Foresight design §3).

An encounter is a note with `round`; its first table is the tracker. These
pin how the table, the struck-through names and the aliases read back, and
that a write changes the table and the two keys and nothing else.
"""

import pytest

from command import encounter, frontmatter as fm, vault
from command.encounter import Row
from command.vault import Conflict, Invalid

FOUGHT = """---
round: 3
turn: "Goblin 2"
tags: [ambush]
---
Goblins hide in the ditch; the boss stays on the ridge.

| Combatant                | HP    | Remarks    |
|--------------------------|-------|------------|
| [[Goblin boss]]          | 12/21 | frightened |
| [[Kira]]                 |       |            |
| [[Goblin\\|Goblin 2]]     | 7/7   |            |
| ~~[[Goblin\\|Goblin 1]]~~ | 0/7   |            |

## Tactics

| Not | The tracker |
|-----|-------------|
| a   | b           |
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def camp(tmp_path):
    c = tmp_path / "Strahd"
    write(c / "Encounters" / "Encounter 4.md", FOUGHT)
    write(c / "Monsters" / "Goblin.md", "Small and cruel.\n")
    return c


def rows_of(enc):
    return [(r["name"], r["link"], r["out"], r["cells"]) for r in enc["rows"]]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_the_first_table_is_the_tracker(camp):
    enc = encounter.read(camp, "Encounters/Encounter 4.md")
    assert enc["name"] == "Encounter 4"
    assert enc["round"] == 3
    assert enc["turn"] == "Goblin 2"
    assert enc["spent"] is None
    assert enc["columns"] == ["Combatant", "HP", "Remarks"]
    assert rows_of(enc) == [
        ("Goblin boss", "Goblin boss", False, ["12/21", "frightened"]),
        ("Kira", "Kira", False, ["", ""]),
        ("Goblin 2", "Goblin", False, ["7/7", ""]),
        ("Goblin 1", "Goblin", True, ["0/7", ""]),
    ]


def test_a_note_without_round_is_not_an_encounter(camp):
    with pytest.raises(Invalid):
        encounter.read(camp, "Monsters/Goblin.md")


def test_lenient_reading(camp):
    write(
        camp / "Encounters" / "Hand.md",
        "---\nround: two\nturn: nobody\n---\n"
        "```\n| not | a table |\n|---|---|\n```\n"
        "Name | Notes\n:--- | ---:\n"
        "Wolf | pack \\| tactics | an extra cell\n"
        "[[Monsters/Goblin|Sneak]]\n"
        "~~Bandit~~ | fled\n",
    )
    enc = encounter.read(camp, "Encounters/Hand.md")
    # A round that isn't a number is round 1; a turn naming no row falls to
    # the first row in the fight.
    assert enc["round"] == 1
    assert enc["turn"] == "Wolf"
    assert enc["columns"] == ["Name", "Notes"]
    assert rows_of(enc) == [
        ("Wolf", None, False, ["pack | tactics"]),
        # A bare pipe inside a link doesn't split the cell.
        ("Sneak", "Monsters/Goblin", False, [""]),
        ("Bandit", None, True, ["fled"]),
    ]


def test_an_encounter_with_no_table_has_no_rows(camp):
    write(camp / "Encounters" / "Empty.md", "---\nround: 1\n---\nJust words.\n")
    enc = encounter.read(camp, "Encounters/Empty.md")
    assert enc["columns"] == [] and enc["rows"] == [] and enc["turn"] is None


def test_the_turn_skips_rows_out_of_the_fight_when_unnamed(camp):
    write(camp / "Encounters" / "E.md", "---\nround: 1\n---\n| N |\n|---|\n| ~~A~~ |\n| B |\n")
    assert encounter.read(camp, "Encounters/E.md")["turn"] == "B"


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def save(camp, rel, **change):
    enc = encounter.read(camp, rel)
    rows = [Row(r["name"], r["link"], r["out"], r["cells"]) for r in enc["rows"]]
    args = {"round_": enc["round"], "turn": enc["turn"], "columns": enc["columns"], "rows": rows, **change}
    return encounter.save(camp, rel, enc["hash"], **args)


def test_an_unchanged_save_writes_nothing(camp):
    path = camp / "Encounters" / "Encounter 4.md"
    before = vault.content_hash(path.read_bytes())
    assert save(camp, "Encounters/Encounter 4.md") == before
    assert path.read_text() == FOUGHT


def test_a_save_rewrites_the_table_and_its_two_keys_only(camp):
    rel = "Encounters/Encounter 4.md"
    enc = encounter.read(camp, rel)
    rows = [Row(r["name"], r["link"], r["out"], r["cells"]) for r in enc["rows"]]
    rows[1].out = True
    rows.append(Row("Bandit | chief", None, False, ["9", "has the key"]))
    encounter.save(camp, rel, enc["hash"], 4, "Goblin boss", enc["columns"], rows)

    text = (camp / rel).read_text()
    meta = fm.load(text)
    assert meta == {"round": 4, "turn": "Goblin boss", "tags": ["ambush"]}
    assert "round: 4\n" in text
    assert "Goblins hide in the ditch; the boss stays on the ridge.\n\n| Combatant" in text
    # The second table, and the text between, stay as written.
    assert text.endswith("\n## Tactics\n\n| Not | The tracker |\n|-----|-------------|\n| a   | b           |\n")
    assert "| ~~[[Kira]]~~ " in text
    assert "| Bandit \\| chief " in text

    again = encounter.read(camp, rel)
    assert again["round"] == 4 and again["turn"] == "Goblin boss"
    assert rows_of(again)[1] == ("Kira", "Kira", True, ["", ""])
    assert rows_of(again)[4] == ("Bandit | chief", None, False, ["9", "has the key"])


def test_aliases_are_written_escaped_and_a_plain_link_stays_plain(camp):
    rel = "Encounters/Encounter 4.md"
    save(camp, rel, round_=5)
    text = (camp / rel).read_text()
    assert "| [[Goblin\\|Goblin 2]] " in text
    assert "| ~~[[Goblin\\|Goblin 1]]~~ " in text
    assert "| [[Goblin boss]] " in text


def test_the_table_is_padded_to_read_in_any_editor(camp):
    write(camp / "Encounters" / "E.md", "---\nround: 1\n---\nIntro.\n\n|N|HP|\n|:-|-:|\n|Wolf|11|\n\nOutro.")
    save(camp, "Encounters/E.md", round_=2)
    text = (camp / "Encounters" / "E.md").read_text()
    # Alignment colons stay; the text after the table is untouched, its
    # missing last newline too. The turn read as the first row is written.
    assert text == (
        '---\nround: 2\nturn: "Wolf"\n---\nIntro.\n\n| N    | HP  |\n|:-----|----:|\n| Wolf | 11  |\n\nOutro.'
    )


def test_cells_past_the_header_are_kept(camp):
    write(camp / "Encounters" / "E.md", "---\nround: 1\n---\n| N | HP |\n|---|---|\n| Wolf | 11 | spare |\n")
    save(camp, "Encounters/E.md", round_=2)
    assert "| Wolf | 11  | spare |" in (camp / "Encounters" / "E.md").read_text()


def test_a_table_is_added_to_an_encounter_without_one(camp):
    write(camp / "Encounters" / "E.md", "---\nround: 1\n---\nJust words.")
    save(camp, "Encounters/E.md", columns=["Combatant", "HP"], rows=[Row("Kira")], turn="Kira")
    text = (camp / "Encounters" / "E.md").read_text()
    assert text.endswith("Just words.\n\n| Combatant | HP  |\n|-----------|-----|\n| Kira      |     |\n")


def test_a_changed_note_is_refused_with_its_hash(camp):
    rel = "Encounters/Encounter 4.md"
    enc = encounter.read(camp, rel)
    write(camp / rel, FOUGHT.replace("ditch", "ford"))
    with pytest.raises(Conflict) as refused:
        encounter.save(camp, rel, enc["hash"], 4, None, enc["columns"], [])
    assert refused.value.current_hash == encounter.read(camp, rel)["hash"]


def test_names_are_unique_and_the_turn_names_a_row(camp):
    rel = "Encounters/Encounter 4.md"
    enc = encounter.read(camp, rel)
    cols = enc["columns"]
    with pytest.raises(Invalid):
        encounter.save(camp, rel, enc["hash"], 1, None, cols, [Row("Wolf"), Row("wolf")])
    with pytest.raises(Invalid):
        encounter.save(camp, rel, enc["hash"], 1, "Bear", cols, [Row("Wolf")])
    with pytest.raises(Invalid):
        encounter.save(camp, rel, enc["hash"], 1, None, cols, [Row("  ")])


def test_a_note_that_lost_its_round_is_not_written(camp):
    write(camp / "Monsters" / "Wolf.md", "Pack tactics.\n")
    with pytest.raises(Invalid):
        encounter.save(camp, "Monsters/Wolf.md", vault.content_hash(b"Pack tactics.\n"), 1, None, ["N"], [])


# ---------------------------------------------------------------------------
# A new encounter
# ---------------------------------------------------------------------------

def test_a_new_encounter_is_numbered_in_the_encounters_track(camp):
    enc = encounter.create(camp, ["Combatant", "HP", "Remarks"], [Row("Kira")])
    assert enc["path"] == "Encounters/Encounter 5.md"
    assert enc["round"] == 1 and enc["turn"] == "Kira"
    assert rows_of(enc) == [("Kira", None, False, ["", ""])]
    assert (camp / enc["path"]).read_text() == (
        "---\nround: 1\nturn: \"Kira\"\n---\n"
        "| Combatant | HP  | Remarks |\n"
        "|-----------|-----|---------|\n"
        "| Kira      |     |         |\n"
    )


def test_the_encounters_track_is_made_a_note_track_on_first_use(tmp_path):
    c = tmp_path / "Fresh"
    c.mkdir()
    enc = encounter.create(c, ["Combatant"], [Row("Kira")])
    assert enc["path"] == "Encounters/Encounter 1.md"
    assert vault.track_order(c) == ["Encounters"]
    assert vault.track_kinds(c) == {"Encounters": "note"}


def test_an_encounters_folder_is_used_as_it_is_spelled(tmp_path):
    c = tmp_path / "Fresh"
    (c / "encounters").mkdir(parents=True)
    assert encounter.create(c, ["Combatant"], [Row("Kira")])["path"] == "encounters/Encounter 1.md"


def test_a_name_taken_elsewhere_is_passed_over(camp):
    write(camp / "NPCs" / "Encounter 5.md", "")
    write(camp / "Secrets" / "encounter 6.md", "")
    assert encounter.next_name(camp) == "Encounter 7"
