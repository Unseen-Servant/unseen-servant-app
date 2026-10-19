"""Command's MCP tools (mcp_server.py, design §8), run against the real
sidecar app in-process: the MCP server is an HTTP adapter over the
sidecar's routes (architecture D5), so these exercise both halves."""

import argparse
import asyncio
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

import mcp_server
from command import prep
from server import create_app

LEGEND_LORE = {"list_collections", "search_library", "get_section", "get_pages", "list_sources", "list_game_systems"}
COMMAND = {"list_campaigns", "current_session", "live_set", "read_note", "find_notes", "create_note", "add_to_live_set", "spend"}


@pytest.fixture
def app(test_store, tmp_path, monkeypatch):
    """The sidecar app, reached by the MCP server's own client."""
    application = create_app(store=test_store, data_dir=tmp_path)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.ASGITransport(app=application), **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client_factory)
    args = argparse.Namespace(sidecar_url="http://sidecar.test", data_dir=None)
    monkeypatch.setattr(mcp_server, "sidecar", mcp_server.SidecarClient(args))
    monkeypatch.setattr(prep, "today", lambda: date(2026, 10, 18))
    return TestClient(application)


@pytest.fixture
def strahd(app, tmp_path):
    """Strahd open in the app at Session 1, which plans Ambush (Ismark and
    the Village of Barovia). Two notes answer to "Ireena": the second was
    made outside Command, which refuses a clash."""
    root = tmp_path / "campaigns"
    root.mkdir()
    app.put("/api/command/settings", json={"root": str(root)})
    app.post("/api/command/campaigns", json={"name": "Strahd"})
    for folder, name, text in [
        ("NPCs", "Ismark", "Son of the burgomaster. Protects [[Ireena]].\n"),
        ("NPCs", "Ireena", "Bitten twice.\n"),
        ("Locations", "Village of Barovia", "Where Ismark waits.\n"),
    ]:
        app.post("/api/command/notes", json={"campaign": "Strahd", "folder": folder, "name": name, "content": text})
    app.post("/api/command/sessions", json={"campaign": "Strahd"})
    beat = app.post("/api/command/beats", json={
        "campaign": "Strahd", "name": "Ambush", "notes": ["NPCs/Ismark.md"], "session": "Sessions/Session 1.md",
    }).json()["path"]
    app.post("/api/command/beats/members", json={
        "campaign": "Strahd", "beat": beat, "note": "Locations/Village of Barovia.md", "member": True,
    })
    (root / "Strahd" / "Locations" / "Ireena.md").write_text("A shrine named for her.\n")
    app.put("/api/command/context", json={"seq": 1, "campaign": "Strahd", "session": "Session 1"})
    return root


def run(coro):
    return asyncio.run(coro)


def test_an_mcp_client_sees_command_beside_legend_lore():
    names = {t.name for t in run(mcp_server.mcp.list_tools())}
    assert LEGEND_LORE | COMMAND <= names


def test_nothing_open_says_so(app, tmp_path):
    (tmp_path / "campaigns").mkdir()
    app.put("/api/command/settings", json={"root": str(tmp_path / "campaigns")})
    assert run(mcp_server.current_session()) == mcp_server._NO_CAMPAIGN


def test_list_campaigns_marks_the_open_one(strahd, app):
    app.post("/api/command/campaigns", json={"name": "Tomb"})
    assert run(mcp_server.list_campaigns()) == "Campaigns:\n  - Strahd (open, session: Session 1)\n  - Tomb"


def test_current_session_reads_the_plan_and_the_live_set(strahd, app):
    app.post("/api/command/live/launch", json={"campaign": "Strahd", "beat": "Beats/Ambush.md"})
    assert run(mcp_server.current_session()) == (
        "Session 1 (2026-10-18) — Strahd\n"
        "\n"
        "Plan:\n"
        "  1. Ambush — live\n"
        "     Ismark (NPCs), Village of Barovia (Locations)\n"
        "\n"
        "Live from Ambush: 2 note(s) — live_set() has their text."
    )


def test_read_and_find_notes(strahd):
    assert run(mcp_server.read_note("ismark")) == (
        "Ismark (NPCs/Ismark.md)\n\nSon of the burgomaster. Protects [[Ireena]].\n"
    )
    assert "names more than one note" in run(mcp_server.read_note("Ireena"))
    assert run(mcp_server.read_note("Locations/Ireena")).startswith("Ireena (Locations/Ireena.md)")
    assert 'Try find_notes("Strahd")' in run(mcp_server.read_note("Strahd"))
    assert run(mcp_server.find_notes("waits", track="Locations")) == (
        'Notes in Strahd mentioning "waits":\n'
        "  - Village of Barovia (Locations/Village of Barovia.md) — Where Ismark waits."
    )
    assert [line.split(" (")[0] for line in run(mcp_server.find_notes("ismark")).splitlines()[1:]] == [
        "  - Ismark", "  - Ambush", "  - Village of Barovia",
    ]
    assert run(mcp_server.find_notes("zzz")) == 'No note in Strahd mentions "zzz".'


def test_create_note_only_in_a_track(strahd):
    assert run(mcp_server.create_note("NPCs", "Doru", "Turned by [[Strahd]].")) == "Created NPCs/Doru.md in Strahd."
    assert (strahd / "Strahd" / "NPCs" / "Doru.md").read_text() == "Turned by [[Strahd]]."
    assert run(mcp_server.create_note("Beats", "Raid")).startswith('Strahd has no track named "Beats"')
    assert run(mcp_server.create_note("Shelf", "Rumour", "The baron is ill.")) == "Created Shelf/Rumour.md in Strahd."


def test_play_from_mcp_live_set_and_spend(strahd, app):
    assert run(mcp_server.add_to_live_set("Ireena", campaign="Strahd")).startswith('"Ireena" names more')
    assert run(mcp_server.add_to_live_set("NPCs/Ireena")) == "Ireena is live: 1 note(s) in play."
    assert run(mcp_server.live_set()) == "Live in Strahd:\n\n## Ireena (NPCs/Ireena.md)\nBitten twice."
    assert run(mcp_server.spend("Ismark")) == "Ismark is spent (2026-10-18)."
    assert run(mcp_server.spend("Ismark", spent=False)) == "Ismark is unspent."


def test_with_the_app_closed_the_tools_say_so(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        mcp_server.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(refuse), **kw),
    )
    args = argparse.Namespace(sidecar_url="http://sidecar.test", data_dir=None)
    monkeypatch.setattr(mcp_server, "sidecar", mcp_server.SidecarClient(args))
    assert run(mcp_server.current_session()) == mcp_server._SIDECAR_DOWN_HINT
    assert run(mcp_server.read_note("Ismark", campaign="Strahd")) == mcp_server._SIDECAR_DOWN_HINT
