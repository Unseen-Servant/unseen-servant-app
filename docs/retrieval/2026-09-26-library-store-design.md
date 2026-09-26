# Library store — Chroma → one normalized SQLite file

**Date:** 2026-09-26 · **Status:** draft for approval
**Context:** Phase 5 store swap (`../roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §4, GO in §8). The runtime swap is postponed while its target is reopened (`../roadmap/2026-09-26-ml-runtime-consolidation.md`), so the store swap goes first. That order also removes the runtime swap's blocker: Chroma pins the embedding function's name in the collection config.
**Rebuild, not migration:** the real library has 5–6 books and is not yet complete. Jerome rebuilds it from scratch, so there is no Chroma → SQLite copy step and `chromadb` leaves in the same change.

---

## 1. Goal

Replace ChromaDB with sqlite-vec, and at the same time stop storing a book's identity on every chunk. One SQLite file owns documents, sections, units, vectors and full-text search. Every write that touches a book is one transaction.

**Success criteria**

- No `chromadb` or `ollama` pip dependency. `sqlite-vec` added.
- Indexing, reindexing, renaming a file or folder, retagging game systems, removing a file and deleting the index are each one SQLite transaction. No nonce-prefixed staging, no partial rollback, no orphan GC, no Compact.
- The retrieval eval on `2026-09-24-v2-rerank` (run with `--hybrid`) gives MRR@5 equal or better on every scope. Exact search should be at least as good as Chroma's HNSW. The p50 change is reported.
- `pytest -v` passes; the frozen sidecar loads the extension; Linux CI is green.

**Non-goals:** moving the manifest into SQLite (a follow-up; see §8), the runtime swap, renaming the `chroma_db` data directory, and any retrieval change. The pipeline from spell correction to tiers is store-agnostic and does not move.

## 2. What Chroma's shape costs today

| Symptom | Root cause |
|---|---|
| Rename and folder rename fetch every vector, delete it and re-add it under a new ID, in three copies of the same code in `router.py`, then patch `parents` and `unit_fts` separately | Chunk IDs embed a hash of the path (`chunk_id_prefix`), and every chunk carries `source`/`filename` |
| Retagging a book rewrites metadata on every chunk, in batches of 5,461 (`METADATA_UPDATE_BATCH_SIZE`) | `game_system` is stored per chunk; Chroma caps the write size |
| Secondary game-system tags become a manifest-built `source $in [paths]` clause, and `lexical.py` repeats the same filtering for BM25 | Chroma metadata is scalar-only |
| Reindex stages under a nonce prefix, deletes stale IDs, rolls back partials; boot runs `gc_orphan_segments`; the UI has a Compact button | One book lives in four stores (manifest JSON, Chroma, `parents`, `unit_fts`) with no transaction across them |
| `/api/sources`, `/api/stats` and `/api/game-systems` load all 25k chunk metadatas and count in Python | No relational query over documents |
| Indexing calls `collection._embedding_function`; the runtime swap needs a drop-and-recreate | The embedder is part of the collection |
| A `"chroma"` fallback mode in the spell corrector | Vocabulary could come from either store |

## 3. Schema

One file, `library.sqlite3`, in the data dir. It replaces both `chroma.sqlite3` (plus its segment folders) and `parents.sqlite3`.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA auto_vacuum = INCREMENTAL;          -- set before the first table

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- schema_version, embedding_model, embedding_dim

CREATE TABLE documents (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    game_system TEXT NOT NULL DEFAULT 'unknown'   -- primary tag
);
CREATE TABLE document_systems (                   -- every tag, primary included
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    system      TEXT NOT NULL,
    PRIMARY KEY (document_id, system)
);

CREATE TABLE parents (                             -- today's table, keyed to documents
    parent_id    TEXT PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    text TEXT NOT NULL, section_heading TEXT,
    page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
    chunk_type TEXT NOT NULL, section_id TEXT, section_path TEXT
);
CREATE INDEX idx_parents_doc_section ON parents(document_id, section_path);
CREATE INDEX idx_parents_section_id  ON parents(section_id);

CREATE TABLE units (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    parent_id   TEXT NOT NULL,
    text        TEXT NOT NULL,                     -- body, as stored in Chroma today
    chunk_type TEXT NOT NULL, section_heading TEXT,
    page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
    page_label_start TEXT, page_label_end TEXT,
    section_id TEXT, section_path TEXT,
    UNIQUE (document_id, ordinal)
);

CREATE VIRTUAL TABLE unit_vec USING vec0(
    unit_id     INTEGER PRIMARY KEY,               -- = units.id
    document_id INTEGER partition key,             -- one shard per book, see notes
    embedding   float[{dim}] distance_metric=cosine
);
CREATE VIRTUAL TABLE unit_fts USING fts5(
    text, tokenize='porter unicode61'              -- rowid = units.id; heading-prepended text
);
```

Notes:

- **IDs.** Units get integer IDs; the path-hash chunk-ID prefix and its nonce disappear. `parent_id` and `section_id` keep today's derivation (a hash that includes the path at indexing time). They are opaque keys stored in rows, so a rename leaves them valid and never recomputes them. `get_section(section_id)` keeps working across renames.
- **Primary vs secondary tags.** `documents.game_system` is the primary tag shown in the UI. `document_systems` holds all tags, so a scope filter is one join and the `$in` path workaround goes away. The manifest keeps its copy for sync bookkeeping until §8, and both are written together.
- **FTS.** `unit_fts` keeps indexing the heading-prepended embed text (`_embed_text`). That's the text the BM25 ranking and the spell vocabulary were tuned on. Its UNINDEXED metadata columns go; they come from `units`/`documents` by rowid.
- **`chunker_version` and `embedding_model` per chunk go.** `meta` holds the store-wide embedding model and dimension; per-file freshness stays in the manifest's `pipeline_version`.
- **`document_id` is a partition key, not a metadata column.** A partition key shards the vectors by book, so a scoped search reads only the selected books' vectors. A metadata column still scans every vector and skips non-matching ones. Measured on sqlite-vec 0.1.9 (§8): one book costs 7 ms whether the library holds 25k or 200k vectors, against 23 ms and 140 ms for the metadata column. The catch: `document_id IN (…)` returns k rows *per book*, so `knn()` merges them to the global top-k in Python. The merged top-100 matched the metadata-column result exactly. Sharding by book also means deleting a book frees whole chunks (§5). Each shard's last chunk is partly empty; if many small books make that waste visible, lower vec0's `chunk_size` (default 1 024 vectors).

## 4. Store API

`legend_lore/library_store.py`, a `LibraryStore` whose methods are named for what the app does. One connection per thread, from a factory that loads sqlite-vec and sets `busy_timeout`. Writes are serialized by the existing sync lock. WAL lets search keep reading during an index write.

```python
class LibraryStore:
    @classmethod
    def open(cls, path: Path, embedding_model: str, dim: int) -> "LibraryStore": ...

    # writes — each is one transaction
    def replace_document(self, path, filename, game_system, systems,
                         units, vectors, parents) -> int: ...
    def rename_document(self, old_path, new_path) -> bool: ...
    def rename_folder(self, old_prefix, new_prefix) -> int: ...
    def set_systems(self, path, primary, systems) -> None: ...
    def delete_document(self, path) -> bool: ...
    def clear(self) -> None: ...

    # reads
    def scope_document_ids(self, *, paths=None, filename=None,
                           systems=None) -> list[int] | None: ...   # None = whole library
    def knn(self, vector, k, doc_ids) -> list[tuple[int, float]]: ...
    def fts(self, match, k, doc_ids) -> list[int]: ...
    def hydrate(self, unit_ids) -> dict[int, Unit]: ...
    def documents(self) -> list[DocumentStats]: ...            # sources, stats, systems
    def document_text(self, path) -> str: ...
    def fts_texts(self) -> Iterator[str]: ...                   # spell vocabulary
    def count_phrases(self, phrases) -> dict[str, int]: ...
```

`parents_store.py`'s section functions (`fetch_parents`, `fetch_parents_extended`, `section_root_for`, `assemble_section`, `fetch_section_by_id`, `fetch_sections`) keep their logic. They take the store's connection and key on `document_id` instead of `source`. Beyond that, the module does not grow.

## 5. Write paths

| Path | Today | New |
|---|---|---|
| Index / reindex a file | Embed and upsert batch by batch under a nonce prefix, delete stale IDs, roll back partials on failure, then write `parents` and `unit_fts` | Embed every batch first (progress events unchanged; ~16 MB of vectors for a 4k-unit book), then one `replace_document` transaction: upsert the `documents` row, delete its units/vectors/FTS/parents, insert the new ones. An embed failure writes nothing, so the previous index survives untouched |
| Rename a file | Fetch, delete and re-add vectors; `rename_source` patches parents and FTS | `UPDATE documents SET path, filename` |
| Rename a folder | The same per file, in a loop | One `UPDATE … WHERE path >= ? AND path < ?` over the prefix range |
| Retag | Batched metadata rewrite plus an FTS update | `set_systems`: one row plus its `document_systems` rows |
| Remove a file | Chroma delete + parents delete + FTS delete | `delete_document`; vector and FTS rows are removed explicitly in the same transaction (virtual tables don't cascade), then `PRAGMA incremental_vacuum` |
| Delete index | Drop and recreate the collection, `rmtree` segment folders, clear parents | `clear()` then `VACUUM` |

**Why no Compact.** Compact existed for two Chroma problems: `delete_collection` left HNSW segment folders on disk (the orphan GC), and deletes left free pages in `chroma.sqlite3` that only a manual `VACUUM` returned. Here nothing is ever orphaned, because every write is one transaction in one file. Space is reclaimed as part of the delete. Measured with 6 × 4 000 vectors: deleting one book freed its 16.9 MB of chunks; `incremental_vacuum` shrank the file from 101.5 to 84.6 MB; re-adding the book grew it back to 101.5 MB; deleting everything took it to 0. So the file tracks what is indexed without a button. `auto_vacuum = INCREMENTAL` must be set before the first table is created, and the pragma must be stepped to completion (`fetchall()`); a single `execute` frees one page.

## 6. Read paths

- **Dense search.** The embedder embeds the query and its spacing variants. `knn(vector, k=n_results*10, doc_ids)` issues `WHERE embedding MATCH ? AND k = ? AND document_id IN (…)` and keeps the k nearest of the per-book results; with no scope it drops the `IN`. k stays well under sqlite-vec's 4 096 cap.
- **BM25.** `fts(match, k, doc_ids)` joins `unit_fts` to `units` on rowid and filters on the same `doc_ids`. One scope resolver feeds both rankings, so `lexical.py`'s copy of the filter and `where_to_sql` go away.
- **Scope.** `scope_document_ids` turns the collection's paths, `source_filter` (filename) and the requested game systems into a list of document IDs with SQL over `documents` and `document_systems`. An empty list short-circuits to "no results" exactly as today.
- **Hydration.** One `SELECT … FROM units JOIN documents … WHERE units.id IN (…)` yields the dict the pipeline reads from Chroma today (`source`, `filename`, `game_system`, pages, labels, `parent_id`, `section_*`), so boost, rerank, dedupe and sections see the same fields.
- **Listings.** `/api/sources`, `/api/stats` and `/api/game-systems` become `GROUP BY` queries via `documents()`. `/api/stats` drops `reclaimable_bytes` and `collection_name`.
- **Spell correction.** Always built from the store (`fts_texts` plus `count_phrases`). The `"chroma"` mode and `from_collection` go.

## 7. Embedder, boot and removals

- `embedder.py` exposes `embed(texts) -> list[list[float]]`: a direct `httpx` POST to Ollama's `/api/embed` with the same timeout and transient-retry behaviour as today. `EMBEDDING_MODEL` and the dimension are checked against `meta` at boot; a mismatch clears the store and flags every file for reindex. That check is also the hook the runtime swap will use.
- `PIPELINE_VERSION` is bumped, so every manifest entry shows as outdated. Manifest entries survive. Reindexing an outdated file takes its tags the way sync does today: `game_system_overrides` from the UI, otherwise detection. Jerome is fine with re-detection during the rebuild (2026-09-26), so tags get no special handling.
- On first boot with the new code, legacy `chroma.sqlite3`, its UUID segment folders and `parents.sqlite3` are deleted (about 620 MB on the real library). One boot-time function, removed in a later release.
- **Removed:** `/api/compact` and the `compact_database` Tauri command, the Compact action and the status-bar reclaimable hint (`StatusBar.svelte`, `+page.svelte`, `types.ts`), `compact_sqlite`, `gc_orphan_segments` and their helpers, `METADATA_UPDATE_BATCH_SIZE`, `_split_chunk_ids_by_prefix`, `chunk_id_prefix`'s nonce, `rename_source`, `where_to_sql`, `SpellCorrector.from_collection`, `COLLECTION_METADATA`, `create_app`'s `chroma_client`/`embedding_function` parameters, and `test_orphan_gc.py`.
- **Packaging:** `--collect-all chromadb` becomes `--collect-all sqlite_vec` in `scripts/build-sidecar.sh`, `sidecar/legend-lore-sidecar.spec` and `release.yml` (both platforms). The uv Python 3.12 build has `enable_load_extension`; the frozen binary must be checked locally. Windows is validated at the release tag, which the CI rules accept.
- **Copy:** the "ChromaDB" mentions in `GettingStartedSteps.svelte`, the comment in `+page.svelte` and the CI comment are updated.

## 8. Scale

Measured with sqlite-vec 0.1.9, exact f32 search, 1 024 dimensions, WAL file, warm, k=100, 4 000 vectors per book, on this Mac. Partition key = this design; metadata column shown for comparison:

| vectors | ≈ books | whole library | 1 book (partition / metadata) | 3 books (partition / metadata) | file |
|---|---|---|---|---|---|
| 25 000 | 6 (real library today) | 44 ms | **7** / 23 ms | **20** / 31 ms | 106 MB |
| 200 000 | 50 | 335 ms | **7** / 140 ms | **20** / 145 ms | 829 MB |

Scoped search costs about 7 ms per selected book, independent of library size: searching within a collection or game system scales with the scope, not the library. Unscoped whole-library search is linear in library size (44 ms today against a 358 ms search p50; the eval measures the actual delta against Chroma). **Trigger:** whole-library dense KNN p50 above 100 ms on the real library, roughly 60k vectors or 15 books. Candidate fixes, to be measured on real bge-m3 vectors when the trigger fires:

1. Binary-quantized prefilter plus f32 rescore inside sqlite-vec (the `vector_engine_spike` configuration: 43 ms filtered at 200k, recall 0.983 on structured synthetic data; a quick synthetic re-run here was inconclusive).
2. An HNSW index file (usearch) *derived* from `unit_vec`: SQLite stays the source of truth, and the index is a cache rebuilt when it disagrees with `meta`. That keeps the one-transaction property this design is for.

Either one is internal to `knn()`.

**Follow-up (option 3):** fold the manifest into `documents` (mtime, hash, size, `pipeline_version`, `last_error`, `indexed_at`) so tags and sync state have a single source of truth.

## 9. Testing and verification

- **New `tests/test_library_store.py`:** schema creation; `replace_document` atomicity (an embed failure leaves the old index intact); rename and folder rename keep search results and section IDs; `set_systems` scopes both dense and BM25 search; `delete_document` leaves no vector or FTS rows; `scope_document_ids` covers primary, secondary, filename and collection; a `meta` mismatch clears the store.
- **Fixture:** `conftest.py` opens a `LibraryStore` in `tmp_path` with fastembed's `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions). That's the same model as Chroma's `DefaultEmbeddingFunction`, so the existing search tests keep their meaning. Tests that call `collection.*` directly are ported to store calls or HTTP endpoints.
- **Eval:** reindex the eval set into a fresh data dir, run `run_eval --hybrid` and compare against `2026-09-24-v2-rerank`. MRR is expected equal or better; any per-query loss gets explained before merging. Report p50.
- **App:** a local `bash scripts/build-sidecar.sh`, the frozen binary boots and searches, then Jerome reindexes the real library and checks results.

## 10. Commit sequence

Each commit leaves `pytest` green:

1. `LibraryStore` plus its unit tests, unused by the app. Add the `sqlite-vec` dependency.
2. `embedder.embed()`, a direct call to Ollama's `/api/embed` (the request the `ollama` client sends, so vectors are unchanged). The truncation probe and keep-warm ticker use it. Indexing and query embedding stay on the collection until step 3, because their tests mock the collection's hooks.
3. Switch the write paths, read paths, indexing and query embedding, the fixture and the eval engine (`evals/engines/v2.py` still imports the pre-prep `build_ollama_embedding_function`) to `LibraryStore` and `embed()`. Legacy files are removed at boot, `PIPELINE_VERSION` is bumped, and the `chromadb`/`ollama` dependencies are dropped.
4. Remove Compact from the Tauri command, the UI and the stats response.
5. Packaging and copy: build script, spec, `release.yml`, Getting Started text.
6. Eval run, CHANGELOG, and the roadmap §8 plus workstation §6 order rows.
