"""Pipeline adapters: one Engine per pipeline generation."""
from .base import (  # noqa: F401
    Engine,
    IndexReport,
    SearchOptions,
    SearchResponse,
    SearchResult,
)


def get_engine(name: str, **kwargs):
    """Factory used by run_eval's --engine flag."""
    if name == "v2":
        from .v2 import V2Engine

        return V2Engine(**kwargs)
    if name == "v3":
        raise NotImplementedError(
            "the v3 engine lands with sidecar-v3 (plan §4, Phase 2)"
        )
    raise ValueError(f"unknown engine {name!r} (expected 'v2' or 'v3')")
