"""Engine-agnostic eval harness (Phase 0 of the v3 pipeline rebuild).

Grades any pipeline that implements ``evals.engines.base.Engine`` —
today the production v2 sidecar (v3 was parked in the spikes repo) — against the corpus
manifest and query suites in this directory.

See docs/retrieval/2026-08-14-v3-scaffold.md for the layout and
docs/roadmap/2026-08-13-pipeline-rebuild-plan.md for what gates what.

Not to be confused with ``sidecar/evals`` (the legacy v2-only harness,
which this one supersedes as suites land here).
"""
