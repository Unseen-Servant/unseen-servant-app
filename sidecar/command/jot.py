"""A jot (design §5.2): a line the GM writes from Play's jot bar, added
as a list item at the end of the session note's text.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import vault

_ITEM = re.compile(r"^[-*+][ \t]")


def _lines(text: str) -> list[tuple[str, int]]:
    """Each line without its break, with the offset just past its break."""
    out, pos = [], 0
    while pos < len(text):
        brk = text.find("\n", pos)
        end = len(text) if brk < 0 else brk + 1
        out.append((text[pos:end].rstrip("\r\n"), end))
        pos = end
    return out


def add_jot(text: str, line: str) -> str:
    """``text`` with ``line`` after its last line that isn't blank. After
    anything but a list item, a blank line first so the jot starts a list.
    Nothing else in the text changes."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _lines(text)
    last = max((j for j, (t, _) in enumerate(lines) if t.strip()), default=None)
    at = 0 if last is None else lines[last][1]
    head = text[:at]
    if head and not head.endswith("\n"):
        head += nl
    if last is not None and not _ITEM.match(lines[last][0].strip()):
        head += nl
    return head + line + nl + text[at:]


def jot(campaign: Path, rel: str, text: str) -> str:
    """Add ``- text`` to the note at ``rel``, at the end of its text.
    Returns the line written."""
    text = " ".join(text.split())
    if not text:
        raise vault.Invalid("A jot can't be empty")
    path = vault.note_path(campaign, rel)
    line = f"- {text}"
    vault.atomic_write(path, add_jot(vault.read_text(path), line).encode("utf-8"))
    return line
