"""G. The one-SQLite-file index (plan §3.2 G, §3.3).

Replaces ChromaDB + parents.sqlite3 + 4 JSON side-stores with a single SQLite
file (via apsw, so loadable extensions work): documents / sections / chunks /
units + vectors (sqlite-vec binary for KNN + f32 for rescore — the vector-spike
winner) + unit_fts (FTS5 lexical). `commit()` is one transaction per document
with content-hash change detection and a pipeline_version (the R5 fix). Search
lives in query/ (Phase 3); this is the write path. No import from sidecar/.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import apsw
import numpy as np
import sqlite_vec

_VOCAB_TERM = re.compile(r"[a-z0-9]+")

from domain.models import SCHEMA_VERSION, Document

DIM = 1024  # bge-m3 (embed_parity spike)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, path TEXT, title TEXT, page_count INTEGER,
  content_hash TEXT, pipeline_version INTEGER, needs_ocr INTEGER, lang TEXT,
  toc TEXT, page_labels TEXT);
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
CREATE TABLE IF NOT EXISTS vocab(term TEXT, lang TEXT, freq INTEGER, PRIMARY KEY(term, lang));
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
               pipeline_version: int = SCHEMA_VERSION, fts_texts=None) -> None:
        """One transaction: replace the document's rows and re-insert everything.
        `vectors` is (len(doc.units), DIM), row-aligned to doc.units. `fts_texts`
        (also row-aligned) is what the FTS/BM25 index stores — pass the heading-
        prepended embed inputs to make the lexical side heading-aware; defaults to
        the raw unit text."""
        assert len(vectors) == len(doc.units), "one vector per unit"
        assert fts_texts is None or len(fts_texts) == len(doc.units), "one fts text per unit"
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
                "INSERT INTO documents(id,path,title,page_count,content_hash,pipeline_version,"
                "needs_ocr,lang,toc,page_labels) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (doc.id, doc.path, doc.title, doc.page_count, content_hash, pipeline_version,
                 int(doc.needs_ocr), doc.lang, json.dumps(doc.toc), json.dumps(doc.page_labels)),
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
            for i, (u, vec) in enumerate(zip(doc.units, vectors)):
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
                self.db.execute("INSERT INTO unit_fts(rowid,text) VALUES(?,?)",
                                (rid, fts_texts[i] if fts_texts is not None else u.text))

    # -- read-back --------------------------------------------------------

    def counts(self, doc_id: str) -> dict[str, int]:
        return {t: self.db.execute(f"SELECT COUNT(*) FROM {t} WHERE doc_id=?", (doc_id,)).fetchone()[0]
                for t in ("sections", "chunks", "units")}

    def pipeline_version(self, doc_id: str) -> int | None:
        row = self.db.execute("SELECT pipeline_version FROM documents WHERE id=?", (doc_id,)).fetchone()
        return row[0] if row else None

    def get_toc(self, doc_id: str) -> tuple[tuple[int, str, int], ...]:
        row = self.db.execute("SELECT toc FROM documents WHERE id=?", (doc_id,)).fetchone()
        return tuple(tuple(e) for e in json.loads(row[0])) if row and row[0] else ()

    def get_page_labels(self, doc_id: str) -> tuple[str, ...]:
        row = self.db.execute("SELECT page_labels FROM documents WHERE id=?", (doc_id,)).fetchone()
        return tuple(json.loads(row[0])) if row and row[0] else ()

    # -- vocab (persisted, incremental per-document deltas — §3.3; populated in Phase 3) --

    def add_vocab(self, counts) -> None:
        """Accumulate (term, lang, freq) deltas into the persisted vocab table."""
        self.db.executemany(
            "INSERT INTO vocab(term,lang,freq) VALUES(?,?,?) "
            "ON CONFLICT(term,lang) DO UPDATE SET freq=freq+excluded.freq",
            [(t, l, f) for t, l, f in counts],
        )

    def vocab_freq(self, term: str, lang: str) -> int:
        row = self.db.execute("SELECT freq FROM vocab WHERE term=? AND lang=?", (term, lang)).fetchone()
        return row[0] if row else 0

    def build_vocab(self, lang: str = "en") -> None:
        """Backfill the library vocab (term → frequency) from the indexed unit
        text — the dictionary spell-correction edit-distances against (rung 7).
        Idempotent: clears this lang and rebuilds. No re-index."""
        counts: Counter = Counter()
        for (text,) in self.db.execute("SELECT text FROM units"):
            counts.update(_VOCAB_TERM.findall(text.lower()))
        with self.db:
            self.db.execute("DELETE FROM vocab WHERE lang=?", (lang,))
            self.add_vocab((t, lang, n) for t, n in counts.items())

    def vocab_dict(self, lang: str = "en") -> dict[str, int]:
        """Whole vocab as an in-memory {term: freq} — one load, O(1) lookups for
        the corrector instead of a DB hit per edit candidate."""
        return {t: f for t, f in self.db.execute(
            "SELECT term, freq FROM vocab WHERE lang=?", (lang,))}

    def get_vector(self, unit_id: str) -> np.ndarray:
        row = self.db.execute(
            "SELECT v FROM unit_fvec JOIN units ON units.rowid=unit_fvec.rowid WHERE units.id=?",
            (unit_id,),
        ).fetchone()
        return np.frombuffer(row[0], np.float32)

    def search_fts(self, query: str, doc_id: str | None = None) -> list[str]:
        if doc_id is None:
            return [r[0] for r in self.db.execute(
                "SELECT units.id FROM unit_fts JOIN units ON units.rowid=unit_fts.rowid "
                "WHERE unit_fts MATCH ? ORDER BY rank", (query,))]
        return [r[0] for r in self.db.execute(
            "SELECT units.id FROM unit_fts JOIN units ON units.rowid=unit_fts.rowid "
            "WHERE unit_fts MATCH ? AND units.doc_id=? ORDER BY rank", (query, doc_id))]

    def search_dense(self, qvec, k: int = 25, prefilter: int = 200,
                     doc_id: str | None = None) -> list[tuple[str, float]]:
        """Dense KNN: binary-quantized hamming prefilter (the sqlite-vec vector-
        spike config — a raw f32 scan is ~800 MB/query) then full-precision cosine
        rescore. `doc_id` scopes the search to one document (source_filter). Returns
        (unit_id, cosine) descending; vectors are L2-normalized so dot == cosine."""
        q = np.asarray(qvec, np.float32)
        if doc_id is None:
            rows = self.db.execute(
                "SELECT rowid FROM unit_vec WHERE bvec MATCH vec_quantize_binary(?) AND k=? "
                "ORDER BY distance", (q.tobytes(), prefilter)).fetchall()
        else:
            rows = self.db.execute(
                "SELECT rowid FROM unit_vec WHERE bvec MATCH vec_quantize_binary(?) AND k=? "
                "AND doc_id=? ORDER BY distance", (q.tobytes(), prefilter, doc_id)).fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        ph = ",".join("?" * len(ids))
        scored = [
            (uid, float(q @ np.frombuffer(blob, np.float32)))
            for uid, blob in self.db.execute(
                f"SELECT units.id, unit_fvec.v FROM unit_fvec "
                f"JOIN units ON units.rowid=unit_fvec.rowid WHERE unit_fvec.rowid IN ({ph})", ids)
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def hydrate(self, unit_ids) -> dict[str, dict]:
        """Join units → chunks → sections → documents into result rows for payload
        assembly (query/). Missing section (content before the first heading) → ""."""
        ids = list(unit_ids)
        if not ids:
            return {}
        ph = ",".join("?" * len(ids))
        out: dict[str, dict] = {}
        for uid, text, ps, pe, doc_id, path, title, heading, chunk_id, section_id, chunk_text in self.db.execute(
            f"SELECT u.id, u.text, u.page_start, u.page_end, d.id, d.path, d.title, "
            f"       COALESCE(s.title, ''), c.id, c.section_id, c.text "
            f"FROM units u JOIN chunks c ON c.id=u.chunk_id "
            f"JOIN documents d ON d.id=u.doc_id "
            f"LEFT JOIN sections s ON s.id=c.section_id "
            f"WHERE u.id IN ({ph})", ids
        ):
            out[uid] = {
                "text": text, "section_heading": heading, "doc_id": doc_id,
                "filename": path.rsplit("/", 1)[-1], "source": title,
                "page_start": ps, "page_end": pe,
                "chunk_id": chunk_id, "section_id": section_id, "chunk_text": chunk_text,
            }
        return out

    def close(self) -> None:
        self.db.close()
