"""G. The one-SQLite-file index (plan §3.2 G, §3.3).

Replaces ChromaDB + parents.sqlite3 + 4 JSON side-stores with a single SQLite
file (via apsw, so loadable extensions work): documents / sections / chunks /
units + vectors (sqlite-vec binary for KNN + f32 for rescore — the vector-spike
winner) + unit_fts (FTS5 lexical). `commit()` is one transaction per document
with content-hash change detection and a pipeline_version (the R5 fix). Search
lives in query/ (Phase 3); this is the write path. No import from sidecar/.
"""
from __future__ import annotations

import apsw
import numpy as np
import sqlite_vec

from domain.models import SCHEMA_VERSION, Document

DIM = 1024  # bge-m3 (embed_parity spike)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, path TEXT, title TEXT, page_count INTEGER,
  content_hash TEXT, pipeline_version INTEGER, needs_ocr INTEGER, lang TEXT);
CREATE TABLE IF NOT EXISTS sections(
  id TEXT PRIMARY KEY, doc_id TEXT, parent_id TEXT, level INTEGER,
  title TEXT, page_start INTEGER, page_end INTEGER);
CREATE TABLE IF NOT EXISTS chunks(
  id TEXT PRIMARY KEY, doc_id TEXT, section_id TEXT, ordinal INTEGER,
  kind TEXT, text TEXT, page_start INTEGER, page_end INTEGER);
CREATE TABLE IF NOT EXISTS units(
  rowid INTEGER PRIMARY KEY, id TEXT UNIQUE, chunk_id TEXT, doc_id TEXT,
  text TEXT, kind TEXT, page_start INTEGER, page_end INTEGER, lang TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS unit_vec USING vec0(doc_id text, bvec bit[{DIM}]);
CREATE TABLE IF NOT EXISTS unit_fvec(rowid INTEGER PRIMARY KEY, v BLOB);
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(text);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


class Store:
    def __init__(self, conn: apsw.Connection):
        self.db = conn

    @classmethod
    def open(cls, path: str) -> "Store":
        conn = apsw.Connection(path)
        conn.enableloadextension(True)
        conn.loadextension(sqlite_vec.loadable_path())
        conn.enableloadextension(False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                     (str(SCHEMA_VERSION),))
        return cls(conn)

    # -- write path -------------------------------------------------------

    def is_unchanged(self, doc_id: str, content_hash: str) -> bool:
        row = self.db.execute("SELECT content_hash FROM documents WHERE id=?", (doc_id,)).fetchone()
        return bool(row) and row[0] == content_hash

    def commit(self, doc: Document, vectors: np.ndarray, content_hash: str,
               pipeline_version: int = SCHEMA_VERSION) -> None:
        """One transaction: replace the document's rows and re-insert everything.
        `vectors` is (len(doc.units), DIM), row-aligned to doc.units."""
        assert len(vectors) == len(doc.units), "one vector per unit"
        with self.db:  # apsw transaction
            for (rid,) in self.db.execute("SELECT rowid FROM units WHERE doc_id=?", (doc.id,)).fetchall():
                self.db.execute("DELETE FROM unit_vec WHERE rowid=?", (rid,))
                self.db.execute("DELETE FROM unit_fvec WHERE rowid=?", (rid,))
                self.db.execute("DELETE FROM unit_fts WHERE rowid=?", (rid,))
            self.db.execute("DELETE FROM units WHERE doc_id=?", (doc.id,))
            self.db.execute("DELETE FROM chunks WHERE doc_id=?", (doc.id,))
            self.db.execute("DELETE FROM sections WHERE doc_id=?", (doc.id,))
            self.db.execute("DELETE FROM documents WHERE id=?", (doc.id,))

            self.db.execute(
                "INSERT INTO documents(id,path,title,page_count,content_hash,pipeline_version,needs_ocr,lang)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (doc.id, doc.path, doc.title, doc.page_count, content_hash, pipeline_version,
                 int(doc.needs_ocr), doc.lang),
            )
            for s in doc.sections:
                self.db.execute(
                    "INSERT INTO sections(id,doc_id,parent_id,level,title,page_start,page_end)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (s.id, doc.id, s.parent_id, s.level, s.title, s.page_start, s.page_end),
                )
            for c in doc.chunks:
                self.db.execute(
                    "INSERT INTO chunks(id,doc_id,section_id,ordinal,kind,text,page_start,page_end)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (c.id, doc.id, c.section_id, c.ordinal, c.kind.value, c.text, c.page_start, c.page_end),
                )
            for u, vec in zip(doc.units, vectors):
                blob = np.asarray(vec, np.float32).tobytes()
                self.db.execute(
                    "INSERT INTO units(id,chunk_id,doc_id,text,kind,page_start,page_end,lang)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (u.id, u.chunk_id, doc.id, u.text, u.kind.value, u.page_start, u.page_end, u.lang),
                )
                rid = self.db.last_insert_rowid()
                self.db.execute("INSERT INTO unit_vec(rowid,doc_id,bvec) VALUES(?,?,vec_quantize_binary(?))",
                                (rid, doc.id, blob))
                self.db.execute("INSERT INTO unit_fvec(rowid,v) VALUES(?,?)", (rid, blob))
                self.db.execute("INSERT INTO unit_fts(rowid,text) VALUES(?,?)", (rid, u.text))

    # -- read-back --------------------------------------------------------

    def counts(self, doc_id: str) -> dict[str, int]:
        return {t: self.db.execute(f"SELECT COUNT(*) FROM {t} WHERE doc_id=?", (doc_id,)).fetchone()[0]
                for t in ("sections", "chunks", "units")}

    def pipeline_version(self, doc_id: str) -> int | None:
        row = self.db.execute("SELECT pipeline_version FROM documents WHERE id=?", (doc_id,)).fetchone()
        return row[0] if row else None

    def get_vector(self, unit_id: str) -> np.ndarray:
        row = self.db.execute(
            "SELECT v FROM unit_fvec JOIN units ON units.rowid=unit_fvec.rowid WHERE units.id=?",
            (unit_id,),
        ).fetchone()
        return np.frombuffer(row[0], np.float32)

    def search_fts(self, query: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT units.id FROM unit_fts JOIN units ON units.rowid=unit_fts.rowid "
            "WHERE unit_fts MATCH ? ORDER BY rank", (query,))]

    def close(self) -> None:
        self.db.close()
