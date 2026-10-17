"""JSON Canvas files (jsoncanvas.org, version 1.0) in the layout Obsidian
writes: tab-indented, one node or edge per line, no space after a colon.

Parsing keeps every key in its order, so a node type or field Command
doesn't know survives a write, and a file Obsidian wrote comes back byte
for byte (design §3.5).
"""

from __future__ import annotations

import json
from collections.abc import Callable


def empty() -> dict:
    return {"nodes": [], "edges": []}


def parse(text: str) -> dict:
    """The canvas in ``text``; a blank file is an empty canvas. Raises
    ValueError for anything that isn't a canvas object."""
    if not text.strip():
        return empty()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("a canvas is a JSON object")
    for key in ("nodes", "edges"):
        items = data.setdefault(key, [])
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ValueError(f"{key} isn't a list of objects")
    return data


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def dump(canvas: dict, final_newline: bool = False) -> str:
    items = []
    for key, value in canvas.items():
        if isinstance(value, list) and value:
            body = ",\n".join(f"\t\t{_compact(item)}" for item in value)
            items.append(f"\t{_compact(key)}:[\n{body}\n\t]")
        else:
            items.append(f"\t{_compact(key)}:{_compact(value)}")
    text = "{\n" + ",\n".join(items) + "\n}" if items else "{}"
    return text + ("\n" if final_newline else "")


def rewrite(
    canvas: dict,
    file_path: Callable[[str], str | None],
    text: Callable[[str], str],
) -> bool:
    """Point file nodes somewhere else and rewrite text nodes' Markdown, in
    place: ``file_path`` returns a node's new path or None to keep it,
    ``text`` returns the text as it should now read. True if anything
    changed."""
    changed = False
    for node in canvas["nodes"]:
        kind = node.get("type")
        if kind == "file" and isinstance(node.get("file"), str):
            new = file_path(node["file"])
            if new is not None and new != node["file"]:
                node["file"] = new
                changed = True
        elif kind == "text" and isinstance(node.get("text"), str):
            new = text(node["text"])
            if new != node["text"]:
                node["text"] = new
                changed = True
    return changed
