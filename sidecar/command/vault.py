"""The vault: campaigns, tracks and notes as folders of Markdown files.

The folders are the only source of truth (design §3). Every call reads the
disk; nothing here remembers which note belongs where. The one file Command
keeps beside the notes, ``.unseen/command.json``, holds track order — a
presentation choice — so a stale entry is ignored and never loses a note.

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

DEFAULT_TRACKS = ("PCs", "NPCs", "Locations", "Secrets", "Monsters", "Treasures")
RESERVED = ("Beats", "Sessions")
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


def _walk_notes(campaign: Path):
    """Every note file under ``campaign``, skipping hidden files and folders.
    Symlinked folders are not followed."""
    for dirpath, dirnames, filenames in os.walk(campaign):
        dirnames[:] = sorted(d for d in dirnames if not _hidden(d))
        for filename in sorted(filenames):
            if _is_note_file(filename):
                yield Path(dirpath) / filename


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


def _saved_order(campaign: Path) -> list[str]:
    try:
        raw = json.loads(_presentation_path(campaign).read_text(encoding="utf-8"))
        tracks = raw.get("tracks", [])
        return [t for t in tracks if isinstance(t, str)]
    except (OSError, ValueError, AttributeError):
        return []


def _save_order(campaign: Path, order: list[str]) -> None:
    path = _presentation_path(campaign)
    path.parent.mkdir(exist_ok=True)
    atomic_write(path, json.dumps({"version": 1, "tracks": order}, indent=2).encode())


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
        "ambiguous": sorted(k for k, count in seen.items() if count > 1),
    }


def _names_in_use(campaign: Path) -> set[str]:
    return {_stem(p.name).casefold() for p in _walk_notes(campaign)}


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_note(campaign: Path, rel: str) -> dict:
    path = resolve(campaign, rel)
    if not path.is_file() or not _is_note_file(path.name):
        raise Invalid(f"Not a note: {rel!r}")
    data = path.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Invalid(f"{rel!r} isn't UTF-8 text, so Command won't edit it")
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


def create_note(campaign: Path, folder: str, name: str) -> str:
    name = validate_name(name)
    parent = _folder(campaign, folder)
    if name.casefold() in _names_in_use(campaign):
        raise Conflict(f"A note named {name!r} already exists in this campaign")
    path = parent / f"{name}.md"
    with open(path, "xb"):
        pass
    return _rel(campaign, path)


def create_campaign(root: Path, name: str) -> str:
    name = validate_name(name)
    if name.casefold() in {c.casefold() for c in list_campaigns(root)}:
        raise Conflict(f"A campaign named {name!r} already exists")
    campaign = root / name
    campaign.mkdir()
    for folder in (*DEFAULT_TRACKS, *RESERVED):
        (campaign / folder).mkdir()
    _save_order(campaign, list(DEFAULT_TRACKS))
    return name


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


def _retarget(target: str, moves: list[tuple[Parts, Parts]]) -> str | None:
    """The new spelling of ``target`` if it pointed at a moved note, else None.

    A link names a note by its name (``Ismark``) or by a path suffix of any
    length (``NPCs/Ismark``, ``Curse of Strahd/NPCs/Ismark`` — Obsidian
    writes paths relative to wherever the vault is rooted). The rewrite keeps
    the link's shape: a name stays a name, an n-part path stays n parts.
    """
    stripped = target.strip()
    has_ext = stripped.lower().endswith(".md")
    bare = stripped[:-3] if has_ext else stripped
    parts = tuple(p for p in bare.split("/") if p)
    if not parts:
        return None
    n = len(parts)
    for old, new in moves:
        if n <= len(old):
            if _fold(parts) != _fold(old[-n:]):
                continue
            rewritten = new[-n:] if n <= len(new) else new
        else:
            if _fold(parts[-len(old):]) != _fold(old):
                continue
            rewritten = parts[: n - len(old)] + new
        result = "/".join(rewritten) + (".md" if has_ext else "")
        return None if result == stripped else result
    return None


def _inside_single_quotes(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    return text.count("'", line_start, pos) % 2 == 1


def rewrite_links(text: str, moves: list[tuple[Parts, Parts]]) -> str:
    """``text`` with every wikilink to a moved note pointing at its new place.

    ``moves`` pairs old and new locations as path parts without ``.md``,
    relative to the vault root. Everything outside a link's target —
    heading, alias, the ``!`` of an embed, the rest of the file — is kept
    byte for byte.
    """
    fm = _FRONTMATTER.match(text)
    fm_end = fm.end() if fm else 0

    def replace(m: re.Match) -> str:
        target, rest = _split_link(m.group(1))
        new = _retarget(target, moves)
        if new is None:
            return m.group(0)
        # A single-quoted YAML scalar escapes ' by doubling it.
        if "'" in new and m.start() < fm_end and _inside_single_quotes(text, m.start()):
            new = new.replace("'", "''")
        return f"[[{new}{rest}]]"

    return _WIKILINK.sub(replace, text)


def _rewrite_campaign(campaign: Path, moves: list[tuple[Parts, Parts]]) -> list[str]:
    """Apply ``moves`` to every note in ``campaign``; the paths it changed."""
    changed = []
    for path in _walk_notes(campaign):
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = rewrite_links(text, moves)
        if new != text:
            atomic_write(path, new.encode("utf-8"))
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
    return _rel(campaign, dst), _rewrite_campaign(campaign, moves)


def move_note(campaign: Path, rel: str, folder: str) -> tuple[str, list[str]]:
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
    moves = _relocate(campaign, campaign / name, campaign / new_name)
    _save_order(campaign, order)
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
