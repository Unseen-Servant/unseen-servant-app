"""Command's routes, under ``/api/command``.

Reads go straight to disk. Every write runs under one lock, so a rename
rewriting links across the campaign can't interleave with a save.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import prep, vault
from .events import VaultWatcher
from .settings import CommandSettings, load_settings, save_settings


class SettingsUpdate(BaseModel):
    root: str | None


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


def build_router(app, data_dir: Path | None) -> APIRouter:
    router = APIRouter(prefix="/api/command")
    write_lock = threading.Lock()
    state = {"settings": load_settings(data_dir)}
    watcher = VaultWatcher(lambda: Path(r) if (r := state["settings"].root) else None)

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

    # -- settings ----------------------------------------------------------

    @router.get("/settings")
    def get_settings():
        return state["settings"].model_dump()

    @router.put("/settings")
    def put_settings(update: SettingsUpdate):
        new_root = None
        if update.root:
            path = Path(update.root).expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise HTTPException(422, f"Not a folder: {update.root}")
            new_root = str(path)
        settings = CommandSettings(root=new_root)
        with write_lock:
            save_settings(data_dir, settings)
            state["settings"] = settings
        watcher.root_changed()
        return settings.model_dump()

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
        with write_lock:
            rewritten = vault.rename_campaign(root(), body.name, body.new_name)
        return {"name": body.new_name.strip(), "rewritten": rewritten}

    @router.get("/campaign")
    def get_campaign(name: str):
        return prep.index(campaign_path(name))

    # -- tracks ------------------------------------------------------------

    @router.post("/tracks")
    def create_track(body: TrackCreate):
        with write_lock:
            return {"name": vault.create_track(campaign_path(body.campaign), body.name)}

    @router.post("/tracks/rename")
    def rename_track(body: TrackRename):
        with write_lock:
            rewritten = vault.rename_track(campaign_path(body.campaign), body.name, body.new_name)
        return {"name": body.new_name.strip(), "rewritten": rewritten}

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
        with write_lock:
            return {"path": vault.create_note(campaign_path(body.campaign), body.folder, body.name)}

    @router.post("/notes/rename")
    def rename_note(body: NoteRename):
        with write_lock:
            path, rewritten = vault.rename_note(campaign_path(body.campaign), body.path, body.new_name)
        return {"path": path, "rewritten": rewritten}

    @router.post("/notes/move")
    def move_note(body: NoteMove):
        with write_lock:
            path, rewritten = vault.move_note(campaign_path(body.campaign), body.path, body.folder)
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
        with write_lock:
            return {"spent": prep.set_spent(campaign_path(body.campaign), body.path, body.spent)}

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
