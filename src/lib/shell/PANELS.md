# Panels

Each tool (Legend Lore, Command, the Servant) is a **panel**: one component that
renders the same whether it is docked as a tab in the main window or popped out
into its own window. Two hosts render panels, and both go through
`PanelView.svelte`:

| Host | Window label | Route | Chrome around the panel |
|---|---|---|---|
| `PanelHost.svelte` | `main` | `/` | tab strip, pop-out per tab |
| `StandaloneFrame.svelte` | `panel-<id>` | `/panel/<id>` | title strip, `[dock back]` |

The panel ids and titles live in `panels.ts`; Rust keeps its own copy of the
window defaults in `src-tauri/src/panels.rs`, because it creates the windows.

## What a panel receives

- **`active: boolean`** — true while the panel is visible. Always true in its
  own window; in the main window, true only for the selected tab. Inactive
  docked panels stay mounted (hidden), so their state survives tab switches.
  A panel with no window-level listeners may leave it undeclared;
  `PanelView.svelte` passes it to those that take it.
- **The shell context**, read through `shellState.ts`: `appContext` (active
  campaign and session, both optional). It mirrors Rust and updates in every
  window when any window changes it.
- **Its own tool's Tauri commands and events.**

## What a panel may emit

- Calls to its own tool's Tauri commands.
- Shell context changes through `setCampaign` / `setSession`. Rust applies them
  and broadcasts `app-context://changed` to every window, the caller included —
  render from the store, not from what you just sent.

Popping out and docking belong to the host chrome, not the panel.

## What a panel must not assume

- **Where it is.** No reading the window label, URL or route, no `goto`, no
  branching on docked vs standalone.
- **That it is visible.** Any window-level listener (`<svelte:window>`,
  `document` handlers, global shortcuts) must do nothing while `active` is
  false — another panel may own the keyboard.
- **A size** beyond its minimum (Legend Lore 940×600). Fill the parent
  (`height: 100%`), never the viewport (`100vh`) — the main window's tab strip
  takes a row.
- **Shared JS state.** Every window is its own JS context. A Svelte store is
  per window; anything two windows must agree on has Rust (or the sidecar) as
  source of truth and reaches windows as events. `localStorage` is not a bus.
- **The window itself.** The panel doesn't set the title, handle close, or
  open windows.

It **may** assume it is the only live instance of itself: Rust won't pop a
panel out twice, and the main window unmounts a panel while it is popped out.
Mounting again (pop out, dock back) starts from a fresh component, so anything
that must survive belongs in the settings store or in Rust.
