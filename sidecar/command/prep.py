"""Prep: beats, sessions and spent notes on top of the vault (design §4, §5.1).

A beat lists its notes and a session lists its beats, as frontmatter lists
of links (`notes`, `beats`); `spent` is a date on the note itself. Every
call reads those back from disk, and every change goes through
frontmatter.set_key, which touches only the key it writes.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path, PurePosixPath

from . import vault
from . import frontmatter as fm

BEATS, SESSIONS, SHELF = vault.RESERVED


def today() -> date:
    """The date written for spends and new sessions (patched in tests)."""
    return date.today()


def _natural(name: str) -> list:
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", name)]


def _in(note: dict, folder: str) -> bool:
    return note["track"] is not None and note["track"].casefold() == folder.casefold()


def _stem(rel: str) -> str:
    return PurePosixPath(rel).name.removesuffix(".md")


def index(campaign: Path) -> dict:
    """The campaign as Prep and Play draw it: the vault scan, each note's
    spent mark, beats with their notes, sessions with their plans — every
    link resolved to a note's path, or None when no single note answers
    to it."""
    base = vault.scan(campaign)

    def text(rel: str) -> str:
        # One unreadable note (not UTF-8) mustn't hide the campaign.
        try:
            return vault.read_text(campaign / rel)
        except vault.Invalid:
            return ""

    texts = {n["path"]: text(n["path"]) for n in base["notes"]}
    metas = {rel: fm.load_lenient(t) for rel, t in texts.items()}
    by_name: dict[str, list[str]] = {}
    for n in base["notes"]:
        by_name.setdefault(n["name"].casefold(), []).append(n["path"])
        n["spent"] = fm.spent_value(metas[n["path"]].get("spent"))
        source = metas[n["path"]].get("source")
        n["source"] = source if isinstance(source, str) and source.strip() else None

    def resolve(name: str) -> str | None:
        paths = by_name.get(name.casefold(), [])
        return paths[0] if len(paths) == 1 else None

    def ref(entry) -> dict:
        target = fm.link_target(entry)
        return {"link": target, "path": resolve(target)}

    base["beats"] = [
        {
            "name": n["name"],
            "path": n["path"],
            "spent": n["spent"],
            "notes": [ref(e) for e in fm.as_list(metas[n["path"]].get("notes"))],
        }
        for n in base["notes"]
        if _in(n, BEATS)
    ]
    # The order the GM gave the beats (vault.beat_order), then by name.
    saved = {name.casefold(): i for i, name in enumerate(vault.beat_order(campaign))}
    base["beats"].sort(key=lambda b: (saved.get(b["name"].casefold(), len(saved)), _natural(b["name"])))
    sessions = [
        {
            "name": n["name"],
            "path": n["path"],
            "date": fm.date_value(metas[n["path"]].get("date")),
            "beats": [ref(e) for e in fm.as_list(metas[n["path"]].get("beats"))],
        }
        for n in base["notes"]
        if _in(n, SESSIONS)
    ]
    base["sessions"] = sorted(sessions, key=lambda s: (s["date"] or "", _natural(s["name"])))
    return base


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _update(campaign: Path, rel: str, key: str, compute):
    """Read the note at ``rel``, set ``key`` to ``compute(current value)``,
    write it back if anything changed. Returns the new value."""
    path = vault.note_path(campaign, rel)
    text = vault.read_text(path)
    value = compute(fm.load(text).get(key))
    new = fm.set_key(text, key, value)
    if new != text:
        vault.atomic_write(path, new.encode("utf-8"))
    return value


def reserved_folder(campaign: Path, name: str) -> str:
    """The reserved folder's name as it is on disk, made if it's missing (a
    campaign started by hand has no Beats/ or Sessions/)."""
    for p in campaign.iterdir():
        if p.is_dir() and p.name.casefold() == name.casefold():
            return p.name
    (campaign / name).mkdir()
    return name


def require_in(campaign: Path, rel: str, folder: str) -> str:
    vault.note_path(campaign, rel)
    if PurePosixPath(rel).parts[0].casefold() != folder.casefold():
        raise vault.Invalid(f"{rel!r} isn't in {folder}/")
    return _stem(rel)


def _targets(entries) -> list[str]:
    return [fm.link_target(e) for e in entries]


def set_member(campaign: Path, beat: str, note: str, member: bool) -> list[str]:
    """Add the note at ``note`` to the beat's notes, or take it out — every
    entry naming it, whatever its spelling (alias, path, case)."""
    require_in(campaign, beat, BEATS)
    name = _stem(str(vault.note_path(campaign, note).relative_to(campaign)))

    def compute(current):
        entries = [fm.entry_text(e) for e in fm.as_list(current)]
        naming = [e for e in entries if fm.link_target(e).casefold() == name.casefold()]
        if member:
            return entries if naming else entries + [f"[[{name}]]"]
        return [e for e in entries if e not in naming]

    return _targets(_update(campaign, beat, "notes", compute))


def create_beat(campaign: Path, name: str, notes: list[str] = (), session: str | None = None) -> str:
    """A new note in Beats/, holding ``notes`` (paths) if any, and added to
    the end of ``session``'s plan if one is given."""
    members = [_stem(str(vault.note_path(campaign, n).relative_to(campaign))) for n in notes]
    rel = vault.create_note(campaign, reserved_folder(campaign, BEATS), name)
    if members:
        _update(campaign, rel, "notes", lambda _: [f"[[{m}]]" for m in members])
    if session:
        edit_plan(campaign, session, "add", beat=rel)
    return rel


def create_session(campaign: Path) -> dict:
    """The next session (design §4): `Session N`, dated today, with nothing
    planned and no board. The last session's unplayed beats wait outside
    the plan, not in it."""
    current = index(campaign)
    numbers = [int(m.group()) for s in current["sessions"] if (m := re.search(r"\d+", s["name"]))]
    n = max(numbers, default=0) + 1
    taken = {x["name"].casefold() for x in current["notes"]}
    while f"Session {n}".casefold() in taken:
        n += 1
    name = f"Session {n}"

    rel = vault.create_note(campaign, reserved_folder(campaign, SESSIONS), name)
    text = fm.set_key("", "date", today())
    text = fm.set_key(text, "beats", [])
    vault.atomic_write(campaign / rel, text.encode("utf-8"))
    return {"path": rel, "name": name}


def edit_plan(
    campaign: Path,
    session: str,
    op: str,
    *,
    beat: str | None = None,
    at: int | None = None,
    to: int | None = None,
    expect: str | None = None,
) -> list[str]:
    """Change a session's plan in place: ``add`` a beat (at ``to``, or the
    end), ``remove`` the entry ``at``, or ``move`` it ``to``. Removing and
    moving name the entry they expect at ``at`` and are refused when the
    plan on disk no longer has it there."""
    require_in(campaign, session, SESSIONS)
    name = require_in(campaign, beat, BEATS) if op == "add" and beat else None

    def compute(current):
        entries = [fm.entry_text(e) for e in fm.as_list(current)]
        if op == "add":
            if name is None:
                raise vault.Invalid("Adding to a plan needs a beat")
            if any(fm.link_target(e).casefold() == name.casefold() for e in entries):
                return entries
            pos = len(entries) if to is None else max(0, min(to, len(entries)))
            entries.insert(pos, f"[[{name}]]")
            return entries
        if op in ("remove", "move"):
            if (
                at is None
                or not 0 <= at < len(entries)
                or expect is None
                or fm.link_target(entries[at]).casefold() != expect.casefold()
            ):
                raise vault.Conflict("The session's plan changed on disk — look again and retry")
            entry = entries.pop(at)
            if op == "move":
                if to is None:
                    raise vault.Invalid("Moving needs a destination")
                entries.insert(max(0, min(to, len(entries))), entry)
            return entries
        raise vault.Invalid(f"Unknown plan edit: {op!r}")

    return _targets(_update(campaign, session, "beats", compute))


def set_spent(campaign: Path, rel: str, spent: bool) -> str | None:
    """Mark the note spent today, or unspent. A note already spent keeps
    the date it was spent."""
    current = spent_of(campaign, rel)
    if spent and current:
        return current
    value = _update(campaign, rel, "spent", lambda _: today() if spent else None)
    return fm.spent_value(value)


def spent_of(campaign: Path, rel: str) -> str | None:
    return fm.spent_value(fm.load(vault.read_text(vault.note_path(campaign, rel))).get("spent"))


def write_text(campaign: Path, rel: str, text: str, base_hash: str) -> str:
    """Save ``text`` as the note's text below its frontmatter, which stays
    as it is, if the file is still the one the caller read (vault.write_note).
    ``text`` may open with that frontmatter, as read_note showed it; a block
    with a key changed is refused, since each key keeps its own writer
    (MCP's edit_note, design §8)."""
    note = vault.read_note(campaign, rel)
    if note["hash"] != base_hash:
        raise vault.Conflict(f"{rel!r} changed on disk", current_hash=note["hash"])
    old, new = fm.split(note["content"]), fm.split(text)
    if new.block is not None and new.block != old.block:
        was, now = fm.load_lenient(note["content"]), fm.load(text)
        changed = sorted(str(k) for k in was.keys() | now.keys() if was.get(k) != now.get(k))
        if changed:
            raise vault.Invalid(
                f"Only the text below the frontmatter changes here, and {', '.join(changed)} "
                "would change. Send the text alone."
            )
    head = old.bom + old.open + (old.block or "") + old.close
    if old.block is not None and new.body and not old.close.endswith("\n"):
        head += old.newline
    return vault.write_note(campaign, rel, head + new.body, base_hash)


# ---------------------------------------------------------------------------
# Gathering: the shelf, material sent from Legend Lore (design §3.6, §8)
# ---------------------------------------------------------------------------

def receive(campaign: Path, track: str | None, name: str, text: str, source: str, cite: str) -> str:
    """A new note in ``track`` — on the shelf when there's none — holding
    ``text``, with ``source`` (where it came from: a PDF page's file URL)
    in its frontmatter and a link back under the text. Named after
    ``name``, made free if it's taken."""
    if track is None:
        track = reserved_folder(campaign, SHELF)
    elif track not in vault.track_order(campaign):
        raise vault.NotFound(f"No track named {track!r}")
    link = source.replace("(", "%28").replace(")", "%29")
    body = text.strip()
    content = fm.set_key("", "source", source) + (f"{body}\n\n" if body else "") + f"[{cite.strip() or 'Source'}]({link})\n"
    return vault.create_note(campaign, track, vault.free_name(campaign, name), content)


def copy_in(campaign: Path, source: Path, rel: str) -> str:
    """Copy the note at ``rel`` in another campaign (``source``) onto this
    campaign's shelf. The copy is this campaign's own: it keeps the text
    and the frontmatter, but not the other table's ``spent`` mark."""
    if source.resolve() == campaign.resolve():
        raise vault.Invalid("That note is already in this campaign")
    path = vault.note_path(source, rel)
    if PurePosixPath(rel).parts[0].casefold() in {BEATS.casefold(), SESSIONS.casefold()}:
        raise vault.Invalid("Beats and sessions belong to their campaign; copy their notes instead")
    return _copy_onto_shelf(campaign, path)


def copy_from_place(campaign: Path, folder: Path, rel: str) -> str:
    """Copy the note at ``rel`` in a place, a folder the GM added (design
    §3.6), onto this campaign's shelf, as another campaign's note is. Its
    folders are its own, so a ``Sessions/`` there holds notes like any."""
    return _copy_onto_shelf(campaign, vault.note_path(folder, rel))


def _copy_onto_shelf(campaign: Path, path: Path) -> str:
    text = vault.read_text(path)
    try:
        text = fm.set_key(text, "spent", None)
    except fm.FrontmatterError:
        pass  # a block that doesn't parse holds no spent mark Command could read
    return vault.create_note(campaign, reserved_folder(campaign, SHELF), _stem(path.name), text)
