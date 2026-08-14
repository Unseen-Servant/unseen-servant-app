# S/M filter + master bypass — behavior audit

**Date:** 2026-08-13
**Status:** Findings 1–5 fixed on this branch (2026-08-14). Findings
6–7 resolved by doctrine, not code: the display-doctrine amendment of
2026-08-13 in the doctrine design doc codifies browsing surfaces dim by
resolved scope, console surfaces by channel state, and the scope bar as
the readout of effect — which makes the observed FilterPanel and
CollectionsPanel behavior correct as-is. Findings ordered by severity.
**Baseline:** `docs/specs/scope/2026-08-08-solo-mute-play-doctrine-design.md`,
`src/lib/searchScope.ts`, commit 6a5b2b0.

## The solo question first

The reported expectation — "mute many tracks but only solo one" — is not
how the app is built, and the difference is deliberate, not drift.
**Solos union within an axis** everywhere: soloing a second system,
folder, file, or curation bucket adds it to the solo set rather than
releasing the first (`toggleSystemSolo`, `toggleScopeSolo`,
`toggleCurationSolo` in `+page.svelte` are all plain set-toggles; the
doctrine spec names "solos union within an axis" as a rule; 40+ unit
tests in `searchScope.test.ts` pin it down; `FilterPanel.svelte:19-22`
documents it).

DAW context: additive solo is Logic Pro / Pro Tools behavior. Ableton
Live defaults to *exclusive* solo (soloing a track un-solos the others
unless you hold Cmd/Ctrl). Both are legitimate DAW grammars; the app
consistently implements the additive one. If exclusive solo is wanted,
that is a design change (one line per toggle plus chip/doctrine
updates), not a bug fix — but nothing in the codebase is inconsistent
on this point.

## Model recap (what resolves where)

- **Algebra:** `src/lib/searchScope.ts` — pure, well-tested. Transport
  arms the mix (`resolveMix`, mute wins over play); three axes narrow
  within it by intersection (systems, folder/file paths, collected/
  loose); within each axis solos union and solo overrides mute.
- **State + toggles:** `+page.svelte` (one set/map per axis, persisted
  whole via the `scopeConsole` store key; bypass deliberately not
  persisted).
- **Surfaces:** FileTree + SystemsView (browsing: dim, optionally hide
  under the focus lens), FilterPanel + CollectionsPanel + SearchScopeBar
  (console: never hide), StatusBar (BYPASS lamp).
- **Bypass:** `scopeBypassed` in `+page.svelte:414` — every axis and the
  mix resolve to "no narrowing" without touching console state. `B`
  tap-latches / hold-momentary through the shared `holdLatch`.

## Findings — inconsistencies

### 1. SystemsView still dims muted / non-soloed groups under bypass

`SystemsView.isGroupDimmed` (`SystemsView.svelte:147-155`) dims on the
**raw** channel state (`group.muted`, `soloedSystems`) plus
`scopeBrightPaths`. Bypass nulls `scopeBrightPaths` but the raw sets
are passed un-gated (`+page.svelte:3659-3660`), so under bypass the
tree un-dims completely while the systems view keeps dimming muted and
non-soloed groups — two browsing surfaces disagreeing about the same
scope. Compounding it: with the focus lens on, bypass + SystemsView
still **hides** those groups (`SystemsView.svelte:261, 518`) even
though every one of their files is in scope and search returns them.
FileTree under the same conditions hides nothing.

### 2. Curation solos hard-narrow the systems view, un-gated by bypass

`displayPaths` (`+page.svelte:1697-1720`) removes rows from the systems
view when a curation solo is engaged. Two problems:

- It never consults `scopeBypassed`, so under bypass the systems view
  keeps dropping loose (or collected) files that search now sees.
- Within the same axis on the same surface, solo **removes** rows while
  mute only **dims** them (via `scopeBrightPaths`). The display
  doctrine's one rule is "out-of-scope dims — never hidden by default";
  the narrowing itself is commented as deliberate, but it makes the
  curation axis the only channel whose S and M speak different display
  languages.

### 3. Keyboard `B` engages a bypass the switch refuses

The scope bar's B switch is disabled until something is bypassable
(`SearchScopeBar.svelte:42-52,100` — "Nothing to bypass yet"). The
global keydown (`+page.svelte:2378-2383`) has no such gate: pressing
`B` over an empty console latches bypass, lights the StatusBar lamp,
and changes nothing. Gesture parity says the key and the switch should
agree; today one refuses what the other allows.

### 4. Bypass dims the three view-switch chips it doesn't suppress

`.left.bypassed .chip` (`SearchScopeBar.svelte:472-474`) dims **every**
chip, but the `hidden shown`, `indexed only`, and `lens on` chips are
display filters bypass explicitly leaves alone — the component's own
`bypassable` comment (`:36-39`) says so, and they keep working while
bypassed. Dimming them signals "suspended" for switches that are still
live.

### 5. The empty-scope ladder can't see systems ∩ path empties

`runSearch` checks three empties independently (`+page.svelte:477-508`):
mix empty, path-scope empty, systems include-list empty. A scope that
is empty only in the **intersection** — e.g. solo system X plus solo
folder Y containing no X-tagged file — passes all three checks, hits
the backend, and comes back as a generic "no results" state, while the
scope-bar meter (driven by `resolvedScopeSet`, which does compute the
true intersection) reads "… of 0 files". The doctrine promises "any
solo engaged and the intersection is empty → *Nothing under the soloed
items.*"; the one number the user sees already knows the scope is
empty, but the message doesn't say why.

### 6. Three surfaces, three grammars for "excluded by someone else's solo"

Within one axis, when a solo is active:

- **SystemsView** dims every non-soloed group (`:153`).
- **FilterPanel** dims only muted rows (`FilterPanel.svelte:310` —
  `dimmed={muted && !soloed}`); a non-muted, non-soloed channel that the
  solo excludes stays fully bright.
- **SearchScopeBar** suppresses overridden mute chips entirely
  (`:76-83`).

The filter panel's choice is defensible (a console shows channel state,
and M staying lit matches a real mixer), but the muted row's dim is
commented "removed from results" — under another channel's solo,
*every* non-soloed channel is removed from results, and only the muted
one dims. At minimum the three treatments were never reconciled.

### 7. Console surfaces disagree about signaling suspension under bypass

Under bypass, the scope bar dims its chips to say "set but not in
effect", while CollectionsPanel keeps its normal contributing-to-the-mix
dims (`CollectionsPanel.svelte:661,763`) describing a mix that is not
currently in effect. Both are console surfaces; one signals the
suspension, the other doesn't. (FilterPanel likewise keeps mute dims
under bypass, consistent with #1's systems view but not with the bar.)

### Transient, acceptable

- Optimistic tag overrides (`pendingTagOverrides`,
  `+page.svelte:1547-1565`) make display scope reflect a retag before
  the backend manifest does, so dims/denominator can briefly disagree
  with search results until the override self-clears. Self-correcting;
  noting for completeness.

## Verified consistent (checked, no action)

- **Axis algebra** is identical across systems / paths / curation:
  solos union, solo overrides mute, axes intersect; the mix layer's
  "mute wins over play" is the one documented exception and is
  implemented exactly as specced (`resolveMix` + tests).
- **No dead chips:** all three creation paths (inline S/M, context
  menu, keyboard) share the `rowHasIndexedMaterial` gate; removal
  always works; stale chips stay visible and removable per the
  staleness doctrine (ghost collection names resolve away, stale path
  solos narrow honestly).
- **Untagged is mute-only** in all three places it could leak: no S
  button (FilterPanel, SystemsView), keyboard S gated
  (`SystemsView.svelte:386`), and the backend include-list never adds
  `unknown` under solos (#307).
- **Frontend/backend systems agreement** including multi-tagged files:
  `passesSystemsAxis` (any-tag-passes) matches the sidecar's
  secondary-path `$or` fold (`server.py:1871-1905`, #308).
- **Hold latch** (tap latches, hold momentary) is one implementation
  shared by S, M, P/Space, and B, with a single window-level
  keyup/blur release.
- **Persistence** covers the whole console in one key with per-field
  defensive parsing; bypass is deliberately excluded (documented,
  `+page.svelte:409-413`) and deliberately outside [reset]'s reach
  (`:1054-1059`) — both read as intended design, not gaps.
- **[reset] reach** matches `scopeConsoleEngaged` term-for-term.
- **Chip suppression** of overridden mutes matches resolution on all
  three axes; play chips and collection-mute chips are never
  suppressed, matching mute-wins-over-play.

## Recommendations (in order)

1. Gate every display predicate on the resolved scope, not raw channel
   state: pass bypass-aware inputs to `SystemsView` (or fold the muted/
   soloed dim conditions into a bypass-gated input) and gate
   `displayPaths`' curation narrowing on `scopeBypassed`. This closes
   #1 and the bypass half of #2 in two small changes.
2. Gate keyboard `B` on the same `anyBypassable` predicate the switch
   uses (#3), and scope the bypassed chip-dim to narrowing chips only
   (#4).
3. Decide the empty-scope check in `runSearch` against
   `resolvedScopeSet` (recomputed synchronously, as the axes already
   are) so cross-axis empties get the doctrine's message (#5).
4. Pick one grammar for "excluded by another channel's solo" on console
   surfaces and write it into the display doctrine (#6, #7).
5. If exclusive solo (Ableton-style) is actually wanted, treat it as a
   doctrine amendment — the union behavior is load-bearing in the spec,
   tests, chips, and tooltips.
