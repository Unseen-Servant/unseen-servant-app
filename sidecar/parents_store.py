"""SQLite-backed parent-document store.

Companion to ChromaDB's vector index for parent-document retrieval
(chunk_granularity_spike, issue #146). ChromaDB stores small embed
units (with parent_id in metadata); this store maps parent_id →
ParentDoc text + provenance metadata, fetched at search time after
deduping by parent_id.

One row per parent. Indexed by source so re-indexing or deleting a
PDF can clear its parents in a single statement.

The same file also holds ``unit_fts``, the persisted FTS5 index over the
embed units (roadmap 1.6, S5). Its rows carry exactly the text the
embedder sees plus the scope columns ``/api/search`` filters on, so a
hybrid search is a single indexed query instead of a full Chroma scan.
Written in the same swap as the Chroma upsert and kept aligned by every
delete / rename / clear path.
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
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(
    chunk_id UNINDEXED, ordinal UNINDEXED, source UNINDEXED, filename UNINDEXED,
    game_system UNINDEXED, parent_id UNINDEXED, text,
    tokenize='porter unicode61'
);
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
    """Wipe every parent and FTS row. Companion to delete-index
    drop-the-collection."""
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("DELETE FROM parents")
        conn.execute("DELETE FROM unit_fts")


# ---------------------------------------------------------------------------
# unit_fts — persisted lexical index over the embed units
# ---------------------------------------------------------------------------

# A row is (chunk_id, ordinal, filename, game_system, parent_id, text); the
# source is passed separately because every write is scoped to one source.
FtsRow = tuple[str, int, str, str, str, str]

# The metadata fields /api/search scopes on. Anything else raises rather
# than silently widening the lexical side of a scoped hybrid search.
_FTS_FIELDS = {"source", "filename", "game_system"}


def where_to_sql(where: dict | None) -> tuple[str, list]:
    """Translate a ChromaDB ``where`` clause into SQL over unit_fts.

    Supports exactly the shapes /api/search builds: field equality,
    ``{"$in": [...]}``, ``$and``, and ``$or``, over `_FTS_FIELDS`.
    Returns (sql_fragment, params); ``("", [])`` when unscoped.
    """
    if not where:
        return "", []
    if "$and" in where or "$or" in where:
        op = "$and" if "$and" in where else "$or"
        parts, params = [], []
        for w in where[op]:
            s, p = where_to_sql(w)
            parts.append(f"({s})")
            params += p
        return (" AND " if op == "$and" else " OR ").join(parts), params
    ((field, cond),) = where.items()
    if field not in _FTS_FIELDS:
        raise ValueError(f"unsupported where field for FTS scope: {field}")
    if isinstance(cond, dict):
        if set(cond) == {"$in"}:
            vals = list(cond["$in"])
            return f"{field} IN ({','.join('?' * len(vals))})", vals
        raise ValueError(f"unsupported where operator: {cond}")
    return f"{field} = ?", [cond]


def upsert_units_fts(data_dir: Path, source: str, rows: list[FtsRow]) -> None:
    """Replace all FTS rows for a source with the given list.

    Delete-by-source + insert, like `upsert_parents`, so a re-index under
    a fresh chunk-id prefix leaves no orphan rows behind.
    """
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("DELETE FROM unit_fts WHERE source = ?", (source,))
        conn.executemany(
            "INSERT INTO unit_fts (chunk_id, ordinal, source, filename, "
            "game_system, parent_id, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (cid, ordinal, source, fn, gs, pid, text)
                for cid, ordinal, fn, gs, pid, text in rows
            ],
        )


def search_units_fts(
    data_dir: Path, match: str, k: int, where: dict | None
) -> list[str]:
    """Top-k chunk ids for an FTS5 MATCH expression, best BM25 first.

    `where` mirrors the dense query's scope; it applies as SQL over the
    UNINDEXED metadata columns alongside the MATCH.
    """
    if not data_dir or not match:
        return []
    scope_sql, params = where_to_sql(where)
    sql = "SELECT chunk_id FROM unit_fts WHERE unit_fts MATCH ?"
    if scope_sql:
        sql += f" AND ({scope_sql})"
    sql += " ORDER BY rank LIMIT ?"
    with _txn(data_dir) as conn:
        return [r[0] for r in conn.execute(sql, [match, *params, k]).fetchall()]


def delete_units_fts_for_source(data_dir: Path, source: str) -> int:
    """Drop all FTS rows for a source path. Returns number deleted."""
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        return conn.execute(
            "DELETE FROM unit_fts WHERE source = ?", (source,)
        ).rowcount


def count_units_fts(data_dir: Path, source: str | None = None) -> int:
    """FTS rows, total or for one source. For diagnostics and tests."""
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        if source is None:
            return conn.execute("SELECT COUNT(*) FROM unit_fts").fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM unit_fts WHERE source = ?", (source,)
        ).fetchone()[0]


def update_units_fts_game_system(
    data_dir: Path, source: str, game_system: str
) -> int:
    """Retag a source's FTS rows. Returns number of rows updated.

    The game-system endpoints rewrite ``game_system`` on every Chroma
    chunk of a file; the FTS copy of that scope column has to move with
    it or a scoped hybrid search would still filter on the old tag.
    """
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        return conn.execute(
            "UPDATE unit_fts SET game_system = ? WHERE source = ?",
            (game_system, source),
        ).rowcount


def rename_source(
    data_dir: Path,
    old_source: str,
    new_source: str,
    new_filename: str,
    new_prefix: str,
) -> None:
    """Move parents and FTS rows to a renamed file. Chunk ids are rebuilt
    from the stored ordinal so they agree with the ids the rename flow
    writes to Chroma (``f"{prefix}_{ordinal}"``)."""
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute(
            "UPDATE parents SET source = ? WHERE source = ?",
            (new_source, old_source),
        )
        conn.execute(
            "UPDATE unit_fts SET source = ?, filename = ?, "
            "chunk_id = ? || '_' || ordinal WHERE source = ?",
            (new_source, new_filename, new_prefix, old_source),
        )
