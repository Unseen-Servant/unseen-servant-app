"""The live set (command/live.py, design §6.2): sidecar state that survives
a restart and follows renames, never written to notes."""

from command.live import LIVE_FILENAME, LiveSets


def test_nothing_is_live_at_first():
    assert LiveSets(None).get("Strahd") == {"campaign": "Strahd", "seq": 0, "beat": None, "notes": []}


def test_each_change_takes_the_next_seq_and_survives_a_restart(tmp_path):
    sets = LiveSets(tmp_path)
    sets.set("Strahd", "Beats/Ambush.md", ["NPCs/Ismark.md", "NPCs/Ismark.md", "NPCs/Ireena.md"])
    snapshot = sets.set("Strahd", "Beats/Ambush.md", ["NPCs/Ismark.md", "NPCs/Ireena.md"])
    assert snapshot == {
        "campaign": "Strahd", "seq": 2, "beat": "Beats/Ambush.md", "notes": ["NPCs/Ismark.md", "NPCs/Ireena.md"],
    }
    assert LiveSets(tmp_path).get("Strahd") == snapshot
    assert LiveSets(tmp_path).set("Strahd", None, [])["seq"] == 3


def test_a_set_with_no_notes_has_no_beat():
    sets = LiveSets(None)
    assert sets.set("Strahd", "Beats/Empty.md", [])["beat"] is None
    sets.set("Strahd", "Beats/Ambush.md", ["NPCs/Ismark.md"])
    assert sets.prune("Strahd", lambda p: p != "NPCs/Ismark.md") == {
        "campaign": "Strahd", "seq": 3, "beat": None, "notes": [],
    }


def test_whatever_is_gone_leaves_the_live_set():
    sets = LiveSets(None)
    sets.set("Strahd", "Beats/Ambush.md", ["NPCs/Ismark.md", "NPCs/Ireena.md"])
    assert sets.prune("Strahd", lambda p: True) is None
    pruned = sets.prune("Strahd", lambda p: p not in ("Beats/Ambush.md", "NPCs/Ireena.md"))
    assert (pruned["beat"], pruned["notes"]) == (None, ["NPCs/Ismark.md"])


def test_a_corrupt_file_means_nothing_is_live(tmp_path):
    (tmp_path / LIVE_FILENAME).write_text("{ nope")
    assert LiveSets(tmp_path).get("Strahd")["notes"] == []
    (tmp_path / LIVE_FILENAME).write_text('{"campaigns": {"Strahd": {"seq": "x", "beat": 3, "notes": ["a.md", 4]}}}')
    assert LiveSets(tmp_path).get("Strahd") == {"campaign": "Strahd", "seq": 0, "beat": None, "notes": ["a.md"]}


def test_renames_and_moves_follow_into_the_live_set(tmp_path):
    sets = LiveSets(tmp_path)
    sets.set("Strahd", "Beats/Ambush.md", ["NPCs/Ismark.md", "Locations/Road.md"])
    assert sets.remap("Strahd", lambda p: p) is None
    moved = sets.remap("Strahd", lambda p: p.replace("NPCs/", "Folk/"))
    assert moved["notes"] == ["Folk/Ismark.md", "Locations/Road.md"]
    assert moved["seq"] == 2


def test_a_renamed_campaign_keeps_its_live_set(tmp_path):
    sets = LiveSets(tmp_path)
    sets.set("Strahd", None, ["NPCs/Ismark.md"])
    assert sets.rename_campaign("Nope", "Other") is None
    renamed = sets.rename_campaign("Strahd", "Barovia")
    assert renamed == {"campaign": "Barovia", "seq": 2, "beat": None, "notes": ["NPCs/Ismark.md"]}
    assert LiveSets(tmp_path).get("Strahd")["notes"] == []
