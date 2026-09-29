# Docs

Design specs and planning notes for Legend Lore. Two buckets, one
level deep — pick by the part of the project a doc is about:

- **[`roadmap/`](roadmap/)** — where the project is going: goals, strategy, and
  eval findings. Cross-cutting, forward-looking (today all retrieval-focused).
- **[`retrieval/`](retrieval/)** — the Python sidecar's search/index design specs.
  This is the "backend" bucket, named for what's actually in it.

UI and interaction rules have no bucket: the code is the source of truth, and
each rule is written as a comment where it's enforced (e.g. the scope doctrine
in `src/routes/legend-lore/+page.svelte`, the confirm keyboard in
`src/lib/ui/confirmKeys.ts`). Visual conventions live in CLAUDE.md.

**Naming:** `YYYY-MM-DD-<topic>-design.md` is the spec. Step-by-step
implementation plans aren't kept once the work lands — outcomes go in the
spec or the roadmap's decision log, and the code is the record of the steps.
The folder is the source of truth; this index is just a map and may lag new
files.

---

## roadmap/

- [Retrieval pipeline improvement roadmap](roadmap/2026-07-01-retrieval-pipeline-improvement-roadmap.md)
- [Search quality goal](roadmap/2026-07-09-search-quality-goal.md)
- [BM25 hybrid retest](roadmap/2026-07-09-bm25-hybrid-retest.md)
- [Spell-correction eval](roadmap/2026-07-10-spell-correction-eval.md)
- [Pipeline rebuild plan](roadmap/2026-08-13-pipeline-rebuild-plan.md) — the v3 program
- [Agent-harness retrieval findings](roadmap/2026-08-14-agent-harness-retrieval-findings.md)
- [Unseen Servant workstation architecture](roadmap/2026-09-24-unseen-servant-workstation-architecture.md) — one repo, one window per tool, MCP as the seam
- [ML runtime consolidation](roadmap/2026-09-26-ml-runtime-consolidation.md) — one provider for embed, rerank and chat; Phase 5 runtime target reopened, sidecar prep landed
- [Retrieval informed by how Legend Lore is searched](roadmap/2026-09-26-search-ux-informed-retrieval.md) — failure classes across both suites, typing vs committing, scoped-search evals, investigation order

## retrieval/

- Table linearization — [design](retrieval/2026-07-02-table-linearization-design.md)
- Typo tolerance — [design](retrieval/2026-07-10-typo-tolerance-design.md)
- Search settings — [design](retrieval/2026-07-11-search-settings-design.md)
- v3 scaffold — [spec](retrieval/2026-08-14-v3-scaffold.md) (implements roadmap §7)
- Library store (Chroma → one normalized SQLite file) — [design](retrieval/2026-09-26-library-store-design.md)
- Headings from the PDF outline — [design](retrieval/2026-09-27-outline-headings-design.md)
