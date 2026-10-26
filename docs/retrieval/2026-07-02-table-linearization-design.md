# Table row-linearization — design (#327)

**Date:** 2026-07-02
**Issue:** [#327](https://github.com/Unseen-Servant/unseen-legend-lore/issues/327) — roadmap item 8, Tier 2
**Evidence:** [`unseen-servant-spikes/table_retrieval_spike/FINDINGS.md`](https://github.com/Unseen-Servant/unseen-servant-spikes/blob/main/table_retrieval_spike/FINDINGS.md) (verdict 2026-04-27)
**Target branch:** `main`

## Problem

Table chunks embed as single atomic vectors (`granularity.build()` exempts
`chunk_type == "table"` from sub-splitting). Two live-verified failure modes:

1. **Dilution.** A multi-page table is one vector averaging hundreds of
   heterogeneous rows; a query for one row loses to a ~400-char prose chunk
   that merely mentions the term. The reranker cannot rescue it — its
   512-token window (`Xenova/ms-marco-MiniLM-L-12-v2`, BERT-class) only sees
   the table head, and a table that never enters the candidate pool is
   invisible to it anyway.
2. **Silent truncation.** The effective Ollama embed context measured ~2048
   tokens on the dev machine (not bge-m3's native 8192 —
   `OLLAMA_CONTEXT_LENGTH` not in effect for the server process, and the
   sidecar's `OllamaEmbeddingFunction` passes no `num_ctx`). Table content
   past ~2048 tokens is not represented in the vector at all.

Additionally, `chunker._enforce_hard_cap` splits oversized chunks on `\n\n`,
which table text (rows joined by `\n`) never contains — so a >20k-char table
falls through to a raw character cut mid-row.

## Measured fix

The spike's `linearized_rows` candidate: emit one row-as-sentence embed unit
per table row (`"Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15"`),
all back-pointing at the source table's `parent_id`. Result on 14
pre-registered table queries: **+0.152 MRR@5** (0.693 → 0.845), 4 queries
flip to rank 1, zero regressions, recall@5 stays 1.000. Cost: +47% embed
units, 1.41× storage, zero LLM time.

The spike measured **replace** (row units instead of the atomic unit), not
augment. This design ships replace; augment is unmeasured and re-adds the
diluted vector.

## Design

### 1. New module `sidecar/linearize.py`

Copy from the spike's `linearize_tables.py`, verbatim where possible:
`_strip_emphasis`, `_split_pipe_row`, `_is_empty_row`, `_parse_table`,
`linearize_table`. Public surface:

```python
def linearize_table(chunk_text: str) -> tuple[list[str], list[str]]:
    """Returns (header, [row_sentence, ...]); ([], []) if unparseable."""
```

Pure functions, stdlib-only (`re`). Never raises. Must include:

- **Title-row heuristic** (load-bearing per the spike): if the row before
  the first separator has < 2 non-empty cells and post-separator rows have
  ≥ 2, demote it to a title and use the first post-separator row as header.
- **Positional header fallback**: empty header cells become `col1`, `col2`, …
  so data is never dropped.
- Emphasis stripping, `<br>`/newline-in-cell flattening, row padding /
  truncation to header width.

### 2. `granularity.build()` — table branch

```
if chunk_type == "table":
    header, sentences = linearize_table(c.text)
    if sentences:
        emit one EmbedUnit per sentence
            (chunk_type="table", parent_id/pages/heading unchanged)
    else:
        emit the atomic EmbedUnit as today   # parse-failure fallback
```

- `chunk_type` stays `"table"` for row units — it is write-only metadata in
  the retrieval path, so nothing downstream changes.
- Parents are untouched: the displayed/generation unit remains the full
  table inline in its section.
- Heading-prepend needs no work: `server._embed_text` already prepends the
  section breadcrumb to embed-unit text at embed time.
- Dedupe-by-parent (already load-bearing in `server.py` search) collapses
  multi-row hits on the same table to one result.

The fallback exists because the spike corpus was 3 clean PDFs; production
libraries will contain malformed tables, and dropping their content would be
a regression outside the spike's zero-regression envelope.

### 3. `chunker._enforce_hard_cap` — newline fallback

Before falling through to the raw character cut, try `rfind("\n")`. After
linearization this path is only reachable by oversized *unparseable* tables
(the fallback population) and mega-paragraphs, but those are exactly the
cases that currently get cut mid-row/mid-cell.

### 4. Startup truncation probe (diagnostics only)

At sidecar startup, once Ollama is confirmed reachable: embed a long filler
text and the same text with a distinctive sentinel tail; bit-identical
vectors mean the tail was truncated. Log a warning with the approximate
effective context when it is below bge-m3's 8192. Constraints:

- Log-only; no behavior change, no retries.
- Silent skip (debug log) if Ollama is unavailable — search must not depend
  on the probe.
- Keep it small (~10 lines); it exists to turn a silent misconfiguration
  into a visible log line.

### 5. Robustness against table-layout variation

PDF-extracted tables vary widely, but the exposure is bounded: the chunker
only tags consecutive pipe-rows as `table`, so the linearizer never sees
arbitrary extraction weirdness — only pipe-shaped text. On the spike corpus
(1,014 tables, three publishers) 98.2% parsed into rows; the 18 failures hit
the atomic fallback (status quo, no recall loss).

The parser does not need to be *accurate*; it needs to be
**token-lossless-or-fallback**. Mis-labeled but token-complete parses
(transposed tables, stat-block pseudo-tables) are measured harmless — bge-m3
rewards rare-token co-occurrence, not schema correctness. The failure mode
that matters is a parse that "succeeds" while dropping content (e.g. data
rows truncated to a too-narrow detected header): in replace mode that loss
is silent. Two safeguards:

- **Coverage guard** (~5 lines, in the `build()` table branch): compare
  content characters emitted across row sentences against the source
  table's non-structural characters (pipes/separators excluded); below
  ~60–70% coverage, fall back to the atomic unit. Converts every
  silent-loss case — known and unknown — into status quo.
- **Index-time counters**: log per-source linearization stats (tables
  linearized / fallbacks / rows emitted), mirroring the spike's summary
  output. Real-library variation becomes visible in diagnostics; an
  unusually high fallback rate for a source is the signal to revisit the
  parser with real examples.

Deliberately *not* doing: smarter heuristics (multi-row headers, transposed
detection) against unmeasured inputs. The guard makes them unnecessary for
safety; the counters will show if they ever become necessary for quality.

## Out of scope (deliberate)

- **`mixed`-type tables** (e.g. BFRPG cleric saving throws): not classified
  as `table`, so not linearized. Known miss in all spike candidates; one-off
  follow-up if it bites in practice.
- **Transposed tables**: linearize semantically inverted but measured
  harmless (Cloud Dragon query hits r1 regardless).
- **LLM captioning** and **sparse/dense hybrid**: spike NO-GOs.
- **Augment mode** (rows + atomic unit): unmeasured; adds storage and
  re-introduces the diluted vector.
- **Retrieval-path changes**: none needed.

## Testing

- `tests/test_linearize.py` — golden cases from the spike:
  - standard table → correct row sentences;
  - title-row prefix (chain mail) → exactly
    `"Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15"`;
  - no-separator table → first row as header;
  - all-empty header → positional `colN` names;
  - non-table text → `([], [])`.
- `tests/test_granularity.py` — the pinned `test_build_tables_atomic` is
  **deliberately replaced** by:
  - parseable table → N row units, all sharing the source table's
    `parent_id`, `chunk_type == "table"`;
  - unparseable table → single atomic unit (fallback);
  - lossy parse (row sentences covering well under the coverage threshold,
    e.g. wide data rows under a narrow detected header) → single atomic
    unit (coverage guard).
- `tests/test_chunker.py` — over-cap text with only `\n` boundaries cuts on
  a newline, not mid-row.
- Truncation probe: unit test with a fake embedding function that truncates
  → warning logged; non-truncating fake → no warning.
- **Manual validation (not CI):** after re-indexing the dev library, run the
  spike's 14 table queries before/after. Success = direction matches the
  spike; roll-table queries return tables (not prose about tables) at rank 1.

## Rollout

- Embed-side only: no schema change, no retrieval change. The existing index
  keeps working; the improvement lands when the user triggers a re-index
  (user-initiated, per project convention).
- Production lift is expected to be a floor, not a ceiling, relative to the
  spike: the spike baseline ran untruncated (`OLLAMA_CONTEXT_LENGTH=8192`),
  while production atomic tables may also be silently truncated — row units
  are tiny and sidestep truncation entirely.
- One PR based on `main`. Close #327 when the PR lands.
