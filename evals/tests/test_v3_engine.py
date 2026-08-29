"""The v3 eval engine's backend switch — the seam where a candidate PDF
backend is selected without disturbing the default path."""
from evals.engines.v3 import _import_v3, _rasterizer_name


def test_every_backend_maps_to_a_rasterizer_the_engine_imports():
    """`layout()` takes `rasterizer=rasterize` by default. Handing it None for
    the default backend overrides that default and crashes every v3 run, so
    each backend must name a rasterizer the engine actually imports."""
    mods = _import_v3()
    for backend in ("pymupdf", "pdfium", "pdfplumber"):
        assert _rasterizer_name(backend) in mods


def test_candidate_backends_rasterize_with_pdfium():
    assert _rasterizer_name("pdfium") == "rasterize_pdfium"
    assert _rasterizer_name("pdfplumber") == "rasterize_pdfium"
