"""Session boards (design §5.2): ``Sessions/<name>.canvas`` beside the
session note, in JSON Canvas, so Obsidian Canvas opens it.

The board holds where the GM put each card, its size, and the lines
between cards. It never decides which notes a beat holds, so it can't
disagree with one. Writes are operations applied to the file as it is on
disk, so whatever else is in it — nodes Obsidian added, fields Command
doesn't know — is kept.
"""

from __future__ import annotations

import math
import os
import re
import secrets
from pathlib import Path, PurePosixPath

from . import canvas, prep, vault

SESSIONS = vault.RESERVED[1]

# Obsidian's ids are 16 hex digits; any short token of these characters is
# accepted, since Obsidian doesn't care either.
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SIDES = ("top", "right", "bottom", "left")
_ENDS = ("none", "arrow")
# A pigment's hex, or one of Obsidian's six preset colours.
_COLOR = re.compile(r"^(#[0-9a-fA-F]{6}|[1-6])$")
MIN_SIZE = 40
MAX_TEXT = 16 * 1024
# The cards `add` makes (the board toolbar), and the field each one's
# content goes in. Note cards are `place`'s.
_CONTENT = {"text": "text", "group": "label", "link": "url"}
# What `set` may change on each kind of card, and on a line.
_SETTABLE = {
    "text": ("text", "color"),
    "group": ("label", "color"),
    "link": ("url", "color"),
    "edge": ("label", "color", "fromEnd", "toEnd"),
}
_NAMES = {"file": "note card", "text": "text card", "group": "frame", "link": "link card", "edge": "line"}


def board_file(campaign: Path, session: str) -> Path:
    """The board of the session note at ``session``, which must exist."""
    path = vault.note_path(campaign, session)
    if PurePosixPath(session).parts[0].casefold() != SESSIONS.casefold():
        raise vault.Invalid(f"{session!r} isn't in {SESSIONS}/")
    return path.with_suffix(".canvas")


def _load(path: Path) -> tuple[dict, bool]:
    """The board at ``path`` and whether its file ends with a line break; an
    empty board while there's no file."""
    if not path.exists():
        return canvas.empty(), False
    text = vault.read_text(path)
    try:
        return canvas.parse(text), text.endswith("\n")
    except ValueError as e:
        raise vault.Invalid(f"{path.name!r} isn't a board Command can read ({e})")


def _file_of(campaign: Path, file, check) -> str | None:
    """The campaign-relative path of the file a card names, if ``check``
    takes it. Command writes paths from the root (Obsidian's vault); a path
    from the campaign folder, as a vault opened there writes, is read too."""
    if not isinstance(file, str):
        return None
    parts = PurePosixPath(file).parts
    candidates = ["/".join(parts[1:])] if len(parts) > 1 and parts[0].casefold() == campaign.name.casefold() else []
    for rel in (*candidates, file):
        try:
            check(campaign, rel)
            return rel
        except vault.VaultError:
            continue
    return None


def note_of(campaign: Path, file) -> str | None:
    """The note a card names, or None when it names none."""
    return _file_of(campaign, file, vault.note_path)


def image_of(campaign: Path, file) -> str | None:
    """The image a card names, as Obsidian names one dropped on a canvas
    (#407), or None when it names none."""
    return _file_of(campaign, file, vault.image_path)


def _view(campaign: Path, board: dict) -> dict:
    """The board as the UI reads it: nodes and edges as on disk, plus the
    note or the image each card shows."""
    files = [n for n in board["nodes"] if n.get("type") == "file" and isinstance(n.get("id"), str)]
    return {
        "nodes": board["nodes"],
        "edges": board["edges"],
        "notes": {n["id"]: rel for n in files if (rel := note_of(campaign, n.get("file")))},
        "images": {n["id"]: rel for n in files if (rel := image_of(campaign, n.get("file")))},
    }


def read(campaign: Path, session: str) -> dict:
    board, _ = _load(board_file(campaign, session))
    return _view(campaign, board)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def _id(op: dict, key: str = "id") -> str:
    value = op.get(key)
    if not isinstance(value, str) or not _ID.match(value):
        raise vault.Invalid(f"Not a board id: {value!r}")
    return value


def _number(op: dict, key: str, least: int | None = None) -> int:
    value = op.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise vault.Invalid(f"{key} must be a number")
    n = round(value)
    return n if least is None else max(least, n)


def _string(value, key: str) -> str:
    if not isinstance(value, str):
        raise vault.Invalid(f"{key} must be text")
    if len(value) > MAX_TEXT:
        raise vault.Invalid(f"{key} is longer than a board card holds")
    return value


def _field(key: str, value):
    """``value`` for a card's or a line's ``key``, checked; None clears it."""
    if key == "color":
        if value is not None and (not isinstance(value, str) or not _COLOR.match(value)):
            raise vault.Invalid(f"Not a board colour: {value!r}")
        return value
    if key in ("fromEnd", "toEnd"):
        if value not in _ENDS:
            raise vault.Invalid(f"A line's end is {' or '.join(_ENDS)}")
        return value
    if key == "label" and value is None:
        return None
    return _string(value, key)


def _frame(node: dict, op: dict) -> None:
    node["x"] = _number(op, "x")
    node["y"] = _number(op, "y")
    node["width"] = _number(op, "width", MIN_SIZE)
    node["height"] = _number(op, "height", MIN_SIZE)


def apply(campaign: Path, session: str, ops: list[dict]) -> dict:
    """Apply ``ops`` in order and write the board once:

    - ``place`` {id, path, x, y, width, height}: put the note or the image
      at ``path`` on the board. One already there is framed instead, and
      ``id`` means that card for the rest of the batch.
    - ``frame`` {id, x, y, width, height}: move or resize a card.
    - ``add`` {id, type, x, y, width, height, text | label | url, color?}:
      a text card, a frame (``group``) or a link card. A frame goes before
      the cards in the file, so Obsidian draws it behind them.
    - ``connect`` {id, source, target, fromSide?, toSide?, label?, color?,
      fromEnd?, toEnd?}: a line between two cards, unless one already joins
      them; without ``toEnd``, no arrowhead.
    - ``set`` {id, field: value, …}: change a card's or a line's fields
      (``_SETTABLE``), or clear one with null. The rest is kept.
    - ``remove`` {id}: a card (with its lines) or a line.

    An operation naming a card or line that's no longer there (removed in
    Obsidian meanwhile) is skipped."""
    path = board_file(campaign, session)
    board, final_newline = _load(path)
    nodes, edges = board["nodes"], board["edges"]
    by_id = {n.get("id"): n for n in nodes}
    alias: dict[str, str] = {}

    def node(op_id: str) -> dict | None:
        return by_id.get(alias.get(op_id, op_id))

    for op in ops:
        kind = op.get("op")
        if kind == "place":
            new_id = _id(op)
            rel = op.get("path")
            if not isinstance(rel, str):
                raise vault.Invalid("Placing a card needs a note's or an image's path")
            image = vault.is_image(rel)
            (vault.image_path if image else vault.note_path)(campaign, rel)
            shown = image_of if image else note_of
            existing = next(
                (n for n in nodes if n.get("type") == "file" and shown(campaign, n.get("file")) == rel),
                None,
            )
            if existing is not None:
                alias[new_id] = existing["id"]
                _frame(existing, op)
                continue
            if new_id in by_id or any(e.get("id") == new_id for e in edges):
                raise vault.Conflict(f"The board already has {new_id!r}")
            card = {"id": new_id, "type": "file", "file": f"{campaign.name}/{rel}"}
            _frame(card, op)
            nodes.append(card)
            by_id[new_id] = card
        elif kind == "add":
            new_id = _id(op)
            node_type = op.get("type")
            if node_type not in _CONTENT:
                raise vault.Invalid(f"Not a card the board makes: {node_type!r}")
            key = _CONTENT[node_type]
            content = _field(key, op.get(key)) if node_type != "group" or op.get(key) is not None else None
            color = _field("color", op.get("color"))
            if new_id in by_id or any(e.get("id") == new_id for e in edges):
                raise vault.Conflict(f"The board already has {new_id!r}")
            # In Obsidian's order: a text's or a link's content before the
            # frame, a group's label after it.
            card = {"id": new_id, "type": node_type}
            if node_type != "group":
                card[key] = content
            _frame(card, op)
            if node_type == "group" and content:
                card["label"] = content
            if color is not None:
                card["color"] = color
            at = len(nodes)
            if node_type == "group":
                at = next((i for i, n in enumerate(nodes) if n.get("type") != "group"), len(nodes))
            nodes.insert(at, card)
            by_id[new_id] = card
        elif kind == "frame":
            target = node(_id(op))
            if target is not None:
                _frame(target, op)
        elif kind == "connect":
            edge_id = _id(op)
            extra = {k: _field(k, op[k]) for k in ("label", "color", "fromEnd", "toEnd") if op.get(k) is not None}
            a, b = node(_id(op, "source")), node(_id(op, "target"))
            if a is None or b is None or a is b:
                continue
            if any({e.get("fromNode"), e.get("toNode")} == {a["id"], b["id"]} for e in edges):
                continue
            if edge_id in by_id or any(e.get("id") == edge_id for e in edges):
                raise vault.Conflict(f"The board already has {edge_id!r}")
            edge = {"id": edge_id, "fromNode": a["id"]}
            if op.get("fromSide") in _SIDES:
                edge["fromSide"] = op["fromSide"]
            edge["toNode"] = b["id"]
            if op.get("toSide") in _SIDES:
                edge["toSide"] = op["toSide"]
            if extra.get("fromEnd") == "arrow":
                edge["fromEnd"] = "arrow"
            # A line, not an arrow, unless asked: JSON Canvas puts an
            # arrowhead on the target end unless told otherwise (design §5.2).
            edge["toEnd"] = extra.get("toEnd", "none")
            for k in ("color", "label"):
                if extra.get(k):
                    edge[k] = extra[k]
            edges.append(edge)
        elif kind == "set":
            target_id = _id(op)
            fields = {k: v for k, v in op.items() if k not in ("op", "id")}
            for k, v in fields.items():
                if not any(k in allowed for allowed in _SETTABLE.values()):
                    raise vault.Invalid(f"The board can't set {k!r}")
                fields[k] = _field(k, v)
            line = next((e for e in edges if e.get("id") == target_id), None)
            target = node(target_id) or line
            if target is None:
                continue
            what = "edge" if target is line else target.get("type")
            if what not in _SETTABLE or set(fields) - set(_SETTABLE[what]):
                named = _NAMES.get(what, f"{what} card")
                raise vault.Invalid(f"The board can't set {', '.join(sorted(fields))} on a {named}")
            for k, v in fields.items():
                if v is None or (k == "label" and v == ""):
                    target.pop(k, None)
                else:
                    target[k] = v
        elif kind == "remove":
            gone = alias.get(_id(op), _id(op))
            if gone in by_id:
                nodes[:] = [n for n in nodes if n.get("id") != gone]
                del by_id[gone]
                edges[:] = [e for e in edges if gone not in (e.get("fromNode"), e.get("toNode"))]
            else:
                edges[:] = [e for e in edges if e.get("id") != gone]
        else:
            raise vault.Invalid(f"Unknown board operation: {kind!r}")

    text = canvas.dump(board, final_newline)
    if not path.exists() or vault.read_text(path) != text:
        vault.atomic_write(path, text.encode("utf-8"))
    return _view(campaign, board)


# ---------------------------------------------------------------------------
# Arranging by beat (board toolbar design §6, step 3)
# ---------------------------------------------------------------------------

# The board's own measures (the frontend's board.ts): a note card's size, the
# gap between cards, and how far a frame clears its cards, more at the top
# for its name.
CARD = (260, 180)
TEXT_CARD = (260, 100)
GAP = 32
FRAME_PAD, FRAME_TOP = 24, 48
# Frames to a row, read left to right; cards to a frame's row, at most.
PER_ROW, CARDS_ACROSS = 4, 3
THROUGHOUT = "Throughout"


def plan_groups(campaign: Path, session: str, index: dict | None = None) -> list[tuple[str, list[str]]]:
    """The session's notes as Arrange lays them out: Throughout first, with
    the notes several planned beats hold, then each planned beat by name
    with the rest of its notes, in plan order and the beat's own order.
    Throughout is left out when no note is shared; a beat whose notes are
    all shared keeps its (empty) frame."""
    index = index or prep.index(campaign)
    entry = next((s for s in index["sessions"] if s["path"] == session), None)
    if entry is None:
        raise vault.NotFound(f"No session at {session!r}")
    beats = {b["path"]: b for b in index["beats"]}
    planned: list[dict] = []
    for ref in entry["beats"]:
        beat = beats.get(ref["path"])
        if beat is not None and beat not in planned:
            planned.append(beat)
    held = [list(dict.fromkeys(r["path"] for r in b["notes"] if r["path"])) for b in planned]
    count: dict[str, int] = {}
    for notes in held:
        for rel in notes:
            count[rel] = count.get(rel, 0) + 1
    shared = list(dict.fromkeys(rel for notes in held for rel in notes if count[rel] > 1))
    groups = [(THROUGHOUT, shared)] if shared else []
    return groups + [(b["name"], [rel for rel in notes if count[rel] == 1]) for b, notes in zip(planned, held)]


def _within(node: dict, frame: dict) -> bool:
    return (
        node["x"] >= frame["x"] and node["y"] >= frame["y"]
        and node["x"] + node["width"] <= frame["x"] + frame["width"]
        and node["y"] + node["height"] <= frame["y"] + frame["height"]
    )


def _overlaps(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
        and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]
    )


def _placed(board: dict) -> list[dict]:
    """The board's cards that say where they are."""
    return [n for n in board["nodes"] if all(isinstance(n.get(k), (int, float)) for k in ("x", "y", "width", "height"))]


def _new_ids(board: dict):
    """A maker of ids the board doesn't use yet."""
    taken = {n.get("id") for n in board["nodes"]} | {e.get("id") for e in board["edges"]}

    def new_id() -> str:
        while (made := secrets.token_hex(8)) in taken:
            pass
        taken.add(made)
        return made
    return new_id


def _under(nodes: list[dict]) -> tuple[int, int]:
    """Where what's added below the board starts: under all of it, at its
    left edge."""
    if not nodes:
        return 0, 0
    return min(n["x"] for n in nodes), max(n["y"] + n["height"] for n in nodes) + GAP * 2


def arrange(campaign: Path, session: str, groups: list[tuple[str, list[str]]] | None = None) -> list[dict]:
    """The operations that lay the board out by beat, for the caller to
    apply as one step (``apply``); nothing is written here.

    Each group of ``plan_groups`` (or of ``groups``: one frame, for MCP's
    ``frame_cards``) gets a frame named after it, holding its notes in a
    grid, the frames in rows of PER_ROW. A frame already named after the
    group is moved and sized rather than made again, and the other cards
    wholly inside it come along, after its notes: a sticky the GM put in a
    beat's frame stays in it. The rest of the board stays where it is, and
    the arrangement starts under it."""
    board, _ = _load(board_file(campaign, session))
    nodes = _placed(board)
    notes = _view(campaign, board)["notes"]
    if groups is None:
        groups = plan_groups(campaign, session)
    for _, rels in groups:
        for rel in rels:
            vault.note_path(campaign, rel)
    new_id = _new_ids(board)

    card_of: dict[str, dict] = {}
    for n in nodes:
        rel = notes.get(n.get("id"))
        if rel and rel not in card_of:
            card_of[rel] = n
    frame_of: dict[str, dict] = {}
    for n in nodes:
        if n.get("type") == "group" and isinstance(n.get("label"), str):
            frame_of.setdefault(n["label"].strip().casefold(), n)
    assigned = {rel for _, rels in groups for rel in rels}
    moving = {id(card_of[rel]) for rel in assigned if rel in card_of}

    # What each frame holds: its notes, then what was inside its old frame.
    laid: list[tuple[str, dict | None, list[tuple[str | dict, int, int]]]] = []
    for name, rels in groups:
        old = frame_of.get(name.casefold())
        items: list[tuple[str | dict, int, int]] = []
        for rel in rels:
            card = card_of.get(rel)
            items.append((card, card["width"], card["height"]) if card else (rel, *CARD))
        if old is not None:
            moving.add(id(old))
            inside = [
                n for n in nodes
                if n is not old and id(n) not in moving and n.get("type") != "group" and _within(n, old)
            ]
            for n in sorted(inside, key=lambda n: (n["y"], n["x"])):
                moving.add(id(n))
                items.append((n, n["width"], n["height"]))
        laid.append((name, old, items))

    staying = [n for n in nodes if id(n) not in moving]
    x0 = min((n["x"] for n in nodes), default=0)
    y0 = max((n["y"] + n["height"] for n in staying), default=None)
    y0 = y0 + GAP * 2 if y0 is not None else min((n["y"] for n in nodes), default=0)

    ops: list[dict] = []
    x, y, row_height = x0, y0, 0
    for i, (name, old, items) in enumerate(laid):
        if i and i % PER_ROW == 0:
            x, y, row_height = x0, y + row_height + GAP * 2, 0
        across = max(1, min(CARDS_ACROSS, math.ceil(math.sqrt(len(items)))))
        down = max(1, math.ceil(len(items) / across))
        cell_w = max((w for _, w, _ in items), default=CARD[0])
        cell_h = max((h for _, _, h in items), default=CARD[1])
        width = across * cell_w + (across - 1) * GAP + FRAME_PAD * 2
        height = FRAME_TOP + down * cell_h + (down - 1) * GAP + FRAME_PAD
        place = {"x": round(x), "y": round(y), "width": round(width), "height": round(height)}
        if old is not None:
            ops.append({"op": "frame", "id": old["id"], **place})
        else:
            ops.append({"op": "add", "id": new_id(), "type": "group", "label": name, **place})
        for k, (item, w, h) in enumerate(items):
            at = {
                "x": round(x + FRAME_PAD + (k % across) * (cell_w + GAP)),
                "y": round(y + FRAME_TOP + (k // across) * (cell_h + GAP)),
                "width": round(w),
                "height": round(h),
            }
            if isinstance(item, str):
                ops.append({"op": "place", "id": new_id(), "path": item, **at})
            else:
                ops.append({"op": "frame", "id": item["id"], **at})
        x += width + GAP * 2
        row_height = max(row_height, height)
    return ops


# ---------------------------------------------------------------------------
# For MCP (board toolbar design §6, step 4)
# ---------------------------------------------------------------------------

def settle(campaign: Path, session: str, live: list[str]) -> dict:
    """Write in the cards the app shows but the file doesn't hold yet,
    where it shows them, and return the board. The app lays the session's
    notes and anything ``live`` out to the right of what's placed, a column
    per group of ``plan_groups``, then one for the rest by name (board.ts
    ``cards``), and its first change to a board places them all
    (``placeAll``). An agent settles a board before changing it, so its
    change moves nothing the GM sees."""
    board, _ = _load(board_file(campaign, session))
    nodes = _placed(board)
    index = prep.index(campaign)
    names = {n["path"]: n["name"] for n in index["notes"]}
    groups = [rels for _, rels in plan_groups(campaign, session, index)]
    on_board = set(_view(campaign, board)["notes"].values())
    wanted = [rel for rels in groups for rel in rels] + list(live)
    loose = {rel for rel in wanted if rel not in on_board and rel in names}
    if not loose:
        return _view(campaign, board)

    grouped = {rel for rels in groups for rel in rels}
    rest = sorted((rel for rel in loose if rel not in grouped), key=lambda rel: prep.natural(names[rel]))
    columns = [c for c in ([rel for rel in rels if rel in loose] for rels in groups + [rest]) if c]
    x0 = max(n["x"] + n["width"] for n in nodes) + GAP * 2 if nodes else 0
    y0 = min(n["y"] for n in nodes) if nodes else 0
    new_id = _new_ids(board)
    ops = [
        {"op": "place", "id": new_id(), "path": rel, "x": x0 + i * (CARD[0] + GAP),
         "y": y0 + row * (CARD[1] + GAP), "width": CARD[0], "height": CARD[1]}
        for i, column in enumerate(columns) for row, rel in enumerate(column)
    ]
    return apply(campaign, session, ops)


def spot(campaign: Path, session: str, size: tuple[int, int], near: str | None = None) -> dict:
    """Where a new card of ``size`` goes: beside the card ``near``, to its
    right, else below it when the right is taken, else past the cards in
    the way to the right, as a duplicate goes (board.ts ``duplicateOps``); a
    frame ``near`` sits in isn't in the way. With no ``near``, under the
    board."""
    board, _ = _load(board_file(campaign, session))
    nodes = _placed(board)
    width, height = size
    if near is None:
        x, y = _under(nodes)
        return {"x": x, "y": y, "width": width, "height": height}
    anchor = next((n for n in nodes if n.get("id") == near), None)
    if anchor is None:
        raise vault.NotFound(f"No card {near!r} on the board")
    in_way = [n for n in nodes if n is not anchor and not (n.get("type") == "group" and _within(anchor, n))]

    def blocking(x: int, y: int) -> list[dict]:
        box = {"x": x, "y": y, "width": width, "height": height}
        return [n for n in in_way if _overlaps(n, box)]

    right = (anchor["x"] + anchor["width"] + GAP, anchor["y"])
    below = (anchor["x"], anchor["y"] + anchor["height"] + GAP)
    x, y = below if blocking(*right) and not blocking(*below) else right
    while hit := blocking(x, y):
        x = max(n["x"] + n["width"] for n in hit) + GAP
    return {"x": round(x), "y": round(y), "width": width, "height": height}


# ---------------------------------------------------------------------------
# Following the session
# ---------------------------------------------------------------------------

def follow_rename(campaign: Path, old: str, new: str) -> str | None:
    """After the session note ``old`` became ``new``, rename its board to
    match. Returns the board's new path, or None if nothing moved."""
    if PurePosixPath(old).parts[0].casefold() != SESSIONS.casefold():
        return None
    src = (campaign / old).with_suffix(".canvas")
    dst = (campaign / new).with_suffix(".canvas")
    if not src.is_file() or dst.exists():
        return None
    os.rename(src, dst)
    return PurePosixPath(new).with_suffix(".canvas").as_posix()
