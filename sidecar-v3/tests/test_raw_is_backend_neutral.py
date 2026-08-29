"""The raw types and the aggregation must not depend on any PDF library —
PyMuPDF is being removed, and a candidate backend that transitively imports it
cannot be evaluated honestly or shipped."""
import subprocess
import sys
from pathlib import Path

PDF_LIBS = ("pymupdf", "fitz", "pdfplumber", "pdfminer", "pypdfium2")

# sidecar-v3/tests/this_file.py -> sidecar-v3, so `import ingest.raw` resolves
# in the child process regardless of the cwd pytest itself was invoked from
# (CI and the documented commands both run pytest from the repo root).
_SIDECAR_V3 = Path(__file__).parent.parent


def _imported_modules(module: str) -> set[str]:
    code = f"import {module}, sys; print(' '.join(sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=_SIDECAR_V3).stdout
    return set(out.split())


def test_raw_imports_no_pdf_library():
    assert not PDF_LIBS_IN(_imported_modules("ingest.raw"))


def PDF_LIBS_IN(modules: set[str]) -> set[str]:
    return {name for name in modules if name.split(".")[0] in PDF_LIBS}
