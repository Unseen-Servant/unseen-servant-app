"""Corpus resolution and integrity gate for the Phase 0 harness.

The corpus itself (``evals/corpus/``, 113 MB of CC/OGL PDFs + references)
is gitignored; only ``evals/corpus.manifest.json`` — the paths, hashes,
and provenance — is committed. This module is what turns that manifest
into a hard guarantee that every run measures the *same* bytes:

- **Resolve** the corpus root across the three environments the spec
  lists (env override → current tree → the main checkout, so a run from
  a git *worktree* — where ignored files don't exist — still finds it).
- **Verify** every PDF against its pinned SHA-256 and *refuse to run* on
  any mismatch. This is the guard against the silent ground-truth drift
  that once left the old eval 30 % wrong (spec §1).
- **Pin** the derived facts the manifest can't be hand-authored with:
  each PDF's ``page_count`` and each reference tree's aggregate
  ``digest`` (SHA-256 of its sorted per-file hashes). First run fills
  them; later runs enforce them. Per-file ref hashes live in
  ``corpus.refs.lock.json`` so a digest mismatch can name *which* files
  changed/appeared/vanished — the response to reference drift differs
  from the response to a corrupt download.

Usage::

    uv run --project sidecar python -m evals.corpus            # verify + pin
    uv run --project sidecar python -m evals.corpus --check    # read-only (CI)

Importable gate for the rest of the harness::

    from evals.corpus import require_corpus
    corpus = require_corpus()          # raises CorpusError on any mismatch
    for doc in corpus.documents:
        engine.index([doc.pdf_path])
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "corpus.manifest.json"
REFS_LOCK_PATH = HERE / "corpus.refs.lock.json"

_CHUNK = 1 << 20


class CorpusError(RuntimeError):
    """Raised when the corpus is missing or fails integrity verification.

    The harness catches this at the top level and exits with the message
    verbatim — it is meant to be the clear, run-stopping error of spec §6.
    """


# -- hashing ----------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _aggregate_digest(per_file: dict[str, str]) -> str:
    """SHA-256 of sorted ``relative path:content hash`` entries.

    Ground-truth references are addressed by path in ``answer_ref``. The
    aggregate must therefore bind both content and tree layout, rather than
    waiting for a content-only mismatch before consulting the lock file.
    """
    joined = "\n".join(f"{path}:{digest}" for path, digest in sorted(per_file.items()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# -- resolution -------------------------------------------------------------


def _main_checkout_corpus() -> Path | None:
    """The main checkout's ``evals/corpus/`` (parent of the common git dir).

    A worktree's ``.git`` is a file pointing elsewhere; ignored files like
    the corpus exist only in the main checkout. ``--git-common-dir`` hops
    there so worktree runs resolve the shared corpus without an env var.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=HERE, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    common = Path(out)
    if not common.is_absolute():
        common = (HERE / common).resolve()
    return common.parent / "evals" / "corpus"


def resolve_corpus_root() -> Path:
    """Locate the corpus, in the order pinned in the manifest.

    ``$LL_EVAL_CORPUS`` (explicit override / CI escape hatch) → this
    tree's ``evals/corpus/`` → the main checkout's ``evals/corpus/``.
    """
    env = os.environ.get("LL_EVAL_CORPUS")
    if env:
        root = Path(env).expanduser()
        if not root.is_dir():
            raise CorpusError(
                f"LL_EVAL_CORPUS is set to '{env}' but that directory does not exist."
            )
        return root.resolve()

    local = HERE / "corpus"
    if local.is_dir():
        return local

    main = _main_checkout_corpus()
    if main and main.is_dir():
        return main

    raise CorpusError(
        "Eval corpus not found. Expected it at 'evals/corpus/' (gitignored) "
        "or set $LL_EVAL_CORPUS to its location. It is not in git — copy it "
        "between machines (see docs/retrieval/2026-08-14-v3-scaffold.md §1)."
    )


# -- model ------------------------------------------------------------------


@dataclass
class Document:
    id: str
    system: str
    root: Path
    pdf_rel: str
    pdf_sha256: str
    ref_glob: str
    ref_digest: str | None = None
    page_count: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def pdf_path(self) -> Path:
        return self.root / self.pdf_rel

    def ref_paths(self) -> list[Path]:
        """Reference files, sorted by POSIX-relative path for determinism."""
        matches = [p for p in self.root.glob(self.ref_glob) if p.is_file()]
        return sorted(matches, key=lambda p: p.relative_to(self.root).as_posix())

    def ref_file_hashes(self) -> dict[str, str]:
        return {
            p.relative_to(self.root).as_posix(): sha256_file(p)
            for p in self.ref_paths()
        }


@dataclass
class DocResult:
    doc_id: str
    pdf_ok: bool
    pdf_detail: str
    ref_ok: bool
    ref_detail: str


@dataclass
class VerifyReport:
    ok: bool
    results: list[DocResult]
    filled: list[str]  # human-readable notes on what was pinned this run

    def raise_if_failed(self) -> None:
        if self.ok:
            return
        lines = ["Corpus integrity check FAILED:"]
        for r in self.results:
            if not r.pdf_ok:
                lines.append(f"  [{r.doc_id}] PDF: {r.pdf_detail}")
            if not r.ref_ok:
                lines.append(f"  [{r.doc_id}] refs: {r.ref_detail}")
        raise CorpusError("\n".join(lines))


class Corpus:
    def __init__(self, root: Path, manifest: dict):
        self.root = root
        self._manifest = manifest
        self.documents = [
            Document(
                id=d["id"],
                system=d.get("system", d["id"]),
                root=root,
                pdf_rel=d["pdf"]["path"],
                pdf_sha256=d["pdf"]["sha256"],
                ref_glob=d["refs"]["glob"],
                ref_digest=d["refs"].get("digest"),
                page_count=d["pdf"].get("page_count"),
                raw=d,
            )
            for d in manifest["documents"]
        ]

    # -- pdf ---------------------------------------------------------------

    def _verify_pdf(self, doc: Document, filled: list[str]) -> tuple[bool, str]:
        if not doc.pdf_path.exists():
            return False, f"missing at {doc.pdf_rel}"
        got = sha256_file(doc.pdf_path)
        if got != doc.pdf_sha256:
            return False, (
                f"SHA-256 mismatch at {doc.pdf_rel}\n"
                f"        expected {doc.pdf_sha256}\n"
                f"        got      {got}"
            )
        if doc.page_count is None:
            pc = _count_pages(doc.pdf_path)
            if pc is not None:
                doc.raw["pdf"]["page_count"] = pc
                doc.page_count = pc
                filled.append(f"{doc.id}: page_count={pc}")
        return True, f"ok ({doc.pdf_sha256[:12]}…, {doc.page_count or '?'} pp)"

    # -- refs --------------------------------------------------------------

    def _verify_refs(
        self, doc: Document, lock: dict, filled: list[str]
    ) -> tuple[bool, str]:
        current = doc.ref_file_hashes()
        if not current:
            return False, f"glob '{doc.ref_glob}' matched no files"
        digest = _aggregate_digest(current)

        if doc.ref_digest is None:
            doc.raw["refs"]["digest"] = digest
            lock[doc.id] = current
            filled.append(f"{doc.id}: refs digest ({len(current)} files)")
            return True, f"pinned {len(current)} files ({digest[:12]}…)"

        if digest == doc.ref_digest:
            lock.setdefault(doc.id, current)  # backfill a missing lock entry
            return True, f"ok ({len(current)} files, {digest[:12]}…)"

        return False, _ref_drift_detail(doc, lock.get(doc.id), current)

    # -- driver ------------------------------------------------------------

    def verify(self, write: bool = True) -> VerifyReport:
        lock = _load_lock()
        filled: list[str] = []
        results: list[DocResult] = []
        ok = True
        for doc in self.documents:
            pdf_ok, pdf_detail = self._verify_pdf(doc, filled)
            # Only hash the reference tree once the PDF is trusted — a bad
            # PDF is already a refuse-to-run, no need to read 1000+ md files.
            if pdf_ok:
                ref_ok, ref_detail = self._verify_refs(doc, lock, filled)
            else:
                ref_ok, ref_detail = True, "skipped (PDF failed)"
            ok = ok and pdf_ok and ref_ok
            results.append(DocResult(doc.id, pdf_ok, pdf_detail, ref_ok, ref_detail))

        if write and ok and filled:
            _write_manifest(self._manifest)
            _write_lock(lock)
        return VerifyReport(ok=ok, results=results, filled=filled)


def _ref_drift_detail(doc: Document, prior: dict | None, current: dict) -> str:
    if prior is None:
        return (
            f"refs digest mismatch and no lock entry to diff against "
            f"(now {len(current)} files). Re-download at the pinned rev or re-pin."
        )
    prior_keys, cur_keys = set(prior), set(current)
    appeared = sorted(cur_keys - prior_keys)
    vanished = sorted(prior_keys - cur_keys)
    changed = sorted(k for k in prior_keys & cur_keys if prior[k] != current[k])
    parts = ["reference drift — ground truth changed:"]

    def _sample(label: str, items: list[str]) -> None:
        if not items:
            return
        shown = ", ".join(items[:5]) + (f", +{len(items) - 5} more" if len(items) > 5 else "")
        parts.append(f"        {label} ({len(items)}): {shown}")

    _sample("changed", changed)
    _sample("appeared", appeared)
    _sample("vanished", vanished)
    return "\n".join(parts)


# -- pdf page count (best effort) -------------------------------------------


def _count_pages(pdf_path: Path) -> int | None:
    """Page count via PyMuPDF. Best-effort: if fitz is absent (corpus.py
    run outside the sidecar env), skip the fill rather than fail — the
    SHA-256 is the integrity gate; page_count is pinned metadata."""
    try:
        import fitz  # PyMuPDF, a sidecar dependency
    except ImportError:
        return None
    with fitz.open(pdf_path) as doc:
        return doc.page_count


# -- persistence ------------------------------------------------------------


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise CorpusError(f"manifest not found at {MANIFEST_PATH}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def _write_manifest(manifest: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _load_lock() -> dict:
    if not REFS_LOCK_PATH.exists():
        return {}
    with open(REFS_LOCK_PATH, encoding="utf-8") as f:
        return json.load(f).get("documents", {})


def _write_lock(documents: dict) -> None:
    payload = {
        "note": (
            "Per-file SHA-256 of each reference tree; the aggregate is "
            "corpus.manifest.json refs.digest. verify() diffs against this "
            "on a digest mismatch to name which files changed. Committed; "
            "machine-maintained — do not hand-edit."
        ),
        "documents": {doc_id: dict(sorted(files.items())) for doc_id, files in documents.items()},
    }
    with open(REFS_LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


# -- public entry points ----------------------------------------------------


def load_corpus() -> Corpus:
    return Corpus(resolve_corpus_root(), load_manifest())


def require_corpus() -> Corpus:
    """Resolve, verify, and return the corpus — the harness's front door.

    Raises :class:`CorpusError` on a missing corpus or any integrity
    failure, so a caller can trust every :class:`Document` it iterates.
    """
    corpus = load_corpus()
    corpus.verify(write=True).raise_if_failed()
    return corpus


def _main(argv: Iterable[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Verify and pin the eval corpus.")
    ap.add_argument(
        "--check", action="store_true",
        help="read-only: verify hashes but do not write filled page counts / digests (CI mode).",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        corpus = load_corpus()
    except CorpusError as exc:
        print(f"✗ {exc}")
        return 1

    print(f"corpus: {corpus.root}")
    report = corpus.verify(write=not args.check)

    for r in report.results:
        pdf_mark = "✓" if r.pdf_ok else "✗"
        ref_mark = "✓" if r.ref_ok else "✗"
        print(f"  {pdf_mark} {r.doc_id:14} PDF  {r.pdf_detail}")
        print(f"  {ref_mark} {'':14} refs {r.ref_detail}")

    if report.filled:
        verb = "would pin" if args.check else "pinned"
        print(f"\n{verb}: " + "; ".join(report.filled))
        if args.check:
            print("(run without --check to write these into the manifest)")

    if report.ok:
        print("\n✓ corpus verified")
        return 0
    print("\n✗ corpus verification FAILED — refusing to run (spec §1)")
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
