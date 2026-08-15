# Table Row-Linearization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Linearize `chunk_type=="table"` chunks into one row-as-sentence embed unit per row (replacing the atomic table vector), with a coverage guard, hard-cap newline fallback, and a startup embed-truncation probe — per `docs/retrieval/2026-07-02-table-linearization-design.md` (#327).

**Architecture:** A new pure-function module `sidecar/linearize.py` (ported from the spike's `linearize_tables.py`) parses Markdown pipe-tables and emits row sentences. `granularity.build()` calls it in the table branch: rows that parse and pass a coverage check become embed units sharing the source table's `parent_id`; anything else falls back to today's atomic unit. Parents, retrieval, and schema are untouched — this is embed-side only. Two small hardening pieces ride along: `chunker._enforce_hard_cap` learns a `\n` fallback, and `server.py` gains a startup probe that warns when Ollama silently truncates embeddings.

**Tech Stack:** Python 3.12 sidecar, pytest via uv (`cd sidecar && uv run pytest`), no new dependencies.

**Reference:** `~/code/unseen-legend-lore-experiments/table_retrieval_spike/linearize_tables.py` (copy source), `FINDINGS.md` (evidence: +0.152 MRR@5, zero regressions).

**Conventions:** All commands run from the repo root. Commit after every task. No `Co-Authored-By` lines in commit messages. Match existing style: `granularity.py` uses `logging.getLogger(__name__)` precedent from `reranker.py`; `server.py` startup messages use `print()`.

---

### Task 1: `sidecar/linearize.py` — pipe-table parser and row linearizer

**Files:**
- Create: `sidecar/linearize.py`
- Create: `sidecar/tests/test_linearize.py`

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_linearize.py`:

```python
"""Unit tests for linearize — pipe-table row-as-sentence linearizer.

Ported behavior is pinned against the table_retrieval_spike's verified
cases (see FINDINGS.md in the experiments repo), most importantly the
title-row heuristic that the spike found load-bearing on BFRPG tables.
"""

from linearize import linearize_table


STANDARD_TABLE = (
    "|**Armor Type**|**Price**|**Weight**|**AC**|\n"
    "|---|---|---|---|\n"
    "|Leather Armor|20gp|15|13|\n"
    "|Chain Mail|60gp|40|15|"
)

# BFRPG armor-table layout: single-cell title row BEFORE the separator,
# real header AFTER it. The spike's first-pass parser broke on this.
TITLE_ROW_TABLE = (
    "|Armor and Shields||||\n"
    "|---|---|---|---|\n"
    "|**Armor Type**|**Price**|**Weight**|**AC**|\n"
    "|Chain Mail|60gp|40|15|"
)


def test_standard_table_rows():
    header, sentences = linearize_table(STANDARD_TABLE)
    assert header == ["Armor Type", "Price", "Weight", "AC"]
    assert sentences == [
        "Armor Type: Leather Armor; Price: 20gp; Weight: 15; AC: 13",
        "Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15",
    ]


def test_title_row_demoted_to_use_real_header():
    """The spike's golden case: title row must not be mistaken for the
    header, or Price/Weight/AC are silently dropped."""
    header, sentences = linearize_table(TITLE_ROW_TABLE)
    assert sentences == [
        "Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15",
    ]


def test_no_separator_first_row_is_header():
    table = "|Thief Level|Open Locks|\n|3|35|\n|4|40|"
    header, sentences = linearize_table(table)
    assert header == ["Thief Level", "Open Locks"]
    assert sentences == [
        "Thief Level: 3; Open Locks: 35",
        "Thief Level: 4; Open Locks: 40",
    ]


def test_partially_empty_header_gets_positional_names():
    table = "|Name||AC|\n|---|---|---|\n|Goblin|small|14|"
    header, sentences = linearize_table(table)
    assert header == ["Name", "col2", "AC"]
    assert sentences == ["Name: Goblin; col2: small; AC: 14"]


def test_empty_cells_skipped_in_sentences():
    table = "|a|b|c|\n|---|---|---|\n|1||3|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: 1; c: 3"]


def test_rows_padded_and_truncated_to_header_width():
    table = "|a|b|\n|---|---|\n|1|\n|2|3|4|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: 1", "a: 2; b: 3"]


def test_br_in_cell_flattened_to_space():
    table = "|a|b|\n|---|---|\n|one<br>two|3|"
    _, sentences = linearize_table(table)
    assert sentences == ["a: one two; b: 3"]


def test_non_table_text_returns_empty():
    assert linearize_table("Just a paragraph of prose, no pipes here.") == ([], [])


def test_empty_input_returns_empty():
    assert linearize_table("") == ([], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sidecar && uv run pytest tests/test_linearize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'linearize'`

- [ ] **Step 3: Create `sidecar/linearize.py`**

Port from the spike (`~/code/unseen-legend-lore-experiments/table_retrieval_spike/linearize_tables.py`) — the parsing core verbatim, minus all spike scaffolding (argparse, cache I/O, `main()`):

```python
"""Linearize Markdown pipe-tables into per-row sentences for embedding.

Ported from table_retrieval_spike/linearize_tables.py (verdict
2026-04-27: +0.152 MRR@5 on table queries, zero regressions). For a
chunk with chunk_type == "table":

  1. Split into pipe-table lines.
  2. Identify the header row (last non-empty row before the first
     ``---`` separator; first row if no separator).
  3. For each data row, build a sentence of the form:
       "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
     skipping empty cells. Markdown emphasis (** **) is stripped.

Edge cases handled (all spike-verified):
  - Title-row prefix (BFRPG armor tables): a row with < 2 non-empty
    cells before the separator is a *title*, not the header — the real
    header is the first post-separator row. Load-bearing: without it,
    row sentences silently drop most columns.
  - Empty header cells: replaced with positional names ("col2") so
    data is never dropped.
  - ``<br>`` / newlines inside cells: flattened to spaces.
  - Rows narrower/wider than the header: padded / truncated to width.
  - Non-pipe text: returns ([], []) — the caller falls back to the
    atomic embed unit.
"""
from __future__ import annotations

import re


_EMPHASIS_RE = re.compile(r"\*+([^*]+)\*+")
_SEPARATOR_RE = re.compile(r"^\s*\|?\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?\s*$")


def _strip_emphasis(s: str) -> str:
    return _EMPHASIS_RE.sub(r"\1", s).strip()


def _split_pipe_row(line: str) -> list[str] | None:
    """Split a markdown pipe-table row. Returns None if not a pipe row.

    Handles leading/trailing pipes by stripping. Treats ``<br>`` /
    newlines inside a cell as a soft break (replaced with space).
    """
    line = line.strip()
    if not line.startswith("|") and "|" not in line:
        return None
    s = line.strip().strip("|")
    cells = [c.strip().replace("<br>", " ").replace("\n", " ") for c in s.split("|")]
    return cells


def _is_empty_row(cells: list[str]) -> bool:
    return all(not _strip_emphasis(c) for c in cells)


def _parse_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse a pipe-table chunk into (header, data_rows).

    Returns ([], []) if no parseable table found.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if _SEPARATOR_RE.match(line):
            # Mark separator with a sentinel so we know where the header ends.
            rows.append(["__SEP__"])
            continue
        cells = _split_pipe_row(line)
        if cells is None:
            continue
        rows.append(cells)

    if not rows:
        return [], []

    sep_idx = None
    for i, r in enumerate(rows):
        if r == ["__SEP__"]:
            sep_idx = i
            break

    def _non_empty_count(r: list[str]) -> int:
        return sum(1 for c in r if _strip_emphasis(c))

    if sep_idx is not None:
        # Header is normally the row immediately before the separator. But
        # some tables (BFRPG armor) put a single-cell title row there,
        # putting the real header AFTER the separator. Detect this: if the
        # candidate header has < 2 non-empty cells AND subsequent rows
        # have >= 2, demote it to a title and use the first post-separator
        # row instead.
        header_idx = sep_idx - 1
        if header_idx < 0:
            return [], []
        candidate = rows[header_idx]
        post_sep = [r for r in rows[sep_idx + 1:] if r != ["__SEP__"] and not _is_empty_row(r)]
        post_sep_max = max((_non_empty_count(r) for r in post_sep), default=0)
        if _non_empty_count(candidate) < 2 and post_sep_max >= 2 and post_sep:
            header = post_sep[0]
            data_start = rows.index(post_sep[0]) + 1
        else:
            header = candidate
            data_start = sep_idx + 1
    else:
        # No separator — take first non-empty row as header.
        header = rows[0]
        data_start = 1

    if not header or _is_empty_row(header):
        return [], []

    data: list[list[str]] = []
    for r in rows[data_start:]:
        if r == ["__SEP__"]:
            continue
        if _is_empty_row(r):
            continue
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        elif len(r) > len(header):
            r = r[: len(header)]
        data.append(r)

    return [_strip_emphasis(c) for c in header], [[_strip_emphasis(c) for c in r] for r in data]


def linearize_table(chunk_text: str) -> tuple[list[str], list[str]]:
    """Returns (header, [row_sentence, ...]); ([], []) if unparseable.

    Row sentence format: "<header_1>: <cell_1>; <header_2>: <cell_2>; ..."
    Cells with empty value are skipped (cell-by-cell).
    """
    header, data = _parse_table(chunk_text)
    if not header:
        return [], []

    header = [h if h else f"col{i+1}" for i, h in enumerate(header)]

    sentences: list[str] = []
    for row in data:
        parts: list[str] = []
        for h, v in zip(header, row):
            v = v.strip()
            if not v:
                continue
            parts.append(f"{h}: {v}")
        if parts:
            sentences.append("; ".join(parts))
    return header, sentences
```

Note one deliberate simplification vs the spike: the spike had a dead `if all(not h for h in header)` branch (unreachable — `_parse_table` already rejects all-empty headers); only the per-cell positional fallback is kept.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sidecar && uv run pytest tests/test_linearize.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/linearize.py sidecar/tests/test_linearize.py
git commit -m "feat(sidecar): add pipe-table row linearizer (ported from table_retrieval_spike)"
```

---

### Task 2: `coverage_ratio` — the lossy-parse tripwire

**Files:**
- Modify: `sidecar/linearize.py` (append function)
- Modify: `sidecar/tests/test_linearize.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `sidecar/tests/test_linearize.py`:

```python
from linearize import coverage_ratio


def test_coverage_high_for_clean_parse():
    header, sentences = linearize_table(STANDARD_TABLE)
    assert coverage_ratio(STANDARD_TABLE, header, sentences) >= 0.6


def test_coverage_high_for_title_row_table():
    header, sentences = linearize_table(TITLE_ROW_TABLE)
    assert coverage_ratio(TITLE_ROW_TABLE, header, sentences) >= 0.6


def test_coverage_low_when_narrow_header_drops_columns():
    """A 2-cell header over 5-cell data rows: _parse_table truncates each
    row to 2 cells, silently dropping 3 columns. The ratio must expose
    this so build() can fall back to the atomic unit."""
    wide_cell = "x" * 20
    rows = "\n".join(
        f"|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|"
        for _ in range(5)
    )
    table = "|Wide|Table|\n|---|---|\n" + rows
    header, sentences = linearize_table(table)
    assert sentences  # parse "succeeds"...
    assert coverage_ratio(table, header, sentences) < 0.6  # ...but lossily


def test_coverage_zero_for_no_sentences():
    assert coverage_ratio("no table here", [], []) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sidecar && uv run pytest tests/test_linearize.py -v`
Expected: FAIL — `ImportError: cannot import name 'coverage_ratio'`

- [ ] **Step 3: Implement `coverage_ratio`**

Append to `sidecar/linearize.py`:

```python
_WS_RE = re.compile(r"\s+")


def _content_len(s: str) -> int:
    return len(_WS_RE.sub("", s))


def coverage_ratio(chunk_text: str, header: list[str], sentences: list[str]) -> float:
    """Rough fraction of the table's cell content represented in the row
    sentences. A tripwire for lossy parses (e.g. data rows truncated to a
    too-narrow detected header), not a precise metric.

    Denominator: content chars of every pipe-row cell in the source,
    plus the header labels repeated once per additional sentence (labels
    appear in every sentence, so without this term long tables would
    inflate the ratio and mask dropped columns).
    """
    src = 0
    for line in chunk_text.splitlines():
        if _SEPARATOR_RE.match(line):
            continue
        cells = _split_pipe_row(line)
        if cells is None:
            continue
        src += sum(_content_len(_strip_emphasis(c)) for c in cells)
    if src == 0 or not sentences:
        return 0.0
    label_chars = sum(_content_len(h) for h in header)
    denom = src + label_chars * (len(sentences) - 1)
    emitted = sum(_content_len(s) for s in sentences)
    return emitted / denom
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sidecar && uv run pytest tests/test_linearize.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/linearize.py sidecar/tests/test_linearize.py
git commit -m "feat(sidecar): coverage-ratio tripwire for lossy table parses"
```

---

### Task 3: `granularity.build()` — emit row units, fallback, counters

**Files:**
- Modify: `sidecar/granularity.py`
- Modify: `sidecar/tests/test_granularity.py`

- [ ] **Step 1: Replace the atomic-table pin with the new contract tests**

In `sidecar/tests/test_granularity.py`, **delete** `test_build_tables_atomic` (the "Table chunks must NOT be sub-split" test — this behavior change is the point of #327) and add in its place:

```python
def test_build_table_linearized_into_row_units():
    """Parseable tables emit one row-as-sentence unit per row, all
    sharing the source table's parent (replaces the atomic unit —
    table_retrieval_spike, +0.152 MRR@5)."""
    table = (
        "|**Armor Type**|**Price**|**Weight**|**AC**|\n"
        "|---|---|---|---|\n"
        "|Leather Armor|20gp|15|13|\n"
        "|Chain Mail|60gp|40|15|"
    )
    chunks = [_chunk(table, "Armor and Shields", 0, chunk_type="table")]
    embed_units, parents = build(chunks)
    assert len(embed_units) == 2
    assert embed_units[1].text == "Armor Type: Chain Mail; Price: 60gp; Weight: 40; AC: 15"
    assert all(eu.chunk_type == "table" for eu in embed_units)
    assert all(eu.parent_id == parents[0].parent_id for eu in embed_units)
    # The parent still carries the full original table for generation.
    assert table in parents[0].text


def test_build_unparseable_table_falls_back_atomic():
    """chunk_type=='table' text the linearizer can't parse is emitted
    verbatim as a single atomic unit — never dropped."""
    not_really_a_table = "A block the chunker tagged as table but has no pipes."
    chunks = [_chunk(not_really_a_table, "Stats", 0, chunk_type="table")]
    embed_units, _ = build(chunks)
    assert len(embed_units) == 1
    assert embed_units[0].text == not_really_a_table
    assert embed_units[0].chunk_type == "table"


def test_build_lossy_parse_falls_back_atomic():
    """Coverage guard: a parse that drops most columns (narrow header
    over wide data rows) must fall back to the atomic unit rather than
    silently losing content."""
    wide_cell = "x" * 20
    rows = "\n".join(
        f"|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|{wide_cell}|"
        for _ in range(5)
    )
    table = "|Wide|Table|\n|---|---|\n" + rows
    chunks = [_chunk(table, "Weird", 0, chunk_type="table")]
    embed_units, _ = build(chunks)
    assert len(embed_units) == 1
    assert embed_units[0].text == table


def test_build_logs_linearization_counters(caplog):
    import logging

    table = "|a|b|\n|---|---|\n|1|2|\n|3|4|"
    chunks = [
        _chunk(table, "T", 0, chunk_type="table"),
        _chunk("no pipes here", "T", 1, chunk_type="table"),
    ]
    with caplog.at_level(logging.INFO, logger="granularity"):
        build(chunks)
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "linearized 1/2 tables" in m and "2 row units" in m and "1 atomic fallback" in m
        for m in messages
    )
```

Also update the module docstring list at the top of the test file: change `- tables atomic` to `- tables linearized into row units (atomic fallback for unparseable/lossy)`.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd sidecar && uv run pytest tests/test_granularity.py -v`
Expected: the 4 new tests FAIL (build still emits one atomic unit); all pre-existing tests still PASS. Note `test_build_emits_embed_units_and_parents` asserts on parents and parent_id linkage only, so it survives; if it fails, re-read it before touching it.

- [ ] **Step 3: Implement the table branch in `granularity.build()`**

In `sidecar/granularity.py`:

Add imports and constants near the top (after the existing `from chunker import Chunk`):

```python
import logging

from linearize import coverage_ratio, linearize_table

logger = logging.getLogger(__name__)
```

Add alongside the other constants:

```python
COVERAGE_MIN = 0.6
```

Replace the table branch in `build()` (currently the `if c.chunk_type == "table":` block that appends one atomic `EmbedUnit`) with:

```python
    embed_units: list[EmbedUnit] = []
    embed_ordinal = 0
    n_tables = n_linearized = n_row_units = n_fallback = 0
    for c in chunks:
        pid = chunk_to_pid[c.ordinal]
        if c.chunk_type == "table":
            n_tables += 1
            header, sentences = linearize_table(c.text)
            if sentences and coverage_ratio(c.text, header, sentences) >= COVERAGE_MIN:
                n_linearized += 1
                n_row_units += len(sentences)
                for sent in sentences:
                    embed_units.append(EmbedUnit(
                        chunk_id=f"{embed_ordinal}",
                        text=sent,
                        parent_id=pid,
                        chunk_type="table",
                        section_heading=c.section_heading,
                        source_pdf=c.source_pdf,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        ordinal=embed_ordinal,
                    ))
                    embed_ordinal += 1
            else:
                n_fallback += 1
                embed_units.append(EmbedUnit(
                    chunk_id=f"{embed_ordinal}",
                    text=c.text,
                    parent_id=pid,
                    chunk_type="table",
                    section_heading=c.section_heading,
                    source_pdf=c.source_pdf,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    ordinal=embed_ordinal,
                ))
                embed_ordinal += 1
            continue
        for sub in _split_prose(c.text):
            ...  # unchanged prose path
```

(The prose loop is unchanged — only the table branch and the counter variables are new.)

After the `for c in chunks:` loop, before `return embed_units, parents`:

```python
    if n_tables:
        logger.info(
            "%s: linearized %d/%d tables into %d row units (%d atomic fallbacks)",
            chunks[0].source_pdf, n_linearized, n_tables, n_row_units, n_fallback,
        )
```

Update the module docstring so it doesn't lie: change `tables stay atomic` (recipe list) to `tables linearize into one row-as-sentence unit per row (atomic fallback when unparseable or coverage < COVERAGE_MIN)`, and replace the `Tables atomic:` paragraph with:

```
Tables linearized: each pipe-table row embeds as its own
"<header>: <cell>; ..." sentence, all pointing at the parent that
contains the full table — so retrieval matches individual rows while
the reader still gets the whole table in context (table_retrieval_spike,
+0.152 MRR@5). Unparseable or lossy parses (coverage_ratio below
COVERAGE_MIN) fall back to the pre-#327 atomic embed unit.
```

Also update `build()`'s own docstring line "Tables are emitted as atomic embed units pointing at their parent." accordingly.

- [ ] **Step 4: Run the granularity tests**

Run: `cd sidecar && uv run pytest tests/test_granularity.py -v`
Expected: all pass, including the 4 new tests

- [ ] **Step 5: Run the full sidecar suite to catch downstream assumptions**

Run: `cd sidecar && uv run pytest -q`
Expected: all pass. If an indexing/search test fails because it assumed one embed unit per table, fix the *test's* fixture expectation (the new contract is N row units per parseable table) — do not weaken the implementation.

- [ ] **Step 6: Commit**

```bash
git add sidecar/granularity.py sidecar/tests/test_granularity.py
git commit -m "feat(search): linearize table chunks into row embed units (#327)"
```

---

### Task 4: `chunker._enforce_hard_cap` — newline fallback

**Files:**
- Modify: `sidecar/chunker.py:116-119`
- Modify: `sidecar/tests/test_chunking.py` (append test)

- [ ] **Step 1: Write the failing test**

Append to `sidecar/tests/test_chunking.py` (it already imports `HARD_CAP`; add `_enforce_hard_cap` and `Chunk` to the existing `from chunker import ...` line if not present):

```python
def test_hard_cap_falls_back_to_single_newline_for_tables():
    """Table text has no \\n\\n boundaries (rows joined by \\n). The cap
    splitter must cut on a row boundary, not mid-row at exactly HARD_CAP."""
    row = "|" + "x" * 96 + "|yy|"
    table = "\n".join(row for _ in range(250))  # ~25k chars, no \n\n anywhere
    chunk = Chunk(
        text=table, page_start=1, page_end=1, chunk_type="table",
        section_heading="Big Table", source_pdf="test.pdf",
        chunker="structure_aware-v2", ordinal=0,
    )
    out = _enforce_hard_cap([chunk], HARD_CAP)
    assert len(out) >= 2
    for c in out:
        assert len(c.text) <= HARD_CAP
        for line in c.text.splitlines():
            assert line.startswith("|") and line.endswith("|")  # no mid-row cut
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && uv run pytest tests/test_chunking.py::test_hard_cap_falls_back_to_single_newline_for_tables -v`
Expected: FAIL — the piece cut at exactly `hard_cap` chars ends mid-row (last line fails the `endswith("|")` assert)

- [ ] **Step 3: Implement the fallback**

In `sidecar/chunker.py`, `_enforce_hard_cap`, change:

```python
            cut = remaining.rfind("\n\n", 0, hard_cap)
            if cut <= 0:
                cut = hard_cap
```

to:

```python
            cut = remaining.rfind("\n\n", 0, hard_cap)
            if cut <= 0:
                # Tables join rows with single \n and never contain \n\n —
                # prefer a row boundary over a mid-row character cut.
                cut = remaining.rfind("\n", 0, hard_cap)
            if cut <= 0:
                cut = hard_cap
```

- [ ] **Step 4: Run the chunking tests**

Run: `cd sidecar && uv run pytest tests/test_chunking.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add sidecar/chunker.py sidecar/tests/test_chunking.py
git commit -m "fix(sidecar): hard-cap splitter cuts on row boundaries, not mid-row (#327)"
```

---

### Task 5: startup embed-truncation probe

**Files:**
- Modify: `sidecar/server.py` (new function near `build_ollama_embedding_function`, ~line 749; one thread start in the `__main__` block, ~line 3329)
- Create: `sidecar/tests/test_embed_probe.py`

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_embed_probe.py`:

```python
"""Startup embed-truncation probe: warn when Ollama's effective context
silently truncates long inputs (#327 — measured ~2048 on a dev machine
vs bge-m3's native 8192)."""

from server import probe_embed_truncation


def test_probe_warns_when_tail_truncated(capsys):
    """An embedder that ignores the tail returns identical vectors for
    base and base+sentinel — the probe must warn."""
    def truncating_embed(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    probe_embed_truncation(embed_fn=truncating_embed)
    out = capsys.readouterr().out
    assert "truncation detected" in out
    assert "OLLAMA_CONTEXT_LENGTH" in out


def test_probe_silent_when_context_full(capsys):
    """Vectors that differ mean the tail was seen — no warning."""
    def full_embed(texts):
        return [[float(len(t) % 97), 0.5] for t in texts]

    probe_embed_truncation(embed_fn=full_embed)
    assert "truncation detected" not in capsys.readouterr().out


def test_probe_swallows_embedder_errors(capsys):
    """Search must not depend on the probe: an unreachable Ollama is a
    debug-level skip, never a raise."""
    def broken_embed(texts):
        raise RuntimeError("connection refused")

    probe_embed_truncation(embed_fn=broken_embed)  # must not raise
    assert "probe skipped" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sidecar && uv run pytest tests/test_embed_probe.py -v`
Expected: FAIL — `ImportError: cannot import name 'probe_embed_truncation'`

- [ ] **Step 3: Implement the probe**

In `sidecar/server.py`, directly below `build_ollama_embedding_function` (~line 763), add:

```python
def probe_embed_truncation(embed_fn=None) -> None:
    """Warn when the effective Ollama embed context silently truncates.

    Embeds a ~8k-token filler text and the same text with a distinctive
    sentinel tail; identical vectors mean the tail was cut off — i.e.
    the Ollama server is running below bge-m3's native 8192 context
    (measured ~2048 on a dev machine when OLLAMA_CONTEXT_LENGTH was not
    set for the server process). Diagnostics only: prints a warning and
    never raises; indexing and search do not depend on it.
    """
    try:
        if embed_fn is None:
            embed_fn = build_ollama_embedding_function()
        base = "word " * 8000  # ~8k bge-m3 tokens, inside the native window
        tail = "zanzibar quetzal umbra"
        vec_a = list(embed_fn([base])[0])
        vec_b = list(embed_fn([base + tail])[0])
        if vec_a == vec_b:
            print(
                "WARNING: Ollama embed truncation detected — a sentinel tail "
                "at ~8k tokens did not change the embedding. The effective "
                "context is below bge-m3's native 8192, so long sections are "
                "only partially searchable. Set OLLAMA_CONTEXT_LENGTH=8192 "
                "for the Ollama server process and re-index."
            )
    except Exception as e:
        print(f"Embed truncation probe skipped: {e}")
```

In the `__main__` block, right after the watchdog thread starts (~line 3329):

```python
    # Truncation probe (daemon thread — diagnostics only, must not block
    # startup and must not fail it if Ollama isn't up yet)
    threading.Thread(target=probe_embed_truncation, daemon=True).start()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sidecar && uv run pytest tests/test_embed_probe.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/server.py sidecar/tests/test_embed_probe.py
git commit -m "feat(sidecar): startup probe for silent Ollama embed truncation (#327)"
```

---

### Task 6: full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete sidecar suite**

Run: `cd sidecar && uv run pytest -q`
Expected: all tests pass, no warnings about collection errors

- [ ] **Step 2: Run frontend + Rust checks only if their files changed**

Nothing in this plan touches `src/` or `src-tauri/` — skip unless a previous step unexpectedly did.

- [ ] **Step 3: Cross-check the spec**

Re-read `docs/retrieval/2026-07-02-table-linearization-design.md` section by section and confirm each maps to a landed commit: linearizer module (Task 1), coverage guard (Task 2), build() replace-with-fallback + counters (Task 3), hard-cap newline fallback (Task 4), truncation probe (Task 5). The "manual validation" item (14 spike queries before/after) is deliberately **not** in this plan — it requires a user-triggered re-index of the dev library and happens at review time.

---

## Post-implementation (outside this plan)

- PR base: `main` (per user direction 2026-07-02, overriding the earlier release-branch convention for this PR). Reference #327; note "re-index required to take effect" in the PR body.
- Manual validation after the user re-indexes: run the spike's 14 table queries (`~/code/unseen-legend-lore-experiments/table_retrieval_spike/queries.yaml`, `category="table"`) via `search_library` and compare rank-1 hits against the spike's per-query table in FINDINGS.md. Success = roll-table/row queries return the actual tables at rank 1; direction matches the spike.
- Close #327 when the PR lands on `main`.
