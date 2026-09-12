# v2 Retrieval Phase 2 — Query-time Structure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return whole sections instead of chunk parents, under an explicit character budget, with the matched passage identified, drill-in tools for agents, cross-edition duplicates collapsed, and the per-request overhead removed — all at query time, no reindex.

**Architecture:** Phase 1 gave every unit and parent a `section_id` and a `/`-joined `section_path` of section ids. Phase 2 assembles a result by section prefix: the shallowest ancestor whose whole subtree fits in `SECTION_CAP` chars is returned in document order, else a window centred on the matched parent. Dedupe moves from parent to assembled section. Each result carries `matched_text` (the embed unit that hit), `chunk_text` (its parent) and `text` (the section). A packer applies `max_context_chars` in rank order, truncating the last result to its matched unit. MCP gets a compact default plus `get_section` / `get_pages`. Settings, manifest and collections are read once per request; the spell vocabulary is built from the persisted `unit_fts` text and invalidated by a manifest content digest; the reranker and vocabulary are warmed at boot. The frontend renders GFM tables, highlights and scrolls to the matched passage, and shows `also_in` chips.

**Tech Stack:** Python 3.12 under `uv --project sidecar` (FastAPI, ChromaDB, sqlite3, difflib, PyMuPDF), `pytest`; `evals/tests` under `uv --project sidecar-v3`; Rust (`src-tauri/src/lib.rs`, serde), Svelte 5 + TypeScript (`svelte-exmarkdown` with its `gfm` plugin), vitest.

**Spec:** `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §4 Phase 2 (items 2.1–2.5), §1.4 (the kraken/dragon diagnosis), §1.7 (latency and payload), §5 (bars). Prior art: `docs/roadmap/2026-08-22-v3-search-recovery-strategy.md` W2.1–W2.3; `docs/roadmap/2026-07-01-retrieval-pipeline-improvement-roadmap.md` items 11, 12, 14; issues #343, #341, #375.

## Global Constraints

- **No reindex.** Nothing in this plan changes `chunker.py`, `granularity.py`, `promote_headings.py`, `heading_text.py`, `_embed_unit_metadata` or `CHUNKER_VERSION`/`PIPELINE_VERSION`. The parents SQLite may gain an index (created on connect, idempotent), never a column.
- **Reference baseline:** `evals/baselines/2026-09-12-v2-headings.json` (all 0.790, single 0.767, cued 0.701, uncued 0.925, cross_page MRR 0.354, p50 1 094 ms, uncued dup_sections@10 0.400). Phase 2's retrieval gate is against it.
- **Legacy stores keep working.** A parents store whose rows have `section_path IS NULL` (indexed before Phase 1) must return the same results as today (`_extend_one` heading walk). Every new path checks for NULL and falls back.
- **Response shape is additive.** `text`, `filename`, `source`, `section_heading`, `page_start`, `page_end`, `page_label_start`, `page_label_end`, `game_system`, `relevance`, `tier`, `reranked` keep their meaning; new keys are `matched_text`, `chunk_text`, `section_id`, `section_path`, `truncated`, `also_in`. `section_heading` stays a `str`, never `None` (Tauri decoder contract, `sidecar/tests/test_search.py::test_search_result_fields_never_null`).
- **Constants:** `SECTION_CAP = 6000` (chars of assembled section text, same as `PARENT_HARD_CAP`), `NEAR_DUP_RATIO = 0.9`, MCP default `max_context_chars=8000`, `MATCHED_SNIPPET_CHARS = 600` (MCP compact view), keepalive interval `120` s.
- **Knobs stay explicit:** the eval adapter pins every request knob; `max_context_chars` is pinned to `None` (unlimited) on every retrieval baseline except the explicit `-8k` budget baseline.
- **Design tokens only** in Svelte (`src/app.css`); no raw colours; highlights use `color-mix` on a token; no glow on hover.
- **Checks:** `uv run --project sidecar pytest sidecar/tests` (661 pass now, 7 known swig warning lines), `uv run --project sidecar-v3 pytest evals/tests` (79), `cd src-tauri && cargo test && cargo clippy -- -D warnings && cargo fmt --check`, `npm run check && npm run lint:css && npm test`.
- **One commit per task**, message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01EXZoNAdieTWWs8SA7M4r8D`. SSH-signed via 1Password; never `--no-gpg-sign`; on a signing error leave the work staged and report.
- **Ollama-backed runs** (Tasks 7 and 9) need bge-m3 up with `OLLAMA_CONTEXT_LENGTH=8192`; a fresh 7-book index takes ~40 min. `--reuse-index` runs cannot write a baseline.

---

## File map

| file | responsibility | task |
|---|---|---|
| `sidecar/mcp_server.py` | restore `search_library` registration; compact output; `get_section`, `get_pages` | 1, 5 |
| `sidecar/parents_store.py` | `idx_parents_section`; `section_root_for`, `assemble_section`, `fetch_sections`; `fetch_section_by_id` | 2, 5 |
| `sidecar/server.py` | dedupe by section + `matched_text`/`chunk_text`/`section_*`; `max_context_chars` packer; `/api/section/{id}`, `/api/source/{filename}/pages`; near-dup collapse; `RequestContext`; boot warm-up | 3, 4, 5, 6, 7 |
| `sidecar/near_dup.py` (new) | pure `collapse_near_dups(results, ratio)` | 6 |
| `sidecar/spelling.py` | `build_vocabulary_from_store(data_dir)` | 7 |
| `evals/engines/base.py`, `evals/engines/v2.py`, `evals/run_eval.py`, `evals/retrieval/grade.py`, `evals/retrieval/metrics.py` | `matched_text` on `SearchResult`; `max_context_chars` knob; `dup_titles@10` metric | 3, 4, 6 |
| `src-tauri/src/lib.rs`, `src/lib/types.ts` | new result fields (serde defaults) | 8 |
| `src/lib/SearchResults.svelte`, `src/lib/SearchInspector.svelte`, `src/lib/matchedSpan.ts` (new) | matched snippet in rows; GFM tables; highlight + scroll; `also_in` chips; page labels | 8 |
| `sidecar/tests/…`, `evals/tests/…`, `src/lib/matchedSpan.test.ts` | tests | all |
| `evals/baselines/<date>-v2-sections.*`, `<date>-v2-sections-8k.*` | Phase 2 numbers | 9 |
| `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md`, `evals/README.md` | §5/§8, commands | 9 |

---

### Task 1: Restore the `search_library` MCP tool (production hotfix)

`@mcp.tool()` at `sidecar/mcp_server.py:249` decorates `_page_span` (inserted by 8019bb5a on 2026-08-30), and `async def search_library(...)` at `:271` has no decorator. `mcp.list_tools()` returns `list_collections, _page_span, list_sources, list_game_systems`. Claude Desktop has had no search tool for two weeks. Fix first, alone.

**Files:**
- Modify: `sidecar/mcp_server.py:249-271`
- Test: `sidecar/tests/test_mcp_tools.py`

**Interfaces:**
- Produces: `search_library` registered; `_page_span` not registered.

- [ ] **Step 1: Failing test**

```python
import asyncio

def test_registered_tools_are_the_public_surface():
    from mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "search_library" in names
    assert "_page_span" not in names
```

Run: `uv run --project sidecar pytest sidecar/tests/test_mcp_tools.py -q -k registered` → FAIL (`search_library` missing, `_page_span` present).

- [ ] **Step 2: Fix** — move the `@mcp.tool()` line from above `def _page_span` to directly above `async def search_library`. No other change.

- [ ] **Step 3: Run** the test and `uv run --project sidecar pytest sidecar/tests -q` → all pass.

- [ ] **Step 4: Commit** — `fix(mcp): re-register search_library — the decorator had landed on _page_span (8019bb5a)`.

---

### Task 2: Section assembly in the parents store (roadmap 2.1, store side)

**Files:**
- Modify: `sidecar/parents_store.py` (schema index; new functions after `fetch_parents_extended`)
- Test: `sidecar/tests/test_parents_store.py`

**Interfaces:**
- Produces:
  - `SECTION_CAP = 6000`.
  - `_SCHEMA` gains `CREATE INDEX IF NOT EXISTS idx_parents_section ON parents(source, section_path);` (idempotent on connect; `section_path` exists after Phase 1's migration, which `_connect` runs first — so append the index creation *after* `_migrate` in `_connect`, not inside `_SCHEMA`).
  - `_prefix_range(path: str) -> tuple[str, str]` → `(path, path + "0")`; `'0'` (0x30) sorts right after `'/'` (0x2F) and section ids are fixed-width `s_` + 16 hex, so `section_path >= path AND section_path < path || '0'` selects exactly the section and its descendants.
  - `section_root_for(conn, source: str, section_path: str, cap: int = SECTION_CAP) -> str` — the shallowest ancestor path (including `section_path` itself) whose subtree text length (`SUM(LENGTH(text)) + 2 * (COUNT(*) - 1)`) is ≤ `cap`; if none fits, returns `section_path` (the leaf).
  - `SectionDoc` dataclass: `root_path: str, section_id: str, section_heading: str | None, text: str, page_start: int, page_end: int, source_pdf: str, windowed: bool`.
  - `assemble_section(conn, source, root_path, matched_parent_id, cap=SECTION_CAP) -> SectionDoc | None` — rows of the subtree in rowid order; if the joined text ≤ cap, all of them; else a window: start from the matched parent and alternately add the previous and next row while the total stays ≤ cap (`windowed=True`). `section_heading` = the root row's heading truncated to the root depth: `" > ".join(root_row.section_heading.split(" > ")[:depth])` where `depth = root_path.count("/") + 1` (headings and paths are positionally aligned — `chunker._breadcrumb` and `_section_path` are built from the same stack).
  - `fetch_sections(data_dir, hits: list[tuple[str, str | None, str | None]]) -> dict[str, SectionDoc]` — `hits` are `(parent_id, section_path, source)`; for a hit with `section_path` None (legacy row) falls back to `_extend_one` and wraps it as a `SectionDoc(root_path="", section_id=parent.section_id or "", windowed=False, ...)`. One connection for the batch.

- [ ] **Step 1: Failing tests**

Append to `sidecar/tests/test_parents_store.py` (uses the existing `_p(pid, source_pdf, text, section, page_start, page_end, chunk_type, sid, path)` helper):

```python
from parents_store import (SECTION_CAP, SectionDoc, _prefix_range, assemble_section,
                           fetch_sections, section_root_for, _txn)

# A monster chapter: Monsters (s_m) > Kraken (s_k) > {Actions (s_ka), Legendary (s_kl)}; Medusa (s_d) > Actions (s_da)
def _monster_tree(tmp_path):
    rows = [
        _p("p_intro", "x.pdf", "Monsters intro " * 20, "Monsters", 1, 1, sid="s_m", path="s_m"),
        _p("p_kra", "x.pdf", "Kraken AC 18 HP 472 " * 30, "Monsters > Kraken", 2, 2, sid="s_k", path="s_m/s_k"),
        _p("p_kra_act", "x.pdf", "Tentacle attack " * 30, "Monsters > Kraken > Actions", 2, 3, sid="s_ka", path="s_m/s_k/s_ka"),
        _p("p_kra_leg", "x.pdf", "Ink cloud legendary " * 30, "Monsters > Kraken > Legendary Actions", 3, 3, sid="s_kl", path="s_m/s_k/s_kl"),
        _p("p_med", "x.pdf", "Medusa AC 15 " * 30, "Monsters > Medusa", 4, 4, sid="s_d", path="s_m/s_d"),
        _p("p_med_act", "x.pdf", "Petrifying gaze " * 30, "Monsters > Medusa > Actions", 4, 4, sid="s_da", path="s_m/s_d/s_da"),
    ]
    upsert_parents(tmp_path, "x.pdf", rows)
    return rows


def test_prefix_range_covers_self_and_descendants_only():
    lo, hi = _prefix_range("s_m/s_k")
    assert lo == "s_m/s_k" and hi == "s_m/s_k0"
    assert lo <= "s_m/s_k" < hi and lo <= "s_m/s_k/s_ka" < hi
    assert not (lo <= "s_m/s_d" < hi) and not (lo <= "s_m/s_kz" < hi)   # 'z' > '0'


def test_section_root_is_the_shallowest_ancestor_that_fits(tmp_path):
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
        # Kraken subtree ≈ 1 800 chars fits; Monsters subtree ≈ 3 800 fits too under 6 000 → Monsters is chosen …
        assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=SECTION_CAP) == "s_m"
        # … but with a 2 000-char cap the whole chapter does not fit and Kraken is the root.
        assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=2000) == "s_m/s_k"
        # A leaf larger than the cap stays the leaf.
        assert section_root_for(conn, "x.pdf", "s_m/s_k/s_ka", cap=100) == "s_m/s_k/s_ka"


def test_assemble_section_returns_the_subtree_in_document_order(tmp_path):
    _monster_tree(tmp_path)
    with _txn(tmp_path) as conn:
        doc = assemble_section(conn, "x.pdf", "s_m/s_k", "p_kra_act", cap=2000)
    assert doc.text.startswith("Kraken AC 18") and "Ink cloud" in doc.text
    assert doc.text.index("Tentacle") < doc.text.index("Ink cloud")
    assert (doc.page_start, doc.page_end) == (2, 3)
    assert doc.section_heading == "Monsters > Kraken"
    assert doc.section_id == "s_k" and doc.windowed is False


def test_assemble_section_windows_a_leaf_larger_than_the_cap(tmp_path):
    rows = [_p(f"p{i}", "y.pdf", f"para{i} " * 40, "Long > Section", 1, 1, sid="s_l", path="s_x/s_l") for i in range(10)]
    upsert_parents(tmp_path, "y.pdf", rows)
    with _txn(tmp_path) as conn:
        doc = assemble_section(conn, "y.pdf", "s_x/s_l", "p5", cap=900)
    assert doc.windowed is True
    assert "para5" in doc.text and len(doc.text) <= 900
    assert "para4" in doc.text or "para6" in doc.text          # grows outward from the match
    assert "para0" not in doc.text and "para9" not in doc.text


def test_fetch_sections_falls_back_to_the_heading_walk_for_legacy_rows(tmp_path):
    upsert_parents(tmp_path, "old.pdf", [_p("a", "old.pdf", "one", "H"), _p("b", "old.pdf", "two", "H")])
    got = fetch_sections(tmp_path, [("a", None, "old.pdf")])
    assert got["a"].text == "one\n\ntwo" and got["a"].root_path == ""


def test_fetch_sections_batches_and_keys_by_parent_id(tmp_path):
    _monster_tree(tmp_path)
    got = fetch_sections(tmp_path, [("p_kra_act", "s_m/s_k/s_ka", "x.pdf"), ("p_med", "s_m/s_d", "x.pdf")])
    assert set(got) == {"p_kra_act", "p_med"}
    assert got["p_kra_act"].root_path == got["p_med"].root_path == "s_m"   # both fit under the chapter at 6 000
```

Run: `uv run --project sidecar pytest sidecar/tests/test_parents_store.py -q` → `ImportError`.

- [ ] **Step 2: Implement**

```python
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


def _subtree_size(conn, source: str, path: str) -> int:
    lo, hi = _prefix_range(path)
    row = conn.execute(
        "SELECT COALESCE(SUM(LENGTH(text)), 0), COUNT(*) FROM parents "
        "WHERE source = ? AND section_path >= ? AND section_path < ?",
        (source, lo, hi),
    ).fetchone()
    total, n = row
    return total + 2 * max(0, n - 1)


def section_root_for(conn, source: str, section_path: str, cap: int = SECTION_CAP) -> str:
    """Shallowest ancestor (or the leaf) whose whole subtree fits in `cap`."""
    ids = section_path.split("/")
    for depth in range(1, len(ids) + 1):
        candidate = "/".join(ids[:depth])
        if _subtree_size(conn, source, candidate) <= cap:
            return candidate
    return section_path


def _heading_at_depth(heading: str | None, depth: int) -> str | None:
    if not heading:
        return heading
    return " > ".join(heading.split(" > ")[:depth])


def assemble_section(conn, source: str, root_path: str, matched_parent_id: str,
                     cap: int = SECTION_CAP) -> SectionDoc | None:
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


def fetch_sections(data_dir: Path, hits: list[tuple[str, str | None, str | None]],
                   cap: int = SECTION_CAP) -> dict[str, SectionDoc]:
    """Assemble one section per hit `(parent_id, section_path, source)`; legacy
    rows (no section_path) take the heading walk of `_extend_one`."""
    if not data_dir or not hits:
        return {}
    out: dict[str, SectionDoc] = {}
    with _txn(data_dir) as conn:
        for pid, path, source in hits:
            if not path or not source:
                legacy = _extend_one(conn, pid, SECTION_EXPANSION_MAX_EXTRA_CHARS)
                if legacy is not None:
                    out[pid] = SectionDoc(root_path="", section_id=legacy.section_id or "",
                                          section_heading=legacy.section_heading, text=legacy.text,
                                          page_start=legacy.page_start, page_end=legacy.page_end,
                                          source_pdf=legacy.source_pdf, windowed=False)
                continue
            root = section_root_for(conn, source, path, cap)
            doc = assemble_section(conn, source, root, pid, cap)
            if doc is not None:
                out[pid] = doc
    return out
```

In `_connect`, after `_migrate(conn)`: `conn.execute("CREATE INDEX IF NOT EXISTS idx_parents_section ON parents(source, section_path)")`.

- [ ] **Step 3: Run** the file, then the full sidecar suite → all pass.

- [ ] **Step 4: Commit** — `feat(sidecar): section assembly by section_path prefix — root selection, windowing, legacy fallback (roadmap 2.1)`.

---

### Task 3: Search returns sections, dedupes by section, exposes `matched_text` (roadmap 2.1, server side)

**Files:**
- Modify: `sidecar/server.py` — import (`:49`), the dedupe loop (`:2165-2184`), the fetch (`:2216-2218`), the format loop (`:2220-2256`)
- Modify: `evals/engines/base.py:51-89` (`SearchResult.matched_text`), `evals/engines/v2.py:236-250`
- Test: `sidecar/tests/test_search_sections.py` (new), `evals/tests/test_v2_engine.py` (or the nearest existing adapter test)

**Interfaces:**
- Consumes: `parents_store.fetch_sections`, `SectionDoc`.
- Produces: per result — `text` = section text; `matched_text` = the unit that hit (`p["doc"]`); `chunk_text` = the hit's parent text (`fetch_parents(...)` batch for the picked parent ids — one `IN (...)` query); `section_id`, `section_path` = the assembled root's; `page_start`/`page_end` = section span; `page_label_*` unchanged (matched unit's); `section_heading` = the root's heading (never `None` → `""`). Dedupe key = `section root path` when the hit has a `section_path`, else `parent_id`. The dedupe loop asks the store for each candidate's root before deciding (cheap aggregate query), stops at `n_results` distinct roots.
- `evals/engines/base.SearchResult` gains `matched_text: str = ""`; v2 adapter fills it from `r.get("matched_text", "")`. Grading text is unchanged (`section_heading + text`).

- [ ] **Step 1: Failing tests** (`sidecar/tests/test_search_sections.py`) — build a tiny index directly with the `client`/`test_collection` fixtures like `test_search_hybrid.py` does: add three units to Chroma with metadata `section_id`/`section_path`/`parent_id` for `Monsters > Kraken`, `Monsters > Kraken > Actions`, `Monsters > Kraken > Legendary Actions`, and the matching parents via `upsert_parents(tmp_path, …)` with paths `s_m/s_k`, `s_m/s_k/s_ka`, `s_m/s_k/s_kl`; monkeypatch `collection.query` to return the `Actions` unit first and `Legendary Actions` second (as `test_search_hybrid.py::hybrid_client` does). Assert:

```python
def test_hit_returns_the_whole_section_and_the_matched_unit(section_client):
    r = _search(section_client, query="kraken ink cloud", rerank=False)["results"]
    assert r[0]["section_id"] == "s_k"
    assert "AC 18" in r[0]["text"] and "Ink cloud" in r[0]["text"]     # the section, not the parent
    assert r[0]["matched_text"] == "Tentacle attack text"               # the unit that hit
    assert r[0]["chunk_text"].startswith("Tentacle")                    # its parent
    assert r[0]["section_heading"] == "Monsters > Kraken"

def test_two_hits_in_one_section_dedupe_to_one_result(section_client):
    r = _search(section_client, query="kraken", rerank=False)["results"]
    assert [x["section_id"] for x in r].count("s_k") == 1

def test_legacy_rows_without_section_path_still_return(section_client_legacy):
    r = _search(section_client_legacy, query="kraken", rerank=False)["results"]
    assert r and r[0]["section_id"] == "" and r[0]["matched_text"]
```

Run → FAIL (`KeyError: 'section_id'`).

- [ ] **Step 2: Implement the server change**

Replace the dedupe loop:

```python
        # Dedupe by assembled section (root chosen by the store); parent_id
        # for legacy rows without a section_path.
        seen: set[str] = set()
        picked: list[dict] = []
        with _txn(data_dir) if data_dir else contextlib.nullcontext(None) as conn:
            for i, (metadata, distance) in enumerate(zip(ordered_metadatas, ordered_distances)):
                pid = metadata.get("parent_id")
                if not pid:
                    continue
                path = metadata.get("section_path") or None
                if conn is not None and path:
                    key = section_root_for(conn, metadata["source"], path)
                else:
                    key = pid
                if key in seen:
                    continue
                seen.add(key)
                picked.append({"metadata": metadata, "distance": distance, "doc": ordered_docs[i],
                               "reranked": rerank_applied and i < pool,
                               "boost": boost_factors[i] if boost_factors is not None else 1.0,
                               "root": key if path else None})
                if len(picked) >= request.n_results:
                    break
```

(`from parents_store import _txn, section_root_for, fetch_sections, fetch_parents` — `_txn` is a module-private name used cross-module; rename it to `open_store` with a `_txn = open_store` alias if the reviewer prefers, but keep one connection for the loop.) The straggler pass is unchanged. Replace the fetch:

```python
        sections = fetch_sections(
            data_dir, [(p["metadata"]["parent_id"], p["metadata"].get("section_path") or None,
                        p["metadata"].get("source")) for p in picked]) if data_dir else {}
        parents = fetch_parents(data_dir, [p["metadata"]["parent_id"] for p in picked]) if data_dir else {}
```

In the format loop: `sec = sections.get(pid)`; `text = sec.text if sec else p["doc"]`; `chunk_text = parents[pid].text if pid in parents else p["doc"]`; `section_heading = (sec.section_heading if sec else None) or metadata.get("section_heading") or ""`; pages from `sec` when present; add to the item: `"matched_text": p["doc"]`, `"chunk_text": chunk_text`, `"section_id": sec.section_id if sec else (metadata.get("section_id") or "")`, `"section_path": sec.root_path if sec else (metadata.get("section_path") or "")`.

- [ ] **Step 3: Eval adapter** — `SearchResult` gains `matched_text: str = ""` (dataclass field with default, after `raw`); `evals/engines/v2.py` sets it. `payload_chars` unchanged.

- [ ] **Step 4: Run** `uv run --project sidecar pytest sidecar/tests -q` (existing `test_parents_store` stitching tests still pass — `_extend_one` is untouched) and `uv run --project sidecar-v3 pytest evals/tests -q`.

- [ ] **Step 5: Commit** — `feat(sidecar): search returns assembled sections, dedupes by section, exposes matched_text/chunk_text/section_id (roadmap 2.1)`.

---

### Task 4: `max_context_chars` packer (roadmap 2.2, API side)

**Files:**
- Modify: `sidecar/server.py` — `SearchRequest` (`:550-598`), a `pack_results(results, budget)` helper next to `_tier_for`, applied after formatting
- Modify: `evals/engines/base.py` (`SearchOptions.max_context_chars: int | None = None`), `evals/engines/v2.py::_request_body`, `evals/run_eval.py` (`--max-context-chars` flag → opts; recorded in baseline `opts`)
- Test: `sidecar/tests/test_search_budget.py` (new), `evals/tests/test_run_eval.py`

**Interfaces:**
- `SearchRequest.max_context_chars: int | None = None` (None = unlimited; must be ≥ 1 when set — pydantic `Field(default=None, ge=1)`).
- `pack_results(results: list[dict], budget: int | None) -> list[dict]`: pure; walks in order accumulating `len(text) + len(section_heading)`; a result that does not fit is replaced by a copy with `text = matched_text` and `truncated = True` if *that* fits, and packing stops after it; results that fit get `truncated = False`. Every returned result carries `truncated`.
- Response gains nothing else; `payload_chars` in the harness therefore ≤ budget by construction when the knob is set.

- [ ] **Step 1: Failing tests**

```python
from server import pack_results

def _r(text, matched, heading="H"):
    return {"text": text, "matched_text": matched, "section_heading": heading}

def test_pack_keeps_everything_when_unbudgeted():
    out = pack_results([_r("a" * 100, "a"), _r("b" * 100, "b")], None)
    assert [x["truncated"] for x in out] == [False, False]

def test_pack_truncates_the_last_result_to_its_matched_unit_and_stops():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "bb"), _r("c" * 100, "cc")], 150)
    assert len(out) == 2
    assert out[0]["truncated"] is False and out[1]["truncated"] is True and out[1]["text"] == "bb"

def test_pack_drops_a_result_whose_matched_unit_does_not_fit_either():
    out = pack_results([_r("a" * 100, "aa"), _r("b" * 100, "b" * 60)], 110)
    assert len(out) == 1

def test_search_honours_max_context_chars(section_client):
    body = _search(section_client, query="kraken", rerank=False, max_context_chars=200)
    total = sum(len(r["text"]) + len(r["section_heading"]) for r in body["results"])
    assert total <= 200 and any(r["truncated"] for r in body["results"])
```

- [ ] **Step 2: Implement**

```python
def pack_results(results: list[dict], budget: int | None) -> list[dict]:
    """Fill in rank order under a character budget; the first result that
    does not fit is cut to its matched unit (if that fits) and ends the list."""
    if budget is None:
        return [{**r, "truncated": False} for r in results]
    out: list[dict] = []
    used = 0
    for r in results:
        cost = len(r["text"]) + len(r["section_heading"])
        if used + cost <= budget:
            out.append({**r, "truncated": False}); used += cost
            continue
        short = len(r["matched_text"]) + len(r["section_heading"])
        if used + short <= budget:
            out.append({**r, "text": r["matched_text"], "truncated": True})
        break
    return out
```

Apply in `_search_sync` after the format loop: `formatted = pack_results(formatted, request.max_context_chars)`. Harness: `SearchOptions.max_context_chars: int | None = None`; `_request_body` always sends `"max_context_chars": opts.max_context_chars`; `run_eval.py` adds `--max-context-chars INT` and records it in `opts` metadata; `top3_fit@8k` keeps its meaning (computed on the returned texts).

- [ ] **Step 3: Run** both suites → pass.

- [ ] **Step 4: Commit** — `feat(sidecar): max_context_chars packer on /api/search; harness knob (roadmap 2.2)`.

---

### Task 5: MCP compact search + drill-in tools (roadmap 2.2, agent side; item 14)

**Files:**
- Modify: `sidecar/server.py` — two endpoints near `/api/source/{filename}/content` (`:3618`)
- Modify: `sidecar/parents_store.py` — `fetch_section_by_id(data_dir, section_id) -> SectionDoc | None` (one query `WHERE section_id = ? LIMIT 1` to find the row and its `source`/`section_path`, then `assemble_section(conn, source, section_path, parent_id)`)
- Modify: `sidecar/mcp_server.py` — `search_library(query, n_results=8, source_filter=None, game_system=None, collection=None, max_context_chars=8000, full_text=False)`, new `get_section(section_id: str) -> str`, `get_pages(filename: str, start: int, end: int) -> str`
- Test: `sidecar/tests/test_mcp_tools.py`, `sidecar/tests/test_source_pages.py` (new)

**Interfaces:**
- `GET /api/section/{section_id}` → `{"section_id", "section_heading", "text", "filename", "source", "page_start", "page_end"}` or 404.
- `GET /api/source/{filename}/pages?start=<int>&end=<int>` → `{"filename", "start", "end", "text"}`: resolves `filename` through the manifest like `/api/source/{filename}/content` does, opens the PDF with `pymupdf`, joins `page.get_text("text")` for pages `start..end` (1-based, inclusive, clamped to the document, `end - start ≤ 20` else 400), 404 when the file is not indexed.
- `search_library` compact output per result: `--- Result i (match: tier) ---`, `Source: {filename} [{system}]`, `Section: {heading} ({page_span})  id={section_id}`, then `matched_text` trimmed to `MATCHED_SNIPPET_CHARS = 600` with `…`, and when `truncated`/compact a line `Full section: get_section("{section_id}")`. `full_text=True` prints `text` instead (the old behaviour). The request always sends `max_context_chars`.
- Server instructions blob (`mcp_server.py:200-218`) gains two sentences describing `get_section` and `get_pages`.

- [ ] **Step 1: Failing tests** — endpoint tests with the `client` fixture (index `sample_pdf_path`, take a `section_id` from a search result, `GET /api/section/{id}` returns 200 with the same heading; unknown id → 404; `GET /api/source/<name>/pages?start=1&end=1` returns the first page's text; `end-start > 20` → 400; unindexed filename → 404). MCP tests with `MockSidecarClient` (`test_mcp_tools.py:33-77`): `search_library` output contains `id=s_…`, the matched snippet, and no text longer than 600 chars per result; `get_section` formats heading + text; `get_pages` formats `Pages 3–4 of X.pdf` + text; the registered-tools test from Task 1 now also asserts `get_section` and `get_pages` are present.

- [ ] **Step 2: Implement** the store function, the two endpoints (reuse the filename→manifest resolution of `/api/source/{filename}/content`), the MCP formatting and tools.

- [ ] **Step 3: Run** `uv run --project sidecar pytest sidecar/tests -q` → pass.

- [ ] **Step 4: Commit** — `feat(mcp): compact search_library under an 8k budget; get_section and get_pages drill-in (roadmap 2.2, item 14)`.

---

### Task 6: Cross-edition near-dup collapse + `also_in` (roadmap 2.3)

`dup_sections@10` keys on `(filename, full breadcrumb)`, so it never counts SRD 5.1/5.2.1 twins; that metric is moved by Task 3's dedupe-by-section. This task targets the user-visible twin and reports a new harness metric instead of gating on the old one.

**Files:**
- Create: `sidecar/near_dup.py`
- Modify: `sidecar/server.py` (after `pack_results`? No — before packing, so the budget sees the collapsed list)
- Modify: `evals/retrieval/grade.py`, `evals/retrieval/metrics.py`, `evals/retrieval/report.py` (`dup_titles@10`)
- Test: `sidecar/tests/test_near_dup.py`, `evals/tests/test_retrieval_grade.py`

**Interfaces:**
- `near_dup.leaf_title(section_heading: str) -> str` — last ` > ` segment, `heading_text.strip_markup`, lowercased, non-alphanumerics collapsed to one space.
- `near_dup.collapse_near_dups(results: list[dict], ratio: float = 0.9) -> list[dict]` — pure; for each result in rank order, if an earlier kept result from a *different* `filename` has the same `leaf_title` and `difflib.SequenceMatcher(None, a["matched_text"], b["matched_text"]).ratio() >= ratio`, the later one is dropped and appended to the earlier's `also_in` as `{"filename", "source", "page_start", "page_end", "page_label_start", "page_label_end", "section_id"}`. Every kept result carries `also_in` (possibly `[]`).
- Harness: `dup_titles@10` = count of results in the top 10 whose `leaf_title` equals an earlier result's from a different file (reported in `COST_METRICS`, not gated); `SearchResult` gains `also_in: list[dict]` from `raw`.

- [ ] **Step 1: Failing tests**

```python
from near_dup import collapse_near_dups, leaf_title

def test_leaf_title_normalises():
    assert leaf_title("Monsters A–Z > **Goblin Warrior**") == "goblin warrior"

def _r(fn, heading, matched):
    return {"filename": fn, "source": f"/l/{fn}", "section_heading": heading, "matched_text": matched,
            "page_start": 1, "page_end": 1, "page_label_start": "", "page_label_end": "", "section_id": "s_" + fn}

def test_collapses_a_cross_edition_twin_into_also_in():
    a = _r("SRD_5.1.pdf", "Spells > Magic Missile", "You create three glowing darts of magical force. Each dart hits a creature of your choice.")
    b = _r("SRD_5.2.1.pdf", "Spells > Magic Missile", "You create three glowing darts of magical force. Each dart hits a creature of your choice.")
    out = collapse_near_dups([a, b])
    assert len(out) == 1 and out[0]["also_in"][0]["filename"] == "SRD_5.2.1.pdf"

def test_same_title_different_text_is_kept():
    a = _r("SRD_5.1.pdf", "Monsters > Goblin", "Small humanoid AC 15 HP 7 scimitar")
    b = _r("OSRIC.pdf", "Monsters > Goblin", "Frequency uncommon No. encountered 40-400 Move 60ft AC 6")
    assert len(collapse_near_dups([a, b])) == 2

def test_same_file_is_never_collapsed():
    a = _r("X.pdf", "A > T", "same text here"); b = _r("X.pdf", "B > T", "same text here")
    assert len(collapse_near_dups([a, b])) == 2
```

- [ ] **Step 2: Implement** `near_dup.py` (≤ 40 lines, stdlib `difflib`), call it in `_search_sync` after the format loop and before `pack_results`; when the collapse shortens the list below `n_results` that is acceptable (documented). Harness metric + report column + `SearchResult.also_in`.

- [ ] **Step 3: Run** both suites.

- [ ] **Step 4: Commit** — `feat(sidecar): cross-edition near-dup collapse with also_in; harness dup_titles@10 (roadmap 2.3)`.

---

### Task 7: Request-scoped reads, persisted spell vocabulary, boot warm-up (roadmap 2.4; #343, #341)

**Files:**
- Modify: `sidecar/server.py` — `RequestContext` dataclass (`settings`, `manifest`, `collections`) built once at the top of `_search_sync`; `_system_boost_factors(..., manifest=ctx.manifest)`; the four `load_manifest` call sites (`:1877`, `:1902`, `:1976`, `:331`) and `load_collections` (`:1871`) read from `ctx`; `_get_spell_corrector` keyed on a manifest content digest; `warm_search_stack()` started as a daemon thread in `__main__` next to `keep_embedder_warm` (reranker `rerank_scores("warm", ["warm"])` + spell corrector); `EMBED_KEEPALIVE_INTERVAL_SECONDS` default `"120"`.
- Modify: `sidecar/spelling.py` — `build_vocabulary_from_store(data_dir) -> dict[str, int]` reading `SELECT text FROM unit_fts` (the exact heading-prepended embed text); `SpellCorrector.from_store(data_dir)`.
- Create: `evals/retrieval/idle_probe.py` — searches once, sleeps 600 s, searches again, prints both latencies (run by the executor with the sidecar up).
- Test: `sidecar/tests/test_request_context.py` (new: `load_manifest` called at most once per search — monkeypatch a counting wrapper), `sidecar/tests/test_search_spelling.py` (vocab built from the store; invalidated when the manifest digest changes, not when chunk count changes), `sidecar/tests/test_embed_keepalive.py` (default interval 120)

**Interfaces:**
- `manifest_digest(manifest) -> str` = sha256 over sorted `(path, content_hash, pipeline_version)`.
- `_get_spell_corrector()` cache keyed on `manifest_digest(load_manifest(data_dir))` when `data_dir` and `count_units_fts(data_dir) > 0`, else the old Chroma-scan path (legacy index without FTS rows).

- [ ] **Step 1: Failing tests** — `test_search_reads_manifest_once` (wrap `server.load_manifest` with a counter via monkeypatch, run a search with `game_system` + `source_filter` set, assert count == 1); `test_spell_vocab_comes_from_unit_fts` (insert FTS rows with a rare token, no Chroma scan needed — monkeypatch `collection.get` to raise — `correct("thta rare token")` uses it); `test_spell_vocab_invalidates_on_manifest_digest_change`; `test_keepalive_default_interval_is_120s`.
- [ ] **Step 2: Implement** as specified; keep the Chroma-scan fallback for legacy stores.
- [ ] **Step 3: Measure** (executor, Ollama up): `uv run --project sidecar python -m evals.run_eval --engine v2 --baseline sections-norerank --no-rerank --no-write` — hmm: `--no-write` prints only; use it to read p50 with rerank off (bar ≤ 200 ms). Then the idle probe against a running sidecar (`uv run --project sidecar python sidecar/server.py` in the background with the eval data dir): second search within 1.5× of the first.
- [ ] **Step 4: Commit** — `perf(sidecar): request-scoped settings/manifest reads; spell vocab from unit_fts keyed on manifest digest; boot warm-up; 120 s keepalive (#343, #341)`.

---

### Task 8: Frontend and Rust — matched passage, GFM tables, `also_in`, page labels (roadmap 2.5)

**Files:**
- Modify: `src-tauri/src/lib.rs:373-395` (`SearchResultItem` gains `#[serde(default)] matched_text: String, chunk_text: String, section_id: String, section_path: String, page_label_start: String, page_label_end: String, truncated: bool, also_in: Vec<AlsoIn>` with `struct AlsoIn { filename, source: String, page_start, page_end: u32, #[serde(default)] page_label_start, page_label_end: String, section_id: String }`); `search_index` forwards an optional `max_context_chars: Option<u32>`.
- Modify: `src/lib/types.ts:119-136` mirror.
- Create: `src/lib/matchedSpan.ts` — `findMatchedRange(sectionText: string, matchedText: string): [number, number] | null` (exact substring, else first 60 chars of `matchedText`, else null) and `splitAround(text, range) -> {before, match, after}`; tests in `src/lib/matchedSpan.test.ts`.
- Modify: `src/lib/SearchResults.svelte:236-263` — the row snippet is `snippetPreview(result.matched_text || result.text)`; an `also_in` count chip (`+1 edition`) after the meta row using the `SystemBadge` recipe (accent wash).
- Modify: `src/lib/SearchInspector.svelte` — `import { gfmPlugin } from 'svelte-exmarkdown/gfm'` and `<Markdown md={…} plugins={[gfmPlugin()]} />` (tables finally render; the dead table CSS at `:316-349` becomes live); render `before` / `match` / `after` as three `Markdown` blocks with the middle one wrapped in `<div class="matched" bind:this={matchEl}>`; `$effect` scrolls `matchEl` into view (`block: 'center'`) when `result` changes; `.matched { background: color-mix(in srgb, var(--text-accent) 14%, transparent); border-left: 2px solid var(--text-accent); }`; `also_in` chips listing `filename · pageHint(...)`, clickable to open that PDF at its page via the existing `onOpenResult`; page-label citation `p.{page_label_start}` when present (falls back to `pageHint`).
- Modify: `src/routes/+page.svelte:535-540` — no change to the request (unbudgeted in the app); pass nothing new.
- Test: `src/lib/matchedSpan.test.ts`; `npm run check`, `npm run lint:css`, `npm test`; `cargo test`/clippy/fmt.

- [ ] **Step 1: Failing test** for `findMatchedRange`/`splitAround` (exact hit; prefix fallback; miss → null; split preserves text).
- [ ] **Step 2: Implement** Rust + TS types, the helper, the two components.
- [ ] **Step 3: Run** all four check commands.
- [ ] **Step 4: Commit** — `feat(ui): matched passage highlight + scroll, GFM tables in the inspector, also_in chips, printed page labels (roadmap 2.5)`.

Splitting a Markdown document into three renders can break a table or list that straddles the match boundary. Rule: `splitAround` snaps the range outward to the nearest blank-line boundaries (`\n\n`) so each part is whole blocks; when the matched unit sits inside a table (no blank lines), the whole table is the match block. Test that in `matchedSpan.test.ts`.

---

### Task 9: Baselines, gate, roadmap **[executor with Ollama; blind round Jerome]**

- [ ] **Step 1:** `OLLAMA_CONTEXT_LENGTH=8192 uv run --project sidecar python -m evals.run_eval --engine v2 --baseline sections --gate evals/baselines/2026-09-12-v2-headings.json` (~40 min). Expected: cross_page recall@10 ≥ 0.5 and MRR@5 up (q005/q006/q041/q042 flip — the kraken/dragon section now carries AC and the ability), single MRR ≥ 0.767, uncued dup_sections@10 0.400 → < 0.1, no scope's mrr@5/recall@3 below headings. If the gate fails on a single-query row, classify per query as in Phase 1 Task 10 and rule; do not loosen the gate.
- [ ] **Step 2:** the budget baseline: same command with `--baseline sections-8k --max-context-chars 8000 --no-gate`… the gate is against headings; run it *with* the gate too: MRR must be unchanged vs `sections` at ranks whose text survived, and `payload_chars ≤ 8 000`, `top3_fit@8k = 1.0` on every query by construction.
- [ ] **Step 3:** blind sheet on `sections` [Jerome scores]; bars: readable@5 ≥ 0.965, human single ≥ 0.87.
- [ ] **Step 4:** roadmap §5 current values (cross_page, dup_sections, payload, p50 rerank-off), §8 two rows (Phase 2 landed; the `dup_sections@10` metric finding and the `dup_titles@10` replacement), README (`--max-context-chars`, the two new MCP tools, `2026-…-v2-sections` as the Phase 3 reference). Commit with the baselines.

---

## Self-review

- **Spec coverage.** 2.1 → Tasks 2–3 (section by prefix, one batched fetch per section instead of the rowid walk, `matched_text`/`chunk_text`, dedupe by section). 2.2 → Tasks 4–5 (packer; MCP compact + `get_section` + `get_pages`). 2.3 → Task 6, with the metric correction recorded. 2.4 → Task 7 (#343 request context; spell vocab persisted via `unit_fts` and manifest digest; #341 boot warm-up and 120 s keepalive; the p50-rerank-off and idle-probe verifications). 2.5 → Task 8 (scroll-to-match, `also_in` chips, page labels in the app, plus GFM tables which the roadmap assumed already worked). Task 1 is outside the roadmap: a production regression found while mapping.
- **Order.** Hotfix first; store → server → packer → MCP → collapse → perf → UI → measure. Tasks 2–4 must precede 5 (`get_section` uses `assemble_section`; compact MCP uses `matched_text` and `truncated`). Task 8 depends on the response fields from 3, 4 and 6.
- **Type consistency.** `SectionDoc` fields are used identically in Tasks 2, 3, 5. `pack_results` reads `text`, `matched_text`, `section_heading` and writes `truncated` — the same keys Task 3 emits and Task 8 decodes. `also_in` entries have the same seven keys in Task 6's Python and Task 8's Rust struct. `SearchRequest.max_context_chars` ↔ `SearchOptions.max_context_chars` ↔ Rust `max_context_chars: Option<u32>`.
- **Placeholders.** Task 5 and Task 7 Steps 1–2 describe tests and implementation in prose with exact names and shapes rather than full code; their executors have the store/server interfaces from Tasks 2–4 in this document. Task 7 Step 3's `--no-rerank` flag: `run_eval.py` already exposes rerank via `SearchOptions.rerank`; if no CLI flag exists, add `--no-rerank` in Task 7 (it sets `opts.rerank = False`).
- **Known risk.** `section_root_for` picks the shallowest ancestor that fits, so a short book chapter (< 6 000 chars) is returned whole even for a hit in one of its sub-sections — intended (the roadmap's "Kraken section" rule generalises to "the largest enclosing section that fits"). If the blind round finds this too wide, `SECTION_CAP` is the knob and `windowed` tells the reader which results were cut.
