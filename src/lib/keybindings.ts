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
  | 'filterMenu'
  | 'contextMenu'
  | 'modal';

export interface KeybindingEntry {
  id: string;
  keys: { mac: string; other: string };
  label: string;
  scope: KeyScope;
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
  { id: 'focus.collections',     keys: { mac: '⌘⌥←',  other: 'Ctrl+Alt+←' },    label: 'Focus left pane',             scope: 'global' },
  { id: 'focus.files',           keys: { mac: '⌘⌥→',  other: 'Ctrl+Alt+→' },    label: 'Focus right pane',            scope: 'global' },
  { id: 'view.toggle',           keys: { mac: '⌘J',   other: 'Ctrl+J' },        label: 'Toggle Tree ↔ Systems view',  scope: 'global' },
  { id: 'sync.run',              keys: { mac: '⌘R',   other: 'Ctrl+R' },        label: 'Re-detect changes from disk', scope: 'global' },
  { id: 'sync.commit',           keys: { mac: '⌘S',   other: 'Ctrl+S' },        label: 'Sync selected files to index', scope: 'global' },
  { id: 'sync.revert',           keys: { mac: '⌘Z',   other: 'Ctrl+Z' },        label: 'Revert pending sync changes',  scope: 'global' },
  { id: 'info.show',             keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: 'Show info for focused file',   scope: 'global' },
  { id: 'search.focus',          keys: { mac: '⌘F',   other: 'Ctrl+F' },        label: 'Focus search input',          scope: 'global' },
  { id: 'filter.toggle',         keys: { mac: '⌘E',   other: 'Ctrl+E' },        label: 'Toggle Filters panel',        scope: 'global' },
  { id: 'filter.toggleHidden',   keys: { mac: '⌘⇧.',  other: 'Ctrl+Shift+.' },  label: 'Toggle show hidden items',    scope: 'global' },
  { id: 'library.reveal',        keys: { mac: '⌘⇧O',  other: 'Ctrl+Shift+O' },  label: 'Reveal library folder in OS', scope: 'global' },
  { id: 'help.overlay',          keys: { mac: '?',    other: '?' },             label: 'Show keyboard shortcuts',     scope: 'global' },
  { id: 'app.escape',            keys: { mac: 'Esc',  other: 'Esc' },           label: 'Cancel / close / step back', scope: 'global' },

  // Search input
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: 'Submit search',                scope: 'searchInput' },
  { id: 'search.intoResults',    keys: { mac: '↓',    other: '↓' },             label: 'Move focus into results',      scope: 'searchInput' },
  { id: 'search.intoTree',       keys: { mac: '↓',    other: '↓' },             label: 'Move focus into file tree',    scope: 'searchInput' },

  // File tree (when a row is focused)
  { id: 'tree.next',             keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'fileTree' },
  { id: 'tree.prev',             keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'fileTree' },
  { id: 'tree.home',             keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'fileTree' },
  { id: 'tree.end',              keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'fileTree' },
  { id: 'tree.expand',           keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand folder / first child',  scope: 'fileTree' },
  { id: 'tree.collapse',         keys: { mac: '← / H', other: '← / H' },        label: 'Collapse folder / parent',     scope: 'fileTree' },
  { id: 'tree.toggleSelect',     keys: { mac: 'Space',other: 'Space' },         label: 'Toggle selection checkbox',    scope: 'fileTree' },
  { id: 'tree.activate',         keys: { mac: '↵',    other: 'Enter' },         label: 'Open file / toggle folder',    scope: 'fileTree' },
  { id: 'tree.openExternal',     keys: { mac: '⌘O',   other: 'Ctrl+O' },        label: 'Reveal row in OS file explorer', scope: 'fileTree' },
  { id: 'tree.contextMenu',      keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: 'Open context menu',         scope: 'fileTree' },
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: 'Rename focused row',           scope: 'fileTree' },
  { id: 'tree.solo',             keys: { mac: 'S',    other: 'S' },             label: 'Solo focused row (narrow search to it)', scope: 'fileTree' },
  { id: 'tree.mute',             keys: { mac: 'M',    other: 'M' },             label: 'Mute focused row (drop from search)',    scope: 'fileTree' },
  { id: 'tree.hide',             keys: { mac: '.',    other: '.' },             label: 'Toggle hidden state',          scope: 'fileTree' },
  { id: 'tree.addToCollection',  keys: { mac: 'C',    other: 'C' },             label: 'Add to collection (opens menu)', scope: 'fileTree' },

  // Systems view (when a row is focused)
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: "Solo the row's system",        scope: 'systemsView' },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: "Mute the row's system",        scope: 'systemsView' },

  // Collections panel (when a row is focused)
  { id: 'collections.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'collections' },
  { id: 'collections.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'collections' },
  { id: 'collections.home',      keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'collections' },
  { id: 'collections.end',       keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'collections' },
  { id: 'collections.play',      keys: { mac: 'P',    other: 'P' },             label: 'Play / stop focused collection', scope: 'collections' },
  { id: 'collections.rename',    keys: { mac: 'F2',   other: 'F2' },            label: 'Rename collection',            scope: 'collections' },
  { id: 'collections.editFiles', keys: { mac: 'F',    other: 'F' },             label: 'Edit collection files',        scope: 'collections' },
  { id: 'collections.new',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: 'New collection (auto-opens panel)', scope: 'global' },
  { id: 'collections.save',      keys: { mac: '⌘↵',   other: 'Ctrl+Enter' },    label: 'Save in-progress collection',  scope: 'global' },

  // Filters panel (while focus is inside it)
  { id: 'filterMenu.next',       keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'filterMenu' },
  { id: 'filterMenu.prev',       keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'filterMenu' },
  { id: 'filterMenu.toggle',     keys: { mac: 'Space',other: 'Space' },         label: 'Toggle mute on focused row',   scope: 'filterMenu' },
  { id: 'filterMenu.solo',       keys: { mac: 'S',    other: 'S' },             label: 'Solo / unsolo focused channel', scope: 'filterMenu' },
  { id: 'filterMenu.mute',       keys: { mac: 'M',    other: 'M' },             label: 'Mute / unmute focused channel', scope: 'filterMenu' },

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
