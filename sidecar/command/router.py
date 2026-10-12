"""Command's routes, under ``/api/command``.

Reads go straight to disk. Every write runs under one lock, so a rename
rewriting links across the campaign can't interleave with a save. The live
set is the one thing not on disk (``live.py``); its changes go out on the
event stream beside the vault's.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import board, log, prep, vault
from .events import VaultWatcher
from .live import LiveSets
from .settings import load_settings, save_settings


class SettingsUpdate(BaseModel):
    # Each field is changed only when sent; ``root: null`` forgets the folder.
    root: str | None = None
    spend_on_launch: bool | None = None


class CampaignCreate(BaseModel):
    name: str


class CampaignRename(BaseModel):
    name: str
    new_name: str


class TrackCreate(BaseModel):
    campaign: str
    name: str


class TrackRename(BaseModel):
    campaign: str
    name: str
    new_name: str


class NoteCreate(BaseModel):
    campaign: str
    folder: str
    name: str
    content: str = ""


class NoteSave(BaseModel):
    campaign: str
    path: str
    content: str
    base_hash: str


class NoteRename(BaseModel):
    campaign: str
    path: str
    new_name: str


class NoteMove(BaseModel):
    campaign: str
    path: str
    folder: str


class Locate(BaseModel):
    campaign: str
    path: str | None = None


class BeatCreate(BaseModel):
    campaign: str
    name: str
    notes: list[str] = []
    session: str | None = None


class Membership(BaseModel):
    campaign: str
    beat: str
    note: str
    member: bool


class SessionCreate(BaseModel):
    campaign: str


class PlanEdit(BaseModel):
    campaign: str
    session: str
    op: str
    beat: str | None = None
    at: int | None = None
    to: int | None = None
    expect: str | None = None


class Spent(BaseModel):
    campaign: str
    path: str
    spent: bool
    # Play passes the session, so the spend is logged (design §4).
    session: str | None = None


class BoardEdit(BaseModel):
    campaign: str
    session: str
    ops: list[dict]


class Launch(BaseModel):
    campaign: str
    beat: str
    session: str | None = None


class LiveNote(BaseModel):
    campaign: str
    note: str
    live: bool


class Stop(BaseModel):
    campaign: str


class Capture(BaseModel):
    campaign: str
    session: str
    name: str


class Jot(BaseModel):
    campaign: str
    session: str
    text: str


class CopyIn(BaseModel):
    campaign: str
    from_campaign: str
    path: str


class Context(BaseModel):
    """The workstation's active campaign and session, pushed by Rust
    (``app_context.rs``) so MCP can answer with no window open."""
    seq: int = 0
    campaign: str | None = None
    session: str | None = None


class Send(BaseModel):
    campaign: str
    # None: onto the campaign's shelf (design §3.6).
    track: str | None = None
    name: str
    text: str
    source: str
    cite: str = ""


def _live_event(snapshot: dict) -> dict:
    return {"type": "live", **snapshot}


def build_router(app, data_dir: Path | None) -> APIRouter:
    router = APIRouter(prefix="/api/command")
    write_lock = threading.Lock()
    state = {"settings": load_settings(data_dir)}
    watcher = VaultWatcher(lambda: Path(r) if (r := state["settings"].root) else None)
    live = LiveSets(data_dir)
    context = {"current": Context(seq=-1)}

    def announce(snapshot: dict | None) -> None:
        if snapshot is not None:
            watcher.publish(_live_event(snapshot))

    @app.exception_handler(vault.VaultError)
    async def vault_error(_request: Request, exc: vault.VaultError):
        body = {"detail": str(exc)}
        if isinstance(exc, vault.Conflict) and exc.current_hash:
            body["hash"] = exc.current_hash
        return JSONResponse(status_code=exc.status, content=body)

    def root() -> Path:
        configured = state["settings"].root
        if not configured:
            raise HTTPException(409, "No campaign folder is set")
        path = Path(configured)
        if not path.is_dir():
            raise HTTPException(409, f"The campaign folder {configured} is missing")
        return path

    def campaign_path(name: str) -> Path:
        return vault.campaign_dir(root(), name)

    def shelf_or(campaign: Path, folder: str) -> str:
        """``folder``, or the shelf as it is on disk — made on first use,
        since a campaign started by hand has none."""
        if folder.casefold() == prep.SHELF.casefold():
            return prep.reserved_folder(campaign, prep.SHELF)
        return folder

    # -- settings ----------------------------------------------------------

    @router.get("/settings")
    def get_settings():
        return state["settings"].model_dump()

    @router.put("/settings")
    def put_settings(update: SettingsUpdate):
        changes = {}
        if "root" in update.model_fields_set:
            changes["root"] = None
            if update.root:
                path = Path(update.root).expanduser()
                if not path.is_absolute() or not path.is_dir():
                    raise HTTPException(422, f"Not a folder: {update.root}")
                changes["root"] = str(path)
        if update.spend_on_launch is not None:
            changes["spend_on_launch"] = update.spend_on_launch
        with write_lock:
            before = state["settings"]
            settings = before.model_copy(update=changes)
            save_settings(data_dir, settings)
            state["settings"] = settings
        if settings.root != before.root:
            watcher.root_changed()
        return settings.model_dump()

    # -- the workstation's context (design §6.2) ----------------------------

    @router.get("/context")
    def get_context():
        current = context["current"]
        return {"campaign": current.campaign, "session": current.session}

    @router.put("/context")
    def put_context(body: Context):
        # Pushes can cross on the way; the newer one wins.
        if body.seq >= context["current"].seq:
            context["current"] = body
        return get_context()

    # -- change events -----------------------------------------------------

    @router.get("/events")
    async def events():
        """Server-sent ``vault`` events (``command/events.py``) for as long
        as the caller stays connected. Rust relays them to every window."""
        async def stream():
            async for event in watcher.listen():
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    # -- campaigns ---------------------------------------------------------

    @router.get("/campaigns")
    def campaigns():
        return {"campaigns": vault.list_campaigns(root())}

    @router.post("/campaigns")
    def create_campaign(body: CampaignCreate):
        with write_lock:
            return {"name": vault.create_campaign(root(), body.name)}

    @router.post("/campaigns/rename")
    def rename_campaign(body: CampaignRename):
        new_name = body.new_name.strip()
        with write_lock:
            rewritten = vault.rename_campaign(root(), body.name, body.new_name)
            moved = live.rename_campaign(body.name, new_name) if new_name != body.name else None
        announce(moved)
        return {"name": new_name, "rewritten": rewritten}

    @router.get("/campaign")
    def get_campaign(name: str):
        return prep.index(campaign_path(name))

    # -- tracks ------------------------------------------------------------

    @router.get("/tracks")
    def get_tracks(campaign: str):
        return {"tracks": vault.track_order(campaign_path(campaign))}

    @router.post("/tracks")
    def create_track(body: TrackCreate):
        with write_lock:
            return {"name": vault.create_track(campaign_path(body.campaign), body.name)}

    @router.post("/tracks/rename")
    def rename_track(body: TrackRename):
        new_name = body.new_name.strip()
        old_prefix, new_prefix = f"{body.name}/", f"{new_name}/"
        with write_lock:
            rewritten = vault.rename_track(campaign_path(body.campaign), body.name, body.new_name)
            moved = live.remap(
                body.campaign,
                lambda p: new_prefix + p[len(old_prefix):] if p.startswith(old_prefix) else p,
            )
        announce(moved)
        return {"name": new_name, "rewritten": rewritten}

    # -- notes -------------------------------------------------------------

    @router.get("/note")
    def get_note(campaign: str, path: str):
        return vault.read_note(campaign_path(campaign), path)

    @router.put("/note")
    def save_note(body: NoteSave):
        with write_lock:
            new_hash = vault.write_note(
                campaign_path(body.campaign), body.path, body.content, body.base_hash
            )
        return {"hash": new_hash}

    @router.post("/notes")
    def create_note(body: NoteCreate):
        camp = campaign_path(body.campaign)
        with write_lock:
            return {"path": vault.create_note(camp, shelf_or(camp, body.folder), body.name, body.content)}

    @router.post("/notes/copy")
    def copy_note(body: CopyIn):
        """Another campaign's note, copied onto this one's shelf."""
        with write_lock:
            path = prep.copy_in(campaign_path(body.campaign), campaign_path(body.from_campaign), body.path)
        return {"path": path}

    @router.get("/find")
    def find(campaign: str, query: str, track: str | None = None):
        return {"notes": vault.find_notes(campaign_path(campaign), query, track)}

    @router.post("/send")
    def send(body: Send):
        """A Legend Lore hit, kept as a note in a track (design §8)."""
        with write_lock:
            path = prep.receive(
                campaign_path(body.campaign), body.track, body.name, body.text, body.source, body.cite,
            )
        return {"path": path}

    @router.post("/notes/rename")
    def rename_note(body: NoteRename):
        camp = campaign_path(body.campaign)
        with write_lock:
            path, rewritten = vault.rename_note(camp, body.path, body.new_name)
            board.follow_rename(camp, body.path, path)
            moved = live.remap(body.campaign, lambda p: path if p == body.path else p)
        announce(moved)
        return {"path": path, "rewritten": rewritten}

    @router.post("/notes/move")
    def move_note(body: NoteMove):
        camp = campaign_path(body.campaign)
        with write_lock:
            path, rewritten = vault.move_note(camp, body.path, shelf_or(camp, body.folder))
            moved = live.remap(body.campaign, lambda p: path if p == body.path else p)
        announce(moved)
        return {"path": path, "rewritten": rewritten}

    # -- prep: beats, sessions, spent (design §4, §5.1) --------------------

    @router.post("/beats")
    def create_beat(body: BeatCreate):
        with write_lock:
            path = prep.create_beat(campaign_path(body.campaign), body.name, body.notes, body.session)
        return {"path": path}

    @router.post("/beats/members")
    def set_member(body: Membership):
        with write_lock:
            notes = prep.set_member(campaign_path(body.campaign), body.beat, body.note, body.member)
        return {"notes": notes}

    @router.post("/sessions")
    def create_session(body: SessionCreate):
        with write_lock:
            return prep.create_session(campaign_path(body.campaign))

    @router.post("/sessions/plan")
    def edit_plan(body: PlanEdit):
        with write_lock:
            beats = prep.edit_plan(
                campaign_path(body.campaign), body.session, body.op,
                beat=body.beat, at=body.at, to=body.to, expect=body.expect,
            )
        return {"beats": beats}

    @router.post("/spent")
    def set_spent(body: Spent):
        camp = campaign_path(body.campaign)
        with write_lock:
            if body.session:
                prep.require_in(camp, body.session, prep.SESSIONS)
            before = prep.spent_of(camp, body.path)
            after = prep.set_spent(camp, body.path, body.spent)
            if body.session and bool(before) != bool(after):
                verb = "spent" if after else "unspent"
                log.append(camp, body.session, f"{verb} [[{vault.note_path(camp, body.path).stem}]]")
        return {"spent": after}

    # -- play: the board, the live set, the log (design §5.2, §5.3) --------

    @router.get("/board")
    def get_board(campaign: str, session: str):
        return board.read(campaign_path(campaign), session)

    @router.post("/board")
    def edit_board(body: BoardEdit):
        with write_lock:
            return board.apply(campaign_path(body.campaign), body.session, body.ops)

    @router.get("/live")
    def get_live(campaign: str):
        return live.get(campaign)

    @router.post("/live/launch")
    def launch(body: Launch):
        """Make the beat's notes the live set and log it. With *spend beats
        on launch* on, the beat is spent too."""
        camp = campaign_path(body.campaign)
        with write_lock:
            prep.require_in(camp, body.beat, prep.BEATS)
            if body.session:
                prep.require_in(camp, body.session, prep.SESSIONS)
            beat = next((b for b in prep.index(camp)["beats"] if b["path"] == body.beat), None)
            if beat is None:
                raise vault.NotFound(f"No beat at {body.beat!r}")
            notes = [r["path"] for r in beat["notes"] if r["path"]]
            if body.session:
                log.append(camp, body.session, f"▶ [[{beat['name']}]]")
            if state["settings"].spend_on_launch and not beat["spent"]:
                prep.set_spent(camp, body.beat, True)
            snapshot = live.set(body.campaign, body.beat, notes)
        announce(snapshot)
        return snapshot

    @router.post("/live/note")
    def live_note(body: LiveNote):
        """Put a note in the live set or take it out — improvising, which
        never changes the beat the set came from (design §5.3)."""
        camp = campaign_path(body.campaign)
        with write_lock:
            vault.note_path(camp, body.note)
            current = live.get(body.campaign)
            notes = [n for n in current["notes"] if n != body.note]
            if body.live:
                notes.append(body.note)
            snapshot = live.set(body.campaign, current["beat"], notes)
        announce(snapshot)
        return snapshot

    @router.post("/live/stop")
    def stop(body: Stop):
        campaign_path(body.campaign)
        with write_lock:
            snapshot = live.set(body.campaign, None, [])
        announce(snapshot)
        return snapshot

    @router.post("/live/capture")
    def capture(body: Capture):
        """Keep the live set as a new beat, placed in the plan after the
        beat it was launched from, and logged. The live set then comes
        from the new beat."""
        camp = campaign_path(body.campaign)
        with write_lock:
            prep.require_in(camp, body.session, prep.SESSIONS)
            current = live.get(body.campaign)
            notes = [n for n in current["notes"] if (camp / n).is_file()]
            path = prep.create_beat(camp, body.name, notes)
            plan = next(s for s in prep.index(camp)["sessions"] if s["path"] == body.session)["beats"]
            after = next((i for i, r in enumerate(plan) if r["path"] == current["beat"]), None)
            prep.edit_plan(camp, body.session, "add", beat=path, to=None if after is None else after + 1)
            log.append(camp, body.session, f"captured [[{vault.note_path(camp, path).stem}]]")
            snapshot = live.set(body.campaign, path, notes)
        announce(snapshot)
        return {"path": path, "live": snapshot}

    @router.post("/log")
    def jot(body: Jot):
        camp = campaign_path(body.campaign)
        with write_lock:
            prep.require_in(camp, body.session, prep.SESSIONS)
            return {"line": log.append(camp, body.session, body.text)}

    # -- deletion is Rust's (the OS trash); this only vouches for the path --

    @router.post("/locate")
    def locate(body: Locate):
        """The absolute path of a campaign, or of a file or folder inside
        one, after the same checks every other route applies. Rust moves it
        to the trash (design §3.5)."""
        target = campaign_path(body.campaign)
        if body.path:
            target = vault.resolve(target, body.path)
        return {"path": str(target)}

    return router
