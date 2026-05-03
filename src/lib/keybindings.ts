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
  { id: 'view.toggle',           keys: { mac: '⌘\\',  other: 'Ctrl+\\' },       label: 'Toggle Tree ↔ Systems view',  scope: 'global' },
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
