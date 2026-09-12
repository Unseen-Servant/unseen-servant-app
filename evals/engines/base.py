"""Engine-agnostic contract for the Phase 0 harness.

An Engine wraps one retrieval pipeline (v2 = today's ``sidecar/``,
v3 = ``sidecar-v3/`` once it exists) behind the same three verbs —
``index``, ``warmup``, ``search`` — so the harness, the graders, and the
baselines never know which pipeline they are talking to. The grading side
(``evals/retrieval/``) consumes :class:`SearchResponse` only.

Design rules (from docs/roadmap/2026-08-13-pipeline-rebuild-plan.md and
docs/retrieval/2026-08-14-v3-scaffold.md):

- Knobs are ALWAYS explicit. The harness pins every pipeline flag in
  :class:`SearchOptions` rather than inheriting server-side settings, so a
  baseline measures what it claims to measure (the lesson written into
  sidecar/evals/run_eval.py and the 2026-07-11 search-settings design).
- ``n_results`` defaults to 25, the UI's first page size, while metrics
  are graded @10 — quality must be gated at the page size the app
  actually sends (the #340 lesson).
- ``payload_chars`` is a first-class measurement: it is the small-model
  context-budget metric (plan §3.5 — a Qwen3.5-4B-class consumer cannot
  digest today's ~24k-char responses).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass
class SearchOptions:
    """Explicit pipeline knobs for one search call.

    Defaults mirror the v2 production defaults so a bare
    ``SearchOptions()`` measures the shipped configuration. Engines that
    lack a knob (e.g. v3 before its reranker exists) must ignore it
    loudly (log once), never silently.
    """

    n_results: int = 25          # UI first-page size; metrics graded @10
    rerank: bool = True          # production default (search-settings design)
    hybrid: bool = False         # experimental flag, default-off in v2
    spell_correction: bool = True
    variant_expansion: bool = False
    source_filter: str | None = None   # filename (v2 semantics)
    game_system: str | None = None
    collection: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # engine-specific


@dataclass
class SearchResult:
    """One result, normalized across engines.

    ``raw`` keeps the engine's untouched result dict so graders can reach
    engine-specific fields (e.g. a future v3 ``bbox``) without the shared
    contract having to grow speculatively.
    """

    text: str
    filename: str
    source: str
    section_heading: str
    page_start: int | None
    page_end: int | None
    relevance: float
    tier: str
    reranked: bool
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    # The narrow unit that matched, when the engine reports one (v2 since
    # roadmap 2.1, where ``text`` became the assembled section). Graded
    # text is unchanged — ``grading_text`` still reads heading + body.
    matched_text: str = ""

    @property
    def grading_text(self) -> str:
        """The text anchors are graded against: heading + body, mirroring
        what the embedder/reranker sees (same rule as the v2 scorer)."""
        return f"{self.section_heading}\n{self.text}"


@dataclass
class SearchResponse:
    results: list[SearchResult]
    latency_ms: float            # engine-side wall clock, excludes HTTP transport
    corrected_query: str | None = None
    message: str | None = None

    @property
    def payload_chars(self) -> int:
        """Total characters a consumer would receive — the small-model
        context-budget metric."""
        return sum(len(r.text) + len(r.section_heading) for r in self.results)


@dataclass
class IndexReport:
    requested: int
    indexed: int                 # newly indexed this call
    skipped: int                 # already present in the engine's index
    errors: list[Any] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Page:
    """One extracted page — the unit the extraction axis grades.

    ``text`` is what the engine's real extraction pipeline produces for the
    page (v2: heading-promoted, furniture-stripped markdown; v3: its layout
    pipeline) — the same text that feeds indexing.
    """

    page_number: int  # 1-based physical page
    text: str


@runtime_checkable
class Engine(Protocol):
    """The contract every pipeline adapter implements.

    Optional adapter hooks the runner probes with ``getattr``:
      ``tag_systems(filename, tag, keywords)`` — stamp an indexed file with a
      game-system tag the way the product does (v2: custom system + tag).
      ``chunks(pdf_path) -> list[dict]`` — the engine's chunker output
      (section_heading, chunk_type, page_start, page_end, chars) for the
      breadcrumb-qa suite; no embedding.
    """

    name: str

    def index(self, pdf_paths: Sequence[Path | str]) -> IndexReport:
        """Index the given PDFs with the engine's production pipeline.
        Idempotent: already-indexed files are skipped, not re-embedded."""
        ...

    def extract(self, pdf_path: Path | str) -> list["Page"]:
        """Extract a PDF to per-page text with the engine's real pipeline —
        the same extraction that feeds indexing. The extraction axis grades
        this against golden page specs."""
        ...

    def warmup(self, options: SearchOptions | None = None) -> None:
        """Fire one untimed search so lazy one-time loads (cross-encoder,
        embed session, spell vocab) don't pollute the first query's
        latency. Call once per (engine, knob-set) before timed runs."""
        ...

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResponse:
        ...

    def close(self) -> None:
        ...
