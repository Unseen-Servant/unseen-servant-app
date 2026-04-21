# GLM-OCR extraction spike

Time-boxed investigation comparing **pypdf** (current), **PyMuPDF**, and **GLM-OCR** (via Ollama) for PDF text extraction quality. Tracks issues [#93](https://github.com/Unseen-Servant/unseen-legend-lore/issues/93), [#100](https://github.com/Unseen-Servant/unseen-legend-lore/issues/100), and [#115](https://github.com/Unseen-Servant/unseen-legend-lore/issues/115).

> **Outcome: no-go on GLM-OCR.** See [FINDINGS.md](FINDINGS.md) for the full verdict, evidence, and redirects to #100 (swap to PyMuPDF) and #115 (layout-aware chunker). This directory is kept as a historical record so the finding is reproducible.

Everything in this directory is **throwaway experimental code**. Do not import from `sidecar/server.py`; do not ship any of this.

## Actual vs planned

The plan below (steps 3–8) was adjusted mid-spike:

- Scanned-PDF category was dropped — the user's library doesn't include scanned documents.
- `extract_pymupdf_layout.py` was added mid-spike to probe whether column-aware block geometry helps; it didn't meaningfully, but the script is kept for reference.
- `prompt_iterate.py` was added to A/B prompt variants against the column-drop bug.
- Steps 5 (blind retrieval scoring) and 6 (DPI sweep) were **not executed** — step 4's findings made them moot. See FINDINGS.md §"Chunker coupling" for the reasoning.

## Prerequisites

```bash
# From repo root
cd sidecar
source .venv/bin/activate   # or however you enter the sidecar venv
pip install pymupdf          # NOT added to requirements.txt during the spike
ollama pull glm-ocr          # ~2.2 GB
ollama show glm-ocr --modelfile | head -5   # record digest for FINDINGS.md
```

## Layout

```
glm_ocr_spike/
  corpus/                    # PDFs to evaluate (gitignored — do not commit copyrighted material)
  outputs/                   # extraction results + timings (gitignored)
  extract_pypdf.py           # mirrors the production pypdf path
  extract_pymupdf.py         # PyMuPDF text extraction (cheaper baseline)
  extract_pymupdf_layout.py  # column-aware variant via get_text("dict")
  extract_glm_ocr.py         # rasterize + ollama.chat(model="glm-ocr")
  run_extraction.py          # CLI runner for all extractors
  prompt_iterate.py          # A/B prompt variants against a target page
  FINDINGS.md                # go/no-go recommendation
```

## Corpus

Populate `corpus/` with 5–8 PDFs covering:

- Text-heavy prose (lore)
- Dense tables (encounter tables, equipment lists)
- Stat blocks (monsters, NPCs)
- Multi-column layout (typical rulebook page)
- Scanned / image-based PDF (where pypdf returns empty today)

Total ~50–100 pages keeps a full GLM-OCR pass in coffee-break range.

## Running

```bash
cd sidecar/experiments/glm_ocr_spike

# Step 3 — spot-check (fast, first 4 pages only, all three extractors)
python run_extraction.py --page-limit 4

# Step 4 — full corpus, default 150 DPI
python run_extraction.py

# Step 6 — DPI sweep on GLM-OCR only
python run_extraction.py --only glm-ocr --dpi 100 --dpi 150 --dpi 200
```

Outputs land in `outputs/{pdf_stem}.{extractor}.{txt|md}` plus `timings.json`.

## Workflow (mirrors the plan)

1. **Step 3 — premise check.** Run with `--page-limit 4`, open the GLM-OCR `.md` files next to the PDF pages, and decide whether the output is materially better than pypdf on tables/stat blocks. **If it is clearly worse, stop here** and write a no-go `FINDINGS.md`.
2. **Step 4 — full corpus + hallucination audit.** Run without `--page-limit`. Manually check 3–4 GLM-OCR pages against the source images for fabricated content. Record in `outputs/hallucination_audit.md`.
3. **Step 5 — blind retrieval scoring.** Write `evaluate.py`: 25–30 queries weighted toward tables/stat blocks/scanned pages, index each extraction into in-memory ChromaDB with `nomic-embed-text`, score blind (shuffled top-5 snippets), compute MRR + recall@5 + mean readability. Include an MD-aware-chunker variant for GLM-OCR output.
4. **Step 6 — perf + DPI sweep.** Re-use timings; add peak-RSS measurement via `/usr/bin/time -l`.
5. **Step 7 — FINDINGS.md.** Headline verdict + evidence.
6. **Step 8 — review with user.**

## Notes on reproducibility

- Record the output of `ollama show glm-ocr --modelfile` in FINDINGS.md so re-runs after model updates are comparable.
- GLM-OCR is called one page per `ollama.chat` invocation. Batching is an interesting follow-up but risks context-window surprises; keep single-page for the spike.
- The chunker used in step 5 is imported verbatim from [sidecar/server.py:88-99](../../server.py#L88-L99). Changing it would conflate extraction quality with chunking quality — the whole point is to isolate extraction.
