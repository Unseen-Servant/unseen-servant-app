# Docs

Design specs, plans, and planning notes for Legend Lore. Three buckets, one
level deep — pick by the part of the project a doc is about:

- **[`roadmap/`](roadmap/)** — where the project is going: goals, strategy, and
  eval findings. Cross-cutting, forward-looking (today all retrieval-focused).
- **[`retrieval/`](retrieval/)** — the Python sidecar's search/index design specs.
  This is the "backend" bucket, named for what's actually in it.
- **[`frontend/`](frontend/)** — every UI/UX/interaction spec on the SvelteKit side.

**Naming:** `YYYY-MM-DD-<topic>-design.md` is the spec; a paired
`…-plan.md` is its implementation plan. One-offs use `…-audit.md`. The folder
is the source of truth; this index is just a map and may lag new files.

---

## roadmap/

- [Retrieval pipeline improvement roadmap](roadmap/2026-07-01-retrieval-pipeline-improvement-roadmap.md)
- [Search quality goal](roadmap/2026-07-09-search-quality-goal.md)
- [BM25 hybrid retest](roadmap/2026-07-09-bm25-hybrid-retest.md)
- [Spell-correction eval](roadmap/2026-07-10-spell-correction-eval.md)
- [Pipeline rebuild plan](roadmap/2026-08-13-pipeline-rebuild-plan.md) — the v3 program
- [Agent-harness retrieval findings](roadmap/2026-08-14-agent-harness-retrieval-findings.md)

## retrieval/

- Table linearization — [design](retrieval/2026-07-02-table-linearization-design.md) · [plan](retrieval/2026-07-02-table-linearization.md)
- Typo tolerance — [design](retrieval/2026-07-10-typo-tolerance-design.md)
- Search settings — [design](retrieval/2026-07-11-search-settings-design.md)
- v3 scaffold — [spec](retrieval/2026-08-14-v3-scaffold.md) (implements roadmap §7)

## frontend/

**Search & tree views**
- Search view behavior — [design](frontend/2026-08-08-search-view-behavior-design.md) · [plan](frontend/2026-08-08-search-view-behavior-plan.md)
- Tree view icons — [design](frontend/2026-08-08-tree-view-icons-design.md)
- Search panel interaction — [audit](frontend/2026-08-13-search-panel-interaction-audit.md)

**Scope / solo-mute-play doctrine**
- Solo-mute-play doctrine — [design](frontend/2026-08-08-solo-mute-play-doctrine-design.md) · [plan](frontend/2026-08-08-solo-mute-play-doctrine-plan.md)
- Hide unindexed — [design](frontend/2026-08-09-hide-unindexed-design.md) · [plan](frontend/2026-08-09-hide-unindexed-plan.md)
- Momentary transport — [design](frontend/2026-08-11-momentary-transport-design.md)
- SM bypass — [audit](frontend/2026-08-13-sm-bypass-audit.md)
- Systems-view row SM — [design](frontend/2026-08-13-systems-view-row-sm-design.md) · [plan](frontend/2026-08-13-systems-view-row-sm-plan.md)
- Systems-view row dim — [plan](frontend/2026-08-14-systems-view-row-dim-plan.md)

**Menus, rows & chrome**
- Header voices — [design](frontend/2026-08-09-header-voices-design.md) · [plan](frontend/2026-08-09-header-voices-plan.md)
- Menu affordances — [design](frontend/2026-08-09-menu-affordances-design.md) · [plan](frontend/2026-08-09-menu-affordances-plan.md)
- Row-state grammar — [design](frontend/2026-08-09-row-state-grammar-design.md)
- Shared menu machinery — [design](frontend/2026-08-11-shared-menu-machinery-design.md)
- System-tag rows — [design](frontend/2026-08-12-system-tag-rows-design.md)

**Modals & panels**
- Modal audit — [design](frontend/2026-08-11-modal-audit-design.md)
- Modal rack units — [design](frontend/2026-08-12-modal-rack-units-design.md) · [plan](frontend/2026-08-12-modal-rack-units-plan.md)
- Scrim extent & depth — [design](frontend/2026-08-13-scrim-extent-and-depth-design.md) · [plan](frontend/2026-08-13-scrim-extent-and-depth-plan.md)

**Keyboard & pane focus**
- Pane activation — [design](frontend/2026-08-09-pane-activation-design.md)
- Pane focus model — [design](frontend/2026-08-09-pane-focus-model-design.md) · [plan](frontend/2026-08-09-pane-focus-model-plan.md)

**Unseen Servant (agent window)**
- Unseen Servant window — [design](frontend/2026-08-09-unseen-servant-design.md) · [plan](frontend/2026-08-09-unseen-servant-plan.md)

**Game-system tagging**
- Manual game-system tagging context menu — [design](frontend/2026-05-10-manual-game-system-tagging-context-menu-design.md) · [plan](frontend/2026-05-10-manual-game-system-tagging-context-menu.md)
