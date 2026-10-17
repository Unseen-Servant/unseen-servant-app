"""The vault: campaigns, tracks and notes as folders of Markdown files.

The folders are the only source of truth (design §3). Every call reads the
disk; nothing here remembers which note belongs where. The one file Command
keeps beside the notes, ``.unseen/command.json``, holds the order of the
tracks, of each folder's notes and of the beats outside a plan —
presentation choices — so a stale entry is ignored and never loses a note.

Paths crossing this module's boundary are campaign-relative POSIX strings
(``NPCs/Ismark.md``); campaigns are addressed by folder name.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from . import canvas

# In the order a GM thinks through prep (the Lazy DM's checklist): the
# characters, what they could learn, where, from whom, what stands in the
# way, and what they win. Strong start and scenes are beats.
DEFAULT_TRACKS = ("PCs", "Secrets", "Locations", "NPCs", "Monsters", "Traps", "Treasures")
# Each default track's pigment, from Legend Lore's palette (palette.ts);
# PCs stay plain.
DEFAULT_PIGMENTS = {
    "Secrets": "#eb98a2",  # Madder
    "Locations": "#c3638d",  # Kermes
    "NPCs": "#8dceee",  # Azurite
    "Monsters": "#f29349",  # Realgar
    "Traps": "#e6c667",  # Ochre
    "Treasures": "#c29ce9",  # Orchil
}
# Beats, sessions, and the shelf of gathered material (design §3.6).
RESERVED = ("Beats", "Sessions", "Shelf")
PRESENTATION_DIR = ".unseen"
PRESENTATION_FILE = "command.json"

# Characters Obsidian refuses in a file name, plus the ones that break a
# wikilink (# ^ [ ] |). A name passing this check is also safe inside a
# double-quoted YAML string, which is how Command writes links (§3.4).
_FORBIDDEN = set('/\\:*?"<>|#^[]')
_MAX_NAME = 200


class VaultError(Exception):
    status = 400


class Invalid(VaultError):
    status = 422


class NotFound(VaultError):
    status = 404


class Conflict(VaultError):
    status = 409

    def __init__(self, message: str, current_hash: str | None = None):
        super().__init__(message)
        self.current_hash = current_hash


# ---------------------------------------------------------------------------
# Names and paths
# ---------------------------------------------------------------------------

def validate_name(name: str) -> str:
    """A campaign, track or note name Command may create. Returns it stripped."""
    name = name.strip()
    if not name:
        raise Invalid("A name can't be empty")
    if len(name) > _MAX_NAME:
        raise Invalid(f"A name can't be longer than {_MAX_NAME} characters")
    if name.startswith("."):
        raise Invalid("A name can't start with a dot")
    if name.endswith("."):
        raise Invalid("A name can't end with a dot")
    bad = sorted({c for c in name if c in _FORBIDDEN or ord(c) < 32})
    if bad:
        shown = " ".join(c if ord(c) >= 32 else repr(c) for c in bad)
        raise Invalid(f"A name can't contain {shown}")
    return name


def _hidden(part: str) -> bool:
    return part.startswith(".")


def _is_reserved(name: str) -> bool:
    return name.casefold() in {r.casefold() for r in RESERVED}


def _is_note_file(name: str) -> bool:
    return not _hidden(name) and name.lower().endswith(".md")


def _stem(filename: str) -> str:
    return filename[:-3]


def campaign_dir(root: Path, campaign: str) -> Path:
    if not campaign or "/" in campaign or "\\" in campaign or _hidden(campaign):
        raise Invalid(f"Not a campaign name: {campaign!r}")
    path = root / campaign
    if not path.is_dir():
        raise NotFound(f"No campaign named {campaign!r}")
    return path


def resolve(campaign: Path, rel: str) -> Path:
    """``rel`` inside ``campaign``, refusing anything that could escape it or
    reach a hidden file (absolute paths, ``..``, dot components)."""
    pure = PurePosixPath(rel)
    if pure.is_absolute() or not pure.parts:
        raise Invalid(f"Not a campaign path: {rel!r}")
    if any(p in ("..", ".") or _hidden(p) for p in pure.parts):
        raise Invalid(f"Not a campaign path: {rel!r}")
    path = campaign.joinpath(*pure.parts)
    if not path.resolve().is_relative_to(campaign.resolve()):
        raise Invalid(f"Not a campaign path: {rel!r}")
    if not path.exists():
        raise NotFound(f"Nothing at {rel!r}")
    return path


def _rel(campaign: Path, path: Path) -> str:
    return path.relative_to(campaign).as_posix()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@dataclass
class NoteEntry:
    name: str
    path: str
    track: str | None  # first folder; None for a loose note at the campaign root
    group: str | None  # folders below the track, e.g. "Vallaki"


def _walk(campaign: Path, keep):
    """Every file under ``campaign`` whose name ``keep`` accepts, skipping
    hidden folders. Symlinked folders are not followed."""
    for dirpath, dirnames, filenames in os.walk(campaign):
        dirnames[:] = sorted(d for d in dirnames if not _hidden(d))
        for filename in sorted(filenames):
            if keep(filename):
                yield Path(dirpath) / filename


def _walk_notes(campaign: Path):
    """Every note file under ``campaign``, skipping hidden files and folders."""
    return _walk(campaign, _is_note_file)


def _is_canvas_file(name: str) -> bool:
    return not _hidden(name) and name.lower().endswith(".canvas")


def _entry(campaign: Path, path: Path) -> NoteEntry:
    parts = path.relative_to(campaign).parts
    folders = parts[:-1]
    return NoteEntry(
        name=_stem(parts[-1]),
        path="/".join(parts),
        track=folders[0] if folders else None,
        group="/".join(folders[1:]) or None,
    )


def list_campaigns(root: Path) -> list[str]:
    return sorted(
        (p.name for p in root.iterdir() if p.is_dir() and not _hidden(p.name)),
        key=str.casefold,
    )


def _track_folders(campaign: Path) -> list[str]:
    return [
        p.name for p in campaign.iterdir()
        if p.is_dir() and not _hidden(p.name) and not _is_reserved(p.name)
    ]


def _presentation_path(campaign: Path) -> Path:
    return campaign / PRESENTATION_DIR / PRESENTATION_FILE


def _presentation(campaign: Path) -> dict:
    try:
        raw = json.loads(_presentation_path(campaign).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _saved_list(campaign: Path, key: str) -> list[str]:
    items = _presentation(campaign).get(key, [])
    return [t for t in items if isinstance(t, str)] if isinstance(items, list) else []


def _save_list(campaign: Path, key: str, items: list[str] | dict[str, list[str]] | dict[str, str]) -> None:
    """Write one entry, keeping whatever else the file holds."""
    path = _presentation_path(campaign)
    path.parent.mkdir(exist_ok=True)
    data = {**_presentation(campaign), "version": 1, key: items}
    atomic_write(path, json.dumps(data, indent=2).encode())


def _saved_order(campaign: Path) -> list[str]:
    return _saved_list(campaign, "tracks")


def _save_order(campaign: Path, order: list[str]) -> None:
    _save_list(campaign, "tracks", order)


def beat_order(campaign: Path) -> list[str]:
    """The beat names the GM ordered, as saved. Beats it doesn't name follow
    them by name (prep.index); names with no beat are ignored."""
    return _saved_list(campaign, "beats")


def save_beat_order(campaign: Path, names: list[str]) -> list[str]:
    _save_list(campaign, "beats", names)
    return names


def note_order(campaign: Path) -> dict[str, list[str]]:
    """The note names the GM ordered, by folder (``NPCs``, ``NPCs/Vallaki``),
    as saved. Notes a folder's list doesn't name follow them by name (the
    grid sorts); names with no note are ignored."""
    raw = _presentation(campaign).get("notes", {})
    if not isinstance(raw, dict):
        return {}
    return {
        folder: [n for n in names if isinstance(n, str)]
        for folder, names in raw.items()
        if isinstance(names, list)
    }


def save_note_order(campaign: Path, folder: str, names: list[str]) -> list[str]:
    """One folder's notes in the order the GM dragged them; other folders'
    orders are kept."""
    _save_list(campaign, "notes", {**note_order(campaign), folder: names})
    return names


def save_track_order(campaign: Path, names: list[str]) -> list[str]:
    """The track order the GM dragged into. Names with no track folder are
    dropped; tracks it doesn't name follow (``track_order``)."""
    _save_order(campaign, names)
    return track_order(campaign)


_PIGMENT = re.compile(r"#[0-9a-f]{6}")


def track_pigments(campaign: Path) -> dict[str, str]:
    """The pigment the GM gave each track, as saved: a hex from Legend
    Lore's palette (palette.ts). Names with no track are ignored."""
    raw = _presentation(campaign).get("pigments", {})
    if not isinstance(raw, dict):
        return {}
    return {t: hex for t, hex in raw.items() if isinstance(hex, str) and _PIGMENT.fullmatch(hex)}


def save_track_pigment(campaign: Path, track: str, pigment: str | None) -> dict[str, str]:
    """Give ``track`` a pigment, or take it away with None; other tracks'
    are kept."""
    if track not in _track_folders(campaign):
        raise NotFound(f"No track named {track!r}")
    if pigment is not None and not _PIGMENT.fullmatch(pigment):
        raise Invalid(f"Not a pigment: {pigment!r}")
    pigments = {t: hex for t, hex in track_pigments(campaign).items() if t != track}
    if pigment is not None:
        pigments[track] = pigment
    _save_list(campaign, "pigments", pigments)
    return pigments


def track_order(campaign: Path) -> list[str]:
    """Tracks in display order: the saved order for tracks it knows, then any
    other track folder alphabetically. Saved names with no folder drop out."""
    present = _track_folders(campaign)
    saved = [t for t in _saved_order(campaign) if t in present]
    rest = sorted((t for t in present if t not in saved), key=str.casefold)
    return saved + rest


def scan(campaign: Path) -> dict:
    """The campaign as the UI draws it: tracks in order, every note, and the
    names more than one note answers to (a link to those is ambiguous)."""
    notes = [_entry(campaign, p) for p in _walk_notes(campaign)]
    seen: dict[str, int] = {}
    for n in notes:
        seen[n.name.casefold()] = seen.get(n.name.casefold(), 0) + 1
    return {
        "name": campaign.name,
        "tracks": track_order(campaign),
        "notes": [asdict(n) for n in notes],
        "note_order": note_order(campaign),
        "pigments": track_pigments(campaign),
        "ambiguous": sorted(k for k, count in seen.items() if count > 1),
    }


def _names_in_use(campaign: Path) -> set[str]:
    return {_stem(p.name).casefold() for p in _walk_notes(campaign)}


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def note_path(campaign: Path, rel: str) -> Path:
    """The note at ``rel``, refusing anything that isn't one."""
    path = resolve(campaign, rel)
    if not path.is_file() or not _is_note_file(path.name):
        raise Invalid(f"Not a note: {rel!r}")
    return path


def read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise Invalid(f"{path.name!r} isn't UTF-8 text, so Command won't edit it")


def read_note(campaign: Path, rel: str) -> dict:
    path = note_path(campaign, rel)
    data = path.read_bytes()
    content = read_text(path)
    return {
        "path": _rel(campaign, path),
        "name": _stem(path.name),
        "content": content,
        "hash": content_hash(data),
    }


# ---------------------------------------------------------------------------
# Writing (design §3.5: surgical, atomic, optimistic)
# ---------------------------------------------------------------------------

def atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to a hidden temp file beside ``path``, then rename it
    over ``path``, so a reader never sees half a file. Keeps the old mode."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_note(campaign: Path, rel: str, content: str, base_hash: str) -> str:
    """Save ``content`` over the note at ``rel`` if the file is still the one
    the caller loaded (``base_hash``); otherwise refuse with the hash now on
    disk, so the caller decides rather than overwriting someone's edit."""
    path = resolve(campaign, rel)
    if not path.is_file() or not _is_note_file(path.name):
        raise Invalid(f"Not a note: {rel!r}")
    current = content_hash(path.read_bytes())
    if current != base_hash:
        raise Conflict(f"{rel!r} changed on disk", current_hash=current)
    data = content.encode("utf-8")
    atomic_write(path, data)
    return content_hash(data)


def _folder(campaign: Path, folder: str) -> Path:
    path = resolve(campaign, folder)
    if not path.is_dir():
        raise Invalid(f"Not a folder: {folder!r}")
    return path


def create_note(campaign: Path, folder: str, name: str, content: str = "") -> str:
    name = validate_name(name)
    parent = _folder(campaign, folder)
    if name.casefold() in _names_in_use(campaign):
        raise Conflict(f"A note named {name!r} already exists in this campaign")
    path = parent / f"{name}.md"
    with open(path, "xb") as f:
        f.write(content.encode("utf-8"))
    return _rel(campaign, path)


def free_name(campaign: Path, wanted: str) -> str:
    """``wanted`` made into a name Command may create, and one no note in
    the campaign has yet: characters a note name can't hold become spaces,
    and a clash takes the next number ("Fire Drake 2")."""
    name = re.sub(r"\s+", " ", "".join(" " if c in _FORBIDDEN or ord(c) < 32 else c for c in wanted))
    name = name.strip().strip(".").strip()[:120].strip() or "Untitled"
    taken = _names_in_use(campaign)
    candidate, n = name, 1
    while candidate.casefold() in taken:
        n += 1
        candidate = f"{name} {n}"
    return candidate


def find_notes(campaign: Path, query: str, track: str | None = None, limit: int = 20) -> list[dict]:
    """Notes whose name or text holds ``query`` (case-insensitive): names
    first, each with a line of context from the text."""
    q = query.strip().casefold()
    if not q:
        return []
    named, inside = [], []
    for path in _walk_notes(campaign):
        entry = _entry(campaign, path)
        if track and (entry.track or "").casefold() != track.casefold():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        at = text.casefold().find(q)
        snippet = ""
        if at >= 0:
            start = max(0, at - 60)
            snippet = " ".join(text[start:at + len(q) + 80].split())
        hit = {**asdict(entry), "snippet": snippet}
        if q in entry.name.casefold():
            named.append(hit)
        elif at >= 0:
            inside.append(hit)
    return (named + inside)[:limit]


def create_campaign(root: Path, name: str) -> str:
    name = validate_name(name)
    if name.casefold() in {c.casefold() for c in list_campaigns(root)}:
        raise Conflict(f"A campaign named {name!r} already exists")
    campaign = root / name
    campaign.mkdir()
    for folder in (*DEFAULT_TRACKS, *RESERVED):
        (campaign / folder).mkdir()
    _save_order(campaign, list(DEFAULT_TRACKS))
    _save_list(campaign, "pigments", DEFAULT_PIGMENTS)
    return name


# -- the untitled campaign ---------------------------------------------------
# With no campaign to reopen, Command opens on a blank campaign named
# Untitled, as Live opens on an empty set. It is a real folder from the start,
# so every route works on it; the name is what marks it, and leaving it blank
# removes it again.

UNTITLED = "Untitled"
_UNTITLED = re.compile(r"Untitled(?: ([1-9][0-9]*))?")
# Finder's file, which appears in any folder it has shown.
_FINDER_FILE = ".DS_Store"


def is_untitled(name: str) -> bool:
    """``Untitled``, or ``Untitled 2`` and on: the names Command gives."""
    return _UNTITLED.fullmatch(name) is not None


def _untitled_number(name: str) -> int:
    match = _UNTITLED.fullmatch(name)
    return int(match.group(1) or 1) if match else 0


def _litter(campaign: Path, path: Path) -> bool:
    """A file that doesn't make a campaign the GM's: Finder's, or Command's
    own track order."""
    return path.name == _FINDER_FILE or path == _presentation_path(campaign)


def is_blank(campaign: Path) -> bool:
    """Nothing the GM made: only folders and litter. A symlink counts as
    something, since removal won't follow it."""
    for dirpath, dirnames, filenames in os.walk(campaign):
        here = Path(dirpath)
        if any((here / d).is_symlink() for d in dirnames):
            return False
        if not all(_litter(campaign, here / f) for f in filenames):
            return False
    return True


def open_untitled(root: Path) -> str:
    """A blank untitled campaign to open: the first one already there (a
    crash can leave one), else a new one under the first free name."""
    untitled = sorted((c for c in list_campaigns(root) if is_untitled(c)), key=_untitled_number)
    for name in untitled:
        if is_blank(root / name):
            return name
    number = 1
    while True:
        name = UNTITLED if number == 1 else f"{UNTITLED} {number}"
        # A file blocks the name as well as a campaign does: mkdir would fail.
        if not any(p.name.casefold() == name.casefold() for p in root.iterdir()):
            return create_campaign(root, name)
        number += 1


def discard_if_blank(root: Path, name: str) -> bool:
    """Remove an untitled campaign the GM left blank. A named campaign stays
    however empty, and so does anything with a note in it. Only litter is
    unlinked and only empty folders removed, so a note that lands while this
    runs stops it rather than going with it."""
    if not is_untitled(name):
        return False
    try:
        campaign = campaign_dir(root, name)
    except VaultError:
        return False
    if not is_blank(campaign):
        return False
    try:
        for dirpath, _dirnames, filenames in os.walk(campaign, topdown=False):
            here = Path(dirpath)
            for f in filenames:
                if _litter(campaign, here / f):
                    (here / f).unlink()
            here.rmdir()
    except OSError:
        return False
    return True


def create_track(campaign: Path, name: str) -> str:
    name = validate_name(name)
    if _is_reserved(name):
        raise Invalid(f"{name!r} is reserved for Command's own notes")
    taken = {p.name.casefold() for p in campaign.iterdir() if p.is_dir()}
    if name.casefold() in taken:
        raise Conflict(f"A folder named {name!r} already exists in this campaign")
    # The order as displayed now, so the new track lands at its end rather
    # than wherever the alphabet puts it.
    order = track_order(campaign)
    (campaign / name).mkdir()
    _save_order(campaign, [*order, name])
    return name


# ---------------------------------------------------------------------------
# Renames and moves rewrite the links that pointed at what moved (§3.3)
# ---------------------------------------------------------------------------

_WIKILINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_FRONTMATTER = re.compile(r"\A﻿?---\r?\n.*?^(?:---|\.\.\.)[ \t]*$", re.S | re.M)

Parts = tuple[str, ...]


def _split_link(inner: str) -> tuple[str, str]:
    """``target`` and the rest (``#heading``, ``|alias``) of a link's inside.
    In a table the alias pipe is escaped as ``\\|``; the backslash goes with
    the rest so the target comes out clean."""
    cut = min((i for i in (inner.find("#"), inner.find("|")) if i >= 0), default=-1)
    if cut < 0:
        return inner, ""
    target, rest = inner[:cut], inner[cut:]
    if target.endswith("\\") and rest.startswith("|"):
        target, rest = target[:-1], "\\" + rest
    return target, rest


def _fold(parts) -> tuple[str, ...]:
    return tuple(p.casefold() for p in parts)


def _answers(parts: Parts, location: Parts) -> bool:
    """Whether a link spelled ``parts`` names the note at ``location``: its
    name, a path suffix of it, or its whole path under a higher vault root."""
    n = min(len(parts), len(location))
    return _fold(parts[-n:]) == _fold(location[-n:]) and (n == len(parts) or n == len(location))


def _stayed(campaign: Path, moves: list[tuple[Parts, Parts]]) -> dict[str, list[Parts]]:
    """The campaign's notes that didn't move, by folded name, for
    ``_retarget`` to tell a link only a moved note answered to."""
    moved = {_fold(new) for _, new in moves}
    stayed: dict[str, list[Parts]] = {}
    for path in _walk_notes(campaign):
        location = _vault_parts(campaign, _rel(campaign, path))
        if _fold(location) not in moved:
            stayed.setdefault(location[-1].casefold(), []).append(location)
    return stayed


def _retarget(
    target: str,
    moves: list[tuple[Parts, Parts]],
    stayed: dict[str, list[Parts]] | None = None,
) -> str | None:
    """The new spelling of ``target`` if it pointed at a moved note, else None.

    A link names a note by its name (``Ismark``) or by a path suffix of any
    length (``NPCs/Ismark``, ``Curse of Strahd/NPCs/Ismark`` — Obsidian
    writes paths relative to wherever the vault is rooted). The rewrite keeps
    the link's shape: a name stays a name, an n-part path stays n parts.

    A link more than one note answers to — a moved one and one in ``stayed``,
    or two moved ones — is ambiguous (``scan``), so it points at neither and
    is left as it is: it may be meant for the other.
    """
    stripped = target.strip()
    has_ext = stripped.lower().endswith(".md")
    bare = stripped[:-3] if has_ext else stripped
    parts = tuple(p for p in bare.split("/") if p)
    if not parts:
        return None
    hits = [(old, new) for old, new in moves if _answers(parts, old)]
    if len(hits) != 1:
        return None
    if any(_answers(parts, other) for other in (stayed or {}).get(parts[-1].casefold(), [])):
        return None
    old, new = hits[0]
    n = len(parts)
    if n <= len(old):
        rewritten = new[-n:] if n <= len(new) else new
    else:
        rewritten = parts[: n - len(old)] + new
    result = "/".join(rewritten) + (".md" if has_ext else "")
    return None if result == stripped else result


def _inside_single_quotes(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    return text.count("'", line_start, pos) % 2 == 1


def rewrite_links(
    text: str,
    moves: list[tuple[Parts, Parts]],
    stayed: dict[str, list[Parts]] | None = None,
) -> str:
    """``text`` with every wikilink to a moved note pointing at its new place.

    ``moves`` pairs old and new locations as path parts without ``.md``,
    relative to the vault root; ``stayed`` holds the notes that didn't move
    (``_stayed``), whose links stay theirs. Everything outside a link's target —
    heading, alias, the ``!`` of an embed, the rest of the file — is kept
    byte for byte.
    """
    fm = _FRONTMATTER.match(text)
    fm_end = fm.end() if fm else 0

    def replace(m: re.Match) -> str:
        target, rest = _split_link(m.group(1))
        new = _retarget(target, moves, stayed)
        if new is None:
            return m.group(0)
        # A single-quoted YAML scalar escapes ' by doubling it.
        if "'" in new and m.start() < fm_end and _inside_single_quotes(text, m.start()):
            new = new.replace("'", "''")
        return f"[[{new}{rest}]]"

    return _WIKILINK.sub(replace, text)


def _rewrite_campaign(campaign: Path, moves: list[tuple[Parts, Parts]]) -> list[str]:
    """Apply ``moves`` to every note and every canvas in ``campaign``; the
    paths it changed. A canvas names notes by path (design §3.5), which
    ``_retarget`` rewrites like a link spelled as a path."""
    stayed = _stayed(campaign, moves)
    changed = []
    for path in _walk_notes(campaign):
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = rewrite_links(text, moves, stayed)
        if new != text:
            atomic_write(path, new.encode("utf-8"))
            changed.append(_rel(campaign, path))
    for path in _walk(campaign, _is_canvas_file):
        try:
            text = path.read_bytes().decode("utf-8")
            board = canvas.parse(text)
        except ValueError:  # not UTF-8, or not a canvas: leave it be
            continue
        if canvas.rewrite(board, lambda f: _retarget(f, moves, stayed), lambda t: rewrite_links(t, moves, stayed)):
            atomic_write(path, canvas.dump(board, text.endswith("\n")).encode("utf-8"))
            changed.append(_rel(campaign, path))
    return changed


def _vault_parts(campaign: Path, rel: str) -> Parts:
    """A note's location as link parts: campaign folder first, no ``.md``."""
    parts = PurePosixPath(rel).parts
    return (campaign.name, *parts[:-1], _stem(parts[-1]))


def _relocate(campaign: Path, src: Path, dst: Path) -> list[tuple[Parts, Parts]]:
    """Rename ``src`` to ``dst`` (a note or a folder) and return the moves it
    made, one per note, for the link rewrite."""
    if src.is_dir():
        olds = [_rel(campaign, p) for p in _walk_notes(src)]
    else:
        olds = [_rel(campaign, src)]
    old_prefix = _rel(campaign, src)
    new_prefix = _rel(campaign, dst)
    os.rename(src, dst)
    return [
        (_vault_parts(campaign, old), _vault_parts(campaign, new_prefix + old[len(old_prefix):]))
        for old in olds
    ]


def _same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def rename_note(campaign: Path, rel: str, new_name: str) -> tuple[str, list[str]]:
    new_name = validate_name(new_name)
    src = resolve(campaign, rel)
    if not src.is_file() or not _is_note_file(src.name):
        raise Invalid(f"Not a note: {rel!r}")
    old_name = _stem(src.name)
    if new_name == old_name:
        return _rel(campaign, src), []
    if not _same_name(new_name, old_name) and new_name.casefold() in _names_in_use(campaign):
        raise Conflict(f"A note named {new_name!r} already exists in this campaign")
    dst = src.with_name(f"{new_name}.md")
    moves = _relocate(campaign, src, dst)
    # A renamed note keeps its place among its folder's notes.
    folder = str(PurePosixPath(_rel(campaign, dst)).parent)
    names = note_order(campaign).get(folder, [])
    if any(_same_name(n, old_name) for n in names):
        save_note_order(campaign, folder, [new_name if _same_name(n, old_name) else n for n in names])
    # A renamed beat keeps its place in the beats' order.
    beats = beat_order(campaign)
    if any(_same_name(b, old_name) for b in beats):
        _save_list(campaign, "beats", [new_name if _same_name(b, old_name) else b for b in beats])
    return _rel(campaign, dst), _rewrite_campaign(campaign, moves)


def move_note(campaign: Path, rel: str, folder: str, order: list[str] | None = None) -> tuple[str, list[str]]:
    """Move a note into ``folder``, first among its notes, or in ``order``
    (a drop between rows: the folder's notes with it in place)."""
    src = resolve(campaign, rel)
    if not src.is_file() or not _is_note_file(src.name):
        raise Invalid(f"Not a note: {rel!r}")
    parent = _folder(campaign, folder)
    dst = parent / src.name
    if dst == src:
        return rel, []
    if dst.exists():
        raise Conflict(f"{_rel(campaign, dst)!r} already exists")
    moves = _relocate(campaign, src, dst)
    # Wherever it came from and whatever its name, so a move always lands
    # the same way. Its old folder forgets it.
    name = _stem(src.name)
    orders = note_order(campaign)
    left, joined = _rel(campaign, src.parent), _rel(campaign, parent)
    if left in orders:
        orders[left] = [n for n in orders[left] if not _same_name(n, name)]
    orders[joined] = order if order is not None else [
        name, *(n for n in orders.get(joined, []) if not _same_name(n, name))
    ]
    _save_list(campaign, "notes", orders)
    return _rel(campaign, dst), _rewrite_campaign(campaign, moves)


def rename_track(campaign: Path, name: str, new_name: str) -> list[str]:
    new_name = validate_name(new_name)
    if name not in _track_folders(campaign):
        raise NotFound(f"No track named {name!r}")
    if _is_reserved(new_name):
        raise Invalid(f"{new_name!r} is reserved for Command's own notes")
    if new_name == name:
        return []
    taken = {p.name.casefold() for p in campaign.iterdir() if p.is_dir()}
    if not _same_name(new_name, name) and new_name.casefold() in taken:
        raise Conflict(f"A folder named {new_name!r} already exists in this campaign")
    order = [new_name if t == name else t for t in track_order(campaign)]

    def renamed(folder: str) -> str:
        head, sep, rest = folder.partition("/")
        return new_name + sep + rest if head == name else folder

    notes = note_order(campaign)
    pigments = track_pigments(campaign)
    moves = _relocate(campaign, campaign / name, campaign / new_name)
    _save_order(campaign, order)
    # Its notes keep their order, a subfolder's too.
    if any(renamed(f) != f for f in notes):
        _save_list(campaign, "notes", {renamed(f): names for f, names in notes.items()})
    # And it keeps its pigment.
    if name in pigments:
        _save_list(campaign, "pigments", {new_name if t == name else t: hex for t, hex in pigments.items()})
    return _rewrite_campaign(campaign, moves)


def rename_campaign(root: Path, name: str, new_name: str) -> list[str]:
    """Rename the campaign folder. Links that spell the campaign folder (a
    vault rooted above it) are rewritten; the usual name-only links aren't
    touched."""
    new_name = validate_name(new_name)
    src = campaign_dir(root, name)
    if new_name == name:
        return []
    if not _same_name(new_name, name) and new_name.casefold() in {
        c.casefold() for c in list_campaigns(root)
    }:
        raise Conflict(f"A campaign named {new_name!r} already exists")
    rels = [_rel(src, p) for p in _walk_notes(src)]
    dst = root / new_name
    os.rename(src, dst)
    moves = [((name, *_vault_parts(dst, r)[1:]), _vault_parts(dst, r)) for r in rels]
    return _rewrite_campaign(dst, moves)
