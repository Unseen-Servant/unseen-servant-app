"""SQLite-backed parent-document store.

Companion to ChromaDB's vector index for parent-document retrieval
(chunk_granularity_spike, issue #146). ChromaDB stores small embed
units (with parent_id in metadata); this store maps parent_id →
ParentDoc text + provenance metadata, fetched at search time after
deduping by parent_id.

One row per parent. Indexed by source so re-indexing or deleting a
PDF can clear its parents in a single statement.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from granularity import ParentDoc


PARENTS_FILENAME = "parents.sqlite3"

# Max characters of sibling-parent text to stitch onto a search hit. A
# section that exceeded PARENT_HARD_CAP during indexing is split across
# multiple parents; this budget lets us stitch them back together at
# retrieval time. Sized to typically capture one full neighbor (most
# split sections produce a "big half + remainder" pair where the
# remainder is well under this cap).
SECTION_EXPANSION_MAX_EXTRA_CHARS = 4000


_SCHEMA = """
CREATE TABLE IF NOT EXISTS parents (
    parent_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    section_heading TEXT,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    chunk_type TEXT NOT NULL,
    section_id TEXT,
    section_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_parents_source ON parents(source);
"""

SCHEMA_COLUMNS = {"section_id": "TEXT", "section_path": "TEXT"}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a store was created (ALTER TABLE is
    idempotent here because we check PRAGMA first)."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(parents)")}
    for col, typ in SCHEMA_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE parents ADD COLUMN {col} {typ}")


def _connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(data_dir / PARENTS_FILENAME))
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


@contextmanager
def _txn(data_dir: Path):
    conn = _connect(data_dir)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_parents(
    data_dir: Path, source: str, parents: list[ParentDoc]
) -> None:
    """Replace all parents for a source with the given list.

    Two-step (delete-by-source + insert) so a re-index leaves no
    orphans even if parent_ids changed between runs.
    """
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("DELETE FROM parents WHERE source = ?", (source,))
        conn.executemany(
            """
            INSERT INTO parents
                (parent_id, source, text, section_heading,
                 page_start, page_end, chunk_type, section_id, section_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    p.parent_id, source, p.text, p.section_heading,
                    p.page_start, p.page_end, p.chunk_type,
                    p.section_id, p.section_path,
                )
                for p in parents
            ],
        )


def fetch_parents(
    data_dir: Path, parent_ids: list[str]
) -> dict[str, ParentDoc]:
    """Batch-fetch parents by id. Missing ids are simply absent in the
    returned dict — callers handle gracefully.
    """
    if not data_dir or not parent_ids:
        return {}
    placeholders = ",".join("?" * len(parent_ids))
    with _txn(data_dir) as conn:
        rows = conn.execute(
            f"""
            SELECT parent_id, source, text, section_heading,
                   page_start, page_end, chunk_type, section_id, section_path
            FROM parents WHERE parent_id IN ({placeholders})
            """,
            parent_ids,
        ).fetchall()
    return {
        row[0]: ParentDoc(
            parent_id=row[0],
            source_pdf=row[1],
            text=row[2],
            section_heading=row[3],
            page_start=row[4],
            page_end=row[5],
            chunk_type=row[6],
            section_id=row[7],
            section_path=row[8],
        )
        for row in rows
    }


def _same_section(r_sid, r_heading, sid, heading) -> bool:
    return r_sid == sid if (sid is not None and r_sid is not None) else r_heading == heading


def _extend_one(
    conn: sqlite3.Connection,
    parent_id: str,
    max_extra_chars: int,
) -> ParentDoc | None:
    """Fetch one parent and stitch contiguous sibling parents that share
    its source + section, capped at `max_extra_chars`.

    Adjacency uses SQLite rowid order. Within a single source, rowid
    order equals document order because upsert_parents does
    delete-then-insert in chunk order. Walks rowid neighbors outward;
    stops on the first neighbor in a different section (compared by
    section_id when both rows have one, else by section_heading — for
    legacy rows predating the section_id migration) or when adding the
    neighbor would exceed the budget.
    """
    target = conn.execute(
        """
        SELECT rowid, parent_id, source, text, section_heading,
               page_start, page_end, chunk_type, section_id, section_path
        FROM parents WHERE parent_id = ?
        """,
        (parent_id,),
    ).fetchone()
    if not target:
        return None
    target_rowid, pid, source, text, section, ps, pe, ctype, sid, spath = target

    parts = [text]
    page_start, page_end = ps, pe
    budget = max_extra_chars

    cursor = target_rowid
    while budget > 0:
        row = conn.execute(
            """
            SELECT rowid, text, section_heading, page_start, page_end, section_id
            FROM parents WHERE source = ? AND rowid < ?
            ORDER BY rowid DESC LIMIT 1
            """,
            (source, cursor),
        ).fetchone()
        if not row:
            break
        r_rowid, r_text, r_section, r_ps, r_pe, r_sid = row
        if not _same_section(r_sid, r_section, sid, section):
            break
        cost = len(r_text) + 2  # "\n\n" join
        if cost > budget:
            break
        parts.insert(0, r_text)
        page_start = min(page_start, r_ps)
        budget -= cost
        cursor = r_rowid

    cursor = target_rowid
    while budget > 0:
        row = conn.execute(
            """
            SELECT rowid, text, section_heading, page_start, page_end, section_id
            FROM parents WHERE source = ? AND rowid > ?
            ORDER BY rowid ASC LIMIT 1
            """,
            (source, cursor),
        ).fetchone()
        if not row:
            break
        r_rowid, r_text, r_section, r_ps, r_pe, r_sid = row
        if not _same_section(r_sid, r_section, sid, section):
            break
        cost = len(r_text) + 2
        if cost > budget:
            break
        parts.append(r_text)
        page_end = max(page_end, r_pe)
        budget -= cost
        cursor = r_rowid

    return ParentDoc(
        parent_id=pid,
        source_pdf=source,
        text="\n\n".join(parts),
        section_heading=section,
        page_start=page_start,
        page_end=page_end,
        chunk_type=ctype,
        section_id=sid,
        section_path=spath,
    )


def fetch_parents_extended(
    data_dir: Path,
    parent_ids: list[str],
    max_extra_chars: int = SECTION_EXPANSION_MAX_EXTRA_CHARS,
) -> dict[str, ParentDoc]:
    """Like `fetch_parents`, but stitches each parent with rowid-adjacent
    sibling parents that share the same source + section identity
    (section_id when both rows carry one, else section_heading).

    Section-aware result expansion: a section that exceeded
    PARENT_HARD_CAP at indexing time was split across multiple parents.
    Without stitching, a search hit on a middle slice loses surrounding
    context. With stitching, the returned text rounds out to the full
    section (or `max_extra_chars` worth, whichever is first).
    """
    if not data_dir or not parent_ids:
        return {}
    out: dict[str, ParentDoc] = {}
    with _txn(data_dir) as conn:
        for pid in parent_ids:
            doc = _extend_one(conn, pid, max_extra_chars)
            if doc is not None:
                out[pid] = doc
    return out


def delete_parents_for_source(data_dir: Path, source: str) -> int:
    """Drop all parents for a source path. Returns number deleted."""
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        cur = conn.execute("DELETE FROM parents WHERE source = ?", (source,))
        return cur.rowcount


def count_parents(data_dir: Path) -> int:
    """Total parents across all sources. For diagnostics."""
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        return conn.execute("SELECT COUNT(*) FROM parents").fetchone()[0]


def clear_all_parents(data_dir: Path) -> None:
    """Wipe every parent. Companion to delete-index drop-the-collection."""
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("DELETE FROM parents")
