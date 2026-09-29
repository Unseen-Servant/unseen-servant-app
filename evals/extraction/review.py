"""Generate a local visual inspector for extracted PDF pages."""
from __future__ import annotations

import argparse
import base64
import html
import json
import webbrowser
from pathlib import Path

import pymupdf

from evals.corpus import require_corpus
from evals.run_eval import build_engine


def parse_pages(value: str) -> list[int]:
    pages: set[int] = set()
    for piece in value.split(","):
        lo, sep, hi = piece.strip().partition("-")
        try:
            start, end = int(lo), int(hi if sep else lo)
        except ValueError as exc:
            raise ValueError(f"invalid page range {piece!r}") from exc
        if start < 1 or end < start:
            raise ValueError(f"invalid page range {piece!r}")
        pages.update(range(start, end + 1))
    return sorted(pages)


def _image(page) -> str:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
    return base64.b64encode(pix.tobytes("png")).decode("ascii")


def _native_text(page) -> str:
    """Render PyMuPDF's structured block rows for side-by-side comparison."""
    return "\n\n".join(block[4].strip() for block in page.get_text("blocks") if block[4].strip())


def render(title: str, pages: list[dict], columns: list[str]) -> str:
    rows = []
    for page in pages:
        cells = "".join(
            f"<section><h3>{html.escape(name)}</h3>"
            f"<pre>{html.escape(page['extracted'][name])}</pre></section>"
            for name in columns
        )
        rows.append(
            f"<article><h2>PDF page {page['page']}</h2><div class=grid>"
            f"<figure><img src='data:image/png;base64,{page['image']}'><figcaption>Original PDF</figcaption></figure>"
            f"{cells}"
            f"<section><h3>Native text oracle</h3><pre>{html.escape(page['native'])}</pre></section>"
            "</div></article>"
        )
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>{html.escape(title)}</title><style>
body{{margin:0 auto;max-width:1800px;padding:24px;background:#191919;color:#c9d1d9;font:15px Georgia,serif}}
h1{{color:rgb(182,159,129)}} h2{{margin:30px 0 10px;color:rgb(182,159,129)}} h3{{margin-top:0;color:#8b949e;font-size:13px;text-transform:uppercase}}
.grid{{display:grid;grid-template-columns:minmax(320px,1.1fr) repeat(auto-fit,minmax(240px,1fr));gap:16px;align-items:start}}
figure,section{{margin:0;border:1px solid #323232;background:#232323;padding:10px}} img{{width:100%;height:auto;display:block}}
figcaption{{color:#8b949e;margin-top:7px;font:12px ui-monospace,monospace}} pre{{margin:0;white-space:pre-wrap;word-break:break-word;line-height:1.45;font:12px ui-monospace,monospace}}
@media(max-width:1000px){{.grid{{grid-template-columns:1fr}}}}
</style><h1>{html.escape(title)}</h1><p>Compare the rendered source with each pipeline's extraction and the PDF engine's native text blocks. Engine columns show the <strong>per-page extraction the gate measures</strong>. v2 emits markdown because pymupdf4llm does. This report is local and self-contained.</p>{''.join(rows)}"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", default="v2", help="the pipeline to extract with (v2)")
    ap.add_argument("--doc", required=True, help="document id from corpus.manifest.json")
    ap.add_argument("--pages", required=True, help="1-based pages, e.g. 30,183 or 324-325")
    ap.add_argument("--dump", type=Path, default=None,
                    help="write this run's extraction as JSON, to --load into a later run")
    ap.add_argument("--load", action="append", default=[], metavar="LABEL=PATH",
                    help="merge a --dump from another environment as an extra column; "
                         "repeatable — how a pipeline that needs another environment "
                         "joins the comparison.")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    engines = [name.strip() for name in args.engine.split(",") if name.strip()]
    unknown = [name for name in engines if name != "v2"]
    if unknown or not engines:
        raise SystemExit(f"--engine takes v2, got {args.engine!r}")
    wanted = parse_pages(args.pages)
    corpus = require_corpus()
    doc = next((item for item in corpus.documents if item.id == args.doc), None)
    if doc is None:
        raise SystemExit(f"unknown corpus document {args.doc!r}")
    if wanted[-1] > (doc.page_count or 0):
        raise SystemExit(f"page {wanted[-1]} exceeds {args.doc}'s page count")
    columns, by_engine = [], {}
    for name in engines:
        columns.append(name)
        engine = build_engine(name, None)
        try:
            by_engine[name] = {page.page_number: page.text for page in engine.extract(doc.pdf_path)}
        finally:
            engine.close()
    for spec in args.load:
        label, sep, path = spec.partition("=")
        if not sep:
            raise SystemExit(f"--load wants LABEL=PATH, got {spec!r}")
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        columns.insert(0, label)
        by_engine[label] = {int(k): v for k, v in saved["pages"].items()}

    if args.dump:
        only = columns[-1]
        args.dump.write_text(json.dumps(
            {"label": only, "doc": args.doc,
             "pages": {str(n): by_engine[only].get(n, "") for n in wanted}},
            ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.dump}")

    with pymupdf.open(doc.pdf_path) as pdf:
        inspected = [{"page": number, "image": _image(pdf[number - 1]),
                      "extracted": {label: by_engine[label].get(number, "") for label in columns},
                      "native": _native_text(pdf[number - 1])}
                     for number in wanted]
    stem = "-".join(engines)
    out = args.output or Path(f"evals/baselines/{stem}-{args.doc}-p{'_'.join(map(str, wanted))}.review.html")
    title = f"{' vs '.join(columns)} extraction review: {args.doc}"
    out.write_text(render(title, inspected, columns), encoding="utf-8")
    print(f"wrote {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
