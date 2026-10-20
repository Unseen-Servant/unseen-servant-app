"""Session boards (design §5.2): ``Sessions/<name>.canvas`` beside the
session note, in JSON Canvas, so Obsidian Canvas opens it.

The board holds where the GM put each card, its size, and the lines
between cards. It never decides which notes a beat holds, so it can't
disagree with one. Writes are operations applied to the file as it is on
disk, so whatever else is in it — nodes Obsidian added, fields Command
doesn't know — is kept.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from . import canvas, vault

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


def note_of(campaign: Path, file) -> str | None:
    """The campaign-relative path of the note a card names, or None when
    it names none. Command writes paths from the root (Obsidian's vault);
    a path from the campaign folder, as a vault opened there writes, is
    read too."""
    if not isinstance(file, str):
        return None
    parts = PurePosixPath(file).parts
    candidates = ["/".join(parts[1:])] if len(parts) > 1 and parts[0].casefold() == campaign.name.casefold() else []
    for rel in (*candidates, file):
        try:
            vault.note_path(campaign, rel)
            return rel
        except vault.VaultError:
            continue
    return None


def _view(campaign: Path, board: dict) -> dict:
    """The board as the UI reads it: nodes and edges as on disk, plus the
    note each card shows."""
    return {
        "nodes": board["nodes"],
        "edges": board["edges"],
        "notes": {
            n["id"]: rel
            for n in board["nodes"]
            if n.get("type") == "file" and isinstance(n.get("id"), str)
            and (rel := note_of(campaign, n.get("file")))
        },
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

    - ``place`` {id, path, x, y, width, height}: put the note at ``path``
      on the board. A note already there is framed instead, and ``id``
      means that card for the rest of the batch.
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
                raise vault.Invalid("Placing a card needs a note's path")
            vault.note_path(campaign, rel)
            existing = next(
                (n for n in nodes if n.get("type") == "file" and note_of(campaign, n.get("file")) == rel),
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
