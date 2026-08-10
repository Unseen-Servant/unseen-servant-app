// Single source of truth for app keybindings.
//
// The global handler in +page.svelte hardcodes the chord checks for speed
// and clarity, but every binding is also registered here so tooltips and
// (eventually) the `?` help overlay can stay in sync. When you add a chord
// to the handler, add (or update) its entry here and reuse `chordHint(id)`
// in the corresponding button's `title` attribute.

export type KeyScope =
  | 'global'
  | 'fileTree'
  | 'systemsView'
  | 'collections'
  | 'searchInput'
  | 'searchResults'
  | 'filterPanel'
  | 'contextMenu'
  | 'modal';

export interface KeybindingEntry {
  id: string;
  keys: { mac: string; other: string };
  label: string;
  scope: KeyScope;
  // Normalized form used to dispatch this chord from inside an open menu.
  // Present only on bindings a menu re-exposes as an accelerator; the menu
  // matches on this rather than on the display string in `keys`.
  match?: string;
}

const isMac =
  typeof navigator !== 'undefined' &&
  /mac|iphone|ipad|ipod/i.test(
    // navigator.platform is deprecated but still the most reliable signal
    // in Tauri webviews; userAgentData isn't available on WebKit.
    navigator.platform || '',
  );

export const KEYBINDINGS: KeybindingEntry[] = [
  // Global
  { id: 'settings.open',         keys: { mac: '⌘,',   other: 'Ctrl+,' },        label: 'Open Settings',               scope: 'global' },
  { id: 'sidebar.toggle',        keys: { mac: '⌘B',   other: 'Ctrl+B' },        label: 'Toggle Collections sidebar',  scope: 'global' },
  { id: 'focus.dock',            keys: { mac: '⌘⌥←',  other: 'Ctrl+Alt+←' },    label: 'Focus the left dock',         scope: 'global' },
  { id: 'focus.files',           keys: { mac: '⌘⌥→',  other: 'Ctrl+Alt+→' },    label: 'Focus right pane',            scope: 'global' },
  { id: 'focus.dockDown',        keys: { mac: '⌘⌥↓',  other: 'Ctrl+Alt+↓' },    label: 'Dock: Collections → Filters', scope: 'global' },
  { id: 'focus.dockUp',          keys: { mac: '⌘⌥↑',  other: 'Ctrl+Alt+↑' },    label: 'Dock: Filters → Collections', scope: 'global' },
  { id: 'view.systems',          keys: { mac: '⌘J',   other: 'Ctrl+J' },        label: 'Shelve by system',            scope: 'global' },
  { id: 'view.tree',             keys: { mac: '⌘T',   other: 'Ctrl+T' },        label: 'Tree view (again collapses all)', scope: 'global' },
  { id: 'sync.run',              keys: { mac: '⌘R',   other: 'Ctrl+R' },        label: 'Re-detect changes from disk', scope: 'global' },
  { id: 'sync.commit',           keys: { mac: '⌘S',   other: 'Ctrl+S' },        label: 'Sync selected files to index', scope: 'global' },
  { id: 'sync.revert',           keys: { mac: '⌘Z',   other: 'Ctrl+Z' },        label: 'Revert pending sync changes',  scope: 'global' },
  { id: 'info.show',             keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: 'Show info for focused file',   scope: 'global', match: 'meta+i' },
  { id: 'search.focus',          keys: { mac: '⌘F',   other: 'Ctrl+F' },        label: 'Focus search input',          scope: 'global' },
  { id: 'filter.toggle',         keys: { mac: '⌘E',   other: 'Ctrl+E' },        label: 'Toggle Filters panel',        scope: 'global' },
  { id: 'filter.toggleHidden',   keys: { mac: '⌘⇧.',  other: 'Ctrl+Shift+.' },  label: 'Toggle show hidden items',    scope: 'global' },
  { id: 'library.reveal',        keys: { mac: '⌘⇧O',  other: 'Ctrl+Shift+O' },  label: 'Reveal library folder in OS', scope: 'global' },
  { id: 'help.overlay',          keys: { mac: '?',    other: '?' },             label: 'Show keyboard shortcuts',     scope: 'global' },
  { id: 'app.escape',            keys: { mac: 'Esc',  other: 'Esc' },           label: 'Cancel / close / step back', scope: 'global' },

  // Search input
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: 'Submit search',                scope: 'searchInput' },
  { id: 'search.intoResults',    keys: { mac: '↓',    other: '↓' },             label: 'Move focus into results',      scope: 'searchInput' },
  { id: 'search.exit',           keys: { mac: 'Esc',  other: 'Esc' },           label: 'Leave search — back to browse view', scope: 'searchInput' },

  // File tree (when a row is focused)
  { id: 'tree.next',             keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'fileTree' },
  { id: 'tree.prev',             keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'fileTree' },
  { id: 'tree.home',             keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'fileTree' },
  { id: 'tree.end',              keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'fileTree' },
  { id: 'tree.expand',           keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand folder / first child',  scope: 'fileTree' },
  { id: 'tree.collapse',         keys: { mac: '← / H', other: '← / H' },        label: 'Collapse folder / parent',     scope: 'fileTree' },
  { id: 'tree.activate',         keys: { mac: 'Space',other: 'Space' },         label: 'Open file / toggle folder',    scope: 'fileTree' },
  { id: 'tree.toggleSelect',     keys: { mac: 'X',    other: 'X' },             label: 'Toggle selection checkbox',    scope: 'fileTree' },
  { id: 'tree.openExternal',     keys: { mac: '⌘O',   other: 'Ctrl+O' },        label: 'Reveal row in OS file explorer', scope: 'fileTree', match: 'meta+o' },
  { id: 'tree.contextMenu',      keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: 'Open context menu',         scope: 'fileTree' },
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: 'Rename focused row',           scope: 'fileTree', match: 'r' },
  { id: 'tree.solo',             keys: { mac: 'S',    other: 'S' },             label: 'Solo focused row (narrow search to it)', scope: 'fileTree', match: 's' },
  { id: 'tree.mute',             keys: { mac: 'M',    other: 'M' },             label: 'Mute focused row (drop from search)',    scope: 'fileTree', match: 'm' },
  { id: 'tree.hide',             keys: { mac: '.',    other: '.' },             label: 'Toggle hidden state',          scope: 'fileTree', match: '.' },
  { id: 'tree.addToCollection',  keys: { mac: 'C',    other: 'C' },             label: 'Add to collection (opens menu)', scope: 'fileTree', match: 'c' },

  // Systems view (when a row is focused)
  { id: 'systems.activate',      keys: { mac: 'Space',other: 'Space' },         label: 'Open file (toggle membership while editing)', scope: 'systemsView' },
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: "Solo the row's system",        scope: 'systemsView' },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: "Mute the row's system",        scope: 'systemsView' },

  // Collections panel (when a row is focused)
  { id: 'collections.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'collections' },
  { id: 'collections.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'collections' },
  { id: 'collections.home',      keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'collections' },
  { id: 'collections.end',       keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'collections' },
  { id: 'collections.play',      keys: { mac: 'P / Space', other: 'P / Space' }, label: 'Play / stop focused collection', scope: 'collections' },
  { id: 'collections.rename',    keys: { mac: 'F2',   other: 'F2' },            label: 'Rename collection',            scope: 'collections' },
  { id: 'collections.editFiles', keys: { mac: 'F',    other: 'F' },             label: 'Edit collection files',        scope: 'collections' },
  { id: 'collections.archive',   keys: { mac: 'A',    other: 'A' },             label: 'Toggle archived',              scope: 'collections' },
  { id: 'collections.new',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: 'New collection (auto-opens panel)', scope: 'global' },
  { id: 'collections.save',      keys: { mac: '⌘↵',   other: 'Ctrl+Enter' },    label: 'Save in-progress collection',  scope: 'global' },

  // Filters panel (while the pane holds focus)
  { id: 'filterPanel.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'filterPanel' },
  { id: 'filterPanel.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'filterPanel' },
  { id: 'filterPanel.home',      keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'filterPanel' },
  { id: 'filterPanel.end',       keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'filterPanel' },
  { id: 'filterPanel.toggle',    keys: { mac: 'Space',other: 'Space' },         label: 'Toggle mute on focused row',   scope: 'filterPanel' },
  { id: 'filterPanel.solo',      keys: { mac: 'S',    other: 'S' },             label: 'Solo / unsolo focused channel', scope: 'filterPanel' },
  { id: 'filterPanel.mute',      keys: { mac: 'M',    other: 'M' },             label: 'Mute / unmute focused channel', scope: 'filterPanel' },
  { id: 'filterPanel.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: 'Release focus / leave the panel', scope: 'filterPanel' },

  // Context menu (when open)
  { id: 'contextMenu.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'contextMenu' },
  { id: 'contextMenu.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'contextMenu' },
  { id: 'contextMenu.openSub',   keys: { mac: '→ / L', other: '→ / L' },        label: 'Open submenu',                 scope: 'contextMenu' },
  { id: 'contextMenu.closeSub',  keys: { mac: '← / H', other: '← / H' },        label: 'Close submenu',                scope: 'contextMenu' },
  { id: 'contextMenu.activate',  keys: { mac: '↵',    other: 'Enter' },         label: 'Activate focused item',        scope: 'contextMenu' },

  // Search results list
  { id: 'results.next',          keys: { mac: '↓',    other: '↓' },             label: 'Next result',                  scope: 'searchResults' },
  { id: 'results.prev',          keys: { mac: '↑',    other: '↑' },             label: 'Previous result (or back to input)', scope: 'searchResults' },
  { id: 'results.open',          keys: { mac: '↵',    other: 'Enter' },         label: 'Open focused result',          scope: 'searchResults' },
  { id: 'results.jumpN',         keys: { mac: '⌘1–9', other: 'Ctrl+1–9' },      label: 'Jump to result N',             scope: 'searchResults' },
  { id: 'results.toInput',       keys: { mac: 'Esc',  other: 'Esc' },           label: 'Back to search input',         scope: 'searchResults' },
];

const BY_ID = new Map(KEYBINDINGS.map(k => [k.id, k]));

export function chord(id: string): string {
  const entry = BY_ID.get(id);
  if (!entry) return '';
  return isMac ? entry.keys.mac : entry.keys.other;
}

// Convenience for `title` attributes: returns " (⌘B)" or "" if the binding
// is unknown. The leading space keeps callers terse: title={`Foo${chordHint('id')}`}.
export function chordHint(id: string): string {
  const c = chord(id);
  return c ? ` (${c})` : '';
}

// The `aria-keyshortcuts` value for a binding: spec modifier names joined with
// '+', then the key. Derived from `match` so it cannot drift from what the menu
// actually dispatches — and so it is empty for bindings the menu only *displays*
// a hint for, which must not claim a shortcut they don't honour.
export function keyShortcut(id: string): string {
  const m = matchKey(id);
  if (!m) return '';
  if (m.startsWith('meta+')) {
    return `${isMac ? 'Meta' : 'Control'}+${m.slice(5).toUpperCase()}`;
  }
  return m.toUpperCase();
}

// True when the chord is a single bare character — R, S, '.'. Alone in a menu's
// hint column such a glyph reads as punctuation or a stray mark rather than a
// key, so menus frame it in brackets. Modifier chords (⌘O) and named keys (F2)
// already look like keys and are left plain.
export function isBareKeyChord(id: string): boolean {
  return chord(id).length === 1;
}

// Structural stand-in for KeyboardEvent so this stays testable under vitest's
// node environment — a real KeyboardEvent satisfies it.
export interface ChordEvent {
  key: string;
  code: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

// Normalized lookup key for a keydown, matching KeybindingEntry.match. Cmd and
// Ctrl both fold to `meta+` so one table serves both platforms. Returns null
// for anything no accelerator uses.
//
// Callers must additionally check `!event.isComposing` before calling this —
// this helper has no DOM access and can't see composition state.
export function eventMatchKey(event: ChordEvent): string | null {
  if (event.shiftKey || event.altKey) return null;
  // event.code is layout-independent; some layouts report ',' for the numpad
  // decimal key.
  const base = event.code === 'NumpadDecimal' ? '.' : event.key.toLowerCase();
  if (base.length !== 1) return null;
  return event.metaKey || event.ctrlKey ? `meta+${base}` : base;
}

// The match key for a binding id, or '' when the binding has no accelerator.
export function matchKey(id: string): string {
  return BY_ID.get(id)?.match ?? '';
}
