# GLM-OCR extraction spike — FINDINGS

**Verdict: no-go on GLM-OCR as a production PDF extractor for #93.**

Recommend redirecting effort to #115 (chunker improvements) and adopting
**PyMuPDF** as the extraction default (informing #100). GLM-OCR has a
capability limit on wide tables — the exact content type #93 was supposed
to fix — and the limit is not prompt-tunable.

Spike date: 2026-04-20. Dates, numbers, and paths refer to the state of
this directory on that date.

---

## Environment

- Model: `glm-ocr` (1.1B, F16 quantization) via Ollama 0.15.5
- Embedding (for planned step 5): `nomic-embed-text` (already in use)
- Rasterization: PyMuPDF (fitz), 150 DPI default, PNG bytes → `ollama.chat`
- Python 3.14, macOS (darwin)

---

## Corpus

3 PDFs under `corpus/` (gitignored):

- `Basic-Fantasy-RPG-Rules-r142.pdf`
- `Black-Flag-Roleplaying.pdf`
- `SRD_CC_v5.1.pdf`

Scanned-PDF category dropped — the user's actual library is not scanned.

---

## What we measured

Four extractors over a set of hand-picked pages (stat blocks, equipment
tables, spell lists, multi-column prose):

| Extractor | Purpose |
|---|---|
| `pypdf` | Current production baseline |
| `pymupdf` | Fast alternative, plain text |
| `pymupdf-layout` | PyMuPDF with column-bucket heuristic from block geometry |
| `glm-ocr@150` | VLM (the proposal under test) |

Outputs live under `outputs/` as `{pdf_stem}.{extractor}{tag}.{md|txt}`
with `<!-- page N -->` markers for visual alignment with the source PDF.

---

## Key finding — GLM-OCR silently corrupts wide tables

This is the finding that decides the verdict.

### Page 67, Basic Fantasy — Beasts of Burden (4-entity stat block)

Ground truth, extracted via `page.get_text("dict")` span geometry:

```
Hit Dice: 2 | 2 | 3 | 2
XP:       75 | 75 | 145 | 145
```

GLM-OCR (baseline prompt) output:

```
| Hit Dice: | 2 | 2 | 2 |      ← drops Draft Horse's "3"
| XP:       | 75 | 75 | 145 |  ← drops Riding Horse's "145"
```

The header line correctly declares 4 columns. The data rows silently emit 3.
The Markdown **looks authoritative** — a GM asking "what's the Hit Dice of a
Draft Horse?" would get the Riding Horse's value with no indication anything
was dropped.

The adjacent 3-entity table (War Horse / Mule / Pony) on the same page
rendered perfectly. The adjacent Ant table (3 entities) rendered perfectly.

### Page 85, Basic Fantasy — Cloud Dragon Age Table (7-column)

Ground truth:

```
Claw: 1d6 | 1d6 | 1d6 | 2d4 | 2d4 | 2d6 | 2d8
Bite: 3d6 | 4d6 | 5d6 | 6d6 | 6d6 | 7d6 | 7d6
```

GLM-OCR output:

```
Claw 1d6 1d6 1d6 2d4 2d6 2d8      ← 6 values, drops one (the repeated 2d4)
Bite 3d6 4d6 5d6 6d6 7d6 7d6      ← 6 values, drops one (the repeated 6d6)
```

Also on this table, GLM-OCR abandoned Markdown table syntax entirely —
no `|` separators in the body — even though it produced clean tables on
p67. Two failure classes compound: structure loss *and* data loss.

### The pattern

**Adjacent cells with visually similar values get collapsed.** Repeated
`13`s on the Armor Class row. Repeated `1d6`s on the Claw row. Repeated
dashes on the Level 5/6 rows. The risk scales with column count and with
cell-value repetition — both of which are characteristic of stat blocks
and random tables, i.e. exactly the content we'd care about.

### pypdf vs GLM-OCR on the same table

```
pypdf:   Hit Dice: 2 2 3 2        ← correct values, ugly, no table structure
glm-ocr: | Hit Dice: | 2 | 2 | 2 | ← wrong values, clean table
```

For retrieval against a semantic search index, **correct-ugly beats
wrong-clean** — the wrong value is likely to be retrieved as confidently
as a right one.

---

## Prompt iteration — 6 variants, none fixed it

Harness: `prompt_iterate.py`. Target: p67 (Beasts of Burden).

| Variant | Strategy | 4-col table outcome |
|---|---|---|
| `v0_baseline` | Current default prompt | Drops column silently |
| `v1_column_count` | "Count columns, pad with empty cells" | Drops column silently (identical output to v0) |
| `v2_verify_then_emit` | "Verify cell count per row" | **Hallucinates** plausible values to pad rows (worst outcome) |
| `v3_never_omit` | Strict fidelity rules, write `?` if unreadable | Skips tables entirely; emits only prose |
| `v4_tables_as_blocks` | Explicit procedural table format | Skips tables entirely |
| `v5_layout_aware` | Mentions two-column prose + full-width tables | Identical output to v0 |

All five variants verbatim at `prompt_iterate.py:17-100` and outputs at
`outputs/Basic-Fantasy-RPG-Rules-r142.prompt-*.p67.md`.

**Interpretation.** The full plausibility range of prompt strategies
produces one of three behaviors: drop (v0/v1/v5), hallucinate (v2), or
abandon tables (v3/v4). This is a model capability limit, not a prompting
limit. v2's hallucination is the most dangerous outcome — invented
values (`Fighter: 2`, `Wild 10d10`, `80' (10')`) that look exactly like
real stat-block content.

---

## Hallucinations (outside of tables)

Spot-checked on cover pages and narrative spreads:

- GLM-OCR transcribes artwork signatures as stray text (e.g. cover-art
  artist credit "Luigi Castellani" emitted into the body as "Kiigi
  Castellani" — both misspelled and injected into an unrelated page).
- Prose passages match the source faithfully in sampling so far;
  hallucinations outside table cells appear rare.

The in-table hallucinations from v2 are the disqualifying finding, not
cover-art drift.

---

## Performance

Per-page latency (p50), averaged across 12 hand-picked pages per PDF
(from `timings.json` and `timings.bf-equip.json`):

| Extractor | p50 seconds / page | Ratio vs pymupdf |
|---|---|---|
| pymupdf | 0.003–0.018 | 1× |
| pypdf | 0.013–0.058 | ~3–10× |
| pymupdf-layout | 0.009–0.068 | ~3–20× |
| glm-ocr@150 | 17.4–23.6 | **~1000–5000×** |

Projection at observed ~20s/page for GLM-OCR:

- 1,000-page library: ~5.5 hours
- 10,000-page library: ~55 hours (unacceptable for target users)

pymupdf at ~0.01s/page handles a 10,000-page library in ~100 seconds.

One anomaly: the `stat1.json` run recorded 354s/page total (vs ~22s/page
per-page), likely caused by Ollama unloading the model between PDFs.
Cold-start cost would need to be measured for a realistic multi-PDF
workload if GLM-OCR were kept in any form.

DPI sweep was not executed — the column-drop bug disqualified GLM-OCR
before we got to it. Higher DPI might help by giving the model more
pixels per column, but at this point it's not worth the spike time to
find out; even if it helped, the ~20s/page floor remains.

---

## Where PyMuPDF lands (answer to #100)

PyMuPDF at plain `get_text("text")` is **faster than pypdf**, **cheaper
to install** (single wheel), and produces comparable text quality. It
doesn't solve the table-structure problem — wide stat blocks still come
out as column-interleaved lines — but neither does pypdf, and PyMuPDF
delivers the text ~3–10× faster.

The layout-aware variant (`extract_pymupdf_layout.py`) using
`get_text("dict")` with a column-bucket heuristic did not meaningfully
improve table output. True table reconstruction would need y-coordinate
row clustering — that belongs in #115, not here.

**Recommendation: swap pypdf → pymupdf as the default extractor.** Low
risk, modest win. Doing this alone would also close #100.

---

## Chunker coupling (answer to #115)

The step 5 blind retrieval-quality experiment was **not executed** —
the step 3 findings (column drops + no prompt fix) made it moot.
Indexing knowingly-wrong table data against a semantic search index
would produce authoritative-looking wrong answers; there is no chunker
sophistication that rescues that.

The Markdown-aware chunker probe is likewise unexecuted. If we return
to VLM extraction later with a more capable model, the probe is still
the right experiment to run.

#115 stands on its own merits: even with PyMuPDF, the fixed
1000-char/200-overlap window splits stat blocks mid-row. A
layout-aware chunker (y-clustering for table rows, header-aware
section breaks for prose) would improve retrieval regardless of the
extractor choice.

---

## Recommendation

**Close #93 as no-go with these findings linked.** The proposal was a
binary toggle for GLM-OCR extraction; the finding is that GLM-OCR
produces confidently-wrong output on exactly the content type the
toggle was meant to improve. Reopening is warranted if and when a
larger VLM (7B+) is tested and shown to handle 4+ column tables
correctly.

**Redirect effort to:**

1. **#100 (pypdf alternatives): swap default to PyMuPDF.** Small PR,
   3–5× faster, equivalent text quality, simpler install. No change
   in table quality, but no regression either.
2. **#115 (chunker): prioritize.** A layout-aware chunker operating
   on PyMuPDF block/line geometry is the highest-value next step for
   retrieval quality. Y-coordinate row clustering for tables; header
   detection for section boundaries.

**Do not pursue** a hybrid (pypdf/PyMuPDF default + GLM-OCR fallback
on empty/low-confidence pages). The detection heuristic for "when to
invoke GLM-OCR" would need to identify wide tables — and those are
the exact pages where GLM-OCR performs worst.

---

## Files produced by this spike

All under `sidecar/experiments/glm_ocr_spike/`:

- `extract_pypdf.py`, `extract_pymupdf.py`, `extract_pymupdf_layout.py`,
  `extract_glm_ocr.py` — extractor implementations
- `run_extraction.py` — corpus runner with `--pdf-ranges`, `--page-range`,
  `--dpi`, `--only`, `--tag` flags
- `prompt_iterate.py` — prompt A/B harness for GLM-OCR
- `outputs/timings*.json` — per-run latency data
- `outputs/*.prompt-*.p67.md`, `*.prompt-*.p85.md` — prompt variant outputs
- `outputs/*.glm-ocr@150.*.md`, `*.pypdf.*.txt`, etc. — extraction outputs
  for spot-check pages
- `README.md`, `FINDINGS.md` (this file)

No production code was modified during the spike.
