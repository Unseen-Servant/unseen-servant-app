"""Run extractors over every PDF in corpus/ and write outputs/timings.

Usage:
    python run_extraction.py                       # full run, 150 DPI
    python run_extraction.py --page-limit 4        # first 4 pages per PDF
    python run_extraction.py --page-range 60-63    # specific pages (1-indexed, inclusive)
    python run_extraction.py --dpi 100 --dpi 200   # GLM-OCR DPI sweep (step 6)
    python run_extraction.py --only pypdf,pymupdf  # skip GLM-OCR

Extractors: pypdf, pymupdf, pymupdf-layout, glm-ocr
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import extract_glm_ocr
import extract_pymupdf
import extract_pymupdf_layout
import extract_pypdf
from extract_pypdf import ExtractionResult, PageExtraction

SPIKE_DIR = Path(__file__).parent
CORPUS_DIR = SPIKE_DIR / "corpus"
OUTPUT_DIR = SPIKE_DIR / "outputs"

SUFFIX_BY_EXTRACTOR = {
    "pypdf": "txt",
    "pymupdf": "txt",
    "pymupdf-layout": "txt",
}  # glm-ocr handled by label


def _label_suffix(extractor_label: str) -> str:
    if extractor_label.startswith("glm-ocr"):
        return "md"
    return SUFFIX_BY_EXTRACTOR.get(extractor_label, "txt")


def _parse_page_range(spec: str | None) -> tuple[int, int] | None:
    """Parse '60-63' (1-indexed, inclusive) -> (59, 63) as [start, end) 0-indexed slice."""
    if not spec:
        return None
    if "-" not in spec:
        raise SystemExit(f"--page-range expects 'N-M', got {spec!r}")
    lo, hi = spec.split("-", 1)
    lo_i, hi_i = int(lo), int(hi)
    if lo_i < 1 or hi_i < lo_i:
        raise SystemExit(f"--page-range bounds invalid: {spec!r}")
    return (lo_i - 1, hi_i)


def _parse_pdf_ranges(spec: str | None) -> dict[str, list[tuple[int, int]]]:
    """Parse 'stem1=10-20,100-150;stem2=5-15' -> {'stem1': [(9,20),(99,150)], 'stem2': [(4,15)]}."""
    if not spec:
        return {}
    out: dict[str, list[tuple[int, int]]] = {}
    for pdf_spec in spec.split(";"):
        pdf_spec = pdf_spec.strip()
        if not pdf_spec:
            continue
        if "=" not in pdf_spec:
            raise SystemExit(f"--pdf-ranges entry missing '=': {pdf_spec!r}")
        stem, ranges = pdf_spec.split("=", 1)
        stem = stem.strip()
        parsed: list[tuple[int, int]] = []
        for r in ranges.split(","):
            r = r.strip()
            if not r:
                continue
            pr = _parse_page_range(r)
            if pr is None:
                continue
            parsed.append(pr)
        out[stem] = parsed
    return out


def _apply_page_filter(
    pages: list[PageExtraction],
    page_limit: int | None,
    page_range: tuple[int, int] | None,
    pdf_ranges: list[tuple[int, int]] | None = None,
) -> list[PageExtraction]:
    if pdf_ranges:
        keep: list[PageExtraction] = []
        for p in pages:
            if any(lo <= p.page_index < hi for (lo, hi) in pdf_ranges):
                keep.append(p)
        return keep
    if page_range is not None:
        lo, hi = page_range
        return [p for p in pages if lo <= p.page_index < hi]
    if page_limit is not None:
        return pages[:page_limit]
    return pages


def _match_pdf_ranges(pdf_path: Path, pdf_ranges_map: dict[str, list[tuple[int, int]]]) -> list[tuple[int, int]] | None:
    """Match a PDF to its range list by substring of stem."""
    if not pdf_ranges_map:
        return None
    stem = pdf_path.stem
    for key, ranges in pdf_ranges_map.items():
        if key in stem:
            return ranges
    return None


def _write_result(result: ExtractionResult, tag: str = "") -> dict:
    stem = result.pdf_path.stem
    suffix = _label_suffix(result.extractor)
    out_path = OUTPUT_DIR / f"{stem}.{result.extractor}{tag}.{suffix}"
    # Mark page boundaries so humans can line up output with the PDF.
    parts = []
    for p in result.pages:
        parts.append(f"\n<!-- page {p.page_index + 1} -->\n{p.text}")
    out_path.write_text("".join(parts).lstrip(), encoding="utf-8")
    return {
        "pdf": result.pdf_path.name,
        "extractor": result.extractor,
        "pages": len(result.pages),
        "total_seconds": round(result.total_seconds, 3),
        "seconds_per_page_p50": _p(result, 0.5),
        "seconds_per_page_p95": _p(result, 0.95),
        "chars": len(result.full_text),
        "error": result.error,
        "output": str(out_path.relative_to(SPIKE_DIR)),
    }


def _p(result: ExtractionResult, q: float) -> float | None:
    if not result.pages:
        return None
    xs = sorted(p.seconds for p in result.pages)
    idx = min(len(xs) - 1, int(q * len(xs)))
    return round(xs[idx], 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="pypdf,pymupdf,pymupdf-layout,glm-ocr",
                    help="comma-separated subset of extractors to run")
    ap.add_argument("--dpi", action="append", type=int,
                    help="GLM-OCR DPI (repeatable, e.g. --dpi 100 --dpi 150). Default: 150")
    ap.add_argument("--page-limit", type=int, default=None,
                    help="first N pages per PDF. Mutually exclusive with --page-range.")
    ap.add_argument("--page-range", default=None,
                    help="1-indexed inclusive range like 60-63. Applied per PDF.")
    ap.add_argument("--pdf-ranges", default=None,
                    help="per-PDF ranges: 'stem1=10-20,100-150;stem2=5-15,60-80'. "
                         "Matches on PDF stem substring. Mutually exclusive with --page-range.")
    ap.add_argument("--tag", default="",
                    help="suffix appended to output filenames (e.g. '.pages60-63').")
    ap.add_argument("--model", default=extract_glm_ocr.DEFAULT_MODEL)
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    requested = {e.strip() for e in args.only.split(",") if e.strip()}
    dpis = args.dpi or [extract_glm_ocr.DEFAULT_DPI]
    page_range = _parse_page_range(args.page_range)
    pdf_ranges_map = _parse_pdf_ranges(args.pdf_ranges)
    opts_set = sum(x is not None and x != {} for x in (args.page_limit, page_range, pdf_ranges_map or None))
    if opts_set > 1:
        raise SystemExit("Pass at most one of --page-limit, --page-range, --pdf-ranges.")

    pdfs = sorted(CORPUS_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs in {CORPUS_DIR}. Add files and re-run.")

    timings: list[dict] = []
    for pdf in pdfs:
        print(f"\n=== {pdf.name} ===")
        pdf_ranges = _match_pdf_ranges(pdf, pdf_ranges_map)
        if pdf_ranges_map and pdf_ranges is None:
            print(f"  (skipped — no --pdf-ranges entry matches stem)")
            continue

        if "pypdf" in requested:
            r = extract_pypdf.extract(pdf)
            r.pages[:] = _apply_page_filter(r.pages, args.page_limit, page_range, pdf_ranges)
            timings.append(_write_result(r, args.tag))
            print(f"  pypdf          : {r.total_seconds:.2f}s, {len(r.full_text)} chars, err={r.error}")
        if "pymupdf" in requested:
            r = extract_pymupdf.extract(pdf)
            r.pages[:] = _apply_page_filter(r.pages, args.page_limit, page_range, pdf_ranges)
            timings.append(_write_result(r, args.tag))
            print(f"  pymupdf        : {r.total_seconds:.2f}s, {len(r.full_text)} chars, err={r.error}")
        if "pymupdf-layout" in requested:
            r = extract_pymupdf_layout.extract(pdf)
            r.pages[:] = _apply_page_filter(r.pages, args.page_limit, page_range, pdf_ranges)
            timings.append(_write_result(r, args.tag))
            print(f"  pymupdf-layout : {r.total_seconds:.2f}s, {len(r.full_text)} chars, err={r.error}")
        if "glm-ocr" in requested:
            for dpi in dpis:
                if pdf_ranges:
                    # Only OCR pages up to the max hi, then filter to the union of ranges.
                    max_hi = max(hi for (_, hi) in pdf_ranges)
                    r = extract_glm_ocr.extract(
                        pdf, model=args.model, dpi=dpi, page_limit=max_hi,
                    )
                    r.pages[:] = _apply_page_filter(r.pages, None, None, pdf_ranges)
                elif page_range is not None:
                    r = extract_glm_ocr.extract(
                        pdf, model=args.model, dpi=dpi, page_limit=page_range[1],
                    )
                    r.pages[:] = [p for p in r.pages if page_range[0] <= p.page_index < page_range[1]]
                else:
                    r = extract_glm_ocr.extract(
                        pdf, model=args.model, dpi=dpi, page_limit=args.page_limit,
                    )
                timings.append(_write_result(r, args.tag))
                print(f"  {r.extractor:14s}: {r.total_seconds:.2f}s, {len(r.full_text)} chars, err={r.error}")

    timings_path = OUTPUT_DIR / f"timings{args.tag}.json"
    timings_path.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"\nWrote {timings_path.relative_to(SPIKE_DIR)}")


if __name__ == "__main__":
    main()
