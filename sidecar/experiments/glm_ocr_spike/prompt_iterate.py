"""Iterate GLM-OCR prompts against a fixed target page to fix the 4-column table bug.

Usage:
    python prompt_iterate.py --pdf Basic-Fantasy --page 67
    python prompt_iterate.py --pdf Basic-Fantasy --page 67 --variants v1,v2,v3

Writes outputs/{stem}.prompt-{variant}.p{page}.md for each variant plus a
side-by-side summary at outputs/prompt-compare.p{page}.md.

Target bug: on 4-column stat tables (e.g. Beasts of Burden p67), the default
prompt produces a 4-col header but 3-col rows, silently dropping values.
Each variant below adds progressively more explicit structural guidance.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import fitz
import ollama

SPIKE_DIR = Path(__file__).parent
CORPUS_DIR = SPIKE_DIR / "corpus"
OUTPUT_DIR = SPIKE_DIR / "outputs"

# Each variant is a (name, prompt) pair. Variants are cumulative in intent:
# v0 is the current baseline, v1 adds column-count discipline, v2 adds
# verification, v3 emphasizes never-omit, v4 rephrases tables-as-blocks.
PROMPTS: dict[str, str] = {
    "v0_baseline": (
        "Convert this PDF page to clean Markdown. Preserve headings, tables "
        "(as Markdown tables), lists, and stat-block structure. Do not invent "
        "content that is not visible on the page. If the page is blank or "
        "unreadable, return an empty response."
    ),
    "v1_column_count": (
        "Convert this PDF page to clean Markdown. Preserve headings, tables "
        "(as Markdown tables), lists, and stat-block structure.\n\n"
        "CRITICAL TABLE RULES:\n"
        "1. Count the number of data columns in each table BEFORE writing it.\n"
        "2. Every row (header, separator, and data) must have exactly that "
        "many cells. Pad with empty cells if needed, never drop values.\n"
        "3. If a table has a label column on the left (e.g. 'Hit Dice:'), "
        "count it as a column.\n\n"
        "Do not invent content. If the page is blank, return an empty response."
    ),
    "v2_verify_then_emit": (
        "Convert this PDF page to clean Markdown.\n\n"
        "For every table on the page, follow this procedure:\n"
        "a) First, identify the number of columns by counting the header cells.\n"
        "b) For each data row, verify you have emitted exactly that many "
        "cells before moving on. If a cell is empty in the source, emit an "
        "empty cell (``| |``); never merge or drop cells.\n"
        "c) Stat blocks with headers like 'Camel | Donkey | Horse, Draft | "
        "Horse, Riding' have one label column plus one column per entity — "
        "treat them as (N+1)-column tables.\n\n"
        "Preserve headings, lists, and prose. Do not invent content. If the "
        "page is blank, return an empty response."
    ),
    "v3_never_omit": (
        "Transcribe this PDF page to Markdown with strict fidelity.\n\n"
        "Rules:\n"
        "- Never omit a value. If you see N numbers on a row, emit all N.\n"
        "- Tables: the number of cells in every row must match the header. "
        "For a stat block with a label column and K entity columns, every "
        "row must have K+1 cells.\n"
        "- Before finalizing each table row, recount: does this row have the "
        "same number of `|` separators as the header? If not, fix it.\n"
        "- If you cannot read a value, write `?` — do not silently drop it.\n"
        "- Do not invent content. Do not add commentary.\n\n"
        "If the page is blank, return an empty response."
    ),
    "v4_tables_as_blocks": (
        "Convert this PDF page to clean Markdown. Preserve prose, headings, "
        "and lists normally.\n\n"
        "Tables need special care. For each table:\n"
        "1. First list the column headers on one line, separated by `|`.\n"
        "2. Then write the separator row `| --- | --- | ... |` with the "
        "same count.\n"
        "3. Then each data row with the SAME cell count as the header.\n"
        "4. Stat blocks (rows like 'Armor Class: 13 13 13 13') are tables "
        "where the left label is the first column and each number is its "
        "own subsequent column. Count the numbers and the label: that is "
        "your column count. Every row in the stat block uses that count.\n\n"
        "Do not invent content. If the page is blank, return an empty response."
    ),
    "v5_layout_aware": (
        "This page is from a tabletop RPG rulebook. The body text is typically "
        "laid out in two columns, but tables, stat blocks, and images often "
        "span the full width of the page across both columns.\n\n"
        "Convert the page to clean Markdown:\n"
        "- For prose, follow the two-column reading order (left column "
        "top-to-bottom, then right column top-to-bottom).\n"
        "- Tables and stat blocks span the full page — read them across the "
        "entire width before moving on. Render them as Markdown tables, "
        "preserving every column and every value.\n"
        "- Preserve headings and lists.\n\n"
        "Do not invent content that is not visible on the page. If the page "
        "is blank or unreadable, return an empty response."
    ),
}


def _render_page_png(doc: fitz.Document, page_index: int, dpi: int) -> bytes:
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


def _find_pdf(stem_fragment: str) -> Path:
    for p in sorted(CORPUS_DIR.glob("*.pdf")):
        if stem_fragment.lower() in p.stem.lower():
            return p
    raise SystemExit(f"No PDF in {CORPUS_DIR} matches {stem_fragment!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="stem substring, e.g. 'Basic-Fantasy'")
    ap.add_argument("--page", type=int, required=True, help="1-indexed page number")
    ap.add_argument("--variants", default=",".join(PROMPTS.keys()),
                    help="comma-separated variant names")
    ap.add_argument("--model", default="glm-ocr")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    pdf_path = _find_pdf(args.pdf)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in variants if v not in PROMPTS]
    if unknown:
        raise SystemExit(f"Unknown variant(s): {unknown}. Known: {list(PROMPTS)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        png = _render_page_png(doc, args.page - 1, args.dpi)
    finally:
        doc.close()

    client = ollama.Client()
    results: list[tuple[str, float, str]] = []
    for name in variants:
        prompt = PROMPTS[name]
        print(f"\n=== {name} ===")
        t0 = time.perf_counter()
        try:
            resp = client.chat(
                model=args.model,
                messages=[{"role": "user", "content": prompt, "images": [png]}],
            )
            text = (resp.get("message", {}) or {}).get("content", "") or ""
        except Exception as e:
            text = f"<!-- error: {e} -->"
        dt = time.perf_counter() - t0
        out_path = OUTPUT_DIR / f"{pdf_path.stem}.prompt-{name}.p{args.page}.md"
        out_path.write_text(text, encoding="utf-8")
        results.append((name, dt, text))
        print(f"  {dt:.1f}s, {len(text)} chars -> {out_path.name}")

    summary = [f"# Prompt iteration — {pdf_path.stem} p{args.page}\n"]
    for name, dt, text in results:
        summary.append(f"\n## {name} ({dt:.1f}s, {len(text)} chars)\n")
        summary.append("```markdown\n")
        summary.append(text.rstrip() + "\n")
        summary.append("```\n")
    (OUTPUT_DIR / f"prompt-compare.p{args.page}.md").write_text(
        "".join(summary), encoding="utf-8"
    )
    print(f"\nWrote prompt-compare.p{args.page}.md")


if __name__ == "__main__":
    main()
