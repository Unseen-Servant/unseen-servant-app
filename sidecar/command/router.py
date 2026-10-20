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

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import board, jot, prep, vault
from .events import VaultWatcher
from .live import LiveSets
from .settings import default_root, load_settings, save_settings


class SettingsUpdate(BaseModel):
    # Each field is changed only when sent; ``root: null`` forgets the folder.
    root: str | None = None
    spend_on_launch: bool | None = None


class CampaignCreate(BaseModel):
    name: str


class CampaignRename(BaseModel):
    name: str
    new_name: str


class CampaignName(BaseModel):
    name: str


class TrackCreate(BaseModel):
    campaign: str
    name: str


class TrackRename(BaseModel):
    campaign: str
    name: str
    new_name: str


class TrackOrder(BaseModel):
    campaign: str
    order: list[str]


class TrackPigment(BaseModel):
    campaign: str
    track: str
    pigment: str | None


class NoteOrder(BaseModel):
    campaign: str
    folder: str
    order: list[str]


class NoteCreate(BaseModel):
    campaign: str
    folder: str
    name: str
    content: str = ""
    # Where it came from, as Send to Command cites it (prep.cited); MCP's
    # create_note(cite_section=).
    source: str | None = None
    cite: str = ""


class NoteSave(BaseModel):
    campaign: str
    path: str
    content: str
    base_hash: str
    keep_frontmatter: bool = False  # content is the text below it (prep.write_text)


class NoteRename(BaseModel):
    campaign: str
    path: str
    new_name: str


class NoteMove(BaseModel):
    campaign: str
    path: str
    folder: str
    order: list[str] | None = None


class Locate(BaseModel):
    campaign: str
    path: str | None = None


class BeatCreate(BaseModel):
    campaign: str
    name: str
    notes: list[str] = []
    session: str | None = None
    content: str = ""


class BeatOrder(BaseModel):
    campaign: str
    order: list[str]


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


class BoardEdit(BaseModel):
    campaign: str
    session: str
    ops: list[dict]


class BoardSettle(BaseModel):
    campaign: str
    session: str


class Launch(BaseModel):
    campaign: str
    beat: str


class LiveNote(BaseModel):
    campaign: str
    note: str
    live: bool


class Stop(BaseModel):
    campaign: str


class Jot(BaseModel):
    campaign: str
    session: str
    text: str


class CopyIn(BaseModel):
    campaign: str
    # Another campaign, or else a place (a folder the GM added).
    from_campaign: str | None = None
    from_place: str | None = None
    path: str


class Place(BaseModel):
    path: str


class Context(BaseModel):
    """The workstation's active campaign and session, pushed by Rust
    (``app_context.rs``) so MCP can answer with no window open."""
    seq: int = 0
    campaign: str | None = None
    session: str | None = None


class OpenSession(BaseModel):
    campaign: str
    session: str  # the session note's path


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

    def remember(campaign: str | None) -> None:
        """Keep the open campaign for the next launch to reopen. No campaign
        is only ever on the way between two, so it isn't kept."""
        with write_lock:
            before = state["settings"]
            if campaign and campaign != before.last_campaign:
                settings = before.model_copy(update={"last_campaign": campaign})
                save_settings(data_dir, settings)
                state["settings"] = settings

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

    # -- places: folders the shelf copies from (design §3.6) ----------------

    def place(path: str) -> Path:
        """A folder the GM added. Only those: the shelf reads no other."""
        if path not in state["settings"].places:
            raise HTTPException(404, f"{path} isn't a folder the shelf copies from")
        folder = Path(path)
        if not folder.is_dir():
            raise HTTPException(409, f"The folder {path} is missing")
        return folder

    def keep_places(update) -> None:
        with write_lock:
            before = state["settings"]
            settings = before.model_copy(update={"places": update(before.places)})
            save_settings(data_dir, settings)
            state["settings"] = settings

    @router.post("/places")
    def add_place(body: Place):
        path = Path(body.path).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise HTTPException(422, f"Not a folder: {body.path}")
        configured = state["settings"].root
        if configured and path.resolve().is_relative_to(Path(configured).resolve()):
            raise HTTPException(422, "That folder is in the campaign folder, whose campaigns are listed already")
        keep_places(lambda places: places if str(path) in places else [*places, str(path)])
        return {"path": str(path)}

    @router.post("/places/remove")
    def remove_place(body: Place):
        keep_places(lambda places: [p for p in places if p != body.path])
        return state["settings"].model_dump()

    @router.get("/place")
    def get_place(path: str):
        return {"notes": vault.folder_notes(place(path))}

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
            remember(body.campaign)
        return get_context()

    @router.post("/context/session")
    def open_session(body: OpenSession):
        """Ask the app to open a session of its open campaign (MCP's
        set_active_session). Rust owns the context: its relay makes the
        switch, then pushes the context back here. ``sent`` is whether the
        relay was listening."""
        name = prep.require_in(campaign_path(body.campaign), body.session, prep.SESSIONS)
        if body.campaign != context["current"].campaign:
            raise HTTPException(409, f"{body.campaign} isn't the campaign open in the app")
        sent = watcher.publish({"type": "session", "campaign": body.campaign, "session": name})
        return {"session": name, "sent": sent}

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

    @router.post("/untitled")
    def open_untitled():
        """A blank untitled campaign to open (``vault.open_untitled``). With no
        campaign folder chosen yet, the default one becomes it."""
        with write_lock:
            before = state["settings"]
            if not before.root:
                path = default_root()
                path.mkdir(parents=True, exist_ok=True)
                settings = before.model_copy(update={"root": str(path)})
                save_settings(data_dir, settings)
                state["settings"] = settings
            name = vault.open_untitled(root())
        if state["settings"].root != before.root:
            watcher.root_changed()
        return {"name": name}

    @router.post("/reopen")
    def reopen():
        """The campaign to open at launch: the one open when the app last
        quit, if it's still in the folder (a blank Untitled went with the
        app), else a blank Untitled."""
        last = state["settings"].last_campaign
        if last and last in vault.list_campaigns(root()):
            return {"name": last}
        return open_untitled()

    @router.post("/campaigns/discard")
    def discard_campaign(body: CampaignName):
        """Remove ``name`` if it's an untitled campaign left blank. Rust asks
        whenever the GM leaves a campaign, and on quitting."""
        with write_lock:
            return {"removed": vault.discard_if_blank(root(), body.name)}

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

    @router.put("/tracks/order")
    def order_tracks(body: TrackOrder):
        """The order of the tracks, as the GM drags their columns (design
        §5.1), kept with the campaign's presentation."""
        with write_lock:
            return {"tracks": vault.save_track_order(campaign_path(body.campaign), body.order)}

    @router.put("/tracks/pigment")
    def pigment_track(body: TrackPigment):
        """A track's pigment from Legend Lore's palette, or none, kept with
        the campaign's presentation."""
        with write_lock:
            return {"pigments": vault.save_track_pigment(campaign_path(body.campaign), body.track, body.pigment)}

    # -- notes -------------------------------------------------------------

    @router.put("/notes/order")
    def order_notes(body: NoteOrder):
        """The order of a folder's notes, as the GM drags their rows (design
        §5.1), kept with the campaign's presentation."""
        with write_lock:
            return {"order": vault.save_note_order(campaign_path(body.campaign), body.folder, body.order)}

    @router.get("/note")
    def get_note(campaign: str, path: str):
        return vault.read_note(campaign_path(campaign), path)

    @router.put("/note")
    def save_note(body: NoteSave):
        write = prep.write_text if body.keep_frontmatter else vault.write_note
        with write_lock:
            new_hash = write(campaign_path(body.campaign), body.path, body.content, body.base_hash)
        return {"hash": new_hash}

    @router.post("/notes")
    def create_note(body: NoteCreate):
        camp = campaign_path(body.campaign)
        content = prep.cited(body.content, body.source, body.cite) if body.source else body.content
        with write_lock:
            return {"path": vault.create_note(camp, shelf_or(camp, body.folder), body.name, content)}

    @router.post("/notes/copy")
    def copy_note(body: CopyIn):
        """Another campaign's note, or a place's, copied onto this one's shelf."""
        camp = campaign_path(body.campaign)
        with write_lock:
            if body.from_campaign is not None:
                path = prep.copy_in(camp, campaign_path(body.from_campaign), body.path)
            elif body.from_place is not None:
                path = prep.copy_from_place(camp, place(body.from_place), body.path)
            else:
                raise HTTPException(422, "Copy from a campaign or a folder")
        return {"path": path}

    @router.get("/find")
    def find(campaign: str, query: str, track: str | None = None, limit: int = 20):
        return {"notes": vault.find_notes(campaign_path(campaign), query, track, limit)}

    @router.post("/send")
    def send(body: Send):
        """A Legend Lore hit, kept as a note in a track (design §8)."""
        with write_lock:
            path = prep.receive(
                campaign_path(body.campaign), body.track, body.name, body.text, body.source, body.cite,
            )
        return {"path": path}

    @router.post("/images")
    async def add_image(request: Request, campaign: str, name: str):
        """An image dropped on a board from Finder, copied onto the
        campaign's shelf (#407), since the campaign is the unit. The body
        is the file's bytes; the answer, the copy's path."""
        data = await request.body()

        def write() -> str:
            camp = campaign_path(campaign)
            with write_lock:
                return vault.add_image(camp, shelf_or(camp, prep.SHELF), name, data)

        return {"path": await run_in_threadpool(write)}

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
            path, rewritten = vault.move_note(camp, body.path, shelf_or(camp, body.folder), body.order)
            moved = live.remap(body.campaign, lambda p: path if p == body.path else p)
        announce(moved)
        return {"path": path, "rewritten": rewritten}

    # -- prep: beats, sessions, spent (design §4, §5.1) --------------------

    @router.post("/beats")
    def create_beat(body: BeatCreate):
        with write_lock:
            path = prep.create_beat(
                campaign_path(body.campaign), body.name, body.notes, body.session, body.content
            )
        return {"path": path}

    @router.put("/beats/order")
    def order_beats(body: BeatOrder):
        """The order of the beats, as the GM drags those outside a plan
        (design §5.1), kept with the campaign's presentation."""
        with write_lock:
            return {"order": vault.save_beat_order(campaign_path(body.campaign), body.order)}

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

    # -- play: the board, the live set, jots (design §5.2, §5.3) -----------

    @router.get("/board")
    def get_board(campaign: str, session: str):
        return board.read(campaign_path(campaign), session)

    @router.post("/board")
    def edit_board(body: BoardEdit):
        with write_lock:
            return board.apply(campaign_path(body.campaign), body.session, body.ops)

    @router.get("/board/arrange")
    def arrange_board(campaign: str, session: str, frame: str | None = None, notes: list[str] = Query([])):
        """The operations that lay the board out by beat, unapplied: the
        app applies them as one step it can undo. With ``frame``, they put
        ``notes`` in the one frame of that name instead (MCP's
        ``frame_cards``)."""
        groups = [(frame.strip(), notes)] if frame and frame.strip() else None
        return {"ops": board.arrange(campaign_path(campaign), session, groups)}

    @router.post("/board/settle")
    def settle_board(body: BoardSettle):
        """Write in the cards the app shows but the board's file doesn't hold
        yet, where it shows them, as the app's first change to a board does:
        MCP settles a board before changing it."""
        camp = campaign_path(body.campaign)
        with write_lock:
            return board.settle(camp, body.session, live.get(body.campaign)["notes"])

    @router.get("/board/spot")
    def board_spot(campaign: str, session: str, kind: str = "text", near: str | None = None):
        """Where a new note card or text card goes: beside the card
        ``near``, else under the board."""
        size = {"file": board.CARD, "text": board.TEXT_CARD}.get(kind)
        if size is None:
            raise HTTPException(422, "A spot is for a note card (file) or a text card (text)")
        return board.spot(campaign_path(campaign), session, size, near)

    @router.get("/live")
    def get_live(campaign: str):
        """What's live, less anything gone since (``LiveSets.prune``)."""
        camp = campaign_path(campaign)
        with write_lock:
            pruned = live.prune(campaign, lambda p: (camp / p).is_file())
        announce(pruned)
        return pruned or live.get(campaign)

    @router.post("/live/launch")
    def launch(body: Launch):
        """Make the beat's notes the live set. With *spend beats on launch*
        on, the beat is spent too."""
        camp = campaign_path(body.campaign)
        with write_lock:
            prep.require_in(camp, body.beat, prep.BEATS)
            beat = next((b for b in prep.index(camp)["beats"] if b["path"] == body.beat), None)
            if beat is None:
                raise vault.NotFound(f"No beat at {body.beat!r}")
            notes = [r["path"] for r in beat["notes"] if r["path"]]
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

    @router.post("/jot")
    def write_jot(body: Jot):
        """A line the GM jots in Play, at the end of the session note's
        text."""
        camp = campaign_path(body.campaign)
        with write_lock:
            prep.require_in(camp, body.session, prep.SESSIONS)
            return {"line": jot.jot(camp, body.session, body.text)}

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
