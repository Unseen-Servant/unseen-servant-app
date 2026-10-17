# Panels

Each tool (Legend Lore, Command, the Servant) is a **panel**: one component that
renders the same whether it is docked in the main window's rack or popped out
into its own window. Two hosts render panels, and both go through
`PanelView.svelte`:

| Host | Window label | Route | Chrome around the panel |
|---|---|---|---|
| `PanelHost.svelte` | `main` | `/` | rack bar (`RackBar.svelte`), rails, dock toggle, status bar |
| `StandaloneFrame.svelte` | `panel-<id>` | `/panel/<id>` | dock toggle, status bar |

The panel ids, titles and rack minimums live in `panels.ts`; Rust keeps its
own copy of the window defaults in `src-tauri/src/panels.rs`, because it
creates the windows.

## The rack

The main window is one rack with eight views, picked by the keys 1–8 in the
rack bar or by bare 1–8 while no field has the caret. A view is a tree of
splits with one tool per slot (`rack.ts`); views start empty, and the user
builds them by pressing a tool's key (it takes a column on the right) or
carrying the key onto an edge of a slot (split) or its middle (swap). The
rails between slots drag to resize, never below a tool's `rackMin`. Each
view's layout and locks are saved in the settings store (`rackViews`,
`rackView`). A tool locked in a view can't be popped out, resized, dropped
onto, carried, or taken out by its key there.

A tool's key lights its lamp while the tool is in the current view and sits
raised while the tool has the keyboard. Each docked tool is mounted once and
laid over its slot, so switching views moves it without remounting; a tool
with no slot in the current view stays mounted, hidden. The Servant isn't in
the rack until it's built.

The status bar under the rack (`StatusBar.svelte`) spans every tool: the
machinery lamps (`machinery.ts`, polled once per window), each docked tool's
status section whatever the view, the window's notes, and the shortcut sheet
and settings at the far end. Settings is Legend Lore's modal for now, so its
key asks with `openSettings()` and brings Legend Lore's window forward when
it's popped out.

## What a panel receives

- **`active: boolean`** — true while the panel has the keyboard. Always true
  in its own window; in the main window, true for the one tool in the current
  view that was last clicked into (or the view's first). A visible panel can
  be inactive, beside the one that has the keyboard; panels with no slot in
  the view stay mounted (hidden), so their state survives view switches.
  A panel with no window-level listeners may leave it undeclared;
  `PanelView.svelte` passes it to those that take it.
- **The shell context**, read through `shellState.ts`: `appContext` (active
  campaign and session, both optional). It mirrors Rust and updates in every
  window when any window changes it.
- **Its own tool's Tauri commands and events.**
- **`windowKey`**, a snippet holding the host's dock toggle (`DockToggle.svelte`):
  unlit in the main window, where it pops the panel out; latched and lit in
  its own window, where it docks it back. A panel with a header renders it
  there (Legend Lore: right of the search bar). While the panel is locked in
  the current view the host dims the toggle and makes it inert.
- **`statusSlot`**, an element in the host's status bar (null until the bar
  is drawn). A panel with something to report renders its status section
  under `use:hoist={statusSlot}` (`hoist.ts`), which moves it into the bar:
  under the rack in the main window, at the window's foot when popped out.
  Wrap it in `.status-section`; the bar dresses `.rule`, `.stats` and
  `.icon-btn` inside it.
- **`filled`** and **`onFill(on)`** — the panel asks for the whole of the
  host's space, or gives it back; `filled` says whether it has it. In the
  main window the tool covers the rack in every view that holds it, the
  others mounted and hidden, until it lets go or the view's layout changes
  (a tool's key, a carry, `panels://show` for another tool). In its own
  window the space is the panel's already. A filled panel may set its header
  aside, so it must keep its own way back on screen: Command's is Play's
  expand key, and leaving Play lets go.

## What a panel may emit

- Calls to its own tool's Tauri commands.
- Shell context changes through `setCampaign` / `setSession`. Rust applies them
  and broadcasts `app-context://changed` to every window, the caller included —
  render from the store, not from what you just sent.

Popping out and docking belong to the host chrome, not the panel: the panel
only gives the toggle a place. Rust can also bring a panel forward
(`show_panel` in `panels.rs`, used by the macOS File menu): it focuses the
panel's own window, or shows the main window and sends it `panels://show`
with the id. `PanelHost` gives the panel the keyboard if it's in the current
view; otherwise it brings up the first view holding it, or mounts it in the
current one. A popped-out panel keeps its slot in every view that holds it,
showing the way back to its window.

## What a panel must not assume

- **Where it is.** No reading the window label, URL or route, no `goto`, no
  branching on docked vs standalone.
- **That it has the keyboard.** Any window-level listener (`<svelte:window>`,
  `document` handlers, global shortcuts) must do nothing while `active` is
  false — another panel may own the keyboard, even one on screen beside it.
  Bare 1–8 belong to the rack.
- **A size** beyond its `rackMin` in the main window (Legend Lore 560×320,
  Command 420×280), or its window minimum in its own window. Fill the parent
  (`height: 100%`), never the viewport (`100vh`) — the rack bar takes a row,
  and other tools share the rest.
- **Shared JS state.** Every window is its own JS context. A Svelte store is
  per window; anything two windows must agree on has Rust (or the sidecar) as
  source of truth and reaches windows as events. `localStorage` is not a bus.
- **The window itself.** The panel doesn't set the title, handle close, or
  open windows.

It **may** assume it is the only live instance of itself: Rust won't pop a
panel out twice, and the main window unmounts a panel while it is popped out.
Mounting again (pop out, dock back) starts from a fresh component, so anything
that must survive belongs in the settings store or in Rust.
