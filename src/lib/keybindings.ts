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
  { id: 'search.focus',          keys: { mac: '⌘F',   other: 'Ctrl+F' },        label: 'Focus search input',          scope: 'global' },
  { id: 'settings.open',         keys: { mac: '⌘,',   other: 'Ctrl+,' },        label: 'Open Settings',               scope: 'global' },
  { id: 'sidebar.toggle',        keys: { mac: '⌘B',   other: 'Ctrl+B' },        label: 'Toggle Collections sidebar',  scope: 'global' },
  { id: 'view.toggle',           keys: { mac: '⌘J',   other: 'Ctrl+J' },        label: 'Toggle Tree ↔ Systems view',  scope: 'global' },
  { id: 'sync.run',              keys: { mac: '⌘R',   other: 'Ctrl+R' },        label: 'Sync / re-index changes',     scope: 'global' },
  { id: 'filter.toggle',         keys: { mac: '⌘⇧F',  other: 'Ctrl+Shift+F' },  label: 'Open filter menu',            scope: 'global' },
  { id: 'filter.toggleHidden',   keys: { mac: '⌘⇧.',  other: 'Ctrl+Shift+.' },  label: 'Toggle show hidden items',    scope: 'global' },
  { id: 'help.overlay',          keys: { mac: '?',    other: '?' },             label: 'Show keyboard shortcuts',     scope: 'global' },
  { id: 'app.escape',            keys: { mac: 'Esc',  other: 'Esc' },           label: 'Dismiss / cancel',            scope: 'global' },

  // Search input
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: 'Submit search',                scope: 'searchInput' },
  { id: 'search.clear',          keys: { mac: 'Esc',  other: 'Esc' },           label: 'Clear query (or disarm chip)', scope: 'searchInput' },
  { id: 'search.clearScope',     keys: { mac: '⌫⌫',   other: 'Backspace ×2' },  label: 'Clear scope chip',             scope: 'searchInput' },
  { id: 'search.intoResults',    keys: { mac: '↓',    other: '↓' },             label: 'Move focus into results',      scope: 'searchInput' },
  { id: 'search.intoTree',       keys: { mac: '↓',    other: '↓' },             label: 'Move focus into file tree',    scope: 'searchInput' },
  { id: 'search.escToTree',      keys: { mac: 'Esc',  other: 'Esc' },           label: 'Empty input → focus tree',     scope: 'searchInput' },

  // File tree (when a row is focused)
  { id: 'tree.next',             keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Move focus down',              scope: 'fileTree' },
  { id: 'tree.prev',             keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Move focus up',                scope: 'fileTree' },
  { id: 'tree.home',             keys: { mac: 'Home', other: 'Home' },          label: 'Jump to first row',            scope: 'fileTree' },
  { id: 'tree.end',              keys: { mac: 'End',  other: 'End' },           label: 'Jump to last row',             scope: 'fileTree' },
  { id: 'tree.expand',           keys: { mac: '→',    other: '→' },             label: 'Expand folder / first child',  scope: 'fileTree' },
  { id: 'tree.collapse',         keys: { mac: '←',    other: '←' },             label: 'Collapse folder / parent',     scope: 'fileTree' },
  { id: 'tree.toggleSelect',     keys: { mac: 'Space',other: 'Space' },         label: 'Toggle selection checkbox',    scope: 'fileTree' },
  { id: 'tree.activate',         keys: { mac: '↵',    other: 'Enter' },         label: 'Open file / toggle folder',    scope: 'fileTree' },
  { id: 'tree.openExternal',     keys: { mac: '⌘O',   other: 'Ctrl+O' },        label: 'Open file with system app',    scope: 'fileTree' },
  { id: 'tree.contextMenu',      keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: 'Open context menu',         scope: 'fileTree' },
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: 'Rename focused row',           scope: 'fileTree' },
  { id: 'tree.scope',            keys: { mac: 'S',    other: 'S' },             label: 'Set as search scope',          scope: 'fileTree' },
  { id: 'tree.info',             keys: { mac: 'I',    other: 'I' },             label: 'Show document info (files)',   scope: 'fileTree' },
  { id: 'tree.hide',             keys: { mac: 'H',    other: 'H' },             label: 'Toggle hidden state',          scope: 'fileTree' },

  // Search results list
  { id: 'results.next',          keys: { mac: '↓',    other: '↓' },             label: 'Next result',                  scope: 'searchResults' },
  { id: 'results.prev',          keys: { mac: '↑',    other: '↑' },             label: 'Previous result (or back to input)', scope: 'searchResults' },
  { id: 'results.open',          keys: { mac: '↵',    other: 'Enter' },         label: 'Open focused result',          scope: 'searchResults' },
  { id: 'results.backToInput',   keys: { mac: 'Esc',  other: 'Esc' },           label: 'Return focus to search input', scope: 'searchResults' },
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
