"""SQLite store: one schema for docs/sections/chunks/units + vectors + FTS, and
a single-transaction index commit (plan §3.3). Replaces ChromaDB + 4 JSON
side-stores + the separate parents SQLite. Migrates on domain.SCHEMA_VERSION.

Intentionally unimplemented — no pipeline code before the Phase 1 verdicts (scaffold §2).
"""
