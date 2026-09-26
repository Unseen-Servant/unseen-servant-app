"""One SQLite file for the whole library: documents, parents, units, vectors, FTS.

Design: ``docs/retrieval/2026-09-26-library-store-design.md``. A book's
identity (path, filename, game systems) lives in one ``documents`` row;
units, parents, vectors and FTS rows reference it by id. So a rename or
retag touches one row, and every write that changes a book is a single
transaction — nothing can be left half-written for a GC to clean up.

Vectors live in a sqlite-vec ``vec0`` table sharded by ``document_id``
(a partition key), so a search scoped to some books reads only their
vectors. Deletes reclaim space through ``auto_vacuum = INCREMENTAL``.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath

import numpy as np
import sqlite_vec

from .granularity import EmbedUnit, ParentDoc

LIBRARY_FILENAME = "library.sqlite3"
SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    game_system TEXT NOT NULL DEFAULT 'unknown'
);
CREATE TABLE IF NOT EXISTS document_systems (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    system      TEXT NOT NULL,
    PRIMARY KEY (document_id, system)
);
CREATE TABLE IF NOT EXISTS parents (
    parent_id       TEXT PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    section_heading TEXT,
    page_start      INTEGER NOT NULL,
    page_end        INTEGER NOT NULL,
    chunk_type      TEXT NOT NULL,
    section_id      TEXT,
    section_path    TEXT
);
CREATE INDEX IF NOT EXISTS idx_parents_doc_section ON parents(document_id, section_path);
CREATE INDEX IF NOT EXISTS idx_parents_section_id ON parents(section_id);
CREATE TABLE IF NOT EXISTS units (
    id               INTEGER PRIMARY KEY,
    document_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal          INTEGER NOT NULL,
    parent_id        TEXT NOT NULL,
    text             TEXT NOT NULL,
    chunk_type       TEXT NOT NULL,
    section_heading  TEXT,
    page_start       INTEGER NOT NULL,
    page_end         INTEGER NOT NULL,
    page_label_start TEXT NOT NULL DEFAULT '',
    page_label_end   TEXT NOT NULL DEFAULT '',
    section_id       TEXT,
    section_path     TEXT,
    UNIQUE (document_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(
    text, tokenize='porter unicode61'
);
"""

# vec0 fixes the dimension at creation, so this table is (re)built on its
# own when the embedding model changes.
_VEC_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS unit_vec USING vec0(
    unit_id     INTEGER PRIMARY KEY,
    document_id INTEGER PARTITION KEY,
    embedding   float[{dim}] distance_metric=cosine
)
"""


@dataclass(frozen=True)
class StoredUnit:
    """A unit as search reads it back, joined with its document."""
    id: int
    text: str
    source: str
    filename: str
    game_system: str
    ordinal: int
    parent_id: str
    chunk_type: str
    section_heading: str | None
    page_start: int
    page_end: int
    page_label_start: str
    page_label_end: str
    section_id: str | None
    section_path: str | None

    @property
    def metadata(self) -> dict:
        """The metadata dict the search pipeline has always read per hit."""
        return {
            "source": self.source,
            "filename": self.filename,
            "chunk": self.ordinal,
            "game_system": self.game_system,
            "chunk_type": self.chunk_type,
            "section_heading": self.section_heading or "",
            "page_start": self.page_start,
            "page_end": self.page_end,
            "page_label_start": self.page_label_start,
            "page_label_end": self.page_label_end,
            "parent_id": self.parent_id,
            "section_id": self.section_id or "",
            "section_path": self.section_path or "",
        }


@dataclass(frozen=True)
class DocumentStats:
    path: str
    filename: str
    game_system: str
    systems: tuple[str, ...]
    units: int
    pages: int  # highest page any unit reaches


class LibraryStore:
    """The library's single store. Thread-safe: one connection per thread.

    Writers must still be serialized by the caller (the sidecar's sync
    lock); ``BEGIN IMMEDIATE`` plus ``busy_timeout`` only keeps a stray
    concurrent writer waiting instead of failing. WAL lets searches read
    while an index write is in flight.
    """

    def __init__(self, path: Path, embedding_model: str, dim: int) -> None:
        self.path = Path(path)
        self.embedding_model = embedding_model
        self.dim = dim
        self._local = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        # True when open() found vectors from another model and cleared
        # the store; the caller flags every file for reindex.
        self.was_reset = False

    @classmethod
    def open(cls, path: Path, embedding_model: str, dim: int) -> "LibraryStore":
        store = cls(path, embedding_model, dim)
        store._init_schema()
        return store

    # -- connections -------------------------------------------------------

    def conn(self) -> sqlite3.Connection:
        """This thread's connection, for read-only helpers outside the class
        (section assembly in ``parents_store``). Writes go through methods."""
        return self._conn()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.path), isolation_level=None, check_same_thread=False
            )
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.execute("PRAGMA busy_timeout = 10000")
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    def _reclaim(self) -> None:
        # Each step of the pragma frees one page; fetchall() runs it out.
        self._conn().execute("PRAGMA incremental_vacuum").fetchall()

    def close(self) -> None:
        with self._conns_lock:
            for conn in self._conns:
                conn.close()
            self._conns.clear()
        self._local = threading.local()

    def _init_schema(self) -> None:
        conn = self._conn()
        fresh = conn.execute(
            "SELECT count(*) FROM sqlite_master"
        ).fetchone()[0] == 0
        if fresh:
            # Only takes effect before the first table exists.
            conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        expected = {
            "schema_version": SCHEMA_VERSION,
            "embedding_model": self.embedding_model,
            "embedding_dim": str(self.dim),
        }
        if meta and meta != expected:
            self._drop_content()
            conn.execute("DROP TABLE IF EXISTS unit_vec")
            self.was_reset = True
        conn.execute(_VEC_SCHEMA.format(dim=self.dim))
        with self._write() as w:
            w.executemany(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                expected.items(),
            )

    def _drop_content(self) -> None:
        with self._write() as conn:
            for table in ("unit_vec", "unit_fts", "units", "parents",
                          "document_systems", "documents"):
                conn.execute(f"DELETE FROM {table}")

    # -- writes ------------------------------------------------------------

    def replace_document(
        self,
        path: str,
        game_system: str,
        systems: Sequence[str],
        units: Sequence[EmbedUnit],
        embed_texts: Sequence[str],
        vectors: Sequence[Sequence[float]] | np.ndarray,
        parents: Sequence[ParentDoc],
        page_labels: dict[int, str] | None = None,
    ) -> int:
        """Index (or reindex) one book in a single transaction.

        ``embed_texts`` is what the embedder saw for each unit (heading
        prepended); it feeds FTS, which BM25 and the spell vocabulary were
        tuned on. Any failure leaves the previous index of the book intact.
        """
        vecs = np.asarray(vectors, dtype=np.float32)
        if not (len(units) == len(embed_texts) == len(vecs)):
            raise ValueError("units, embed_texts and vectors differ in length")
        if len(units) and vecs.shape[1] != self.dim:
            raise ValueError(
                f"vector dimension {vecs.shape[1]} != store dimension {self.dim}"
            )
        labels = page_labels or {}
        with self._write() as conn:
            doc_id = conn.execute(
                "INSERT INTO documents (path, filename, game_system) "
                "VALUES (?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
                "filename = excluded.filename, game_system = excluded.game_system "
                "RETURNING id",
                (path, PurePath(path).name, game_system),
            ).fetchone()[0]
            self._delete_document_rows(conn, doc_id, keep_document=True)
            self._write_systems(conn, doc_id, game_system, systems)
            conn.executemany(
                "INSERT INTO parents (parent_id, document_id, text, "
                "section_heading, page_start, page_end, chunk_type, "
                "section_id, section_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (p.parent_id, doc_id, p.text, p.section_heading,
                     p.page_start, p.page_end, p.chunk_type,
                     p.section_id, p.section_path)
                    for p in parents
                ],
            )
            conn.executemany(
                "INSERT INTO units (document_id, ordinal, parent_id, text, "
                "chunk_type, section_heading, page_start, page_end, "
                "page_label_start, page_label_end, section_id, section_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (doc_id, u.ordinal, u.parent_id, u.text, u.chunk_type,
                     u.section_heading, u.page_start, u.page_end,
                     labels.get(u.page_start, ""), labels.get(u.page_end, ""),
                     u.section_id, u.section_path)
                    for u in units
                ],
            )
            ids = dict(conn.execute(
                "SELECT ordinal, id FROM units WHERE document_id = ?", (doc_id,)
            ))
            unit_ids = [ids[u.ordinal] for u in units]
            conn.executemany(
                "INSERT INTO unit_vec (unit_id, document_id, embedding) "
                "VALUES (?, ?, ?)",
                [(uid, doc_id, v.tobytes()) for uid, v in zip(unit_ids, vecs)],
            )
            conn.executemany(
                "INSERT INTO unit_fts (rowid, text) VALUES (?, ?)",
                zip(unit_ids, embed_texts),
            )
        self._reclaim()
        return doc_id

    def rename_document(self, old_path: str, new_path: str) -> bool:
        """Move a book to a new path. False when ``old_path`` isn't indexed."""
        with self._write() as conn:
            cur = conn.execute(
                "UPDATE documents SET path = ?, filename = ? WHERE path = ?",
                (new_path, PurePath(new_path).name, old_path),
            )
        return cur.rowcount > 0

    def rename_folder(self, old_prefix: str, new_prefix: str) -> int:
        """Re-root every book under ``old_prefix``. Returns books moved.

        Prefixes include the trailing separator, so ``/a/b/`` never
        matches ``/a/bc/x.pdf``. Filenames don't change.
        """
        with self._write() as conn:
            cur = conn.execute(
                "UPDATE documents SET path = ? || substr(path, ?) "
                "WHERE substr(path, 1, ?) = ?",
                (new_prefix, len(old_prefix) + 1, len(old_prefix), old_prefix),
            )
        return cur.rowcount

    def set_systems(self, path: str, primary: str, systems: Sequence[str]) -> bool:
        """Retag a book. False when ``path`` isn't indexed."""
        with self._write() as conn:
            row = conn.execute(
                "UPDATE documents SET game_system = ? WHERE path = ? RETURNING id",
                (primary, path),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "DELETE FROM document_systems WHERE document_id = ?", (row[0],)
            )
            self._write_systems(conn, row[0], primary, systems)
        return True

    def delete_document(self, path: str) -> int:
        """Remove a book and reclaim its space. Returns the units removed,
        0 when the book isn't indexed."""
        with self._write() as conn:
            row = conn.execute(
                "SELECT d.id, (SELECT count(*) FROM units u "
                "WHERE u.document_id = d.id) FROM documents d WHERE d.path = ?",
                (path,),
            ).fetchone()
            if row is None:
                return 0
            self._delete_document_rows(conn, row[0], keep_document=False)
        self._reclaim()
        return row[1]

    def clear(self) -> None:
        """Empty the library and shrink the file."""
        self._drop_content()
        self._conn().execute("VACUUM")

    @staticmethod
    def _write_systems(conn, doc_id: int, primary: str, systems) -> None:
        tags = {s for s in (*systems, primary) if s and s != "unknown"}
        conn.executemany(
            "INSERT INTO document_systems (document_id, system) VALUES (?, ?)",
            [(doc_id, s) for s in sorted(tags)],
        )

    @staticmethod
    def _delete_document_rows(conn, doc_id: int, keep_document: bool) -> None:
        # Virtual tables don't take part in foreign-key cascades.
        conn.execute("DELETE FROM unit_vec WHERE document_id = ?", (doc_id,))
        conn.execute(
            "DELETE FROM unit_fts WHERE rowid IN "
            "(SELECT id FROM units WHERE document_id = ?)", (doc_id,)
        )
        if keep_document:
            for table in ("units", "parents", "document_systems"):
                conn.execute(
                    f"DELETE FROM {table} WHERE document_id = ?", (doc_id,)
                )
        else:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # -- reads -------------------------------------------------------------

    def scope_document_ids(
        self,
        *,
        paths: Sequence[str] | None = None,
        filename: str | None = None,
        systems: Sequence[str] | None = None,
    ) -> list[int] | None:
        """Books a search may see. ``None`` = no scope (whole library).

        Filters combine with AND. ``systems`` matches a book whose primary
        tag or any secondary tag is listed; "unknown" matches untagged
        books through the primary column.
        """
        if paths is None and filename is None and systems is None:
            return None
        clauses, params = [], []
        if paths is not None:
            clauses.append(f"path IN ({_marks(paths)})")
            params += list(paths)
        if filename is not None:
            clauses.append("filename = ?")
            params.append(filename)
        if systems is not None:
            marks = _marks(systems)
            clauses.append(
                f"(game_system IN ({marks}) OR id IN (SELECT document_id "
                f"FROM document_systems WHERE system IN ({marks})))"
            )
            params += [*systems, *systems]
        sql = "SELECT id FROM documents WHERE " + " AND ".join(clauses)
        return [r[0] for r in self._conn().execute(sql, params)]

    def knn(
        self,
        vector: Sequence[float] | np.ndarray,
        k: int,
        doc_ids: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        """The k nearest units as (unit_id, cosine distance), nearest first.

        A partition-key ``IN`` returns k rows *per book*, so the per-book
        results are merged down to the global k here.
        """
        if doc_ids is not None and not doc_ids:
            return []
        q = np.asarray(vector, dtype=np.float32).tobytes()
        sql = ("SELECT unit_id, distance FROM unit_vec "
               "WHERE embedding MATCH ? AND k = ?")
        params: list = [q, k]
        if doc_ids is not None:
            sql += f" AND document_id IN ({_marks(doc_ids)})"
            params += list(doc_ids)
        rows = self._conn().execute(sql, params).fetchall()
        rows.sort(key=lambda r: r[1])
        return rows[:k]

    def fts(
        self, match: str, k: int, doc_ids: Sequence[int] | None = None
    ) -> list[int]:
        """Top-k unit ids for an FTS5 MATCH expression, best BM25 first."""
        if not match or (doc_ids is not None and not doc_ids):
            return []
        sql = ("SELECT unit_fts.rowid FROM unit_fts "
               "JOIN units ON units.id = unit_fts.rowid "
               "WHERE unit_fts MATCH ?")
        params: list = [match]
        if doc_ids is not None:
            sql += f" AND units.document_id IN ({_marks(doc_ids)})"
            params += list(doc_ids)
        sql += " ORDER BY rank LIMIT ?"
        params.append(k)
        return [r[0] for r in self._conn().execute(sql, params)]

    def hydrate(self, unit_ids: Sequence[int]) -> dict[int, StoredUnit]:
        """Units by id, joined with their book. Missing ids are absent."""
        if not unit_ids:
            return {}
        rows = self._conn().execute(
            "SELECT u.id, u.text, d.path, d.filename, d.game_system, "
            "u.ordinal, u.parent_id, u.chunk_type, u.section_heading, "
            "u.page_start, u.page_end, u.page_label_start, u.page_label_end, "
            "u.section_id, u.section_path "
            f"FROM units u JOIN documents d ON d.id = u.document_id "
            f"WHERE u.id IN ({_marks(unit_ids)})",
            list(unit_ids),
        )
        return {r[0]: StoredUnit(*r) for r in rows}

    def documents(self) -> list[DocumentStats]:
        """Every indexed book with its tags and unit count, by path."""
        conn = self._conn()
        systems: dict[int, list[str]] = {}
        for doc_id, system in conn.execute(
            "SELECT document_id, system FROM document_systems ORDER BY system"
        ):
            systems.setdefault(doc_id, []).append(system)
        return [
            DocumentStats(path, filename, game_system,
                          tuple(systems.get(doc_id, ())), units, pages)
            for doc_id, path, filename, game_system, units, pages in conn.execute(
                "SELECT d.id, d.path, d.filename, d.game_system, "
                "count(u.id), coalesce(max(u.page_end), 0) "
                "FROM documents d LEFT JOIN units u ON u.document_id = d.id "
                "GROUP BY d.id ORDER BY d.path"
            )
        ]

    def count_units(self) -> int:
        return self._conn().execute("SELECT count(*) FROM units").fetchone()[0]

    def document_text(self, path: str) -> str | None:
        """A book's unit texts in reading order, or None when not indexed."""
        conn = self._conn()
        row = conn.execute(
            "SELECT id FROM documents WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return None
        return "\n".join(t for (t,) in conn.execute(
            "SELECT text FROM units WHERE document_id = ? ORDER BY ordinal",
            (row[0],),
        ))

    def fts_texts(self) -> Iterator[str]:
        """Every unit's embed text — the spell corrector's vocabulary source."""
        for (text,) in self._conn().execute("SELECT text FROM unit_fts"):
            yield text

    def count_phrases(
        self, phrases: Sequence[tuple[str, ...]]
    ) -> dict[tuple[str, ...], int]:
        """Units containing each phrase (adjacent tokens, porter-stemmed).

        Tokens are quoted into one FTS5 phrase, so operators in them are
        literal.
        """
        conn = self._conn()
        return {
            p: conn.execute(
                "SELECT count(*) FROM unit_fts WHERE unit_fts MATCH ?",
                ['"' + " ".join(t.replace('"', "") for t in p) + '"'],
            ).fetchone()[0]
            for p in phrases
        }


def _marks(values: Sequence) -> str:
    return ",".join("?" * len(values))
