# Manual game-system tagging via context menu

**Status:** Approved, awaiting implementation plan
**Owner:** Solo (jay)
**Target:** v2.0.0 release

## Problem

An indexed PDF whose game system the auto-detector couldn't identify (it ends up with `game_system="unknown"` and `game_systems=[]`) has no obvious way to receive a first tag. The tree row shows a small, dashed-border `+` button on the right — easy to miss when the user's natural reach for "do something to this file" is right-click. The user reported this as a v2 release blocker.

The backend already has every primitive needed: `set_game_systems` Tauri command and `/api/set-game-systems` endpoint update both ChromaDB metadata and the manifest with no re-index. `handleSetGameSystems` in `+page.svelte:1415` already wraps it. The gap is purely UX: discoverability of the entry point.

## Goal

Right-clicking an indexed PDF whose game system needs to be set (or changed) reveals a clear "Game system…" submenu in the context menu that lists known systems with check marks for current tags. Clicking toggles. Same backend path the badge dropdown uses today; same optimistic-update behaviour.

## Non-goals

- **Folder bulk-tagging.** Real feature, but adds partial-failure UX and a separate confirmation flow. Worth a separate design after v2.
- **Backend changes.** `set_game_systems` already does what's needed.
- **Re-indexing.** This is a metadata flip only.
- **Tagging unindexed files.** The backend keys by filename in the manifest; an unindexed file has no manifest entry to tag.

## Approach

Two paths to tagging will exist after this PR, intentionally:
1. **Click the badge cluster** on a tagged file in the tree → existing dropdown opens with checks; toggles edit tags. The visible affordance IS the data.
2. **Right-click any indexed PDF** → "Game system…" submenu does the same thing, regardless of whether tags are currently applied.

Rule of thumb the user can internalize: *tags visible → click to edit. No tags → right-click to add.*

The current `+` button on indexed-untagged files (FileTree.svelte:262-265) is the awkward retrofit of the badge approach for the empty case. It goes away — its job is taken over by the context menu, which is more discoverable and also addresses the "I want to change a tagged file but the tag is hard to read" case.

## Components

### `src/lib/ContextMenu.svelte`

New submenu trigger between *Get info* and *Add to collection…*, only rendered when `isIndexed && !item.is_dir && knownSystems.length > 0`. Reuses the existing `submenu-trigger` pattern (the same one *Add to collection* uses) so the kb-focused fix from #273 still applies.

New props:
- `knownSystems: KnownGameSystem[]` — same shape as the badge dropdown receives.
- `currentTags: string[]` — tags already on this file.
- `onSetGameSystems: (tags: string[]) => void` — called with the new tag list when the user toggles. Wraps the page-level `handleSetGameSystems` so the component doesn't need to know about path/filename plumbing.

Submenu content:
- Each system in `knownSystems` rendered as a row with a leading check (`✓` if applied) and the tag name.
- A divider + "Clear tags" entry, only shown when `currentTags.length > 0`.

### `src/routes/+page.svelte`

The `<ContextMenu />` instantiation (line 2986 area) gains three new props passed through:
- `knownSystems={knownSystems}`
- `currentTags={effectiveGameSystemMap.get(contextMenu.item.path) ?? []}`
- `onSetGameSystems={(tags) => handleSetGameSystems(contextMenu.item.path, contextMenu.item.name, tags)}`

No changes to `handleSetGameSystems` itself; it already does what's needed including the `pendingTagOverrides` optimistic update.

### `src/lib/FileTree.svelte`

Remove the `{:else if isIndexed}` branch (lines 262-266) that renders the `+` button. The badge cluster path remains for tagged files. `toggleDropdown`, `toggleSystem`, `clearSystem` and the dropdown markup stay — they're still used by the badge cluster.

The associated CSS (`.add-tag-btn` and `.add-tag-btn:hover`) is removed.

## Data flow

```
Right-click PDF row
  → ContextMenu opens
  → User hovers "Game system…"
  → Submenu opens with knownSystems checked against currentTags
  → User clicks a system
  → onSetGameSystems(nextTags) called
  → handleSetGameSystems(path, filename, nextTags) in +page.svelte
  → invoke('set_game_systems', { filename, gameSystems: nextTags })
  → Rust set_game_systems Tauri command
  → POST /api/set-game-systems
  → _apply_game_systems updates ChromaDB metadata + manifest
  → refreshIndexStatus() picks up the new tags
  → Optimistic pendingTagOverrides clears
```

## Edge cases

| Case | Behaviour |
|---|---|
| Indexed file, no tags | Submenu shows all systems unchecked; click adds first tag. **The reported gap.** |
| Indexed file, with tags | Submenu shows tags checked; click toggles. Same as badge dropdown. |
| Folder | Submenu hidden (`!item.is_dir` guard). |
| Unindexed file | Submenu hidden (`isIndexed` guard). |
| `knownSystems` empty | Submenu trigger hidden entirely. No point showing an empty list, and the "Clear tags" footer alone would be confusing for a never-tagged file. |
| Backend failure mid-set | Existing `handleSetGameSystems` reverts the optimistic update on catch. Same behaviour as the badge dropdown today. |

## Testing

- **Unit (Vitest):** small test that `ContextMenu.svelte` renders the trigger when `isIndexed && !is_dir && knownSystems.length > 0`, hides it otherwise. No need to drive the click through to the backend — `handleSetGameSystems` is already exercised by the badge dropdown path.
- **Manual:**
  1. Index a PDF whose system the detector won't find (a generic-named indie supplement). Right-click → "Game system…" → pick D&D 5E. Tree row shows the badge. SystemsView count for D&D 5E increments.
  2. Right-click a tagged PDF → "Game system…" → uncheck its current system. Badge disappears, "+" no longer present (per FileTree change).
  3. Right-click a folder → no "Game system…" entry.
  4. Right-click an unindexed PDF → no "Game system…" entry.

## Risks

- **Removing the `+` is a behaviour change for any user relying on it.** Single-user codebase, low risk; release notes mention it.
- **Submenu opens on hover**, like *Add to collection*. Inherits the same UX strengths and quirks (#273's fix already applies).

## Out of scope

- Folder bulk-tagging (separate design).
- Quick-add new custom system from inside the submenu (today the user has to go to Settings → Game Systems → New).
- Pinning frequently-used systems to the top of the list.
