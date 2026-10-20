"""Command's MCP tools (mcp_server.py, design §8), run against the real
sidecar app in-process: the MCP server is an HTTP adapter over the
sidecar's routes (architecture D5), so these exercise both halves."""

import argparse
import asyncio
import hashlib
import json
import threading
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

import mcp_server
from command import events, prep
from legend_lore.granularity import ParentDoc
from server import create_app

LEGEND_LORE = {"list_collections", "search_library", "get_section", "get_pages", "list_sources", "list_game_systems"}
COMMAND = {"campaign_overview", "current_session", "live_set", "read_note", "find_notes", "create_note", "edit_note", "create_beat", "add_to_beat", "set_active_session", "create_session", "plan_beat", "add_to_live_set", "spend", "connect_cards", "frame_cards", "add_text", "arrange_board", "create_track", "move_note"}


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


def test_campaign_overview_lists_the_campaigns_then_the_open_ones_shape(strahd, app):
    app.post("/api/command/campaigns", json={"name": "Tomb"})
    app.post("/api/command/notes", json={"campaign": "Strahd", "folder": "Shelf", "name": "Rumour"})
    app.post("/api/command/spent", json={"campaign": "Strahd", "path": "NPCs/Ismark.md", "spent": True})
    app.post("/api/command/sessions", json={"campaign": "Strahd"})
    (strahd / "Strahd" / "Sessions" / "Session 2.md").write_text(
        '---\ndate: 2026-10-18\nbeats:\n  - "[[Ambush]]"\n  - "[[Raid]]"\n---\n'
    )
    assert run(mcp_server.campaign_overview()) == (
        "Campaigns:\n"
        "  - Strahd (open, session: Session 1)\n"
        "  - Tomb\n"
        "\n"
        "Tracks in Strahd:\n"
        "  PCs: (empty)\n"
        "  Secrets: (empty)\n"
        "  Locations: Ireena, Village of Barovia\n"
        "  NPCs: Ireena, Ismark (spent)\n"
        "  Monsters: (empty)\n"
        "  Traps: (empty)\n"
        "  Treasures: (empty)\n"
        "\n"
        "Shelf: Rumour\n"
        "\n"
        "Beats:\n"
        "  Ambush: Ismark, Village of Barovia — planned in Session 1, Session 2\n"
        "\n"
        "Sessions:\n"
        "  Session 1 (2026-10-18): 1 beat(s) planned\n"
        "  Session 2 (2026-10-18): 2 beat(s) planned, 1 not written yet\n"
        "\n"
        "Names more than one note answers to (pass the path):\n"
        "  Ireena: Locations/Ireena.md, NPCs/Ireena.md"
    )
    assert run(mcp_server.campaign_overview(campaign="Tomb")).endswith(
        "Shelf: (empty)\n\nBeats:\n  (none yet)\n\nSessions:\n  (none yet)"
    )
    assert run(mcp_server.campaign_overview(campaign="Ravenloft")).endswith("\n\nNo campaign named 'Ravenloft'")


def test_campaign_overview_with_nothing_open_lists_the_campaigns(app, tmp_path):
    (tmp_path / "campaigns").mkdir()
    app.put("/api/command/settings", json={"root": str(tmp_path / "campaigns")})
    assert run(mcp_server.campaign_overview()) == "No campaigns yet. Create one in Command."
    app.post("/api/command/campaigns", json={"name": "Tomb"})
    assert run(mcp_server.campaign_overview()) == (
        "Campaigns:\n  - Tomb\n\nNone is open in the app: pass campaign= to see one."
    )


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
    text = "Son of the burgomaster. Protects [[Ireena]].\n"
    assert run(mcp_server.read_note("ismark")) == (
        f"Ismark (NPCs/Ismark.md)\nhash: {hashlib.sha256(text.encode()).hexdigest()}\n\n{text}"
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
    assert run(mcp_server.find_notes(" ")) == (
        "Give find_notes() words to look for. campaign_overview() lists every note by name."
    )


def test_find_notes_says_when_it_lists_only_the_first(strahd, app, monkeypatch):
    monkeypatch.setattr(mcp_server, "FIND_LIMIT", 2)
    assert run(mcp_server.find_notes("ismark")).splitlines()[1:] == [
        "  - Ismark (NPCs/Ismark.md) — Son of the burgomaster. Protects [[Ireena]].",
        "  - Ambush (Beats/Ambush.md)",
        "(The first 2 only: narrow the words, or pass track=.)",
    ]


def test_create_note_only_in_a_track(strahd):
    assert run(mcp_server.create_note("NPCs", "Doru", "Turned by [[Strahd]].")) == "Created NPCs/Doru.md in Strahd."
    assert (strahd / "Strahd" / "NPCs" / "Doru.md").read_text() == "Turned by [[Strahd]]."
    assert run(mcp_server.create_note("Beats", "Raid")).startswith('Strahd has no track named "Beats"')
    assert run(mcp_server.create_note("Shelf", "Rumour", "The baron is ill.")) == "Created Shelf/Rumour.md in Strahd."
    assert run(mcp_server.create_note("Locations", "doru")) == (
        'A note named "Doru" already exists (NPCs/Doru.md). If you just made it, '
        'it\'s there: read_note("NPCs/Doru.md"). Otherwise pick another name.'
    )
    assert run(mcp_server.create_note("NPCs", "Doru/Son")) == "A name can't contain /"
    assert run(mcp_server.create_note("npcs", "Kasimir")) == "Created NPCs/Kasimir.md in Strahd."


def test_create_note_cites_a_library_section(strahd, app, test_store):
    book = "/corpus/Curse of Strahd.pdf"
    test_store.replace_document(book, "unknown", (), [], [], [], parents=[ParentDoc(
        parent_id="p-k", text="Kasimir Velikov, a dusk elf.", section_heading="Kasimir", chunk_type="prose",
        source_pdf=book, page_start=120, page_end=121, section_id="s_k", section_path="s_k",
    )])
    assert run(mcp_server.create_note("NPCs", "Kasimir", "A dusk elf.\n", cite_section="s_k")) == (
        "Created NPCs/Kasimir.md in Strahd, citing Curse of Strahd, PDF pp.120–121."
    )
    url = "file:///corpus/Curse%20of%20Strahd.pdf#page=120"
    assert (strahd / "Strahd" / "NPCs" / "Kasimir.md").read_text() == (
        f'---\nsource: "{url}"\n---\nA dusk elf.\n\n[Curse of Strahd, PDF pp.120–121]({url})\n'
    )
    index = app.get("/api/command/campaign", params={"name": "Strahd"}).json()
    assert next(n for n in index["notes"] if n["name"] == "Kasimir")["source"] == url
    assert run(mcp_server.create_note("NPCs", "Doru", cite_section="s_zz")) == (
        "Section not found: s_zz. search_library() gives a section's id."
    )
    assert not (strahd / "Strahd" / "NPCs" / "Doru.md").exists()


def test_create_track_then_move_a_note_onto_it(strahd, app):
    assert run(mcp_server.create_track("Factions")) == (
        "Created the track Factions in Strahd. Its tracks: PCs, Secrets, Locations, NPCs, Monsters, Traps, "
        "Treasures, Factions."
    )
    assert run(mcp_server.create_track("factions")) == 'Strahd has a track named "Factions" already.'
    assert run(mcp_server.create_track("Beats")) == "'Beats' is reserved for Command's own notes"
    # A link by path follows the note; the beat that holds it still does.
    village = strahd / "Strahd" / "Locations" / "Village of Barovia.md"
    village.write_text("Where [[NPCs/Ismark]] waits.\n")
    assert run(mcp_server.move_note("Ismark", "factions")) == "Moved Ismark to Factions/Ismark.md in Strahd."
    assert village.read_text() == "Where [[Factions/Ismark]] waits.\n"
    assert "Ismark (Factions), Village of Barovia (Locations)" in run(mcp_server.current_session())
    assert run(mcp_server.move_note("Ismark", "Factions")) == "Ismark is in Factions already."
    assert run(mcp_server.move_note("Ismark", "shelf")) == "Moved Ismark to Shelf/Ismark.md in Strahd."
    assert run(mcp_server.move_note("Ismark", "Beats")).startswith('Strahd has no track named "Beats"')
    assert run(mcp_server.move_note("Ambush", "NPCs")).startswith('No note named "Ambush"')


def test_create_beat_holds_notes_and_joins_a_plan(strahd):
    beats = strahd / "Strahd" / "Beats"
    assert run(mcp_server.create_beat(
        "Church", notes=["ismark", "Village of Barovia"], content="Doru howls below.\n", session="session 1",
    )) == "Created Beats/Church.md in Strahd, holding Ismark, Village of Barovia. It's beat 2 of Session 1's plan."
    assert (beats / "Church.md").read_text() == (
        '---\nnotes:\n  - "[[Ismark]]"\n  - "[[Village of Barovia]]"\n---\nDoru howls below.\n'
    )
    assert "  2. Church\n     Ismark (NPCs), Village of Barovia (Locations)" in run(mcp_server.current_session())
    # A missing session or note, or a name in use, makes nothing.
    assert run(mcp_server.create_beat("Raid", session="Session 9")) == (
        'Strahd has no session named "Session 9". Its sessions: Session 1.'
    )
    assert run(mcp_server.create_beat("Raid", notes=["Doru"])).startswith('No note named "Doru"')
    assert run(mcp_server.create_beat("ambush")).startswith('A beat named "Ambush" already exists (Beats/Ambush.md).')
    assert sorted(p.name for p in beats.iterdir()) == ["Ambush.md", "Church.md"]
    assert run(mcp_server.create_beat("Raid")) == "Created Beats/Raid.md in Strahd, holding no notes yet."


def test_add_to_beat_puts_a_note_in_and_takes_it_out(strahd):
    assert run(mcp_server.add_to_beat("Ismark", "Ambush", member=False)) == (
        "Ismark is out of Ambush, which holds Village of Barovia."
    )
    for _ in range(2):
        assert run(mcp_server.add_to_beat("ismark", "ambush")) == (
            "Ismark is in Ambush, which holds Village of Barovia, Ismark."
        )
    assert run(mcp_server.add_to_beat("Ismark", "Village of Barovia")) == (
        'No beat named "Village of Barovia" in Strahd. campaign_overview() lists the beats.'
    )


def test_a_beat_may_be_named_after_its_place(strahd, app):
    assert run(mcp_server.create_beat(
        "Village of Barovia", notes=["Village of Barovia", "Ismark"], session="Session 1",
    )) == (
        "Created Beats/Village of Barovia.md in Strahd, holding Village of Barovia, Ismark. "
        "It's beat 2 of Session 1's plan."
    )
    assert "  2. Village of Barovia\n     Village of Barovia (Locations), Ismark (NPCs)" in run(
        mcp_server.current_session()
    )
    # A tool that takes a note or a beat knows which is meant; one that
    # takes either asks for the path.
    assert run(mcp_server.add_to_beat("Village of Barovia", "Village of Barovia", member=False)) == (
        "Village of Barovia is out of Village of Barovia, which holds Ismark."
    )
    assert run(mcp_server.plan_beat("Village of Barovia", planned=False)) == "Session 1's plan:\n  1. Ambush"
    assert run(mcp_server.add_to_live_set("Village of Barovia")) == "Village of Barovia is live: 1 note(s) in play."
    assert run(mcp_server.read_note("Village of Barovia")) == (
        '"Village of Barovia" names more than one note in Strahd '
        "(Beats/Village of Barovia.md, Locations/Village of Barovia.md) — pass the path."
    )
    assert run(mcp_server.read_note("Beats/Village of Barovia")).startswith(
        "Village of Barovia (Beats/Village of Barovia.md)"
    )
    assert "Names more than one note answers to (pass the path):\n  Ireena:" in run(mcp_server.campaign_overview())
    assert "  Village of Barovia:" not in run(mcp_server.campaign_overview()).split("Names more")[1]


def test_current_session_reads_any_session_by_name(strahd, app):
    app.post("/api/command/sessions", json={"campaign": "Strahd"})
    assert run(mcp_server.current_session(session="session 2")) == (
        "Session 2 (2026-10-18) — Strahd\n\nPlan:\n  (nothing planned)\n\nNothing is live."
    )
    assert run(mcp_server.current_session(session="Session 9")) == (
        'Strahd has no session named "Session 9". Its sessions: Session 1, Session 2.'
    )


def test_plan_beat_adds_moves_and_takes_out(strahd, app):
    for name in ("Church", "Raid"):
        app.post("/api/command/beats", json={"campaign": "Strahd", "name": name})
    assert run(mcp_server.plan_beat("Church")) == "Session 1's plan:\n  1. Ambush\n  2. Church"
    assert run(mcp_server.plan_beat("raid", position=1)) == "Session 1's plan:\n  1. Raid\n  2. Ambush\n  3. Church"
    assert run(mcp_server.plan_beat("Church", position=1)).endswith("1. Church\n  2. Raid\n  3. Ambush")
    assert run(mcp_server.plan_beat("Church")).endswith("1. Church\n  2. Raid\n  3. Ambush")  # planned already
    assert run(mcp_server.plan_beat("Raid", planned=False)) == "Session 1's plan:\n  1. Church\n  2. Ambush"
    assert run(mcp_server.plan_beat("Raid", planned=False)) == "Raid isn't in Session 1's plan."
    # An entry whose beat is gone can still be taken out, but not planned.
    session = strahd / "Strahd" / "Sessions" / "Session 1.md"
    session.write_text(session.read_text().replace("beats:\n", 'beats:\n  - "[[Gone]]"\n'))
    assert run(mcp_server.plan_beat("Gone", planned=False)) == "Session 1's plan:\n  1. Church\n  2. Ambush"
    assert run(mcp_server.plan_beat("Gone")).startswith('No beat named "Gone"')
    assert run(mcp_server.plan_beat("Ismark")) == 'No beat named "Ismark" in Strahd. campaign_overview() lists the beats.'
    assert run(mcp_server.plan_beat("Raid", position=0)) == "position counts from 1, the plan's first beat."


@pytest.fixture
def relay(app, monkeypatch):
    """Rust's relay, as far as MCP can tell: it hears an ask to open a
    session, and pushes the context back a moment later."""
    real = events.VaultWatcher.publish
    seq = iter(range(100, 200))

    def publish(self, event):
        if event["type"] != "session":
            return real(self, event)
        push = {"seq": next(seq), "campaign": event["campaign"], "session": event["session"]}
        threading.Timer(0.05, lambda: app.put("/api/command/context", json=push)).start()
        return True

    monkeypatch.setattr(events.VaultWatcher, "publish", publish)


def test_create_session_opens_it_in_the_app(strahd, app, relay):
    assert run(mcp_server.create_session()) == (
        "Created Session 2 (Sessions/Session 2.md) in Strahd, with nothing planned. Session 2 is open in the app."
    )
    assert app.get("/api/command/context").json() == {"campaign": "Strahd", "session": "Session 2"}
    assert run(mcp_server.set_active_session("session 1")) == "Session 1 is open in the app."
    assert run(mcp_server.set_active_session("Session 1")) == "Session 1 is open in the app."
    app.post("/api/command/campaigns", json={"name": "Tomb"})
    assert run(mcp_server.create_session(campaign="Tomb")).endswith(
        "The app has Strahd open, not Tomb, so Session 1 isn't open there."
    )


def test_with_no_app_listening_a_session_isnt_opened(strahd, app):
    app.post("/api/command/sessions", json={"campaign": "Strahd"})
    assert run(mcp_server.set_active_session("Session 2")) == "The app isn't listening, so Session 2 isn't open there."
    assert app.get("/api/command/context").json()["session"] == "Session 1"


def hash_in(reply):
    return next(line.removeprefix("hash: ") for line in reply.splitlines() if line.startswith("hash: "))


def test_edit_note_replaces_the_text_and_keeps_the_frontmatter(strahd):
    ambush = strahd / "Strahd" / "Beats" / "Ambush.md"
    read = run(mcp_server.read_note("Ambush"))
    saved = run(mcp_server.edit_note("Ambush", "Wolves at dusk.\n", hash_in(read)))
    assert saved.startswith("Saved Beats/Ambush.md in Strahd.\nhash: ")
    assert ambush.read_text().endswith("---\nWolves at dusk.\n")
    assert "Ismark (NPCs), Village of Barovia (Locations)" in run(mcp_server.current_session())

    assert run(mcp_server.edit_note("Ambush", "Clobber.\n", hash_in(read))) == (
        'Ambush changed since you read it. read_note("Beats/Ambush.md") again.'
    )
    as_read = run(mcp_server.read_note("Ambush")).split("\n\n", 1)[1]
    assert run(mcp_server.edit_note("Ambush", as_read.replace("Wolves", "Ghouls"), hash_in(saved))).startswith("Saved")
    assert ambush.read_text().endswith("---\nGhouls at dusk.\n")
    meddled = as_read.replace("notes:", "spent: 2026-10-18\nnotes:")
    assert run(mcp_server.edit_note("Ambush", meddled, hash_in(run(mcp_server.read_note("Ambush"))))) == (
        "Only the text below the frontmatter changes here, and spent would change. Send the text alone."
    )


def test_play_from_mcp_live_set_and_spend(strahd, app):
    assert run(mcp_server.add_to_live_set("Ireena", campaign="Strahd")).startswith('"Ireena" names more')
    assert run(mcp_server.add_to_live_set("NPCs/Ireena")) == "Ireena is live: 1 note(s) in play."
    assert run(mcp_server.live_set()) == "Live in Strahd:\n\n## Ireena (NPCs/Ireena.md)\nBitten twice."
    assert run(mcp_server.add_to_live_set("Ismark")) == "Ismark is live: 2 note(s) in play."
    assert run(mcp_server.add_to_live_set("NPCs/Ireena", live=False)) == "Ireena is out of play: 1 note(s) in play."
    assert run(mcp_server.spend("Ismark")) == "Ismark is spent (2026-10-18)."
    assert run(mcp_server.spend("Ismark", spent=False)) == "Ismark is unspent."


def test_an_image_plays_and_joins_beats_but_has_no_text_to_read_or_spend(strahd, app):
    # Images design §7: the tools that take a note by name take an image.
    (strahd / "Strahd" / "Locations" / "Barovia.png").write_bytes(b"\x89PNG")
    assert run(mcp_server.add_to_beat("Barovia.png", "Ambush")).startswith("Barovia.png")
    assert run(mcp_server.add_to_live_set("Barovia.png")) == "Barovia.png is live: 1 note(s) in play."
    assert run(mcp_server.live_set()) == "Live in Strahd:\n\n## Barovia.png (Locations/Barovia.png)\n(an image, shown on its card)"
    said = "Barovia.png is an image (Locations/Barovia.png): it has no text. Its card shows it in Play."
    assert run(mcp_server.read_note("Barovia.png")) == said
    assert run(mcp_server.edit_note("Barovia.png", "text", "hash")) == said
    assert run(mcp_server.spend("Barovia.png")).startswith("An image isn't spent")
    assert run(mcp_server.connect_cards("Barovia.png", "Ismark", label="map of")).startswith("Joined Barovia.png and Ismark")


def board_of(strahd, session="Session 1"):
    canvas = json.loads((strahd / "Strahd" / "Sessions" / f"{session}.canvas").read_text())
    return canvas, {n["file"].removeprefix("Strahd/"): n for n in canvas["nodes"] if n["type"] == "file"}


def inside(card, frame):
    return (
        card["x"] >= frame["x"] and card["y"] >= frame["y"]
        and card["x"] + card["width"] <= frame["x"] + frame["width"]
        and card["y"] + card["height"] <= frame["y"] + frame["height"]
    )


def test_connect_cards_first_places_what_the_app_shows(strahd, app):
    # Session 1's board was never touched: the app shows Ambush's notes in a
    # column, and they're written in there before the line.
    assert run(mcp_server.connect_cards("Ismark", "village of barovia", label="waits in")) == (
        'Joined Ismark and Village of Barovia on Session 1\'s board, labelled "waits in".'
    )
    canvas, cards = board_of(strahd)
    assert {rel: (c["x"], c["y"]) for rel, c in cards.items()} == {
        "NPCs/Ismark.md": (0, 0), "Locations/Village of Barovia.md": (0, 212),
    }
    assert [(e["fromNode"], e["toNode"], e["label"], e["toEnd"]) for e in canvas["edges"]] == [
        (cards["NPCs/Ismark.md"]["id"], cards["Locations/Village of Barovia.md"]["id"], "waits in", "none"),
    ]
    assert run(mcp_server.connect_cards("Village of Barovia", "Ismark")) == (
        "A line joins Village of Barovia and Ismark on Session 1's board already."
    )
    # A note the session doesn't hold goes beside the other end.
    assert run(mcp_server.connect_cards("NPCs/Ireena", "Ismark", label="sister of")) == (
        'Joined Ireena and Ismark on Session 1\'s board, labelled "sister of". Ireena is on it now, beside Ismark.'
    )
    ireena = board_of(strahd)[1]["NPCs/Ireena.md"]
    assert (ireena["x"], ireena["y"]) == (292, 0)
    assert run(mcp_server.connect_cards("Ismark", "ismark")) == "A line joins two different notes."
    app.post("/api/command/notes", json={"campaign": "Strahd", "folder": "NPCs", "name": "Doru"})
    assert run(mcp_server.connect_cards("Doru", "Locations/Ireena")).startswith(
        "Neither Doru nor Ireena is on Session 1's board."
    )
    assert run(mcp_server.connect_cards("Ismark", "Ambush")).startswith('No note named "Ambush"')


def test_frame_cards_gathers_notes_under_the_board(strahd):
    run(mcp_server.add_text("Session goals"))
    assert run(mcp_server.frame_cards("Family", ["Ismark", "NPCs/Ireena"])) == (
        "Framed Ismark, Ireena in Family on Session 1's board."
    )
    canvas, cards = board_of(strahd)
    family = next(n for n in canvas["nodes"] if n.get("label") == "Family")
    village = cards["Locations/Village of Barovia.md"]
    assert family["y"] > village["y"] + village["height"]
    for rel in ("NPCs/Ismark.md", "NPCs/Ireena.md"):
        assert inside(cards[rel], family)
    # Framing again under the same name uses that frame, keeping what's in it.
    assert run(mcp_server.frame_cards("family", ["Village of Barovia"])) == (
        "Framed Village of Barovia in Family on Session 1's board. It keeps what was in it."
    )
    canvas, cards = board_of(strahd)
    frames = [n for n in canvas["nodes"] if n["type"] == "group"]
    assert len(frames) == 1 and all(inside(c, frames[0]) for c in cards.values())
    assert run(mcp_server.frame_cards(" ", ["Ismark"])) == "A frame needs a label."


def test_add_text_beside_a_note_or_under_the_board(strahd):
    assert run(mcp_server.add_text("Wolves howl at dusk.", near="Ismark")) == (
        "Added a text card to Session 1's board, beside Ismark."
    )
    assert run(mcp_server.add_text("Ask about [[Ireena]].")) == "Added a text card to Session 1's board, under the rest."
    canvas, _ = board_of(strahd)
    texts = {n["text"]: (n["x"], n["y"], n["width"], n["height"]) for n in canvas["nodes"] if n["type"] == "text"}
    assert texts == {"Wolves howl at dusk.": (292, 0, 260, 100), "Ask about [[Ireena]].": (0, 456, 260, 100)}
    assert run(mcp_server.add_text("Hi", near="NPCs/Ireena")) == (
        "Ireena isn't on Session 1's board. Leave near out to put the card under the board."
    )
    assert run(mcp_server.add_text("  ")) == "A text card needs text."


def test_arrange_board_frames_each_planned_beat(strahd, app):
    assert run(mcp_server.arrange_board()) == "Arranged Session 1's board by beat, a frame each: Ambush."
    canvas, cards = board_of(strahd)
    ambush = next(n for n in canvas["nodes"] if n["type"] == "group")
    assert ambush["label"] == "Ambush" and all(inside(c, ambush) for c in cards.values())
    assert run(mcp_server.arrange_board()) == "Arranged Session 1's board by beat, a frame each: Ambush."
    assert len([n for n in board_of(strahd)[0]["nodes"] if n["type"] == "group"]) == 1
    app.post("/api/command/sessions", json={"campaign": "Strahd"})
    assert run(mcp_server.arrange_board(session="Session 2")) == (
        "Session 2 has nothing planned, so its board has nothing to arrange."
    )
    assert run(mcp_server.arrange_board(session="Session 9")).startswith('Strahd has no session named "Session 9"')


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
