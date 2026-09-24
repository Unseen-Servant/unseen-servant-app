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
from dataclasses import dataclass
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
    # section_path only exists once _migrate has run (a legacy store predates
    # it), so this index is created here rather than inside _SCHEMA.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_parents_section ON parents(source, section_path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_parents_section_id ON parents(section_id)"
    )
    return conn


@contextmanager
def _txn(data_dir: Path):
    conn = _connect(data_dir)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Public alias: the search path holds one connection open across the
# dedupe loop (one section_root_for query per candidate).
open_store = _txn


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


# ---------------------------------------------------------------------------
# Section assembly by section_path prefix (roadmap 2.1)
# ---------------------------------------------------------------------------

# Max characters of an assembled section (root subtree, or a window grown
# outward from the matched parent when the subtree is bigger than this).
SECTION_CAP = 6000


@dataclass(frozen=True)
class SectionDoc:
    root_path: str
    section_id: str
    section_heading: str | None
    text: str
    page_start: int
    page_end: int
    source_pdf: str
    windowed: bool


def _prefix_range(path: str) -> tuple[str, str]:
    """Half-open key range selecting `path` and every descendant: ids are
    fixed-width, '/' (0x2F) sorts just below '0' (0x30)."""
    return path, path + "0"


def _subtree_stats(
    conn, source: str, path: str,
    cache: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Assembled size (text + the "\\n\\n" joins) and row count of a subtree.

    The SUM re-reads every row's text under the prefix, so the shallow
    candidates are the expensive ones. `cache`, keyed (source, prefix),
    memoises them for the caller's lifetime — one search asks for the same
    chapter once per candidate otherwise.
    """
    if cache is not None and (source, path) in cache:
        return cache[(source, path)]
    lo, hi = _prefix_range(path)
    row = conn.execute(
        "SELECT COALESCE(SUM(LENGTH(text)), 0), COUNT(*) FROM parents "
        "WHERE source = ? AND section_path >= ? AND section_path < ?",
        (source, lo, hi),
    ).fetchone()
    total, n = row
    stats = (total + 2 * max(0, n - 1), n)
    if cache is not None:
        cache[(source, path)] = stats
    return stats


def section_root_for(
    conn, source: str, section_path: str, cap: int = SECTION_CAP,
    cache: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> str | None:
    """Shallowest ancestor (or the leaf) whose whole subtree fits in `cap`.

    `None` when the source has no parent rows at all under the path's first
    segment — a Chroma index whose parents rows were cleared or never
    written. Without that guard an empty subtree measures 0, "fits" at
    depth 1, and every hit in the book collapses onto one section key.

    `cache` is passed straight to `_subtree_stats`; share one dict across
    the candidates of a single request.
    """
    ids = section_path.split("/")
    for depth in range(1, len(ids) + 1):
        candidate = "/".join(ids[:depth])
        size, rows = _subtree_stats(conn, source, candidate, cache)
        if depth == 1 and rows == 0:
            return None
        if size <= cap:
            return candidate
    return section_path


def _heading_at_depth(heading: str | None, depth: int) -> str | None:
    if not heading:
        return heading
    return " > ".join(heading.split(" > ")[:depth])


def assemble_section(conn, source: str, root_path: str, matched_parent_id: str,
                     cap: int = SECTION_CAP) -> SectionDoc | None:
    """Assemble the subtree rooted at `root_path`, in document order, or a
    window grown outward from `matched_parent_id` when the subtree exceeds
    `cap`. The matched parent is always included, so `text` can exceed
    `cap` when that single parent is larger than the cap.
    """
    lo, hi = _prefix_range(root_path)
    rows = conn.execute(
        "SELECT rowid, parent_id, text, section_heading, page_start, page_end "
        "FROM parents WHERE source = ? AND section_path >= ? AND section_path < ? "
        "ORDER BY rowid",
        (source, lo, hi),
    ).fetchall()
    if not rows:
        return None
    depth = root_path.count("/") + 1
    heading = _heading_at_depth(rows[0][3], depth)
    section_id = root_path.rsplit("/", 1)[-1]
    total = sum(len(r[2]) for r in rows) + 2 * (len(rows) - 1)
    if total <= cap:
        chosen = rows
        windowed = False
    else:
        idx = next((i for i, r in enumerate(rows) if r[1] == matched_parent_id), 0)
        lo_i = hi_i = idx
        size = len(rows[idx][2])
        while True:
            grew = False
            if lo_i > 0 and size + len(rows[lo_i - 1][2]) + 2 <= cap:
                lo_i -= 1; size += len(rows[lo_i][2]) + 2; grew = True
            if hi_i < len(rows) - 1 and size + len(rows[hi_i + 1][2]) + 2 <= cap:
                hi_i += 1; size += len(rows[hi_i][2]) + 2; grew = True
            if not grew:
                break
        chosen = rows[lo_i:hi_i + 1]
        windowed = True
    return SectionDoc(
        root_path=root_path, section_id=section_id, section_heading=heading,
        text="\n\n".join(r[2] for r in chosen),
        page_start=min(r[4] for r in chosen), page_end=max(r[5] for r in chosen),
        source_pdf=source, windowed=windowed,
    )


def fetch_section_by_id(data_dir: Path, section_id: str) -> SectionDoc | None:
    """Look up one section by its id and assemble it fresh.

    Unlike `fetch_sections`/`section_root_for`, this is not capped up to a
    shallower ancestor — the caller asked for exactly this section (e.g. the
    `section_id` a search result printed), so its own `section_path` is the
    assembly root. `None` when no row lies under that id, or a legacy row
    predating the section_id/section_path columns.

    The id is resolved as a path *segment*, not via the section_id column:
    a heading immediately followed by a sub-heading owns no chunk of its
    own, so no row carries its id — yet `section_root_for` prefers it as
    the shallowest fitting ancestor and search advertises it. Such a
    container is only ever found through its descendants' paths.
    """
    if not data_dir or not section_id:
        return None
    with _txn(data_dir) as conn:
        # The common case — the section owns a row — is an indexed lookup.
        row = conn.execute(
            "SELECT parent_id, source, section_path FROM parents "
            "WHERE section_id = ? ORDER BY rowid LIMIT 1",
            (section_id,),
        ).fetchone()
        if row and row[2]:
            parent_id, source, section_path = row
            return assemble_section(conn, source, section_path, parent_id)
        # Container root: find any descendant whose path contains the id as
        # a segment. LIKE is only a pre-filter (a section id contains '_',
        # LIKE's single-character wildcard), so every candidate is verified
        # in Python; the first by rowid is the section's own first row.
        rows = conn.execute(
            "SELECT parent_id, source, section_path FROM parents "
            "WHERE section_path LIKE '%' || ? || '%' ORDER BY rowid",
            (section_id,),
        ).fetchall()
        for parent_id, source, path in rows:
            if not path:
                continue
            segments = path.split("/")
            if section_id not in segments:
                continue
            root_path = "/".join(segments[: segments.index(section_id) + 1])
            return assemble_section(conn, source, root_path, parent_id)
        return None


def fetch_sections(data_dir: Path, hits: list[tuple[str, str | None, str | None]],
                   cap: int = SECTION_CAP,
                   roots: dict[str, str] | None = None,
                   cache: dict[tuple[str, str], tuple[int, int]] | None = None,
                   ) -> dict[str, SectionDoc]:
    """Assemble one section per hit `(parent_id, section_path, source)`; legacy
    rows (no section_path, or a source with no parent rows) take the heading
    walk of `_extend_one`.

    `roots` supplies roots the caller already computed (the search path picks
    each candidate's root while deduping), keyed by parent_id; `cache` is the
    `_subtree_stats` memo for whatever is left to compute.
    """
    if not data_dir or not hits:
        return {}
    out: dict[str, SectionDoc] = {}
    with _txn(data_dir) as conn:
        for pid, path, source in hits:
            root = None
            if path and source:
                root = (roots or {}).get(pid)
                if root is None:
                    root = section_root_for(conn, source, path, cap, cache)
            if root is None:
                legacy = _extend_one(conn, pid, SECTION_EXPANSION_MAX_EXTRA_CHARS)
                if legacy is not None:
                    out[pid] = SectionDoc(root_path="", section_id=legacy.section_id or "",
                                          section_heading=legacy.section_heading, text=legacy.text,
                                          page_start=legacy.page_start, page_end=legacy.page_end,
                                          source_pdf=legacy.source_pdf, windowed=False)
                continue
            doc = assemble_section(conn, source, root, pid, cap)
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
    Returns (sql_fragment, params); ``("", [])`` when unscoped. An
    unscoped sub-clause (``{}``) is TRUE: dropped from ``$and``, and it
    makes an ``$or`` unscoped; an empty ``$or`` matches nothing.
    """
    if not where:
        return "", []
    if "$and" in where or "$or" in where:
        op = "$and" if "$and" in where else "$or"
        parts, params = [], []
        for w in where[op]:
            s, p = where_to_sql(w)
            if not s:
                if op == "$or":
                    return "", []
                continue
            parts.append(f"({s})")
            params += p
        if not parts:
            return ("0", []) if op == "$or" else ("", [])
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


def count_phrases(
    data_dir: Path, phrases: list[tuple[str, ...]]
) -> dict[tuple[str, ...], int]:
    """Units containing each phrase (adjacent tokens, porter-stemmed).

    Context for the spell corrector's tie-break: how often the library
    prints "thief skill" vs "this skill". Tokens are quoted into one FTS5
    phrase, so operators in them are literal. One connection for the
    batch.
    """
    if not data_dir or not phrases:
        return {}
    with _txn(data_dir) as conn:
        return {
            p: conn.execute(
                "SELECT count(*) FROM unit_fts WHERE unit_fts MATCH ?",
                ['"' + " ".join(t.replace('"', "") for t in p) + '"'],
            ).fetchone()[0]
            for p in phrases
        }


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
