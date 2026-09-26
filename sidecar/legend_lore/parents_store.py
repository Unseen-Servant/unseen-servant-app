"""Parent and section reads over the library store.

Parents are the units of generation context a search result returns;
``library_store`` writes them with the rest of a book in one
transaction. This module reads them back: batch fetch by id, the legacy
sibling-stitch walk, and section assembly by ``section_path`` prefix.
Callers still address a book by its path, which is joined through
``documents``.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .granularity import ParentDoc
from .library_store import LibraryStore

# Max characters of sibling-parent text to stitch onto a search hit. A
# section that exceeded PARENT_HARD_CAP during indexing is split across
# multiple parents; this budget lets us stitch them back together at
# retrieval time. Sized to typically capture one full neighbor (most
# split sections produce a "big half + remainder" pair where the
# remainder is well under this cap).
SECTION_EXPANSION_MAX_EXTRA_CHARS = 4000

# A book's id from its path, for the per-book range scans below.
_DOC_ID = "(SELECT id FROM documents WHERE path = ?)"


def fetch_parents(
    store: LibraryStore, parent_ids: list[str]
) -> dict[str, ParentDoc]:
    """Batch-fetch parents by id. Missing ids are simply absent in the
    returned dict — callers handle gracefully.
    """
    if not parent_ids:
        return {}
    placeholders = ",".join("?" * len(parent_ids))
    rows = store.conn().execute(
        f"""
        SELECT p.parent_id, d.path, p.text, p.section_heading,
               p.page_start, p.page_end, p.chunk_type, p.section_id, p.section_path
        FROM parents p JOIN documents d ON d.id = p.document_id
        WHERE p.parent_id IN ({placeholders})
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

    Adjacency uses SQLite rowid order. Within a single book, rowid
    order equals document order because ``replace_document`` inserts a
    book's parents in chunk order. Walks rowid neighbors outward;
    stops on the first neighbor in a different section (compared by
    section_id when both rows have one, else by section_heading — for
    legacy rows predating the section_id migration) or when adding the
    neighbor would exceed the budget.
    """
    target = conn.execute(
        """
        SELECT p.rowid, p.parent_id, p.document_id, d.path, p.text,
               p.section_heading, p.page_start, p.page_end, p.chunk_type,
               p.section_id, p.section_path
        FROM parents p JOIN documents d ON d.id = p.document_id
        WHERE p.parent_id = ?
        """,
        (parent_id,),
    ).fetchone()
    if not target:
        return None
    (target_rowid, pid, doc_id, source, text, section, ps, pe, ctype,
     sid, spath) = target

    parts = [text]
    page_start, page_end = ps, pe
    budget = max_extra_chars

    cursor = target_rowid
    while budget > 0:
        row = conn.execute(
            """
            SELECT rowid, text, section_heading, page_start, page_end, section_id
            FROM parents WHERE document_id = ? AND rowid < ?
            ORDER BY rowid DESC LIMIT 1
            """,
            (doc_id, cursor),
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
            FROM parents WHERE document_id = ? AND rowid > ?
            ORDER BY rowid ASC LIMIT 1
            """,
            (doc_id, cursor),
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
    store: LibraryStore,
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
    if not parent_ids:
        return {}
    out: dict[str, ParentDoc] = {}
    conn = store.conn()
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
        f"WHERE document_id = {_DOC_ID} AND section_path >= ? AND section_path < ?",
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
    segment — a book with no parents rows (a hit whose book was removed
    mid-search). Without that guard an empty subtree measures 0, "fits" at
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
        f"FROM parents WHERE document_id = {_DOC_ID} "
        "AND section_path >= ? AND section_path < ? ORDER BY rowid",
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


def fetch_section_by_id(store: LibraryStore, section_id: str) -> SectionDoc | None:
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
    if not section_id:
        return None
    conn = store.conn()
    # The common case — the section owns a row — is an indexed lookup.
    row = conn.execute(
        "SELECT p.parent_id, d.path, p.section_path "
        "FROM parents p JOIN documents d ON d.id = p.document_id "
        "WHERE p.section_id = ? ORDER BY p.rowid LIMIT 1",
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
        "SELECT p.parent_id, d.path, p.section_path "
        "FROM parents p JOIN documents d ON d.id = p.document_id "
        "WHERE p.section_path LIKE '%' || ? || '%' ORDER BY p.rowid",
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


def fetch_sections(store: LibraryStore, hits: list[tuple[str, str | None, str | None]],
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
    if not hits:
        return {}
    out: dict[str, SectionDoc] = {}
    conn = store.conn()
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
