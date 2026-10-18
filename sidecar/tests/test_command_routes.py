"""Command's HTTP surface: settings, campaigns, tracks and notes under
``/api/command``. The vault behaviour itself is pinned in
test_command_vault.py; these check the wiring and the status codes."""

import pytest
from fastapi.testclient import TestClient

from command.settings import load_settings
from command.vault import DEFAULT_PIGMENTS
from server import create_app


@pytest.fixture
def bare_client(test_store, tmp_path):
    return TestClient(create_app(store=test_store, data_dir=tmp_path))


@pytest.fixture
def campaign_root(tmp_path):
    root = tmp_path / "campaigns"
    root.mkdir()
    return root


@pytest.fixture
def cmd(bare_client, campaign_root):
    assert bare_client.put("/api/command/settings", json={"root": str(campaign_root)}).status_code == 200
    assert bare_client.post("/api/command/campaigns", json={"name": "Strahd"}).status_code == 200
    return bare_client


def test_nothing_works_until_a_campaign_folder_is_set(bare_client):
    assert bare_client.get("/api/command/settings").json() == {
        "root": None, "spend_on_launch": False, "last_campaign": None, "places": [],
    }
    assert bare_client.get("/api/command/campaigns").status_code == 409


def test_settings_refuse_a_missing_folder_and_persist(bare_client, campaign_root, tmp_path):
    assert bare_client.put("/api/command/settings", json={"root": str(tmp_path / "nope")}).status_code == 422
    assert bare_client.put("/api/command/settings", json={"root": str(campaign_root)}).json() == {
        "root": str(campaign_root), "spend_on_launch": False, "last_campaign": None, "places": [],
    }
    assert load_settings(tmp_path).root == str(campaign_root)


def test_settings_change_only_the_fields_sent(bare_client, campaign_root, tmp_path):
    bare_client.put("/api/command/settings", json={"root": str(campaign_root)})
    assert bare_client.put("/api/command/settings", json={"spend_on_launch": True}).json() == {
        "root": str(campaign_root), "spend_on_launch": True, "last_campaign": None, "places": [],
    }
    assert bare_client.put("/api/command/settings", json={"root": None}).json() == {
        "root": None, "spend_on_launch": True, "last_campaign": None, "places": [],
    }
    assert load_settings(tmp_path).spend_on_launch is True


def test_campaign_round_trip(cmd, campaign_root):
    assert cmd.get("/api/command/campaigns").json() == {"campaigns": ["Strahd"]}
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["tracks"] == ["PCs", "Secrets", "Locations", "NPCs", "Monsters", "Traps", "Treasures"]
    assert index["notes"] == []
    assert cmd.post("/api/command/campaigns", json={"name": "strahd"}).status_code == 409
    assert cmd.get("/api/command/campaign", params={"name": "Nope"}).status_code == 404


def test_note_create_read_save_and_conflict(cmd, campaign_root):
    created = cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "Ismark"})
    assert created.json() == {"path": "NPCs/Ismark.md"}

    note = cmd.get("/api/command/note", params={"campaign": "Strahd", "path": "NPCs/Ismark.md"}).json()
    saved = cmd.put("/api/command/note", json={
        "campaign": "Strahd", "path": "NPCs/Ismark.md", "content": "Hello\n", "base_hash": note["hash"],
    })
    assert saved.status_code == 200

    # A save from the stale hash is refused, and says what's on disk now.
    stale = cmd.put("/api/command/note", json={
        "campaign": "Strahd", "path": "NPCs/Ismark.md", "content": "Clobber\n", "base_hash": note["hash"],
    })
    assert stale.status_code == 409
    assert stale.json()["hash"] == saved.json()["hash"]
    assert (campaign_root / "Strahd" / "NPCs" / "Ismark.md").read_text() == "Hello\n"


def test_rename_reports_the_notes_it_rewrote(cmd, campaign_root):
    cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "Ismark"})
    (campaign_root / "Strahd" / "NPCs" / "Ireena.md").write_text("[[Ismark]]")
    renamed = cmd.post("/api/command/notes/rename", json={
        "campaign": "Strahd", "path": "NPCs/Ismark.md", "new_name": "Ismark the Lesser",
    }).json()
    assert renamed == {"path": "NPCs/Ismark the Lesser.md", "rewritten": ["NPCs/Ireena.md"]}


def test_bad_names_are_422(cmd):
    assert cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "a/b"}).status_code == 422
    assert cmd.post("/api/command/tracks", json={"campaign": "Strahd", "name": "Sessions"}).status_code == 422


def test_locate_vouches_only_for_paths_inside_the_campaign(cmd, campaign_root):
    assert cmd.post("/api/command/locate", json={"campaign": "Strahd"}).json() == {"path": str(campaign_root / "Strahd")}
    assert cmd.post("/api/command/locate", json={"campaign": "Strahd", "path": "NPCs"}).json() == {
        "path": str(campaign_root / "Strahd" / "NPCs")
    }
    assert cmd.post("/api/command/locate", json={"campaign": "Strahd", "path": "../Other"}).status_code == 422
    assert cmd.post("/api/command/locate", json={"campaign": "..", "path": None}).status_code == 422


def test_prep_round_trip_over_http(cmd, campaign_root, monkeypatch):
    from datetime import date

    from command import prep

    monkeypatch.setattr(prep, "today", lambda: date(2026, 10, 18))
    cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "Ismark"})
    made = cmd.post("/api/command/sessions", json={"campaign": "Strahd"}).json()
    assert made == {"path": "Sessions/Session 1.md", "name": "Session 1"}

    beat = cmd.post("/api/command/beats", json={
        "campaign": "Strahd", "name": "Ambush", "notes": ["NPCs/Ismark.md"], "session": made["path"],
    }).json()["path"]
    assert cmd.post("/api/command/beats/members", json={
        "campaign": "Strahd", "beat": beat, "note": "NPCs/Ismark.md", "member": False,
    }).json() == {"notes": []}
    assert cmd.post("/api/command/spent", json={
        "campaign": "Strahd", "path": beat, "spent": True,
    }).json() == {"spent": "2026-10-18"}

    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["sessions"] == [{
        "name": "Session 1", "path": "Sessions/Session 1.md", "date": "2026-10-18",
        "beats": [{"link": "Ambush", "path": "Beats/Ambush.md"}], "log": [],
    }]
    assert index["beats"] == [{"name": "Ambush", "path": "Beats/Ambush.md", "spent": "2026-10-18", "notes": []}]

    stale = cmd.post("/api/command/sessions/plan", json={
        "campaign": "Strahd", "session": made["path"], "op": "remove", "at": 0, "expect": "Nope",
    })
    assert stale.status_code == 409


def test_note_order_over_http(cmd):
    for name in ("Ireena", "Ismark"):
        cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": name})
    assert cmd.put("/api/command/notes/order", json={
        "campaign": "Strahd", "folder": "NPCs", "order": ["Ismark", "Ireena"],
    }).json() == {"order": ["Ismark", "Ireena"]}
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["note_order"] == {"NPCs": ["Ismark", "Ireena"]}


def test_beat_order_over_http(cmd):
    for name in ("Ambush", "Tser Pool"):
        cmd.post("/api/command/beats", json={"campaign": "Strahd", "name": name})
    assert cmd.put("/api/command/beats/order", json={
        "campaign": "Strahd", "order": ["Tser Pool", "Ambush"],
    }).json() == {"order": ["Tser Pool", "Ambush"]}
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert [b["name"] for b in index["beats"]] == ["Tser Pool", "Ambush"]


def test_track_order_over_http(cmd):
    assert cmd.put("/api/command/tracks/order", json={
        "campaign": "Strahd", "order": ["Monsters", "PCs"],
    }).json()["tracks"] == ["Monsters", "PCs", "Locations", "NPCs", "Secrets", "Traps", "Treasures"]
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["tracks"][:2] == ["Monsters", "PCs"]


def test_track_pigment_over_http(cmd):
    assert cmd.put("/api/command/tracks/pigment", json={
        "campaign": "Strahd", "track": "NPCs", "pigment": "#4e9766",
    }).json() == {"pigments": {**DEFAULT_PIGMENTS, "NPCs": "#4e9766"}}
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["pigments"] == {**DEFAULT_PIGMENTS, "NPCs": "#4e9766"}
    others = {t: hex for t, hex in DEFAULT_PIGMENTS.items() if t != "NPCs"}
    assert cmd.put("/api/command/tracks/pigment", json={
        "campaign": "Strahd", "track": "NPCs", "pigment": None,
    }).json() == {"pigments": others}
    assert cmd.put("/api/command/tracks/pigment", json={
        "campaign": "Strahd", "track": "Gone", "pigment": "#4e9766",
    }).status_code == 404


# ---------------------------------------------------------------------------
# Play: the board, the live set, the log
# ---------------------------------------------------------------------------

@pytest.fixture
def table(cmd, campaign_root, monkeypatch):
    """Strahd with Ismark and Ireena, an Ambush beat holding Ismark, and
    Session 1 planning it. Every log line is stamped 19:42."""
    from datetime import date, datetime

    from command import log, prep

    monkeypatch.setattr(prep, "today", lambda: date(2026, 10, 18))
    monkeypatch.setattr(log, "now", lambda: datetime(2026, 10, 18, 19, 42))
    for name in ("Ismark", "Ireena"):
        cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": name})
    cmd.post("/api/command/sessions", json={"campaign": "Strahd"})
    cmd.post("/api/command/beats", json={
        "campaign": "Strahd", "name": "Ambush", "notes": ["NPCs/Ismark.md"], "session": "Sessions/Session 1.md",
    })
    return cmd


def session_log(client):
    index = client.get("/api/command/campaign", params={"name": "Strahd"}).json()
    return [(e["kind"], e["link"], e["path"]) for e in index["sessions"][0]["log"]]


def test_launching_a_beat_makes_its_notes_live_and_logs_it(table, campaign_root):
    launched = table.post("/api/command/live/launch", json={
        "campaign": "Strahd", "beat": "Beats/Ambush.md", "session": "Sessions/Session 1.md",
    }).json()
    assert launched == {"campaign": "Strahd", "seq": 1, "beat": "Beats/Ambush.md", "notes": ["NPCs/Ismark.md"]}
    assert table.get("/api/command/live", params={"campaign": "Strahd"}).json() == launched
    assert "## Log\n- 19:42 ▶ [[Ambush]]\n" in (campaign_root / "Strahd" / "Sessions" / "Session 1.md").read_text()
    assert session_log(table) == [("launch", "Ambush", "Beats/Ambush.md")]
    index = table.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["beats"][0]["spent"] is None

    missing = table.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Nope.md"})
    assert missing.status_code == 404


def test_spend_on_launch_spends_the_beat(table):
    table.put("/api/command/settings", json={"spend_on_launch": True})
    table.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Ambush.md"})
    index = table.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["beats"][0]["spent"] == "2026-10-18"
    assert session_log(table) == []


def test_improvising_changes_the_live_set_not_the_beat(table):
    table.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Ambush.md"})
    added = table.post("/api/command/live/note", json={"campaign": "Strahd", "note": "NPCs/Ireena.md", "live": True}).json()
    assert added["notes"] == ["NPCs/Ismark.md", "NPCs/Ireena.md"]
    taken = table.post("/api/command/live/note", json={"campaign": "Strahd", "note": "NPCs/Ismark.md", "live": False}).json()
    assert taken["notes"] == ["NPCs/Ireena.md"]
    assert taken["beat"] == "Beats/Ambush.md"
    index = table.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["beats"][0]["notes"] == [{"link": "Ismark", "path": "NPCs/Ismark.md"}]

    stopped = table.post("/api/command/live/stop", json={"campaign": "Strahd"}).json()
    assert (stopped["beat"], stopped["notes"]) == (None, [])


def test_a_jot_lands_in_the_session_note_not_its_log(table, campaign_root):
    assert table.post("/api/command/jot", json={
        "campaign": "Strahd", "session": "Sessions/Session 1.md", "text": "the party insulted the burgomaster",
    }).json() == {"line": "- the party insulted the burgomaster"}
    text = (campaign_root / "Strahd" / "Sessions" / "Session 1.md").read_text()
    assert text.endswith("\n- the party insulted the burgomaster\n")
    assert session_log(table) == []
    not_a_session = table.post("/api/command/jot", json={"campaign": "Strahd", "session": "NPCs/Ismark.md", "text": "x"})
    assert not_a_session.status_code == 422


def test_spends_from_play_are_logged(table):
    play = {"campaign": "Strahd", "path": "NPCs/Ismark.md", "session": "Sessions/Session 1.md"}
    table.post("/api/command/spent", json={**play, "spent": True})
    table.post("/api/command/spent", json={**play, "spent": True})  # already spent: no second line
    table.post("/api/command/spent", json={**play, "spent": False})
    table.post("/api/command/spent", json={"campaign": "Strahd", "path": "NPCs/Ireena.md", "spent": True})  # from Prep
    assert session_log(table) == [
        ("spent", "Ismark", "NPCs/Ismark.md"),
        ("unspent", "Ismark", "NPCs/Ismark.md"),
    ]


def test_the_board_over_http_follows_a_session_rename(table):
    session = "Sessions/Session 1.md"
    assert table.get("/api/command/board", params={"campaign": "Strahd", "session": session}).json() == {
        "nodes": [], "edges": [], "notes": {},
    }
    view = table.post("/api/command/board", json={"campaign": "Strahd", "session": session, "ops": [
        {"op": "place", "id": "a1", "path": "NPCs/Ismark.md", "x": 0, "y": 0, "width": 260, "height": 180},
    ]}).json()
    assert view["notes"] == {"a1": "NPCs/Ismark.md"}
    bad = table.post("/api/command/board", json={"campaign": "Strahd", "session": session, "ops": [{"op": "nope"}]})
    assert bad.status_code == 422

    table.post("/api/command/notes/rename", json={"campaign": "Strahd", "path": session, "new_name": "The mists"})
    renamed = table.get("/api/command/board", params={"campaign": "Strahd", "session": "Sessions/The mists.md"})
    assert renamed.json()["notes"] == {"a1": "NPCs/Ismark.md"}


def test_renaming_a_live_note_keeps_it_live(table):
    table.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Ambush.md"})
    table.post("/api/command/notes/rename", json={"campaign": "Strahd", "path": "NPCs/Ismark.md", "new_name": "Isaac"})
    table.post("/api/command/tracks/rename", json={"campaign": "Strahd", "name": "NPCs", "new_name": "Folk"})
    table.post("/api/command/notes/rename", json={"campaign": "Strahd", "path": "Beats/Ambush.md", "new_name": "Raid"})
    live = table.get("/api/command/live", params={"campaign": "Strahd"}).json()
    assert (live["beat"], live["notes"]) == ("Beats/Raid.md", ["Folk/Isaac.md"])
    table.post("/api/command/campaigns/rename", json={"name": "Strahd", "new_name": "Barovia"})
    assert table.get("/api/command/live", params={"campaign": "Barovia"}).json()["notes"] == ["Folk/Isaac.md"]


def test_a_trashed_beat_or_note_leaves_the_live_set(table, campaign_root):
    table.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Ambush.md"})
    table.post("/api/command/live/note", json={"campaign": "Strahd", "note": "NPCs/Ireena.md", "live": True})
    (campaign_root / "Strahd" / "Beats" / "Ambush.md").unlink()
    (campaign_root / "Strahd" / "NPCs" / "Ismark.md").unlink()
    live = table.get("/api/command/live", params={"campaign": "Strahd"}).json()
    assert (live["beat"], live["notes"]) == (None, ["NPCs/Ireena.md"])


# ---------------------------------------------------------------------------
# Cross-tool: the workstation's context, tracks, finding, sending (design §8)
# ---------------------------------------------------------------------------

def test_the_context_keeps_the_newest_push(cmd):
    assert cmd.get("/api/command/context").json() == {"campaign": None, "session": None}
    cmd.put("/api/command/context", json={"seq": 2, "campaign": "Strahd", "session": "Session 1"})
    cmd.put("/api/command/context", json={"seq": 1, "campaign": "Old", "session": None})
    assert cmd.get("/api/command/context").json() == {"campaign": "Strahd", "session": "Session 1"}
    assert cmd.put("/api/command/context", json={"seq": 2, "campaign": "Strahd", "session": None}).json() == {
        "campaign": "Strahd", "session": None,
    }


def test_tracks_find_and_send_over_http(cmd):
    assert cmd.get("/api/command/tracks", params={"campaign": "Strahd"}).json()["tracks"][:2] == ["PCs", "Secrets"]
    made = cmd.post("/api/command/notes", json={
        "campaign": "Strahd", "folder": "NPCs", "name": "Ismark", "content": "Brother of Ireena.\n",
    }).json()
    found = cmd.get("/api/command/find", params={"campaign": "Strahd", "query": "ireena"}).json()["notes"]
    assert [(n["path"], n["snippet"]) for n in found] == [(made["path"], "Brother of Ireena.")]

    sent = cmd.post("/api/command/send", json={
        "campaign": "Strahd", "track": "Monsters", "name": "Fire Drake: lair",
        "text": "Breathes fire.", "source": "file:///b.pdf#page=3", "cite": "Monsters, p.3",
    }).json()
    assert sent == {"path": "Monsters/Fire Drake lair.md"}
    bad = cmd.post("/api/command/send", json={
        "campaign": "Strahd", "track": "Beats", "name": "x", "text": "", "source": "file:///b.pdf",
    })
    assert bad.status_code == 404


def test_the_shelf_over_http(cmd, campaign_root):
    import shutil
    shutil.rmtree(campaign_root / "Strahd" / "Shelf")  # a campaign made by hand has none
    cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "Idea"})
    moved = cmd.post("/api/command/notes/move", json={"campaign": "Strahd", "path": "NPCs/Idea.md", "folder": "Shelf"})
    assert moved.json()["path"] == "Shelf/Idea.md"
    made = cmd.post("/api/command/notes", json={"campaign": "Strahd", "folder": "shelf", "name": "Hunch"}).json()
    assert made == {"path": "Shelf/Hunch.md"}
    sent = cmd.post("/api/command/send", json={
        "campaign": "Strahd", "name": "Fire Drake", "text": "Breathes fire.", "source": "file:///b.pdf#page=3",
    }).json()
    assert sent == {"path": "Shelf/Fire Drake.md"}
    cmd.post("/api/command/campaigns", json={"name": "Tomb"})
    copied = cmd.post("/api/command/notes/copy", json={"campaign": "Tomb", "from_campaign": "Strahd", "path": "Shelf/Idea.md"})
    assert copied.json() == {"path": "Shelf/Idea.md"}
    assert cmd.post("/api/command/notes/copy", json={
        "campaign": "Tomb", "from_campaign": "Strahd", "path": "Shelf/Idea.md",
    }).status_code == 409


def test_the_shelf_copies_from_a_folder_the_gm_added(cmd, campaign_root, tmp_path):
    vault = tmp_path / "Old vault"
    (vault / "NPCs" / "Vallaki").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "Sessions").mkdir()
    (vault / "Ideas.md").write_text("A hunch.\n")
    (vault / "NPCs" / "Vallaki" / "Lady Wachter.md").write_text("---\nspent: 2026-01-02\nmood: sly\n---\nSly.\n")
    (vault / "Sessions" / "Session 1.md").write_text("Notes from the first night.\n")
    (vault / ".obsidian" / "Hidden.md").write_text("")

    assert cmd.post("/api/command/places", json={"path": str(vault)}).json() == {"path": str(vault)}
    cmd.post("/api/command/places", json={"path": str(vault)})  # added once
    assert cmd.get("/api/command/settings").json()["places"] == [str(vault)]
    assert load_settings(tmp_path).places == [str(vault)]

    notes = cmd.get("/api/command/place", params={"path": str(vault)}).json()["notes"]
    assert [(n["path"], n["track"], n["group"]) for n in notes] == [
        ("Ideas.md", None, None),
        ("NPCs/Vallaki/Lady Wachter.md", "NPCs", "Vallaki"),
        ("Sessions/Session 1.md", "Sessions", None),
    ]

    # A folder's Sessions are its own notes, not a campaign's.
    for rel in ("NPCs/Vallaki/Lady Wachter.md", "Sessions/Session 1.md"):
        copied = cmd.post("/api/command/notes/copy", json={"campaign": "Strahd", "from_place": str(vault), "path": rel})
        assert copied.status_code == 200
    copy = (campaign_root / "Strahd" / "Shelf" / "Lady Wachter.md").read_text()
    assert copy == "---\nmood: sly\n---\nSly.\n"
    assert (campaign_root / "Strahd" / "Shelf" / "Session 1.md").exists()
    escape = cmd.post("/api/command/notes/copy", json={"campaign": "Strahd", "from_place": str(vault), "path": "../x.md"})
    assert escape.status_code == 422

    assert cmd.post("/api/command/places/remove", json={"path": str(vault)}).json()["places"] == []
    assert cmd.get("/api/command/place", params={"path": str(vault)}).status_code == 404
    gone = cmd.post("/api/command/notes/copy", json={"campaign": "Strahd", "from_place": str(vault), "path": "Ideas.md"})
    assert gone.status_code == 404


def test_a_place_must_be_a_folder_outside_the_campaigns(cmd, campaign_root, tmp_path):
    assert cmd.post("/api/command/places", json={"path": str(tmp_path / "nope")}).status_code == 422
    assert cmd.post("/api/command/places", json={"path": str(campaign_root)}).status_code == 422
    assert cmd.post("/api/command/places", json={"path": str(campaign_root / "Strahd")}).status_code == 422
    assert cmd.get("/api/command/settings").json()["places"] == []


def test_untitled_takes_the_default_folder_when_none_is_set(bare_client, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    assert bare_client.post("/api/command/untitled").json() == {"name": "Untitled"}
    root = home / "Unseen Servant"
    assert (root / "Untitled" / "NPCs").is_dir()
    assert bare_client.get("/api/command/settings").json()["root"] == str(root)
    assert load_settings(tmp_path).root == str(root)


def test_untitled_and_discard_over_http(cmd, campaign_root):
    assert cmd.post("/api/command/untitled").json() == {"name": "Untitled"}
    assert cmd.post("/api/command/untitled").json() == {"name": "Untitled"}
    assert cmd.post("/api/command/campaigns/discard", json={"name": "Strahd"}).json() == {"removed": False}
    assert cmd.post("/api/command/campaigns/discard", json={"name": "Untitled"}).json() == {"removed": True}
    assert cmd.get("/api/command/campaigns").json() == {"campaigns": ["Strahd"]}


def test_launch_reopens_the_last_campaign_open(cmd, campaign_root, tmp_path):
    assert cmd.post("/api/command/reopen").json() == {"name": "Untitled"}
    cmd.put("/api/command/context", json={"seq": 1, "campaign": "Strahd", "session": None})
    cmd.put("/api/command/context", json={"seq": 2, "campaign": None, "session": None})
    assert load_settings(tmp_path).last_campaign == "Strahd"
    assert cmd.post("/api/command/reopen").json() == {"name": "Strahd"}

    # Gone since (a blank Untitled goes with the app): a blank Untitled.
    (campaign_root / "Strahd").rename(campaign_root / "Barovia")
    assert cmd.post("/api/command/reopen").json() == {"name": "Untitled"}
