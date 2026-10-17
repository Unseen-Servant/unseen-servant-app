"""The session log (design §4): timestamped list items under the session
note's ``## Log`` heading. Command only ever appends to it; the Play
arrangement reads it back. A jot from Play goes above it, in the note's
own text.

    ## Log
    - 19:42 ▶ [[Ambush on the road]]
    - 20:15 spent [[Ravens watch]]
    - 20:22 the party insulted the burgomaster
    - 20:31 captured [[Bildrath's shop]]
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import frontmatter as fm
from . import vault

_HEADING = re.compile(r"^##[ \t]+Log[ \t]*$", re.I)
_SECTION_END = re.compile(r"^#{1,2}[ \t]")
_ITEM = re.compile(r"^[-*+][ \t]+(?:(\d{1,2}:\d{2})(?:[ \t]+|$))?(.*)$")
_EVENT = re.compile(r"^(▶|spent|unspent|captured)[ \t]+(\[\[[^\[\]\n]+?\]\])[ \t]*$")
_KINDS = {"▶": "launch", "spent": "spent", "unspent": "unspent", "captured": "captured"}


def now() -> datetime:
    """The time written on each entry (patched in tests)."""
    return datetime.now()


def _lines(text: str) -> list[tuple[str, int]]:
    """Each line without its break, with the offset just past its break."""
    out, pos = [], 0
    while pos < len(text):
        brk = text.find("\n", pos)
        end = len(text) if brk < 0 else brk + 1
        out.append((text[pos:end].rstrip("\r\n"), end))
        pos = end
    return out


def _section(lines: list[tuple[str, int]]) -> tuple[int, int] | None:
    """The last ``## Log`` heading's line and the line its section ends
    before (the next heading of level one or two, or the end)."""
    heading = max((i for i, (t, _) in enumerate(lines) if _HEADING.match(t)), default=None)
    if heading is None:
        return None
    end = next((j for j in range(heading + 1, len(lines)) if _SECTION_END.match(lines[j][0])), len(lines))
    return heading, end


def add_line(text: str, line: str) -> str:
    """``text`` with ``line`` after the last entry of its last log section,
    adding a ``## Log`` heading at the end when there is none. Nothing
    else in the text changes."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _lines(text)
    found = _section(lines)
    if found is None:
        head = text
        if head and not head.endswith("\n"):
            head += nl
        if head.strip() and not head.endswith(nl + nl):
            head += nl
        return f"{head}## Log{nl}{line}{nl}"
    heading, end = found
    last = max((j for j in range(heading + 1, end) if lines[j][0].strip()), default=heading)
    at = lines[last][1]
    if text[:at].endswith("\n"):
        return text[:at] + line + nl + text[at:]
    return text[:at] + nl + line + text[at:]


def append(campaign: Path, rel: str, entry: str) -> str:
    """Append ``- HH:MM entry`` to the log of the note at ``rel``. Returns
    the line written."""
    entry = " ".join(entry.split())
    if not entry:
        raise vault.Invalid("A log entry can't be empty")
    path = vault.note_path(campaign, rel)
    line = f"- {now():%H:%M} {entry}"
    vault.atomic_write(path, add_line(vault.read_text(path), line).encode("utf-8"))
    return line


def add_jot(text: str, line: str) -> str:
    """``text`` with ``line`` after the last line of the note's own text:
    above its last ``## Log`` section, or at the end. After anything but a
    list item, a blank line first so the jot starts a list; a blank line
    after it before the log. Nothing else in the text changes."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = _lines(text)
    found = _section(lines)
    stop = found[0] if found else len(lines)
    last = max((j for j in range(stop) if lines[j][0].strip()), default=None)
    at = 0 if last is None else lines[last][1]
    head = text[:at]
    if head and not head.endswith("\n"):
        head += nl
    if last is not None and not _ITEM.match(lines[last][0].strip()):
        head += nl
    after = nl if found and (last is None or last + 1 == stop) else ""
    return head + line + nl + after + text[at:]


def jot(campaign: Path, rel: str, text: str) -> str:
    """Add ``- text`` to the note at ``rel``, at the end of its own text
    (not in the log). Returns the line written."""
    text = " ".join(text.split())
    if not text:
        raise vault.Invalid("A jot can't be empty")
    path = vault.note_path(campaign, rel)
    line = f"- {text}"
    vault.atomic_write(path, add_jot(vault.read_text(path), line).encode("utf-8"))
    return line


def parse(text: str) -> list[dict]:
    """The entries of the last log section, in order. A line in Command's
    own shape (``- HH:MM ▶ [[Beat]]``) says what happened; anything else
    the GM wrote there is a jot, with its time if it has one."""
    lines = _lines(text)
    found = _section(lines)
    if found is None:
        return []
    heading, end = found
    entries = []
    for raw, _ in lines[heading + 1:end]:
        line = raw.strip()
        if not line:
            continue
        item = _ITEM.match(line)
        time, rest = (item.group(1), item.group(2).strip()) if item else (None, line)
        event = _EVENT.match(rest) if time else None
        if event:
            entries.append({
                "time": time,
                "kind": _KINDS[event.group(1)],
                "link": fm.link_target(event.group(2)),
                "text": rest,
            })
        else:
            entries.append({"time": time, "kind": "jot", "link": None, "text": rest})
    return entries
