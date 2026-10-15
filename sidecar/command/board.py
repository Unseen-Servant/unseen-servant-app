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
MIN_SIZE = 40


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
    - ``connect`` {id, source, target, fromSide?, toSide?}: a line (no
      arrowhead) between two cards, unless one already joins them.
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
        elif kind == "frame":
            target = node(_id(op))
            if target is not None:
                _frame(target, op)
        elif kind == "connect":
            edge_id = _id(op)
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
            # A line, not an arrow: JSON Canvas puts an arrowhead on the
            # target end unless told otherwise (design §5.2).
            edge["toEnd"] = "none"
            edges.append(edge)
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
