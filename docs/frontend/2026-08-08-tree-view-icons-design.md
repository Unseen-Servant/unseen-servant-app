# Tree view icons — design

**Date:** 2026-08-08
**Status:** Approved (icons only; no behavior changes)

## Problem

Systems-view file rows read as `[book icon] filename` — the row feels like a
solid object when focused or selected. Tree rows are bare text with a lone
▸/▾ arrow on folders, so the same file feels different between the two views.
File names at a given depth also sit ~1.3rem left of sibling folder names,
because only folder rows carry the arrow slot.

## Decision

Mirror the systems view's row anatomy in `FileTree.svelte`: the arrow carries
expand state, the icon carries identity.

- **Folder rows:** `[▸/▾ arrow] [folder icon] [name]`. Folder icon is Font
  Awesome "folder" (solid) in `--text-accent`, matching the die icon on
  systems-view group headers. The arrow drops to `--text-secondary` at the
  smaller systems-view size (0.7rem), so the accent lives on the icon.
- **File rows:** `[gutter] [book icon] [name]`. The book icon is the same
  Font Awesome "book" SVG the systems view uses, 13px, `--text-secondary`.
  The gutter is a phantom spacer the width of the arrow slot so icons form an
  aligned column and file names line up with sibling folder names.

Click, selection, and keyboard behavior are untouched. The book SVG is
duplicated inline with a source comment, following the existing die-icon
pattern — no shared-icon abstraction.

## Alternatives rejected

- **Icons without the gutter/arrow restyle:** least change, but the icon
  column zigzags at every level — worse than today.
- **Folder open/closed icon replacing the arrow (VS Code style):** cleanest
  column, but removes an existing affordance and diverges from the
  systems-view anatomy this change is meant to match.

## Verification

- `npm run check` (svelte-check), `npm run lint:css` (token rule), vite build.
- Visual pass in dev: mixed folder/file levels align; hidden-item and
  out-of-scope dimming still read correctly (icons inherit row opacity).
