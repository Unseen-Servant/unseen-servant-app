# v2 Retrieval Phase 1 — Index-side Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the breadcrumb every embed unit, parent, reranker input and search result carries; give every unit a stable section identity; persist the lexical index and the pipeline version at index time — all in the one reindex Phase 1 is allowed.

**Architecture:** Extraction (`_extract_pdf_pages`'s pymupdf4llm call and span/TOC capture) is untouched. Everything changes downstream of it: a new pure module `sidecar/heading_text.py` sanitises heading text inside `promote_headings.py` using the page's own PDF spans as the oracle (the probe on 2026-09-09 showed the spans hold `Halfling Traits` intact where the Markdown line reads `Halfling Halflin Traits g`); promotion gains junk-shape rejection, a singleton-cluster rule and TOC effective-depth pinning; the chunker stamps `section_id`/`section_path` and tight page spans; the parents SQLite gains a migration, the two section columns and a persisted `unit_fts` table written in the same swap as the Chroma upsert; the manifest records `pipeline_version` and `/api/index-status` reports files indexed by an older pipeline. The harness (`evals/`) is tightened first so every later task is measured against an honest detector.

**Tech Stack:** Python 3.12 under `uv --project sidecar` (FastAPI, ChromaDB, sqlite3 FTS5, PyMuPDF, pymupdf4llm), `pytest`; `evals/tests` under `uv --project sidecar-v3` (pure Python); Rust (`src-tauri/src/lib.rs`, serde) and Svelte/TypeScript for the index-status surface.

**Spec:** `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §4 Phase 1 (items 1.1–1.7), §1.5 (metadata damage), §5 (bars), §8 (decision log). Issues [#367](https://github.com/Unseen-Servant/unseen-legend-lore/issues/367) (1.1) and [#328](https://github.com/Unseen-Servant/unseen-legend-lore/issues/328) (1.2).

## Global Constraints

- **Extraction stays put.** No change to `_extract_pdf_pages` before `promote_markdown` is called (`sidecar/server.py:457-467`), to `_extract_spans`, `_extract_toc`, or `_flatten_br_packed_cells`. Promotion, cleanup and chunking may change.
- **Extraction gate is non-regression, not byte identity.** The eval extraction adapter (`evals/engines/v2.py:172-181`) grades `_extract_pdf_pages` output, which includes promotion and cleanup, so sanitised headings *will* change its text. The gate is `--gate evals/baselines/2026-08-31-v2-extraction.json` (no per-page metric may drop). The roadmap's "byte-identical" wording is corrected in Task 10.
- **One reindex.** `CHUNKER_VERSION` is bumped once, in Task 6, to `structure_aware-v3`; `PIPELINE_VERSION` is introduced there. Tasks 2–5 and 7 change chunk output but do not bump anything themselves.
- **Knobs stay explicit; hybrid stays default-off in Phase 1.** Task 9 swaps the lexical backend only. Fusion weight, stopword handling and default-on are Phase 3.
- **Sidecar tests:** `uv run --project sidecar pytest` must stay green (CI). Harness tests: `uv run --project sidecar-v3 pytest evals/tests`. Rust: `cd src-tauri && cargo test && cargo clippy`. Frontend: `npm run check && npm run lint:css`.
- **Design tokens only** in Svelte (`src/app.css`); no raw colours; no filled-rectangle buttons.
- **One commit per task**, message ends with the repo's `Co-Authored-By` / `Claude-Session` trailers. Commits are SSH-signed via 1Password; never `--no-gpg-sign`.
- **Jerome triggers** every Ollama-backed retrieval run and the real-library reindex; those steps are marked **[Jerome runs]**. Breadcrumb-qa and the extraction suite need no Ollama and can be run by the executor (~8 min and ~3 min).
- **Eval corpus** lives at `evals/corpus/` (gitignored, hash-gated by `require_corpus()`); `evals/.eval_data/v2` is the harness's index directory.

---

## File map

| file | responsibility | task |
|---|---|---|
| `evals/retrieval/breadcrumb_qa.py` | tighter `_MARKUP`; `residue()` listing; `regressions()` gate | 1 |
| `evals/run_eval.py` | `--gate` for breadcrumb-qa; residue in the md | 1 |
| `evals/README.md` | gate command; Phase 1 reference baselines | 1, 10 |
| `sidecar/heading_text.py` (new) | `strip_markup`, `normalize_small_caps`, `repair_from_spans`, `sanitize` | 2 |
| `sidecar/promote_headings.py` | sanitise rows before signatures; multi-part rewrite; junk shapes; singleton rule; sub-modal levels; unmatched ≠ root; TOC effective depth | 2, 3, 4 |
| `sidecar/chunker.py` | markup-safe heading stack; `section_id`/`section_path`; per-paragraph page spans; `CHUNKER_VERSION`, `PIPELINE_VERSION` | 2, 6, 7 |
| `sidecar/granularity.py` | carry `section_id`/`section_path` on `EmbedUnit`/`ParentDoc`; group by `section_id` | 6 |
| `sidecar/parents_store.py` | column migration; section columns; stitch by `section_id`; `unit_fts` table + upsert/search/delete/rename/clear | 6, 9 |
| `sidecar/lexical.py` | `PersistedLexicalIndex`, `where_to_sql`; keep `rrf_fuse`; drop the in-memory index | 9 |
| `sidecar/server.py` | metadata keys; manifest `pipeline_version`; `compute_diff` outdated; FTS writes in `_atomic_index_pdf`; delete/rename/clear wiring; `_get_lexical_index`; hybrid block | 6, 8, 9 |
| `src-tauri/src/lib.rs`, `src/lib/types.ts` | `outdated` on the index-status payload | 8 |
| `src/routes/+page.svelte`, `src/lib/SettingsModal.svelte`, `src/lib/LibrarySettings.svelte` | "N files indexed with an older pipeline — re-index" line | 8 |
| `evals/engines/v2.py` | `pipeline_identity()` → `PIPELINE_VERSION` | 8 |
| `sidecar/tests/test_heading_text.py` (new), `test_promote_headings.py`, `test_chunking.py`, `test_granularity.py`, `test_parents_store.py`, `test_indexing.py`, `test_sync.py`, `test_rename_detection.py`, `test_search_hybrid.py`, `test_atomic_reindex.py`, `test_file_operations.py` | tests | 2–9 |
| `evals/tests/test_breadcrumb_qa.py`, `test_run_eval.py` | harness tests | 1 |
| `evals/baselines/<date>-v2-breadcrumb-qa.*`, `…-v2-extraction.*`, `…-v2-headings.*` (+ `.blind.*`) | Phase 1 numbers | 1, 10 |
| `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` | §5 gate wording, §8 decision rows | 10 |

---

### Task 1: Tighten the breadcrumb detector and give breadcrumb-qa a gate

Phase 0 deferred three harness minors that matter now: `_MARKUP` misses a single `*`, a stray `_` and a leading `#` (the `*sEllinG EquipMEnt**` breadcrumb Jerome saw on 2026-09-09 has a lone `*`); the suite ignores `--gate`, so a heading change that helps the mean and hurts one book passes silently; and the report lists roots but not the flawed headings themselves, so residue after Task 2 would be invisible. Fix the detector first so every later task is measured against the honest number, then re-baseline.

**Files:**
- Modify: `evals/retrieval/breadcrumb_qa.py:27-62`
- Modify: `evals/run_eval.py:377-393` (`run_breadcrumb_qa`) and `:523-536` (output block)
- Modify: `evals/README.md` (breadcrumb-qa paragraph, gate table row)
- Test: `evals/tests/test_breadcrumb_qa.py`, `evals/tests/test_run_eval.py`

**Interfaces:**
- Produces: `breadcrumb_qa.residue(chunks, per_flaw=8) -> dict[str, list[tuple[str, int]]]` — flaw → most frequent flawed headings with counts. `breadcrumb_qa.regressions(current_by_doc, reference_by_doc) -> list[dict]` — `{doc, flaw, ref, cur}` for every per-doc `<flaw>` count that rose. Baseline JSON gains `"residue": {doc_id: {flaw: [[heading, n], ...]}}`.

- [ ] **Step 1: Write the failing detector tests**

Append to `evals/tests/test_breadcrumb_qa.py`:

```python
from evals.retrieval.breadcrumb_qa import regressions, residue


def test_markup_catches_single_star_underscore_and_hash():
    assert "markup" in flaws("*sEllinG EquipMEnt** > **Vex**")
    assert "markup" in flaws("_Gargantuan_ > Kraken")
    assert "markup" in flaws("# Combat > Grappling")
    assert "markup" not in flaws("Snake_eyes Tavern > Bar")   # underscore inside a word


def test_residue_lists_the_most_frequent_flawed_headings():
    chunks = [{"section_heading": "**S eed** **<u>p</u>** > **Goblin**"}] * 3 \
        + [{"section_heading": "chaRacteR RaceS > Elves"}] * 2 \
        + [{"section_heading": "Combat > Grappling"}]
    r = residue(chunks, per_flaw=5)
    assert r["markup"][0] == ("**S eed** **<u>p</u>** > **Goblin**", 3)
    assert r["split_letter"][0][1] == 3
    assert r["mixed_case"] == [("chaRacteR RaceS > Elves", 2)]
    assert r["furniture_root"] == []


def test_regressions_flag_a_rate_that_rose_on_any_doc():
    ref = {"osric_2e": {"markup_rate": 0.0, "split_letter_rate": 0.0},
           "all": {"markup_rate": 0.0, "split_letter_rate": 0.0}}
    cur = {"osric_2e": {"markup_rate": 0.0, "split_letter_rate": 0.02},
           "all": {"markup_rate": 0.0, "split_letter_rate": 0.001}}
    regs = regressions(cur, ref)
    assert {(r["doc"], r["flaw"]) for r in regs} == {("osric_2e", "split_letter"), ("all", "split_letter")}


def test_regressions_ignore_docs_missing_on_either_side():
    assert regressions({"a": {"markup_rate": 0.5}}, {"b": {"markup_rate": 0.0}}) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_breadcrumb_qa.py -q`
Expected: 4 failures — `ImportError: cannot import name 'regressions'`, and the single-star assertion once imports are stubbed.

- [ ] **Step 3: Implement the detector, residue and regressions**

In `evals/retrieval/breadcrumb_qa.py` replace the `_MARKUP` line and add the two functions after `aggregate`:

```python
# Emphasis (any run of * or _ at a word edge), inline HTML, backticks, and a
# leading Markdown heading marker. An underscore inside a word (snake_case
# names in some indie titles) is not markup.
_MARKUP = re.compile(r"\*+|(?<!\w)_+|_+(?!\w)|</?[a-z][a-z0-9]*(?:\s[^>]*)?>|`|^#+\s*")
```

```python
def residue(chunks: list[dict], per_flaw: int = 8) -> dict[str, list[tuple[str, int]]]:
    """Per flaw, the most frequent headings that carry it — what a fix
    would have to handle next. Keys are every flaw, empty when clean."""
    counts: dict[str, Counter] = {f: Counter() for f in FLAWS}
    for c in chunks:
        h = c.get("section_heading")
        for f in flaws(h):
            counts[f][h or ""] += 1
    return {f: counts[f].most_common(per_flaw) for f in FLAWS}


def regressions(current: dict, reference: dict) -> list[dict]:
    """Fail closed: any per-doc flaw count that rose vs the reference."""
    out = []
    for doc, ref in reference.items():
        cur = current.get(doc)
        if cur is None:
            continue
        for f in FLAWS:
            if f in ref and f in cur and cur[f] > ref[f]:
                out.append({"doc": doc, "flaw": f, "ref": ref[f], "cur": cur[f]})
    return out
```

Extend `render_md(meta, result)` so that after the "Top roots per doc" section it renders `result.get("residue", {})` as:

```python
    if result.get("residue"):
        lines += ["", "## Residue (most frequent flawed headings per doc)"]
        for doc, per_flaw in result["residue"].items():
            items = [(f, h, n) for f, rows in per_flaw.items() for h, n in rows]
            if not items:
                continue
            lines.append(f"- **{doc}**: " + "; ".join(
                f"{f}: `{h}` ×{n}" for f, h, n in items[:12]))
```

- [ ] **Step 4: Wire residue and `--gate` into the runner**

In `evals/run_eval.py` `run_breadcrumb_qa`, collect residue next to the rows:

```python
    rows, res = [], {}
    for d in corpus.documents:
        chunks = chunks_fn(d.pdf_path)
        rows.append(breadcrumb_qa.grade_doc(d.id, chunks))
        res[d.id] = {f: [list(t) for t in v] for f, v in breadcrumb_qa.residue(d.id, chunks).items()}
        print(f"  {d.id}: {rows[-1]['chunks']} chunks")
    return {"by_doc": breadcrumb_qa.aggregate(rows), "docs": rows, "residue": res}
```

In the `args.suite == "breadcrumb-qa"` output block, after writing the files:

```python
        if args.gate is not None:
            ref = json.loads(args.gate.read_text(encoding="utf-8"))["by_doc"]
            regs = breadcrumb_qa.regressions(result["by_doc"], ref)
            print(f"\n## Breadcrumb gate vs {args.gate.name}")
            for r in regs:
                print(f"  {r['doc']:<14}{r['flaw']:<16}{r['ref']:.4f} → {r['cur']:.4f}")
            if regs:
                print(f"GATE FAILED: {len(regs)} breadcrumb flaw rate(s) above the reference")
                return 1
            print("  no flaw rate rose on any doc")
        return 0
```

Update the `--gate` help string to `"reference baseline .json; retrieval blocks headline scope regressions, extraction blocks any per-page metric regression, breadcrumb-qa blocks any per-doc flaw-rate rise"`.

Add to `evals/tests/test_run_eval.py` a runner-level test with a fake engine exposing `chunks()`:

```python
def test_breadcrumb_qa_result_carries_residue(tmp_path):
    from evals.run_eval import run_breadcrumb_qa

    class Eng:
        name = "fake"
        def chunks(self, _p):
            return [{"section_heading": "**Bold** > Sub"}, {"section_heading": "Clean > Sub"}]

    corpus = SimpleNamespace(documents=[SimpleNamespace(id="d1", pdf_path=tmp_path / "d1.pdf")])
    out = run_breadcrumb_qa(Eng(), corpus)
    assert out["residue"]["d1"]["markup"] == [["**Bold** > Sub", 1]]
    assert out["by_doc"]["d1"]["markup_rate"] == 0.5
```

- [ ] **Step 5: Run the harness tests**

Run: `uv run --project sidecar-v3 pytest evals/tests -q`
Expected: all pass (previous 70 + 5 new).

- [ ] **Step 6: Re-baseline breadcrumb-qa with the tightened detector**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa` (~8 min, no Ollama).
Expected: writes `evals/baselines/<today>-v2-breadcrumb-qa.{json,md}`; `by_doc.all.markup_rate` ≥ 0.903 (the tighter regex can only find more). Note the new corpus-wide numbers in the commit message. This file is the `--gate` reference for Tasks 2–5.

- [ ] **Step 7: Document**

In `evals/README.md`, extend the breadcrumb-qa command with the gate form:

```bash
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa \
    --gate evals/baselines/<last-committed>-v2-breadcrumb-qa.json
```

and one sentence: "The `.md` lists the residue — the most frequent flawed headings per book — so a fix can see what it did not catch."

- [ ] **Step 8: Commit**

```bash
git add evals/retrieval/breadcrumb_qa.py evals/run_eval.py evals/README.md evals/tests/test_breadcrumb_qa.py evals/tests/test_run_eval.py evals/baselines/<today>-v2-breadcrumb-qa.json evals/baselines/<today>-v2-breadcrumb-qa.md
git commit -m "feat(evals): breadcrumb-qa gate + residue; tighter markup detector

..."
```

---

### Task 2: Heading sanitation — markup, split letters, small caps (roadmap 1.1, #367)

The breadcrumb the embedder, the FTS row, the reranker and the UI all see is built from the Markdown heading line pymupdf4llm emits, which keeps `**`, `<u>`, `<mark>`, and — on the SRDs — reorders descender glyphs (`S eed p`, `Halfling Halflin Traits g`). The page's spans (`_extract_spans`, already loaded for font signatures) carry the intact text. This task adds a pure module and wires it into promotion so that every heading row is sanitised *before* its font signature is computed (an intact `Speed` matches its 9.8pt body span and gets a sub-modal level instead of the level-1 fallback that made it the root of 719 SRD chunks).

**Files:**
- Create: `sidecar/heading_text.py`
- Modify: `sidecar/promote_headings.py:101-119` (`collect_heading_signatures`), `:208-229` (`_rewrite_page_md`), `:232-305` (`promote_markdown`)
- Modify: `sidecar/chunker.py:182-191` (heading stack)
- Test: `sidecar/tests/test_heading_text.py` (new), `sidecar/tests/test_promote_headings.py`, `sidecar/tests/test_chunking.py`

**Interfaces:**
- Produces:
  - `heading_text.strip_markup(text: str) -> str` — removes `*`, `_` at word edges, backticks, inline HTML tags (`<u>`, `<mark>`, `<br>`, `<sup>`…), leading `#`; collapses whitespace.
  - `heading_text.normalize_small_caps(text: str) -> str` — a word containing a lowercase letter followed by an uppercase one (and no digit) becomes `Word` (first upper, rest lower). `THAC0`, `PCs`, `d20` untouched.
  - `heading_text.repair_from_spans(text: str, spans: list[dict], min_size: float = 0.0) -> list[tuple[str, tuple[float, bool] | None]]` — when `text` has a stranded single letter, finds the shortest run of ≤ 4 consecutive page spans whose alphabetic letters (lowercased) are exactly the heading's letters *and* of which the heading with its stranded letters removed is an ordered subsequence; returns one `(text, (size, bold))` per distinct consecutive font signature in that run (a merged 18pt + 13.9pt line becomes two headings). No match, or no stranded letter → `[(text, None)]`.
  - `heading_text.sanitize(text: str, spans: list[dict], min_size: float = 0.0) -> list[tuple[str, tuple[float, bool] | None]]` — `strip_markup` → `repair_from_spans` → `normalize_small_caps` + whitespace collapse on each part; drops empty parts.
  - Rows from `collect_heading_signatures` gain `"parts": [(text, sig_or_None), ...]` and `"text"` is the sanitised first part; `"sig"` is computed from the sanitised text (or taken from the oracle span when the oracle matched).
  - `_rewrite_page_md(md, rows_for_page, level_by_loc, level_by_sig)` emits one heading line per part; part *i > 0* gets `level_by_sig.get(part_sig, min(6, first_level + 1))`.

- [ ] **Step 1: Write the failing unit tests for the pure module**

Create `sidecar/tests/test_heading_text.py`:

```python
from heading_text import normalize_small_caps, repair_from_spans, sanitize, strip_markup


def _sp(text, size, bold=True):
    return {"text": text, "size": size, "bold": bold}


def test_strip_markup_removes_emphasis_tags_and_hash():
    assert strip_markup("**Monsters A–Z** > **<mark>Medusa</mark>** > <u>Actions</u>") \
        == "Monsters A–Z > Medusa > Actions"
    assert strip_markup("*sEllinG EquipMEnt**") == "sEllinG EquipMEnt"
    assert strip_markup("_Gargantuan_ **_,_** chaotic") == "Gargantuan , chaotic"
    assert strip_markup("# Combat<br>Grappling") == "CombatGrappling"
    assert strip_markup("Snake_eyes Tavern") == "Snake_eyes Tavern"
    assert strip_markup("  Two   spaces ") == "Two spaces"


def test_normalize_small_caps_title_cases_only_mixed_words():
    assert normalize_small_caps("chaRacteR RaceS") == "Character Races"
    assert normalize_small_caps("sEllinG EquipMEnt") == "Selling Equipment"
    assert normalize_small_caps("mUltI-claSSInG and dUal-claSSInG") == "Multi-classing and Dual-classing"
    assert normalize_small_caps("THAC0 and PCs at d20") == "THAC0 and PCs at d20"
    assert normalize_small_caps("Speed") == "Speed"


def test_repair_rejoins_a_descender_from_the_page_spans():
    spans = [_sp("Kraken", 13.9), _sp("Speed ", 9.8, bold=True), _sp("30 ft.", 9.8, bold=False)]
    assert repair_from_spans("S eed p", spans) == [("Speed", (9.8, True))]


def test_repair_splits_a_merged_pair_of_headings_by_font():
    spans = [_sp("Elf Traits ", 13.9), _sp("Halfling ", 18.0), _sp("Halfling Traits ", 13.9),
             _sp("Your halfling character", 9.8, bold=False)]
    assert repair_from_spans("Halfling Halflin Traits g", spans) == \
        [("Halfling", (18.0, True)), ("Halfling Traits", (13.9, True))]


def test_repair_joins_same_font_spans_into_one_heading():
    spans = [_sp("Ranger ", 18.0), _sp("Spells ", 18.0)]
    assert repair_from_spans("Ran er S ells g p", spans) == [("Ranger Spells", (18.0, True))]


def test_repair_requires_fragment_order_not_just_an_anagram():
    # "dear" is an anagram of "read"+"" but the fragments are out of order.
    spans = [_sp("dear", 12.0)]
    assert repair_from_spans("rea d", spans) == [("rea d", None)]


def test_repair_leaves_a_clean_heading_alone():
    assert repair_from_spans("Combat", [_sp("Combat", 12.0)]) == [("Combat", None)]
    assert repair_from_spans("A Pit and I", [_sp("A Pit and I", 12.0)]) == [("A Pit and I", None)]


def test_repair_ignores_spans_below_min_size():
    spans = [_sp("Speed", 9.8, bold=False)]
    assert repair_from_spans("S eed p", spans, min_size=12.0) == [("S eed p", None)]


def test_sanitize_chains_the_three_rules():
    spans = [_sp("Ranger ", 18.0), _sp("Spells ", 18.0)]
    assert sanitize("**Ran er S ells** **<u>g p</u>**", spans) == [("Ranger Spells", (18.0, True))]
    assert sanitize("**chaRacteR RaceS**", []) == [("Character Races", None)]
    assert sanitize("****", []) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project sidecar pytest tests/test_heading_text.py -q`
Expected: `ModuleNotFoundError: No module named 'heading_text'`.

- [ ] **Step 3: Implement `sidecar/heading_text.py`**

```python
"""Heading text sanitation — roadmap 2026-09-02 item 1.1, issue #367.

pymupdf4llm's heading lines keep inline markup and, on small-caps display
fonts, pull descender glyphs (g, p, y, q, j) out of their words and append
them: ``S eed p`` for ``Speed``, ``Halfling Halflin Traits g`` for the two
headings ``Halfling`` / ``Halfling Traits``. The page's raw spans
(``server._extract_spans``) still carry the intact text, so they are the
oracle: a run of consecutive spans whose letters are exactly the heading's
letters, in fragment order, replaces the heading.

Pure functions, no I/O. Applied in promote_headings before font
signatures are computed, so a repaired ``Speed`` matches its body-size
span and stops being a level-1 root.
"""
from __future__ import annotations

import re

_MARKUP_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?>|\*+|(?<!\w)_+|_+(?!\w)|`|^#+\s*")
_WS_RE = re.compile(r"\s+")
_MIXED_RE = re.compile(r"[a-z][A-Z]")
_LONE_RE = re.compile(r"(?<![\w'])(?![aAI](?![\w']))[A-Za-z](?![\w'])")
_NON_ALPHA_RE = re.compile(r"[^a-z]")
_MAX_RUN = 4


def strip_markup(text: str) -> str:
    return _WS_RE.sub(" ", _MARKUP_RE.sub("", text or "")).strip()


def normalize_small_caps(text: str) -> str:
    def fix(word: str) -> str:
        if any(ch.isdigit() for ch in word) or not _MIXED_RE.search(word):
            return word
        return word[0].upper() + word[1:].lower()
    return " ".join(fix(w) for w in text.split(" "))


def _letters(s: str) -> str:
    return _NON_ALPHA_RE.sub("", s.lower())


def _is_subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(ch in it for ch in needle)


def _group_by_sig(parts: list[dict]) -> list[tuple[str, tuple[float, bool]]]:
    out: list[tuple[str, tuple[float, bool]]] = []
    for sp in parts:
        sig = (round(float(sp["size"]), 1), bool(sp["bold"]))
        text = _WS_RE.sub(" ", sp["text"]).strip()
        if out and out[-1][1] == sig:
            out[-1] = (f"{out[-1][0]} {text}", sig)
        else:
            out.append((text, sig))
    return out


def repair_from_spans(text: str, spans: list[dict], min_size: float = 0.0):
    if not _LONE_RE.search(text):
        return [(text, None)]
    target = _letters(text)
    kept = _letters(_LONE_RE.sub(" ", text))     # heading minus its stranded letters
    if not target:
        return [(text, None)]
    cands = [sp for sp in spans if _letters(sp.get("text", "")) and float(sp.get("size", 0)) >= min_size]
    for start in range(len(cands)):
        acc = ""
        for end in range(start, min(start + _MAX_RUN, len(cands))):
            acc += _letters(cands[end]["text"])
            if len(acc) > len(target):
                break
            if len(acc) == len(target) and sorted(acc) == sorted(target) and _is_subsequence(kept, acc):
                return _group_by_sig(cands[start:end + 1])
    return [(text, None)]


def sanitize(text: str, spans: list[dict], min_size: float = 0.0):
    clean = strip_markup(text)
    if not clean:
        return []
    out = []
    for part, sig in repair_from_spans(clean, spans, min_size):
        part = _WS_RE.sub(" ", normalize_small_caps(strip_markup(part))).strip()
        if part:
            out.append((part, sig))
    return out
```

- [ ] **Step 4: Run the unit tests**

Run: `uv run --project sidecar pytest tests/test_heading_text.py -q`
Expected: 9 passed. If `test_repair_requires_fragment_order_not_just_an_anagram` fails, check `_is_subsequence("read", "dear")` returns False (it must).

- [ ] **Step 5: Write the failing promotion tests**

Append to `sidecar/tests/test_promote_headings.py`:

```python
def test_rows_are_sanitised_before_signatures():
    md = "# **S eed** **<u>p</u>**\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Kraken", 13.9, True), ("Speed ", 9.8, True)])}]
    rows = collect_heading_signatures(pages, spans_pages)
    assert rows[0]["text"] == "Speed"
    assert rows[0]["parts"] == [("Speed", (9.8, True))]
    assert rows[0]["sig"] == (9.8, True)


def test_promote_rewrites_a_merged_line_as_two_headings():
    # Two 13.9pt rows make that signature the modal cluster (level 2); the
    # lone 18pt part is then the larger cluster and lands at level 1.
    md = "# **Halfling Halflin Traits** **<u>g</u>**\n\nBody.\n\n## Elf Traits\n\nMore.\n\n## Dwarf Traits\n\nEnd."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([
        ("Halfling ", 18.0, True), ("Halfling Traits ", 13.9, True), ("Elf Traits", 13.9, True),
        ("Dwarf Traits", 13.9, True), ("body", 9.8, False)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    lines = promoted[0]["markdown"].split("\n")
    assert lines[0] == "# Halfling"
    assert lines[1] == "## Halfling Traits"
    assert "## Elf Traits" in lines


def test_promote_strips_markup_and_small_caps_from_every_heading():
    md = "## **chaRacteR RaceS**\n\nBody."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("chaRacteR RaceS", 11.0, True)])}]
    promoted, _ = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    assert promoted[0]["markdown"].split("\n")[0] == "## Character Races"
```

Run: `uv run --project sidecar pytest tests/test_promote_headings.py -q` → Expected: 3 new failures (`KeyError: 'parts'`, markup still present).

- [ ] **Step 6: Wire sanitation into promotion**

In `sidecar/promote_headings.py`:

1. `from heading_text import sanitize` at the top.
2. Replace the body of `collect_heading_signatures`:

```python
    spans_by_page = {p["page_number"]: p["spans"] for p in spans_pages}
    rows: list[dict] = []
    for page in pages:
        page_num = page["page_number"]
        page_spans = spans_by_page.get(page_num, [])
        for line_idx, level, text in _md_heading_lines(page["markdown"]):
            parts = sanitize(text, page_spans)
            if not parts:
                rows.append({"page_number": page_num, "line_idx": line_idx,
                             "original_level": level, "text": "", "parts": [], "sig": None})
                continue
            first_text, first_sig = parts[0]
            sig = first_sig or _heading_font_signature(first_text, page_spans)
            rows.append({
                "page_number": page_num,
                "line_idx": line_idx,
                "original_level": level,
                "text": first_text,
                "parts": parts,
                "sig": sig,
            })
    return rows
```

3. Replace `_rewrite_page_md`:

```python
def _rewrite_page_md(
    md: str,
    rows_for_page: list[dict],
    level_by_loc: dict[tuple[int, int], int],
    level_by_sig: dict[tuple[float, bool], int] | None = None,
) -> str:
    """Replace each heading line with its sanitised text at its promoted
    level. A line the span oracle resolved to several headings (a merged
    18pt + 13.9pt pair) becomes several lines; parts after the first take
    the level of their own font signature, else one level deeper. An empty
    sanitised heading (pure markup) is dropped.

    Splits/rejoins on ``\\n`` only so any ``\\r`` characters embedded in
    non-heading lines (the SRD's CR-fragmented prose) survive verbatim
    for R1 downstream.
    """
    level_by_sig = level_by_sig or {}
    lines = md.split("\n")
    for r in rows_for_page:
        loc = (r["page_number"], r["line_idx"])
        if not HEADING_RE.match(lines[r["line_idx"]]):
            continue
        parts = r.get("parts") or [(r["text"], r.get("sig"))]
        if not parts or not parts[0][0]:
            lines[r["line_idx"]] = ""
            continue
        first_level = max(1, min(6, int(level_by_loc.get(loc, r["original_level"]))))
        out = [("#" * first_level) + " " + parts[0][0]]
        for text, sig in parts[1:]:
            level = level_by_sig.get(sig, min(6, first_level + 1))
            out.append(("#" * max(1, min(6, int(level)))) + " " + text)
        lines[r["line_idx"]] = "\n".join(out)
    return "\n".join(lines)
```

4. In `promote_markdown`, pass the map: `new_md = _rewrite_page_md(page["markdown"], page_rows, level_by_loc, font_info["level_by_sig"])`.

- [ ] **Step 7: Make the chunker markup-safe too**

`structure_aware` is also called by tests and by `V2Engine.chunks` after promotion; a heading line that reaches it with markup (a caller that skipped promotion) must not put markup in the breadcrumb. In `sidecar/chunker.py`, add `from heading_text import strip_markup` and change the stack push:

```python
                text = strip_markup(hm.group(2))
                flush_prose()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                if text:
                    heading_stack.append((level, text))
```

Add to `sidecar/tests/test_chunking.py`:

```python
def test_breadcrumb_never_carries_markup():
    pages = [_page(1, "## **<mark>Medusa</mark>**\n\n### <u>Actions</u>\n\nBite.")]
    chunks = structure_aware(pages, source_pdf="x.pdf")
    assert chunks[0].section_heading == "Medusa > Actions"
```

- [ ] **Step 8: Run the sidecar suite**

Run: `uv run --project sidecar pytest -q`
Expected: all pass. `test_collect_heading_signatures_with_corrupted_text` still passes (its span `Legendary Actions` now also repairs the text; the assertion on `sig` holds). If `test_promotion_anchors_stat_block_subsection_to_parent` fails, check the fixture's heading text for markup the strip now removes and update its expected breadcrumb strings accordingly (the intent of that test — `Solar` not in Kraken's breadcrumb — is unchanged).

- [ ] **Step 9: Measure against the Task 1 baseline**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa --gate evals/baselines/<task1-date>-v2-breadcrumb-qa.json`
Expected: gate passes; `all.markup_rate == 0.0`; `split_letter_rate ≤ 0.005` on every book with the residue section listing what is left; `mixed_case_rate == 0.0` on `osric_2e` and `srd_5_2_1`. Paste the `by_doc` table into the commit message. If split residue remains on `srd_5_1`/`srd_5_2_1`, read the residue lines: a heading whose intact text is *not* on the same page (a running column title) is out of the oracle's reach and is a Task 4 furniture case, not a failure of this rule.

- [ ] **Step 10: Commit**

```bash
git add sidecar/heading_text.py sidecar/promote_headings.py sidecar/chunker.py sidecar/tests/test_heading_text.py sidecar/tests/test_promote_headings.py sidecar/tests/test_chunking.py evals/baselines/<today>-v2-breadcrumb-qa.json evals/baselines/<today>-v2-breadcrumb-qa.md
git commit -m "feat(sidecar): sanitise heading text before signatures — markup, split letters, small caps (#367)

..."
```

---

### Task 3: Heading promotion quality — junk shapes, distinct sub-modal levels, no fallback roots (roadmap 1.2 b/e, #328)

Three promotion rules that need no oracle. (b) A stat line (`Armor Class 12 Hit Points 7`), a caption (`Table 3-1: Weapons`), a sentence-length line, a line with no letters, a URL, or a lead-in ending in `:` is not a heading — it is demoted to a bold paragraph so it stays in the body. (e) Every signature smaller than the modal cluster currently collapses to level 3; they now get 3, 4, 5, 6 in descending size. (f) A heading whose signature matched no span keeps pymupdf4llm's original level, which is often `#` — that is how corrupted lines became roots; an unmatched heading may not be level 1.

**Files:**
- Modify: `sidecar/promote_headings.py:122-162` (`build_font_cluster_levels`), `:232-305` (`promote_markdown`), `_rewrite_page_md`
- Test: `sidecar/tests/test_promote_headings.py`

**Interfaces:**
- Produces: `promote_headings.is_junk_heading(text: str) -> bool`; rows gain `"junk": bool`; report gains `"junk_demoted": int`. `_rewrite_page_md` writes a junk row as `**{text}**`.

- [ ] **Step 1: Write the failing tests**

```python
from promote_headings import is_junk_heading


def test_junk_shapes():
    assert is_junk_heading("Armor Class 12 Hit Points 7 Speed 30")     # ≥ 2 numbers
    assert is_junk_heading("Table 3-1: Weapons")                        # caption
    assert is_junk_heading("Figure 2. The map")
    assert is_junk_heading("For free updates, errata and other OSRIC support, visit:")  # lead-in
    assert is_junk_heading("www.knights-n-knaves.com/osric")
    assert is_junk_heading("1d6")                                        # no letters beyond a die code? no — see next
    assert not is_junk_heading("Chapter 3")
    assert not is_junk_heading("Level 1 Spells")
    assert not is_junk_heading("THAC0")
    assert not is_junk_heading("Combat")
    assert is_junk_heading("This is a long sentence that explains at length what the reader is about to see next in the text")


def test_junk_heading_is_demoted_to_bold_paragraph():
    md = "# Armor Class 12 Hit Points 7\n\nBody.\n\n## Combat\n\nMore."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Armor Class 12 Hit Points 7", 9.8, True), ("Combat", 12.0, True)])}]
    promoted, report = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    lines = promoted[0]["markdown"].split("\n")
    assert lines[0] == "**Armor Class 12 Hit Points 7**"
    assert report["junk_demoted"] == 1


def test_sub_modal_signatures_get_distinct_levels():
    rows = [{"sig": (12.0, True)}] * 5 + [{"sig": (10.0, True)}] * 2 + [{"sig": (9.0, True)}] * 2 + [{"sig": (8.0, False)}]
    out = build_font_cluster_levels(rows)
    assert out["level_by_sig"] == {(12.0, True): 2, (10.0, True): 3, (9.0, True): 4, (8.0, False): 5}


def test_unmatched_heading_never_becomes_a_root():
    md = "# Zzqx\n\nBody.\n\n## Combat\n\nMore."
    pages = [{"page_number": 1, "markdown": md}]
    spans_pages = [{"page_number": 1, "spans": _spans([("Combat", 12.0, True), ("Grappling", 12.0, True)])}]
    promoted, report = promote_markdown(pages, spans_pages, {"entries": []}, strategy="font_cluster")
    assert promoted[0]["markdown"].split("\n")[0] == "## Zzqx"
    assert report["fallback_count"] == 1
```

Remove the `assert is_junk_heading("1d6")` line before running — a bare die code has letters and one number and is *not* junk by these rules; the line is there to make the point and must not stay.

Run: `uv run --project sidecar pytest tests/test_promote_headings.py -q` → Expected: `ImportError: is_junk_heading`, then the three behavioural failures.

- [ ] **Step 2: Implement**

In `sidecar/promote_headings.py`:

```python
_NUM_RE = re.compile(r"\d+")
_CAPTION_RE = re.compile(r"^(table|figure|fig\.|chart|map|illustration)\s+[\dA-Z][\w.-]*\s*[:.\-–]", re.IGNORECASE)
_URL_RE = re.compile(r"www\.|https?://|\.(com|net|org)\b", re.IGNORECASE)
_JUNK_MAX_LEN = 80


def is_junk_heading(text: str) -> bool:
    """Shapes that are never section headings (v3 structure.py rule +
    #328's caption/lead-in/URL cases). Stat lines carry ≥ 2 numbers;
    ``Chapter 3`` / ``Level 1 Spells`` keep one."""
    t = text.strip()
    if not t or len(t) > _JUNK_MAX_LEN:
        return True
    if not any(ch.isalpha() for ch in t):
        return True
    if len(_NUM_RE.findall(t)) >= 2:
        return True
    if _CAPTION_RE.match(t) or _URL_RE.search(t) or t.endswith(":"):
        return True
    return False
```

In `build_font_cluster_levels`, replace the sub-modal loop:

```python
    for k, s in enumerate(smaller_than_modal):
        level_by_sig[s] = min(6, 3 + k)
```

In `promote_markdown`, after `rows = collect_heading_signatures(...)`, mark junk rows and keep them out of the font histogram:

```python
    for r in rows:
        r["junk"] = is_junk_heading(r["text"])
    font_info = build_font_cluster_levels([r for r in rows if not r["junk"]])
```

and change the fallback branch so an unmatched heading is never a root:

```python
        if new_level is None:
            new_level = max(2, r["original_level"])
            fallback_count += 1
```

Add `"junk_demoted": sum(1 for r in rows if r["junk"])` to the report. In `_rewrite_page_md`, *after* the empty-parts check (an empty heading is dropped, never bolded) and before computing `first_level`:

```python
        if r.get("junk"):
            lines[r["line_idx"]] = f"**{parts[0][0]}**"
            continue
```

- [ ] **Step 3: Run the suite**

Run: `uv run --project sidecar pytest -q` → Expected: all pass. `test_promotion_anchors_stat_block_subsection_to_parent` (test_chunking.py:209) is the one to watch: its fixture headings must not trip `is_junk_heading`; if one does (e.g. a stat-line heading in the fixture), that is the rule working — adjust the fixture to a real heading and keep the assertion.

- [ ] **Step 4: Measure**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa --gate evals/baselines/<task2-date>-v2-breadcrumb-qa.json`
Expected: gate passes; `osric_2e.furniture_root_rate` drops from 0.984 (the footer ends with `:` → demoted); record the `top_roots` for `srd_5_1`, `srd_5_2_1`, `osric_2e` in the commit message. Do not commit this baseline yet (Task 4 re-measures); commit only code.

- [ ] **Step 5: Commit**

```bash
git add sidecar/promote_headings.py sidecar/tests/test_promote_headings.py
git commit -m "feat(sidecar): promotion rejects junk heading shapes; distinct sub-modal levels; no fallback roots (#328)

..."
```

---

### Task 4: Furniture roots — singleton clusters and TOC effective depth (roadmap 1.2 a/d)

The 2026-09-09 probe on OSRIC's first 70 pages: 780 TOC entries but a single depth-1 entry (the book title), so depth-1 pinning matched nothing (`toc_used 0`); the font rule then gave level 1 to the *largest* signature, which occurs once — the front-matter footer on page 3 — while the real 24pt chapter titles landed at level 2. Two rules: a signature seen fewer than twice cannot own level 1 (the top cluster with ≥ 2 rows does); and TOC pinning uses the shallowest depth that has ≥ 2 entries as "level 1". Running-heading detection (R4) is unchanged — the footer is front matter, not chrome.

**Files:**
- Modify: `sidecar/promote_headings.py:122-162` (`build_font_cluster_levels`), `:165-205` (`build_toc_levels`), `promote_markdown` (the `toc_level == 1` test)
- Test: `sidecar/tests/test_promote_headings.py`

**Interfaces:**
- Produces: `build_toc_levels(rows, toc_entries)` returns levels *relative to the effective top depth* (an entry at `effective_depth` reports level 1); the dict gains `"effective_depth": int`. `build_font_cluster_levels` gains `min_root_count: int = 2`.

- [ ] **Step 1: Write the failing tests**

```python
def test_singleton_largest_signature_is_not_the_root():
    rows = [{"sig": (30.0, True)}] + [{"sig": (24.0, True)}] * 3 + [{"sig": (11.0, True)}] * 10
    out = build_font_cluster_levels(rows)
    assert out["level_by_sig"][(24.0, True)] == 1
    assert out["level_by_sig"][(30.0, True)] == 2
    assert out["level_by_sig"][(11.0, True)] == 2


def test_toc_effective_depth_shifts_when_depth_one_is_a_lone_book_title():
    rows = [
        {"page_number": 3, "line_idx": 0, "original_level": 1, "text": "Contributors", "sig": None},
        {"page_number": 15, "line_idx": 0, "original_level": 1, "text": "Combat", "sig": None},
    ]
    toc = [[1, "OSRIC", 1], [2, "Contributors", 3], [2, "Combat", 15], [3, "Initiative", 16]]
    out = build_toc_levels(rows, toc)
    assert out["effective_depth"] == 2
    assert out["level_by_row"] == {(3, 0): 1, (15, 0): 1}


def test_toc_effective_depth_is_one_when_depth_one_has_chapters():
    rows = [{"page_number": 5, "line_idx": 0, "original_level": 1, "text": "Combat", "sig": None}]
    toc = [[1, "Characters", 1], [1, "Combat", 5], [2, "Initiative", 6]]
    out = build_toc_levels(rows, toc)
    assert out["effective_depth"] == 1
    assert out["level_by_row"] == {(5, 0): 1}
```

Run: `uv run --project sidecar pytest tests/test_promote_headings.py -q` → Expected: 3 failures.

- [ ] **Step 2: Implement**

In `build_font_cluster_levels(rows, min_root_count: int = 2)`, replace the larger-than-modal assignment:

```python
    eligible = [s for s in larger_than_modal if hist[s] >= min_root_count]
    root = eligible[0] if eligible else None
    for s in larger_than_modal:
        level_by_sig[s] = 1 if s == root else 2
```

(Keep the modal → 2 and the sub-modal 3..6 lines from Task 3.) Note this also changes the old `larger_count == 1` branch: a lone larger signature with ≥ 2 rows is still level 1; a singleton is level 2. Update `test_three_cluster_promotion` (`:35-71`) if its top cluster has a single row — give it two rows; the intent (largest cluster → 1) is unchanged. Task 2's `test_promote_rewrites_a_merged_line_as_two_headings` has a single 18pt row: add a second 18pt heading to its fixture (`# Dwarf` with an `("Dwarf ", 18.0, True)` span, and assert `"# Dwarf" in lines`) so the 18pt cluster keeps level 1 under this rule.

In `build_toc_levels`, compute the effective depth before matching and pin relative to it:

```python
    depth_counts = Counter(int(e[0]) for e in toc_entries if len(e) >= 3)
    effective_depth = next((d for d in sorted(depth_counts) if depth_counts[d] >= 2),
                           min(depth_counts) if depth_counts else 1)
    ...
            if best is not None and best_overlap > 0:
                rel = int(toc_level) - effective_depth + 1
                if rel >= 1:
                    by_page_idx[(best["page_number"], best["line_idx"])] = rel
                    matched += 1
                break
    return {"level_by_row": by_page_idx, "matched": matched, "total": len(rows),
            "effective_depth": effective_depth}
```

Entries shallower than the effective depth (the lone book title) are skipped (`rel < 1`). `promote_markdown`'s `toc_level == 1` test needs no change — it now sees relative levels. Add `"toc_effective_depth": toc_info["effective_depth"]` to the report.

- [ ] **Step 3: Run the suite**

Run: `uv run --project sidecar pytest -q` → Expected: all pass (adjust `test_three_cluster_promotion` as noted if needed; `test_toc_depth`, `test_depth2_falls_through`, `test_depth1_precedence` keep passing because their fixtures have ≥ 2 depth-1 entries — verify, and if a fixture has a single depth-1 entry add a second so it tests what it meant to).

- [ ] **Step 4: Measure and commit the Phase 1 breadcrumb baseline**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa --gate evals/baselines/<task2-date>-v2-breadcrumb-qa.json`
Expected: gate passes; `furniture_root_rate ≤ 0.01` on every book (OSRIC's residue should be its own contents pages under a `Contents` root — legitimate); `markup 0`, `split_letter ≤ 0.005`, `mixed_case 0`. Read the `top_roots` for all 7 books: each should be a chapter or part title. If `srd_5_1`'s top root is still a stat-block label, report it in the commit message — it is the staleness case Task 5 measures.

- [ ] **Step 5: Commit**

```bash
git add sidecar/promote_headings.py sidecar/tests/test_promote_headings.py evals/baselines/<today>-v2-breadcrumb-qa.json evals/baselines/<today>-v2-breadcrumb-qa.md
git commit -m "feat(sidecar): singleton signatures cannot be roots; TOC pins at its effective top depth

..."
```

---

### Task 5: Heading staleness — measure, then cap only if the corpus says so (roadmap 1.2 c)

The roadmap asks for "a heading with no descendant may not cover more than N pages (N derived from the corpus, not asserted)". After Tasks 2–4 the giant roots may already be gone; this task measures before it builds. A childless heading is always the top of the chunker's stack, so the cap is a single check when a new page starts.

**Files:**
- Create: `evals/retrieval/heading_spans.py` (measurement script, harness-side)
- Modify (conditional): `sidecar/chunker.py:134-222` (`structure_aware`)
- Test (conditional): `sidecar/tests/test_chunking.py`

**Interfaces:**
- Produces: `chunker.structure_aware(pages, source_pdf, soft_cap, hard_cap, leaf_page_cap: int | None = None)`; `chunker.LEAF_PAGE_CAP: int | None` (module default, set from the measurement).

- [ ] **Step 1: Write the measurement script**

`evals/retrieval/heading_spans.py`:

```python
"""How many pages does each heading stay on the chunker's stack, and did it
get a child? Feeds roadmap 1.2(c): the cap N is the 99th percentile of the
childless-leaf span across the 7-book corpus, or no cap if the tail is flat.

    uv run --project sidecar python -m evals.retrieval.heading_spans
"""
from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sidecar"))

from evals.corpus import load_corpus, require_corpus  # noqa: E402

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def leaf_spans(pages: list) -> list[tuple[str, int, bool]]:
    """(heading, pages_on_stack, had_child) for every heading pushed."""
    stack: list[list] = []          # [level, text, page_pushed, had_child]
    done: list[tuple[str, int, bool]] = []
    last_page = 0
    for page in pages:
        last_page = page.page_number
        for line in page.markdown.splitlines():
            m = _HEADING_RE.match(line)
            if not m:
                continue
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                lvl, text, since, child = stack.pop()
                done.append((text, page.page_number - since + 1, child))
            if stack:
                stack[-1][3] = True
            stack.append([level, m.group(2), page.page_number, False])
    for lvl, text, since, child in stack:
        done.append((text, last_page - since + 1, child))
    return done


def main() -> int:
    import server  # noqa: F401  (sidecar import path set above)
    from server import _extract_pdf_pages

    corpus = load_corpus()
    require_corpus(corpus)
    rows = []
    for d in corpus.documents:
        pages = _extract_pdf_pages(d.pdf_path)
        for text, span, child in leaf_spans(pages):
            rows.append((d.id, text, span, child))
    leaves = sorted(r[2] for r in rows if not r[3])
    if not leaves:
        print("no childless headings")
        return 0
    q = statistics.quantiles(leaves, n=100)
    print(f"childless headings: {len(leaves)}  p50 {q[49]}  p90 {q[89]}  p99 {q[98]}  max {leaves[-1]}")
    worst = sorted((r for r in rows if not r[3]), key=lambda r: -r[2])[:15]
    for doc, text, span, _ in worst:
        print(f"  {doc:<12}{span:>5} pages  {text[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add a pure test for `leaf_spans` in `evals/tests/test_heading_spans.py`:

```python
from types import SimpleNamespace

from evals.retrieval.heading_spans import leaf_spans


def test_leaf_spans_count_pages_and_children():
    pages = [SimpleNamespace(page_number=1, markdown="# A\n\n## B\n\ntext"),
             SimpleNamespace(page_number=2, markdown="text"),
             SimpleNamespace(page_number=3, markdown="# C\n\ntext")]
    out = leaf_spans(pages)
    assert ("B", 3, False) in out      # pages 1–3, no child
    assert ("A", 3, True) in out       # had B
    assert ("C", 1, False) in out
```

Run: `uv run --project sidecar-v3 pytest evals/tests/test_heading_spans.py -q` → Expected: pass.

- [ ] **Step 2: Measure**

Run: `uv run --project sidecar python -m evals.retrieval.heading_spans` (~8 min; extraction only).
Record `p50/p90/p99/max` and the 15 worst leaves in the task report.

**Decision rule:** if `p99 ≤ 3` pages and the 15 worst are all under 10 pages, there is no tail — set `LEAF_PAGE_CAP = None`, skip Step 3, and record "no cap needed after Tasks 2–4" in the commit. Otherwise `N = ceil(p99)` and implement Step 3.

*Outcome 2026-09-11: p99 = 2 pages, max 16; the tail was legitimate leaf sections, so no cap was built (ruling in the Phase 1 ledger).*

- [ ] **Step 3 (conditional): Implement the cap in the chunker**

In `sidecar/chunker.py`, add `LEAF_PAGE_CAP: int | None = <N>` under `HARD_CAP`, add the parameter `leaf_page_cap: int | None = LEAF_PAGE_CAP` to `structure_aware`, track `(level, text, page_pushed, had_child)` on the stack, and at the top of the `for page in pages:` loop:

```python
        if leaf_page_cap is not None and heading_stack:
            level, text, since, had_child = heading_stack[-1]
            if not had_child and current_page - since >= leaf_page_cap:
                flush_prose()
                heading_stack.pop()
```

(`current_page` must be assigned before the check; move `current_page = page.page_number` above it.) When pushing a heading, set the parent's `had_child = True`. `_breadcrumb` reads `text` from the 4-tuple.

Test:

```python
def test_childless_heading_expires_after_the_leaf_page_cap():
    pages = [_page(1, "# Part\n\n## Sidebar\n\nintro")] + [_page(n, f"page {n} prose") for n in range(2, 8)]
    chunks = structure_aware(pages, source_pdf="x.pdf", leaf_page_cap=3)
    assert chunks[0].section_heading == "Part > Sidebar"
    assert chunks[-1].section_heading == "Part"


def test_heading_with_a_child_is_never_expired():
    pages = [_page(1, "# Part\n\n## Sub\n\nintro")] + [_page(n, "prose") for n in range(2, 8)]
    chunks = structure_aware(pages, source_pdf="x.pdf", leaf_page_cap=3)
    assert all(c.section_heading.startswith("Part") for c in chunks)
```

Run: `uv run --project sidecar pytest tests/test_chunking.py -q` → Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add evals/retrieval/heading_spans.py evals/tests/test_heading_spans.py [sidecar/chunker.py sidecar/tests/test_chunking.py]
git commit -m "feat(evals): heading staleness measurement; <cap N pages | no cap needed> (roadmap 1.2c)

..."
```

---

### Task 6: Section identity — `section_id` / `section_path` end to end (roadmap 1.3)

Every parent and unit gets a stable section identity so Phase 2 can assemble by hierarchy instead of by heading-string equality. `section_id` is a hash of (doc, heading path, push ordinal); `section_path` is the `/`-joined ids of the stack, so a prefix match is a hierarchy match even when two monsters both have an `Actions` child. `section_heading` stays the human breadcrumb. Parents SQLite gains the two columns through an `ALTER TABLE` migration; stitching compares `section_id`. This is the task that bumps `CHUNKER_VERSION` and introduces `PIPELINE_VERSION`.

**Files:**
- Modify: `sidecar/chunker.py:18-21`, `:36-52`, `:54-98` (`_emit_prose` Chunk constructors), `:134-222`
- Modify: `sidecar/granularity.py:51-74`, `:145-168`, `:171-260`
- Modify: `sidecar/parents_store.py:32-57`, `:60-90`, `:93-116`, `:118-196`
- Modify: `sidecar/server.py:1049-1067` (`_embed_unit_metadata`)
- Test: `sidecar/tests/test_chunking.py`, `test_granularity.py`, `test_parents_store.py`, `test_indexing.py`

**Interfaces:**
- Produces: `chunker.CHUNKER_VERSION = "structure_aware-v3"`, `chunker.PIPELINE_VERSION = f"{CHUNKER_VERSION}/{EMBEDDING_MODEL}"`. `Chunk`, `EmbedUnit`, `ParentDoc` gain `section_id: str | None` and `section_path: str | None`. Chroma metadata gains `"section_id"`, `"section_path"` (`""` when None). `parents_store.SCHEMA_COLUMNS = {"section_id": "TEXT", "section_path": "TEXT"}` and `_migrate(conn)`. Parent rows carry both; `_extend_one` stops when `section_id` differs (falls back to heading equality when the row's `section_id` is NULL — legacy rows).

- [ ] **Step 1: Write the failing chunker tests**

```python
def test_chunks_carry_section_id_and_path():
    pages = [_page(1, "# Monsters\n\n## Kraken\n\nbody\n\n### Actions\n\nbite\n\n## Medusa\n\ngaze\n\n### Actions\n\nglare")]
    chunks = structure_aware(pages, source_pdf="x.pdf")
    by_heading = {c.section_heading: c for c in chunks}
    kraken, kraken_actions = by_heading["Monsters > Kraken"], by_heading["Monsters > Kraken > Actions"]
    medusa_actions = by_heading["Monsters > Medusa > Actions"]
    assert kraken.section_id and kraken.section_id.startswith("s_")
    assert kraken_actions.section_path.startswith(kraken.section_path + "/")
    assert not medusa_actions.section_path.startswith(kraken.section_path + "/")
    assert kraken_actions.section_id != medusa_actions.section_id   # same title, different section


def test_section_ids_are_stable_across_runs():
    pages = [_page(1, "# A\n\n## B\n\ntext")]
    a = structure_aware(pages, source_pdf="x.pdf")
    b = structure_aware(pages, source_pdf="x.pdf")
    assert [c.section_id for c in a] == [c.section_id for c in b]


def test_pipeline_version_names_chunker_and_embedder():
    from chunker import CHUNKER_VERSION, EMBEDDING_MODEL, PIPELINE_VERSION
    assert CHUNKER_VERSION == "structure_aware-v3"
    assert PIPELINE_VERSION == f"{CHUNKER_VERSION}/{EMBEDDING_MODEL}"
```

Run: `uv run --project sidecar pytest tests/test_chunking.py -q` → Expected: `AttributeError: section_id`, `ImportError: PIPELINE_VERSION`.

- [ ] **Step 2: Implement in the chunker**

```python
CHUNKER_VERSION = "structure_aware-v3"
EMBEDDING_MODEL = "bge-m3"
PIPELINE_VERSION = f"{CHUNKER_VERSION}/{EMBEDDING_MODEL}"
```

Add `section_id: str | None` and `section_path: str | None` to `Chunk` (after `section_heading`). Stack entries become `(level, text, section_id)`; add:

```python
def _section_id(source_pdf: str, ordinal: int, path_titles: list[str]) -> str:
    digest = hashlib.sha256(f"{source_pdf}::{ordinal}::{' > '.join(path_titles)}".encode()).hexdigest()[:16]
    return f"s_{digest}"


def _section_path(stack) -> str | None:
    return "/".join(sid for _, _, sid in stack) if stack else None
```

(`import hashlib`.) In `structure_aware`, keep `section_counter = 0`; on push: `section_counter += 1; sid = _section_id(source_pdf, section_counter, [t for _, t, _ in heading_stack] + [text]); heading_stack.append((level, text, sid))`. Thread `section_id=heading_stack[-1][2] if heading_stack else None` and `section_path=_section_path(heading_stack)` through `flush_prose` → `_emit_prose` (two new parameters) and the table `Chunk(...)`. `_breadcrumb` unpacks the 3-tuple. Note `_emit_prose` is reshaped again in Task 7; add the two parameters now, keep the rest.

- [ ] **Step 3: Granularity**

Add both fields to `EmbedUnit` and `ParentDoc`; in `_group_into_parents` the boundary is `c.section_id` (`bc = c.section_id`), and every constructor copies `section_id=c.section_id, section_path=c.section_path` (parent: from `group[0]`). Test in `test_granularity.py`:

```python
def test_parents_and_units_carry_section_identity():
    chunks = [_chunk("a", "H", 0, "prose", 1, 1), _chunk("b", "H", 1, "prose", 1, 1)]
    chunks = [Chunk(**{**c.__dict__, "section_id": "s_1", "section_path": "s_0/s_1"}) for c in chunks]
    units, parents = build(chunks)
    assert parents[0].section_id == "s_1" and parents[0].section_path == "s_0/s_1"
    assert {u.section_id for u in units} == {"s_1"}
```

(`_chunk` at `test_granularity.py:25-40` must gain the two fields with `None` defaults.)

- [ ] **Step 4: Parents store migration + stitching**

In `parents_store.py`:

```python
SCHEMA_COLUMNS = {"section_id": "TEXT", "section_path": "TEXT"}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a store was created (ALTER TABLE is
    idempotent here because we check PRAGMA first)."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(parents)")}
    for col, typ in SCHEMA_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE parents ADD COLUMN {col} {typ}")
```

`_connect` calls `_migrate(conn)` after `executescript(_SCHEMA)`; the `_SCHEMA` `CREATE TABLE` gains the two columns for fresh stores. `upsert_parents` inserts them; `fetch_parents` and `_extend_one` select them and pass them to `ParentDoc`. In `_extend_one`, the boundary becomes:

```python
def _same_section(r_sid, r_heading, sid, heading) -> bool:
    return r_sid == sid if (sid is not None and r_sid is not None) else r_heading == heading
```

used in both walks (`if not _same_section(r_sid, r_section, sid, section): break`).

Tests in `test_parents_store.py`:

```python
def test_migrate_adds_section_columns_to_an_old_store(tmp_path):
    import sqlite3
    db = tmp_path / "parents.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript("""CREATE TABLE parents (parent_id TEXT PRIMARY KEY, source TEXT NOT NULL,
        text TEXT NOT NULL, section_heading TEXT, page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL, chunk_type TEXT NOT NULL);""")
    conn.execute("INSERT INTO parents VALUES ('p1','old.pdf','t','H',1,1,'prose')")
    conn.commit(); conn.close()
    got = fetch_parents(tmp_path, ["p1"])
    assert got["p1"].section_id is None and got["p1"].section_heading == "H"


def test_extended_stops_at_section_id_boundary_even_with_equal_headings(tmp_path):
    upsert_parents(tmp_path, "x.pdf", [
        _parent_full("p1", "x.pdf", "a" * 10, "Actions", sid="s_k"),
        _parent_full("p2", "x.pdf", "b" * 10, "Actions", sid="s_m"),
    ])
    got = fetch_parents_extended(tmp_path, ["p1"])
    assert got["p1"].text == "a" * 10
```

(`_parent_full` is the existing `_make_parent`-style helper at `:14-32` extended with `sid=None, path=None`.)

- [ ] **Step 5: Chroma metadata**

`_embed_unit_metadata` adds `"section_id": eu.section_id or ""` and `"section_path": eu.section_path or ""`. Extend `test_index_stores_correct_metadata` (`test_indexing.py:29-58`): `assert metadata["section_id"].startswith("s_")`, `assert "/" in metadata["section_path"] or metadata["section_path"].startswith("s_")`, and `metadata["chunker_version"] == "structure_aware-v3"`. Update the two hand-built metadata dicts in `test_search_rerank.py:88` and `test_search_tiers.py:121` only if a test asserts on the version string (they use `"test"`; leave them).

- [ ] **Step 6: Run everything**

Run: `uv run --project sidecar pytest -q` → Expected: all pass. `test_atomic_reindex.py`'s `_make_units` (`:30-44`) must gain `section_id=None, section_path=None`.

- [ ] **Step 7: Commit**

```bash
git add sidecar/chunker.py sidecar/granularity.py sidecar/parents_store.py sidecar/server.py sidecar/tests/
git commit -m "feat(sidecar): section_id/section_path on every unit and parent; parents store migration; structure_aware-v3

..."
```

---

### Task 7: Tight page spans for prose chunks (roadmap 1.5)

`_emit_prose` stamps every chunk cut from a heading-sparse buffer with the whole buffer's page span (`chunker.py:77-78`, `:90-91`); a 9-page run reports pp. 33–41 on each of its chunks. Paragraphs know their page when they enter the buffer; carry that through the split.

**Files:**
- Modify: `sidecar/chunker.py:54-98` (`_emit_prose`), `:149-169` (`flush_prose`), `:215-218` (buffer append)
- Test: `sidecar/tests/test_chunking.py`

**Interfaces:**
- Produces: `_paragraphs(lines: list[tuple[str, int]]) -> list[tuple[str, int, int]]`; `_emit_prose(paragraphs, heading, section_id, section_path, source_pdf, start_ordinal, soft_cap)`; buffer is `list[tuple[str, int]]`.

- [ ] **Step 1: Failing test**

```python
def test_prose_chunks_report_only_the_pages_they_touch():
    # Each page ends with a blank line, as pymupdf4llm output does; without
    # it consecutive pages' lines would form one paragraph.
    pages = [_page(1, "# Part\n\n" + ("alpha " * 150) + "\n\n" + ("beta " * 150) + "\n\n"),
             _page(2, ("gamma " * 150) + "\n\n"), _page(3, ("delta " * 150) + "\n\n")]
    chunks = structure_aware(pages, source_pdf="x.pdf", soft_cap=1000)
    spans = [(c.page_start, c.page_end) for c in chunks]
    assert spans[0] == (1, 1)
    assert spans[-1][0] >= 2
    assert all(ps <= pe for ps, pe in spans)
    assert (1, 3) not in spans
```

Run: `uv run --project sidecar pytest tests/test_chunking.py -q -k pages_they_touch` → Expected: FAIL (`(1, 3)` present).

- [ ] **Step 2: Implement**

```python
def _paragraphs(lines: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """Group buffered (line, page) pairs into paragraphs split on blank
    lines; each paragraph carries the first and last page it touches."""
    out: list[tuple[str, int, int]] = []
    buf: list[str] = []
    ps = pe = None
    for line, page in lines:
        if not line.strip():
            if buf:
                out.append(("\n".join(buf).strip(), ps, pe))
                buf, ps, pe = [], None, None
            continue
        buf.append(line)
        ps = page if ps is None else ps
        pe = page
    if buf:
        out.append(("\n".join(buf).strip(), ps, pe))
    return [p for p in out if p[0]]


def _emit_prose(paragraphs, heading, section_id, section_path, source_pdf, start_ordinal, soft_cap):
    chunks: list[Chunk] = []
    ordinal = start_ordinal
    buf, bps, bpe = "", None, None

    def flush():
        nonlocal buf, bps, bpe, ordinal
        if buf.strip():
            chunks.append(Chunk(text=buf, page_start=bps, page_end=bpe, chunk_type="prose",
                                section_heading=heading, section_id=section_id,
                                section_path=section_path, source_pdf=source_pdf,
                                chunker=CHUNKER_VERSION, ordinal=ordinal))
            ordinal += 1
        buf, bps, bpe = "", None, None

    for para, ps, pe in paragraphs:
        candidate = (buf + "\n\n" + para).strip() if buf else para
        if len(candidate) <= soft_cap:
            buf, bps, bpe = candidate, (ps if bps is None else bps), pe
            continue
        flush()
        buf, bps, bpe = para, ps, pe
    flush()
    return chunks
```

`structure_aware`: `buffer_lines: list[tuple[str, int]]`, append `(line, current_page)`; `flush_prose` calls `_emit_prose(_paragraphs(buffer_lines), _breadcrumb(heading_stack), <sid>, <path>, source_pdf, ordinal, soft_cap)` and drops `buffer_page_start/end`.

- [ ] **Step 3: Run the suite**

Run: `uv run --project sidecar pytest -q` → Expected: all pass, including `test_multi_page_input_tracks_page_range` (`:143-152`, a chunk that really spans pages 1→2 still reports 1→2).

- [ ] **Step 4: Commit**

```bash
git add sidecar/chunker.py sidecar/tests/test_chunking.py
git commit -m "fix(sidecar): prose chunks report the pages they touch, not the whole buffer span (roadmap 1.5)

..."
```

---

### Task 8: `pipeline_version` in the manifest, compared in `/api/index-status`, surfaced in Library settings (roadmap 1.4)

The manifest records nothing about which pipeline indexed a file, so a shipped fix never reaches an indexed library unless the user guesses to re-index. Write `pipeline_version` on every successful index, copy it on rename, compare it in `compute_diff`, count it in the summary, and say it in the Library settings danger zone next to "Re-index all".

**Files:**
- Modify: `sidecar/server.py:709-727` (`ManifestEntry`), `:1569-1763` (`compute_diff`), `:2404-2413`, `:2456-2465`, `:2587-2595`, `:2643-2652`, `:2692-2701`, `:2939-2948`, `:3067-3076` (seven `ManifestEntry(...)` sites), `:2478-2506` (`index_status`)
- Modify: `src-tauri/src/lib.rs:52-62`, `:78-88`; `src/lib/types.ts:46-72`
- Modify: `src/routes/+page.svelte:3961` (SettingsModal props), `src/lib/SettingsModal.svelte:89-109`, `src/lib/LibrarySettings.svelte:9-14`, `:352-365`
- Modify: `evals/engines/v2.py:123-128`
- Test: `sidecar/tests/test_sync.py`, `test_rename_detection.py`, `test_file_operations.py`

**Interfaces:**
- Produces: `ManifestEntry.pipeline_version: str = ""`; `compute_diff(...)` returns an extra key `"outdated": list[str]` (paths whose entry is `up_to_date` or `to_update` with `pipeline_version != PIPELINE_VERSION`) and each `up_to_date`/`to_update` dict carries `"pipeline_version"`; summary gains `"outdated": int`. Rust `IndexStatusResult.outdated: Vec<String>` and `IndexStatusSummary.outdated: u32`, both `#[serde(default)]`. `LibrarySettings` prop `outdatedFileCount: number`.

- [ ] **Step 1: Failing sidecar tests**

In `test_sync.py`:

```python
def test_index_files_records_pipeline_version(client, sample_pdf_path, tmp_path):
    from chunker import PIPELINE_VERSION
    from server import load_manifest
    r = client.post("/api/index-files", json={"pdf_paths": [str(sample_pdf_path)]})
    assert r.status_code == 200
    entry = load_manifest(tmp_path).files[str(sample_pdf_path)]
    assert entry.pipeline_version == PIPELINE_VERSION


def test_index_status_counts_files_indexed_by_an_older_pipeline(client, sample_pdf_path, tmp_path):
    from server import load_manifest, save_manifest
    client.post("/api/index-files", json={"pdf_paths": [str(sample_pdf_path)]})
    m = load_manifest(tmp_path)
    m.files[str(sample_pdf_path)].pipeline_version = "structure_aware-v2/bge-m3"
    save_manifest(tmp_path, m)
    r = client.post("/api/index-status", json={"selected_paths": [str(sample_pdf_path)]})
    body = r.json()
    assert body["summary"]["outdated"] == 1
    assert body["outdated"] == [str(sample_pdf_path)]
    assert body["up_to_date"][0]["pipeline_version"] == "structure_aware-v2/bge-m3"


def test_manifest_backward_compat_missing_pipeline_version(tmp_path):
    from server import IndexManifest, ManifestEntry
    raw = {"version": 1, "files": {"/a.pdf": {"filename": "a.pdf", "mtime": 1.0, "chunk_count": 1,
                                                 "indexed_at": "2026-01-01T00:00:00+00:00"}}}
    m = IndexManifest(**raw)
    assert m.files["/a.pdf"].pipeline_version == ""
```

In `test_rename_detection.py` (next to `test_manifest_backward_compat_content_hash` at `:289`), a sync-rename integration test asserting the renamed entry keeps the old `pipeline_version` value (set it to `"old/x"` before the rename, assert `"old/x"` after — rename copies, never recomputes). In `test_file_operations.py`, the same assertion for `/api/file-rename`.

Run: `uv run --project sidecar pytest tests/test_sync.py tests/test_rename_detection.py tests/test_file_operations.py -q` → Expected: new tests fail.

- [ ] **Step 2: Implement in the server**

`from chunker import CHUNKER_VERSION, EMBEDDING_MODEL, PIPELINE_VERSION` (`server.py:38-39`). `ManifestEntry` gains `pipeline_version: str = ""` after `file_size`. The four fresh-index sites (`/api/index-files`, `/api/reindex-file`, sync add, sync update) add `pipeline_version=PIPELINE_VERSION`. The three rename sites copy it: in `_sync_core` rename, capture `old_entry = manifest.files[old_path_str]` before `del` and pass `pipeline_version=old_entry.pipeline_version`; in `/api/file-rename` and `/api/folder-rename` the old entry is already in hand — same field.

In `compute_diff`, add `outdated: list[str] = []`; both the `to_update` and `up_to_date` dicts gain `"pipeline_version": entry.pipeline_version`, and after each append: `if entry.pipeline_version != PIPELINE_VERSION: outdated.append(path_str)`. Return `"outdated": outdated` alongside the existing keys. In `index_status`, add `"outdated": len(diff["outdated"])` to the summary (the key `stale` is taken — it means selected-but-missing).

- [ ] **Step 3: Run sidecar tests** → `uv run --project sidecar pytest -q` → all pass.

- [ ] **Step 4: Rust and TS types**

`src-tauri/src/lib.rs`: add `#[serde(default)] outdated: u32,` to `IndexStatusSummary` and `#[serde(default)] outdated: Vec<String>,` to `IndexStatusResult`. `src/lib/types.ts`: `outdated: number;` and `outdated: string[];`. Run: `cd src-tauri && cargo test && cargo clippy -- -D warnings` and `npm run check` → clean.

- [ ] **Step 5: Surface it in Library settings**

`src/routes/+page.svelte:3961`: add `outdatedFileCount={indexStatus?.summary?.outdated ?? 0}` to the `SettingsModal` props; `SettingsModal.svelte:89-109`: declare `export let outdatedFileCount = 0;` and forward it to `LibrarySettings`; `LibrarySettings.svelte`: `export let outdatedFileCount: number = 0;` and in the "Re-index all files" row (`:355-360`) append inside `.row-text`:

```svelte
          {#if outdatedFileCount > 0}
            <span class="row-note">
              {outdatedFileCount} {outdatedFileCount === 1 ? 'file was' : 'files were'} indexed
              with an older pipeline — re-index to pick up the current one.
            </span>
          {/if}
```

with `.row-note { display: block; margin-top: 4px; color: var(--text-accent); }` (accent = data/content per the design conventions; no glow, no new hue). Run `npm run check && npm run lint:css` → clean.

- [ ] **Step 6: Eval adapter**

`evals/engines/v2.py` `pipeline_identity()` returns `self._mods["PIPELINE_VERSION"]`; `_import_sidecar` imports it. Run: `uv run --project sidecar-v3 pytest evals/tests -q` → pass.

- [ ] **Step 7: Commit**

```bash
git add sidecar/server.py sidecar/tests/ src-tauri/src/lib.rs src/lib/types.ts src/routes/+page.svelte src/lib/SettingsModal.svelte src/lib/LibrarySettings.svelte evals/engines/v2.py
git commit -m "feat: manifest records pipeline_version; index-status reports outdated files; Library settings says so (roadmap 1.4)

..."
```

---

### Task 9: Persisted FTS5 index for hybrid search (roadmap 1.6, S5)

`lexical.py` rebuilds an in-memory FTS5 table from a full Chroma scan on the first hybrid search and again whenever the chunk count changes (`server.py:3726-3742`), holding every metadata dict and document in RAM. Replace it with a `unit_fts` table in the parents SQLite, written per document inside the same swap as the Chroma upsert, deleted with the source, renamed with the source, cleared with the index. Row text is exactly what the embedder sees (`_embed_text`: sanitised breadcrumb + unit text). Metadata columns let the dense `where` apply as SQL. The `hybrid` flag stays default-off; fusion stays unweighted RRF — Phase 3 sets the weight.

**Files:**
- Modify: `sidecar/parents_store.py` (schema + five functions)
- Modify: `sidecar/lexical.py` (replace `LexicalIndex`/`matches_where`; keep `rrf_fuse`)
- Modify: `sidecar/server.py:1238-1277` (`_atomic_index_pdf`), `:1546-1567` (`delete_source_chunks`), `:2560-2601`, `:2918-2966`, `:3040-3078` (rename flows), `:2832-2896` (`/api/delete-index`), `:2003-2046` (hybrid block), `:3724-3742` (`_get_lexical_index`)
- Test: `sidecar/tests/test_parents_store.py`, `test_search_hybrid.py`, `test_atomic_reindex.py`, `test_sources.py`, `test_file_operations.py`

**Interfaces:**
- Produces (parents_store):
  - `FtsRow = tuple[str, int, str, str, str, str]` = `(chunk_id, ordinal, filename, game_system, parent_id, text)`.
  - `upsert_units_fts(data_dir, source: str, rows: list[FtsRow]) -> None` (delete-by-source then insert).
  - `search_units_fts(data_dir, match: str, k: int, where: dict | None) -> list[str]` (chunk ids, BM25 order).
  - `delete_units_fts_for_source(data_dir, source) -> int`; `rename_source(data_dir, old_source, new_source, new_filename, new_prefix) -> None` (updates `parents.source`, `unit_fts.source/filename`, and `chunk_id = new_prefix || '_' || ordinal`); `clear_all_parents` also clears `unit_fts`; `count_units_fts(data_dir, source=None) -> int`.
  - `where_to_sql(where: dict | None) -> tuple[str, list]` — `""`/`[]` for none; supports `{field: value}`, `{field: {"$in": [...]}}`, `$and`, `$or` over `source`, `filename`, `game_system`; raises `ValueError` otherwise.
- Produces (lexical): `PersistedLexicalIndex(data_dir, collection)` with `search(query, k, where) -> list[str]` and `lookup(ids) -> dict[str, tuple[dict, str]]` (metadata, document from Chroma by id); `fts_match(query) -> str` (tokens OR'd, quoted). `rrf_fuse` unchanged.
- Server: `_atomic_index_pdf` writes FTS rows after the swap; rename flows build new ids as `f"{chunk_id_prefix(new_path)}_{m['chunk']}"` (ordinal, not list position) so Chroma ids and FTS ids agree.

- [ ] **Step 1: Failing store tests**

```python
def test_fts_rows_follow_units_per_source(tmp_path):
    upsert_units_fts(tmp_path, "a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "Combat\n\nthe owlbear has THAC0 15"),
                                         ("a_1", 1, "a.pdf", "OSR", "p1", "rounds have phases")])
    upsert_units_fts(tmp_path, "b.pdf", [("b_0", 0, "b.pdf", "5E", "p2", "fireball deals 8d6")])
    assert count_units_fts(tmp_path) == 3
    upsert_units_fts(tmp_path, "a.pdf", [("a_9", 0, "a.pdf", "OSR", "p1", "replaced")])
    assert count_units_fts(tmp_path, "a.pdf") == 1
    assert delete_units_fts_for_source(tmp_path, "b.pdf") == 1
    assert count_units_fts(tmp_path) == 1


def test_fts_search_is_scoped_by_where(tmp_path):
    upsert_units_fts(tmp_path, "/lib/a.pdf", [("a_0", 0, "a.pdf", "OSR", "p1", "owlbear THAC0 15")])
    upsert_units_fts(tmp_path, "/lib/b.pdf", [("b_0", 0, "b.pdf", "5E", "p2", "owlbear AC 13")])
    assert set(search_units_fts(tmp_path, '"owlbear"', 10, None)) == {"a_0", "b_0"}
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"filename": "b.pdf"}) == ["b_0"]
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"source": {"$in": ["/lib/a.pdf"]}}) == ["a_0"]
    assert search_units_fts(tmp_path, '"owlbear"', 10, {"$and": [{"game_system": "5E"}, {"filename": "b.pdf"}]}) == ["b_0"]


def test_where_to_sql_rejects_unknown_operators():
    import pytest
    with pytest.raises(ValueError):
        where_to_sql({"filename": {"$ne": "x"}})
    with pytest.raises(ValueError):
        where_to_sql({"page_start": 3})


def test_rename_source_rewrites_ids_from_ordinals(tmp_path):
    upsert_parents(tmp_path, "/old/a.pdf", [_parent("p1", "/old/a.pdf")])
    upsert_units_fts(tmp_path, "/old/a.pdf", [("h_a_0", 0, "a.pdf", "OSR", "p1", "text"), ("h_a_1", 1, "a.pdf", "OSR", "p1", "more")])
    rename_source(tmp_path, "/old/a.pdf", "/new/b.pdf", "b.pdf", "deadbeef_b")
    assert count_units_fts(tmp_path, "/old/a.pdf") == 0
    assert search_units_fts(tmp_path, '"more"', 5, {"filename": "b.pdf"}) == ["deadbeef_b_1"]
    assert fetch_parents(tmp_path, ["p1"])["p1"].source_pdf == "/new/b.pdf"
```

Run → Expected: `ImportError`.

- [ ] **Step 2: Implement the store side**

Append to `_SCHEMA`:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(
    chunk_id UNINDEXED, ordinal UNINDEXED, source UNINDEXED, filename UNINDEXED,
    game_system UNINDEXED, parent_id UNINDEXED, text,
    tokenize='porter unicode61'
);
```

Functions:

```python
_FTS_FIELDS = {"source", "filename", "game_system"}


def where_to_sql(where: dict | None) -> tuple[str, list]:
    if not where:
        return "", []
    if "$and" in where or "$or" in where:
        op = "$and" if "$and" in where else "$or"
        parts, params = [], []
        for w in where[op]:
            s, p = where_to_sql(w)
            parts.append(f"({s})"); params += p
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


def upsert_units_fts(data_dir: Path, source: str, rows: list[tuple]) -> None:
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("DELETE FROM unit_fts WHERE source = ?", (source,))
        conn.executemany(
            "INSERT INTO unit_fts (chunk_id, ordinal, source, filename, game_system, parent_id, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(cid, ordinal, source, fn, gs, pid, text) for cid, ordinal, fn, gs, pid, text in rows],
        )


def search_units_fts(data_dir: Path, match: str, k: int, where: dict | None) -> list[str]:
    if not data_dir or not match:
        return []
    scope_sql, params = where_to_sql(where)
    sql = "SELECT chunk_id FROM unit_fts WHERE unit_fts MATCH ?"
    if scope_sql:
        sql += f" AND ({scope_sql})"
    sql += " ORDER BY rank LIMIT ?"
    with _txn(data_dir) as conn:
        return [r[0] for r in conn.execute(sql, [match, *params, k]).fetchall()]


def delete_units_fts_for_source(data_dir: Path, source: str) -> int:
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        return conn.execute("DELETE FROM unit_fts WHERE source = ?", (source,)).rowcount


def count_units_fts(data_dir: Path, source: str | None = None) -> int:
    if not data_dir:
        return 0
    with _txn(data_dir) as conn:
        if source is None:
            return conn.execute("SELECT COUNT(*) FROM unit_fts").fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM unit_fts WHERE source = ?", (source,)).fetchone()[0]


def rename_source(data_dir: Path, old_source: str, new_source: str, new_filename: str, new_prefix: str) -> None:
    """Move parents and FTS rows to a renamed file. Chunk ids are rebuilt
    from the stored ordinal so they agree with the ids the rename flow
    writes to Chroma (``f"{prefix}_{ordinal}"``)."""
    if not data_dir:
        return
    with _txn(data_dir) as conn:
        conn.execute("UPDATE parents SET source = ? WHERE source = ?", (new_source, old_source))
        conn.execute(
            "UPDATE unit_fts SET source = ?, filename = ?, chunk_id = ? || '_' || ordinal WHERE source = ?",
            (new_source, new_filename, new_prefix, old_source),
        )
```

`clear_all_parents` adds `conn.execute("DELETE FROM unit_fts")`. Note FTS5 `UPDATE` on an external-content-free table works row by row; the tests pin it.

- [ ] **Step 3: Replace `lexical.py`'s index**

```python
class PersistedLexicalIndex:
    """FTS5 rows live in the parents SQLite (parents_store.unit_fts),
    written at index time; nothing is rebuilt at search time."""

    def __init__(self, data_dir, collection) -> None:
        self._data_dir = data_dir
        self._collection = collection

    def search(self, query: str, k: int, where: dict | None = None) -> list[str]:
        match = fts_match(query)
        if not match:
            return []
        return search_units_fts(self._data_dir, match, k, where)

    def lookup(self, ids: list[str]) -> dict[str, tuple[dict, str]]:
        if not ids:
            return {}
        got = self._collection.get(ids=ids, include=["metadatas", "documents"])
        return {cid: (meta, doc) for cid, meta, doc in zip(got["ids"], got["metadatas"], got["documents"])}


def fts_match(query: str) -> str:
    tokens = _TOKEN_RE.findall(query)
    return " OR ".join(f'"{t}"' for t in tokens)
```

Delete `LexicalIndex` and `matches_where` (nothing else uses them after this task — `grep -rn "matches_where\|LexicalIndex" sidecar/` must return only tests you are rewriting). Keep `rrf_fuse` and `RRF_K`. Update the module docstring: "Persisted FTS5 … (S5 fixed 2026-09)".

- [ ] **Step 4: Server wiring**

`_atomic_index_pdf`, after `upsert_parents(...)`:

```python
    if data_dir:
        upsert_parents(data_dir, str(pdf_path), parents)
        upsert_units_fts(data_dir, str(pdf_path), [
            (f"{new_prefix}_{eu.ordinal}", eu.ordinal, pdf_path.name, game_system,
             eu.parent_id, _embed_text(eu))
            for eu in embed_units
        ])
```

`delete_source_chunks`: also `delete_units_fts_for_source(data_dir, source_path)`. The three rename flows: build ids as `f"{new_prefix}_{m['chunk']}"` (iterate `zip(results["ids"], results["metadatas"])`) and call `rename_source(data_dir, old_path_str, new_path_str, new_path.name, new_prefix)` after the Chroma re-add. `/api/delete-index` already calls `clear_all_parents`. `_get_lexical_index` becomes:

```python
    lexical_index = PersistedLexicalIndex(data_dir, collection)

    def _get_lexical_index() -> PersistedLexicalIndex:
        return lexical_index
```

(remove `lexical_cache`/`lexical_lock`; leave the spell-corrector cache as is). Hybrid block:

```python
            lex_rows: dict[str, tuple[dict, str]] = {}
            if knobs.hybrid:
                lex = get_lexical_index()
                lex_ids = lex.search(query_text, k=request.n_results * 10, where=query_kwargs.get("where"))
                rankings.append(lex_ids)
                lex_rows = lex.lookup([cid for cid in lex_ids if cid not in dense_best])
            ...
                elif cid in lex_rows:
                    meta, doc = lex_rows[cid]
                    fused_metadatas.append(meta); fused_distances.append(1.0); fused_docs.append(doc)
                else:
                    continue   # FTS row whose Chroma twin is gone mid-reindex
```

- [ ] **Step 5: Rewrite the hybrid tests**

`test_search_hybrid.py`: replace the `LexicalIndex` unit tests (`:26-77`) with `fts_match` tests; replace the `matches_where` tests (`:100-135`) with the `where_to_sql` tests from Step 1 (move them here or keep in test_parents_store — one place). The `hybrid_client` fixture (`:151-172`) adds the two chunks to Chroma **and** calls `upsert_units_fts(tmp_path, "/corpus/rules.pdf", [("c-prose", 0, "rules.pdf", "OSR", "p-prose", "...")])` / same for `monsters.pdf` (`data_dir` is `tmp_path` — take it from the `client` fixture's `tmp_path`). Keep `test_hybrid_bm25_only_candidate_has_floor_relevance` and `test_hybrid_respects_source_scope` as they are — they must still pass. Add:

```python
def test_first_hybrid_search_does_not_scan_the_collection(hybrid_client, test_collection, monkeypatch):
    calls = []
    orig = type(test_collection).get
    def spy(self, **kw):
        calls.append(kw)
        return orig(self, **kw)
    monkeypatch.setattr(type(test_collection), "get", spy)
    _search(hybrid_client, query="owlbear THAC0", hybrid=True)
    assert all("ids" in kw for kw in calls)      # only id lookups, never a paginated scan
```

`test_atomic_reindex.py`'s `_RecordingCollection` needs no change (FTS writes go to `tmp_path`); add one assertion to `test_successful_swap` (`:217`): `count_units_fts(tmp_path, "…source…") == n_units`. `test_sources.py::test_delete_source` adds `count_units_fts(tmp_path) == 0` after delete. `test_file_operations.py` rename test adds `count_units_fts(tmp_path, old) == 0 and count_units_fts(tmp_path, new) > 0`.

- [ ] **Step 6: Run everything**

Run: `uv run --project sidecar pytest -q` → all pass. Then a timing check on the eval index (no Ollama needed for FTS alone):

```bash
uv run --project sidecar python -c "
import time, sys; sys.path.insert(0,'sidecar')
from pathlib import Path; from parents_store import search_units_fts
d=Path('evals/.eval_data/v2'); t=time.perf_counter()
print(search_units_fts(d,'\"owlbear\" OR \"thac0\"',150,None)[:3], round((time.perf_counter()-t)*1000,1),'ms')"
```

Expected: ≤ 50 ms (the roadmap's first-search bar) — note the number in the commit. If `evals/.eval_data/v2` predates this task it has no `unit_fts` rows; that is fine, Task 10's reindex fills it.

- [ ] **Step 7: Commit**

```bash
git add sidecar/parents_store.py sidecar/lexical.py sidecar/server.py sidecar/tests/
git commit -m "feat(sidecar): persisted FTS5 unit index written with the swap; rename/delete/clear keep it aligned (roadmap 1.6, S5)

..."
```

---

### Task 10: Reindex the eval corpus; baseline `v2-headings`; gates; blind sheet; roadmap **[Jerome runs]**

**Files:**
- Create: `evals/baselines/<date>-v2-extraction.{json,md}`, `<date>-v2-headings.{json,md}` (+ gitignored `.results.json`, `.html`, `.blind.html`), `<date>-v2-headings.blind.{json,md}` after Jerome scores
- Modify: `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §5 (gate wording), §8 (two rows); `evals/README.md`

- [ ] **Step 1: Extraction gate (executor, ~3 min, no Ollama)**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite extraction --gate evals/baselines/2026-08-31-v2-extraction.json`
Expected: no per-page regression (exit 0). Sanitised headings can only raise `content_recall` on pages whose golden text has the intact heading. Commit the new `<date>-v2-extraction.{json,md}`.

- [ ] **Step 2: Breadcrumb gate on the final code (executor)**

Run: `uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa --gate evals/baselines/<task4-date>-v2-breadcrumb-qa.json`
Expected: no rate rose vs Task 4 (Tasks 5–9 do not touch headings; this proves it).

- [ ] **Step 3: Retrieval baseline `v2-headings` [Jerome runs, Ollama up, ~40 min]**

```bash
OLLAMA_CONTEXT_LENGTH=8192 uv run --project sidecar python -m evals.run_eval --engine v2 --baseline headings \
    --gate evals/baselines/2026-09-02-v2-phase0b.json
```

Expected: gate passes (no scope's MRR@5 / recall@3 below phase0b); single and uncued expected up (v3's ladder put +0.205 on heading quality); cued not down. Record `by_scope` and `cross_page`, `top3_fit@8k`, p50 in the §8 row. If the gate fails, do **not** loosen it: run the per-query diff (`/Users/jay/.claude/jobs/d5944035/tmp/diff_phase0b.py` pattern — copy it into `evals/retrieval/diff_baselines.py` if it is still useful) and classify each regressed query as (a) breadcrumb now *more* specific and the anchor sits in a sibling section, (b) a page-span change moved the anchor page, or (c) ranking noise; report before deciding.

*Outcome 2026-09-12: gate failed on two single-query rows (q041, q063); accepted by controller ruling — see roadmap §8.*

- [ ] **Step 4: Blind sheet [Jerome scores]**

```bash
uv run --project sidecar python -m evals.blind.generate evals/baselines/<date>-v2-headings
cd evals/baselines && nohup python3 -m http.server 8765 >| /tmp/blindserver.log 2>&1 &
```

Jerome scores at `http://localhost:8765/<date>-v2-headings.blind.html`, exports, moves the `.blind.json` into `evals/baselines/`; then `uv run --project sidecar python -m evals.blind.score evals/baselines/<date>-v2-headings`. Bars: κ ≥ 0.70, human single ≥ phase0b's 0.87, readable@5 ≥ 0.965 (Task 7 must not have torn more tables — it does not touch tables, so this should hold).

- [ ] **Step 5: Real library [Jerome runs]**

Open the app: Library settings should show "N files were indexed with an older pipeline — re-index". Re-index all. Then `uv run --project sidecar python sidecar/evals/library_probe.py` (the real-library breadcrumb probe): markup ≤ 2 %, furniture roots 0, split letters 0 on the real library; and `uv run --project sidecar python -m evals.run_eval --engine v2 --suite library --data-dir <app data dir>` if `library.yaml` has queries by then.

- [ ] **Step 6: Roadmap + README**

§5: change the "golden extraction gate" row to `no per-page regression vs 2026-08-31-v2-extraction (promotion/cleanup output changes; the pymupdf4llm call does not)` and the "breadcrumb QA, real library" row to record the measured numbers. §8: two rows — `Phase 1 landed <date>` (what changed, `v2-headings` numbers vs phase0b, the blind numbers) and `Heading oracle = the page's own spans` (rationale: the 2026-09-09 probe; reopen if a book's spans are themselves scrambled — then the TOC/vocabulary fallback from the plan's Task 2 notes is the next rule). Also correct the §1.3/§4 "byte-identical" wording. README: "The v2 reference for Phase 2+ is `<date>-v2-headings`; gate against it."

- [ ] **Step 7: Commit**

```bash
git add evals/baselines/<date>-v2-extraction.* evals/baselines/<date>-v2-headings.json evals/baselines/<date>-v2-headings.md evals/baselines/<date>-v2-headings.blind.json evals/baselines/<date>-v2-headings.blind.md docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md evals/README.md
git commit -m "eval(evals): v2 Phase 1 baselines — headings, extraction gate, blind round; roadmap §5/§8

..."
```

---

## Self-review

- **Spec coverage.** 1.1 → Task 2 (+ Task 1's detector so the 0 % is honest). 1.2(a) furniture → Task 4 (singleton signatures, TOC effective depth) + Task 3's lead-in/URL junk rule; (b) stat/caption shapes → Task 3; (c) staleness cap → Task 5 (measured, conditional); (d) TOC depth-1 pinning stays → Task 4 keeps it, relative to the effective depth; (e) sub-modal distinct levels → Task 3. 1.3 → Task 6. 1.4 → Task 8. 1.5 → Task 7. 1.6 → Task 9. 1.7 → Task 10. Junk audit "< 2 % junk roots per book" → Task 4 Step 4's `top_roots` read plus the `furniture_root_rate ≤ 1 %` bar; a dedicated junk-root metric is not added (breadcrumb-qa's `furniture_root` + residue is the committed successor of the v3 ad-hoc audit).
- **Ordering.** Harness first (1), then heading quality in three steps each measured against the previous baseline (2, 3, 4), the measured staleness decision (5), then the schema/version/store work that needs the reindex (6, 7, 8, 9), then the one reindex with all gates (10). Task 6 is the only version bump.
- **Type consistency.** `sanitize` returns `list[tuple[str, sig | None]]` everywhere it is consumed (rows `parts`, `_rewrite_page_md`). `Chunk`/`EmbedUnit`/`ParentDoc` gain the same two optional fields in Task 6; Task 7's `_emit_prose` signature includes them. `FtsRow` order `(chunk_id, ordinal, filename, game_system, parent_id, text)` is the same in `upsert_units_fts`, the server call site and the tests. `PIPELINE_VERSION` is defined once (chunker) and imported by server and the eval adapter.
- **Placeholder scan.** Dates in file names are `<date>`/`<today>` because they are decided at run time, not placeholders for content. The one conditional implementation (Task 5 Step 3) carries its full code. The `1d6` line in Task 3's test is explicitly removed by the step text so no contradictory assertion ships.
- **Known risk.** Task 2's oracle needs the intact heading on the *same page*; the residue section will show whether any book keeps split letters after it (running column titles would). Task 4's singleton rule could demote a legitimate one-off book title to level 2 — acceptable, the next chapter title is the root.
