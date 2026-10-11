"""Command's HTTP surface: settings, campaigns, tracks and notes under
``/api/command``. The vault behaviour itself is pinned in
test_command_vault.py; these check the wiring and the status codes."""

import pytest
from fastapi.testclient import TestClient

from command.settings import load_settings
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
    assert bare_client.get("/api/command/settings").json() == {"root": None}
    assert bare_client.get("/api/command/campaigns").status_code == 409


def test_settings_refuse_a_missing_folder_and_persist(bare_client, campaign_root, tmp_path):
    assert bare_client.put("/api/command/settings", json={"root": str(tmp_path / "nope")}).status_code == 422
    assert bare_client.put("/api/command/settings", json={"root": str(campaign_root)}).json() == {"root": str(campaign_root)}
    assert load_settings(tmp_path).root == str(campaign_root)


def test_campaign_round_trip(cmd, campaign_root):
    assert cmd.get("/api/command/campaigns").json() == {"campaigns": ["Strahd"]}
    index = cmd.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert index["tracks"] == ["PCs", "NPCs", "Locations", "Secrets", "Monsters", "Treasures"]
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
    assert made == {"path": "Sessions/Session 1.md", "name": "Session 1", "carried": []}

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
        "beats": [{"link": "Ambush", "path": "Beats/Ambush.md"}],
    }]
    assert index["beats"] == [{"name": "Ambush", "path": "Beats/Ambush.md", "spent": "2026-10-18", "notes": []}]

    stale = cmd.post("/api/command/sessions/plan", json={
        "campaign": "Strahd", "session": made["path"], "op": "remove", "at": 0, "expect": "Nope",
    })
    assert stale.status_code == 409
