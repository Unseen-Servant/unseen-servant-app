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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS parents (
    parent_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    section_heading TEXT,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    chunk_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parents_source ON parents(source);
"""


def _connect(data_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(data_dir / PARENTS_FILENAME))
    conn.executescript(_SCHEMA)
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
                 page_start, page_end, chunk_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    p.parent_id, source, p.text, p.section_heading,
                    p.page_start, p.page_end, p.chunk_type,
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
                   page_start, page_end, chunk_type
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
        )
        for row in rows
    }


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
