// Single source of truth for app keybindings.
//
// The handlers hardcode the chord checks for speed and clarity — keys.ts
// for the chords that work whichever tool has the keyboard, each tool's
// own window listener for the rest — but every binding is also registered
// here so tooltips and the `?` help overlay can stay in sync. When you add
// a chord to a handler, add (or update) its entry here and reuse
// `chordHint(id)` in the corresponding button's `title` attribute.

import type { FocusPath } from './focus';

export type KeyScope =
  | 'global'
  // Either tool's, on the one that has the keyboard: the same chord, each
  // tool's own meaning for it.
  | 'tool'
  | 'fileTree'
  | 'systemsView'
  | 'collections'
  | 'searchInput'
  | 'searchResults'
  | 'filterPanel'
  // Command in either view, then in Prep's lists, then in Play.
  | 'command'
  | 'commandPrep'
  | 'commandPlay'
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
  // True when this key throws a physical switch in the window — one of
  // the app's 18px hardware squares that lights when engaged. The cheat sheet
  // caps every key, but gives these a purple edge, because the difference is
  // real: a switch has a square you can point at, a command does not. A key that only reaches a context-menu item — R, A, '.', C — is a
  // command, however bare it looks. Shift can ride along only where the
  // shifted chord still lands on a real square (⇧S/⇧M reach the systems
  // view's group cluster); the test pins those by id.
  //
  // The square goes by three class names and they are one control: `.sm-btn`
  // (S / M / B), `.tr-btn` (collections' P and E), and `.app-checkbox` (X) —
  // same 18px, same --border-subtle, same --radius-sm. Every flag below was
  // checked against the component that renders it rather than against a list,
  // which is what caught this: "an .sm-btn" is false for several of them. The
  // test for it lives in keybindings.test.ts; the flag is what the key *does*, and
  // the renderer decides what that earns.
  switch?: true;
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
  { id: 'settings.open',         keys: { mac: '⌘,',   other: 'Ctrl+,' },        label: 'Settings', scope: 'global' },
  { id: 'sidebar.toggle',        keys: { mac: '⌘B',   other: 'Ctrl+B' },        label: 'Show or hide the sidebars', scope: 'tool' },
  { id: 'focus.dock',            keys: { mac: '⌘⌥←',  other: 'Ctrl+Alt+←' },    label: 'Focus the panel to the left', scope: 'global' },
  { id: 'focus.files',           keys: { mac: '⌘⌥→',  other: 'Ctrl+Alt+→' },    label: 'Focus the panel to the right', scope: 'global' },
  { id: 'focus.dockDown',        keys: { mac: '⌘⌥↓',  other: 'Ctrl+Alt+↓' },    label: 'Focus the panel below', scope: 'global' },
  { id: 'focus.dockUp',          keys: { mac: '⌘⌥↑',  other: 'Ctrl+Alt+↑' },    label: 'Focus the panel above', scope: 'global' },
  { id: 'view.toggle',           keys: { mac: 'Tab',  other: 'Tab' },           label: 'Tree ⇄ systems, Prep ⇄ Play', scope: 'tool' },
  { id: 'rack.view',             keys: { mac: '1–8',  other: '1–8' },           label: 'Rack view N', scope: 'global' },
  { id: 'collections.slot',      keys: { mac: '⌘1–9', other: 'Ctrl+1–9' },      label: 'Play collection N alone, or stop', scope: 'global' },
  { id: 'collections.slotMix',   keys: { mac: '⌘⇧1–9', other: 'Ctrl+Shift+1–9' }, label: 'Collection N into the mix, or out', scope: 'global' },
  { id: 'sync.run',              keys: { mac: '⌘R',   other: 'Ctrl+R' },        label: 'Re-detect library changes', scope: 'global' },
  { id: 'sync.commit',           keys: { mac: '⌘S',   other: 'Ctrl+S' },        label: 'Sync the ticked files', scope: 'global' },
  { id: 'search.focus',          keys: { mac: '⌘K',   other: 'Ctrl+K' },        label: 'Search', scope: 'global' },
  { id: 'filter.toggle',         keys: { mac: '⌘F',   other: 'Ctrl+F' },        label: 'Filters panel', scope: 'global' },
  { id: 'filter.toggleHidden',   keys: { mac: '⌘⇧.',  other: 'Ctrl+Shift+.' },  label: 'Show hidden items', scope: 'global' },
  { id: 'library.reveal',        keys: { mac: '⌘⇧O',  other: 'Ctrl+Shift+O' },  label: 'Reveal the library on disk', scope: 'global' },
  { id: 'scope.bypass',          keys: { mac: 'B',    other: 'B' },             label: 'Bypass the scope console', scope: 'global', switch: true },
  // Not a chord of its own — one line teaching the idiom every transport
  // key shares, so the sheet doesn't have to repeat it on eight labels.
  { id: 'scope.peek',            keys: { mac: 'hold S/M/P/B', other: 'hold S/M/P/B' }, label: 'Hold: on only while held', scope: 'global' },
  { id: 'help.overlay',          keys: { mac: '? / ⌘/', other: '? / Ctrl+/' },  label: 'This sheet', scope: 'global' },
  { id: 'app.escape',            keys: { mac: 'Esc',  other: 'Esc' },           label: 'Cancel, close, step back', scope: 'global' },

  // Search input
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: 'Search; focus on the first result', scope: 'searchInput' },
  { id: 'search.mention',        keys: { mac: '@',    other: '@' },             label: 'Play a collection: ↵ alone, ⇧↵ into the mix', scope: 'searchInput' },
  { id: 'search.filter',         keys: { mac: '/',    other: '/' },             label: 'Filter by name; ↵ to the first match', scope: 'searchInput' },
  { id: 'search.intoBrowse',     keys: { mac: '↓',    other: '↓' },             label: 'Down into the view', scope: 'searchInput' },
  { id: 'search.exit',           keys: { mac: 'Esc',  other: 'Esc' },           label: 'Leave the search', scope: 'searchInput' },

  // File tree (when a row is focused)
  { id: 'tree.next',             keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'fileTree' },
  { id: 'tree.prev',             keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'fileTree' },
  { id: 'tree.home',             keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: 'First row', scope: 'fileTree' },
  { id: 'tree.end',              keys: { mac: 'End / ⌥↓', other: 'End' },           label: 'Last row', scope: 'fileTree' },
  { id: 'tree.expand',           keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand', scope: 'fileTree' },
  { id: 'tree.collapse',         keys: { mac: '← / H', other: '← / H' },        label: 'Collapse', scope: 'fileTree' },
  { id: 'tree.collapseAll',      keys: { mac: '⇧← / ⇧H', other: 'Shift+← / Shift+H' }, label: 'Collapse the whole tree', scope: 'fileTree' },
  { id: 'tree.toggleSelect',     keys: { mac: 'X',    other: 'X' },             label: "Tick the row's checkbox", scope: 'fileTree', switch: true },
  { id: 'tree.tickRange',        keys: { mac: '⇧X',   other: 'Shift+X' },       label: 'Tick from the last tick to here', scope: 'fileTree', switch: true },
  { id: 'tree.activate',         keys: { mac: '↵',    other: 'Enter' },         label: 'Open the file, or fold the folder', scope: 'fileTree' },
  { id: 'tree.open',             keys: { mac: '⌘O',   other: 'Ctrl+O' },        label: 'Open the file', scope: 'fileTree', match: 'meta+o' },
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: 'Rename', scope: 'fileTree', match: 'r' },
  { id: 'tree.delete',           keys: { mac: '⌘⌫',   other: 'Del' },           label: 'Move to Trash', scope: 'fileTree' },
  { id: 'tree.openExternal',     keys: { mac: '⌥⌘R',  other: 'Ctrl+Alt+R' },    label: 'Reveal on disk', scope: 'fileTree' },
  { id: 'tree.contextMenu',      keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: "Open the row's menu", scope: 'fileTree' },
  { id: 'tree.solo',             keys: { mac: 'S',    other: 'S' },             label: 'Solo: search only this', scope: 'fileTree', match: 's', switch: true },
  { id: 'tree.mute',             keys: { mac: 'M',    other: 'M' },             label: 'Mute: drop from search', scope: 'fileTree', match: 'm', switch: true },
  { id: 'tree.hide',             keys: { mac: '.',    other: '.' },             label: 'Hide, or unhide', scope: 'fileTree', match: '.' },
  { id: 'tree.addToCollection',  keys: { mac: 'C',    other: 'C' },             label: 'Add to a collection, from a menu', scope: 'fileTree', match: 'c' },
  { id: 'info.show',             keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: 'Show info', scope: 'fileTree', match: 'meta+i' },

  // Systems view (when a row is focused)
  { id: 'systems.expand',        keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand', scope: 'systemsView' },
  { id: 'systems.collapse',      keys: { mac: '← / H', other: '← / H' },        label: 'Collapse', scope: 'systemsView' },
  { id: 'systems.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: 'Open the file', scope: 'systemsView' },
  { id: 'systems.rename',        keys: { mac: 'R',    other: 'R' },             label: 'Rename', scope: 'systemsView' },
  { id: 'systems.toggleSelect',  keys: { mac: 'X',    other: 'X' },             label: "Tick the row's checkbox", scope: 'systemsView', switch: true },
  { id: 'systems.tickRange',     keys: { mac: '⇧X',   other: 'Shift+X' },       label: 'Tick from the last tick to here', scope: 'systemsView', switch: true },
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: 'Solo: search only this', scope: 'systemsView', switch: true },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: 'Mute: drop from search', scope: 'systemsView', switch: true },
  { id: 'systems.soloGroup',     keys: { mac: '⇧S',   other: 'Shift+S' },       label: 'Solo the whole system', scope: 'systemsView', switch: true },
  { id: 'systems.muteGroup',     keys: { mac: '⇧M',   other: 'Shift+M' },       label: 'Mute the whole system', scope: 'systemsView', switch: true },
  { id: 'systems.info',          keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: 'Show info', scope: 'systemsView' },

  // Collections panel (when a row is focused)
  { id: 'collections.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'collections' },
  { id: 'collections.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'collections' },
  { id: 'collections.home',      keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: 'First row', scope: 'collections' },
  { id: 'collections.end',       keys: { mac: 'End / ⌥↓', other: 'End' },           label: 'Last row', scope: 'collections' },
  { id: 'collections.expand',    keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand', scope: 'collections' },
  { id: 'collections.collapse',  keys: { mac: '← / H', other: '← / H' },        label: 'Collapse', scope: 'collections' },
  { id: 'collections.toggle',    keys: { mac: '↵',    other: 'Enter' },         label: 'Fold or unfold the collection', scope: 'collections' },
  { id: 'collections.openFile',  keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: 'Open the file', scope: 'collections' },
  { id: 'collections.removeFile', keys: { mac: '⌘⌫',  other: 'Del' },           label: 'Remove the file', scope: 'collections' },
  { id: 'collections.play',      keys: { mac: 'P / Space', other: 'P / Space' }, label: 'Play, or stop', scope: 'collections', switch: true },
  { id: 'collections.mute',      keys: { mac: 'M',    other: 'M' },             label: 'Mute: drop from search', scope: 'collections', switch: true },
  { id: 'collections.rename',    keys: { mac: 'R',    other: 'R' },             label: 'Rename', scope: 'collections' },
  { id: 'collections.arm',       keys: { mac: 'E',    other: 'E' },             label: 'Arm, or disarm', scope: 'collections', switch: true },
  { id: 'collections.archive',   keys: { mac: 'A',    other: 'A' },             label: 'Archive, or unarchive', scope: 'collections' },
  { id: 'collections.delete',    keys: { mac: '⌘⌫',   other: 'Del' },           label: 'Delete the collection', scope: 'collections' },
  { id: 'collections.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: 'Release the list', scope: 'collections' },
  { id: 'collections.new',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: 'New collection, ready to name', scope: 'global' },

  // Filters panel (while the pane holds focus)
  { id: 'filterPanel.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'filterPanel' },
  { id: 'filterPanel.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'filterPanel' },
  { id: 'filterPanel.home',      keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: 'First row', scope: 'filterPanel' },
  { id: 'filterPanel.end',       keys: { mac: 'End / ⌥↓', other: 'End' },           label: 'Last row', scope: 'filterPanel' },
  { id: 'filterPanel.expand',    keys: { mac: '→ / L', other: '→ / L' },        label: 'Expand', scope: 'filterPanel' },
  { id: 'filterPanel.collapse',  keys: { mac: '← / H', other: '← / H' },        label: 'Collapse', scope: 'filterPanel' },
  // Channel rows (curation, system) answer with their M; view rows have no M,
  // so this hits their single switch instead. One key, "do this row's thing".
  { id: 'filterPanel.toggle',    keys: { mac: 'X',    other: 'X' },             label: "Tick the row's checkbox", scope: 'filterPanel', switch: true },
  { id: 'filterPanel.solo',      keys: { mac: 'S',    other: 'S' },             label: 'Solo: search only this', scope: 'filterPanel', switch: true },
  { id: 'filterPanel.mute',      keys: { mac: 'M',    other: 'M' },             label: 'Mute: drop from search', scope: 'filterPanel', switch: true },
  { id: 'filterPanel.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: 'Release the list', scope: 'filterPanel' },

  // Command, in Prep (on the selected row). No `match`: Command's menus show
  // the hint without taking the key, as the collections menu does, and 'r'
  // is tree.rename's.
  { id: 'command.rename',        keys: { mac: 'R',    other: 'R' },             label: 'Rename', scope: 'commandPrep' },
  // The list grammar, on the selection (keybindings audit §4): what the
  // tree's rows answer, Command's answer too.
  { id: 'command.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: 'Open in the inspector', scope: 'commandPrep' },
  { id: 'command.newNote',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: 'New note beside the selection', scope: 'commandPrep' },
  { id: 'command.newBeat',       keys: { mac: '⇧⌘N',  other: 'Ctrl+Shift+N' },  label: 'New beat, armed, ready to name', scope: 'commandPrep' },
  { id: 'command.arm',           keys: { mac: 'E',    other: 'E' },             label: 'Arm, or disarm, the beat', scope: 'commandPrep', switch: true },
  { id: 'command.tick',          keys: { mac: 'X',    other: 'X' },             label: 'Into the armed beat, or out of it', scope: 'commandPrep' },
  { id: 'command.delete',        keys: { mac: '⌘⌫',   other: 'Del' },           label: 'Move to Trash', scope: 'commandPrep' },
  { id: 'command.reveal',        keys: { mac: '⌥⌘R',  other: 'Ctrl+Alt+R' },    label: 'Reveal on disk', scope: 'commandPrep' },
  { id: 'command.contextMenu',   keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: "Open the row's menu", scope: 'commandPrep' },
  // Prep's lists — the shelf, the tracks, the beats — are its regions:
  // the arrows step the one the selection is in, or the one last clicked
  // into, and ⌘⌥←/→ walk between them. The vi letters are free here.
  { id: 'command.listNext',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'commandPrep' },
  { id: 'command.listPrev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'commandPrep' },
  { id: 'command.listHome',      keys: { mac: 'Home / ⌥↑', other: 'Home' },     label: 'First row', scope: 'commandPrep' },
  { id: 'command.listEnd',       keys: { mac: 'End / ⌥↓', other: 'End' },       label: 'Last row', scope: 'commandPrep' },
  { id: 'command.trackAcross',   keys: { mac: '→ ← / L H', other: '→ ← / L H' }, label: 'Same row, next or previous track', scope: 'commandPrep' },
  { id: 'command.lists',         keys: { mac: '⌘⌥← →', other: 'Ctrl+Alt+← →' }, label: 'Shelf ⇄ tracks ⇄ beats', scope: 'commandPrep' },
  // In Prep and Play, on the row or card under the pointer, else the
  // selected one, as Legend Lore's A shelves a collection. No `match`, as R.
  { id: 'command.spend',         keys: { mac: 'A',    other: 'A' },             label: 'Spend, or unspend, the pointed or selected row', scope: 'command' },
  // In Prep: Live's Insert Audio and MIDI Track, as a note or an image
  // track, after the selected note's track, else at the end.
  { id: 'command.insertNoteTrack',  keys: { mac: '⌘T',  other: 'Ctrl+T' },       label: 'Insert a note track', scope: 'commandPrep' },
  { id: 'command.insertImageTrack', keys: { mac: '⇧⌘T', other: 'Ctrl+Shift+T' }, label: 'Insert an image track', scope: 'commandPrep' },
  // In Prep and Play, from the editor too: Obsidian's reading-view key.
  { id: 'command.read',          keys: { mac: '⌘E',   other: 'Ctrl+E' },        label: 'Read the note rendered, or edit it', scope: 'command' },
  // In Play: the jot bar, from the editor too. ⇧⌘J in Prep and Play, from
  // the editor and the jot bar too; ⌘O is the selection's, as in the tree.
  { id: 'command.jot',           keys: { mac: '⌘J',   other: 'Ctrl+J' },        label: 'Jot a line to the session note', scope: 'commandPlay' },
  { id: 'command.sessionNote',   keys: { mac: '⇧⌘J',  other: 'Ctrl+Shift+J' },  label: 'Open the session note', scope: 'command' },
  { id: 'command.editorEscape',  keys: { mac: 'Esc',  other: 'Esc' },           label: 'Leave the editor; the note stays open', scope: 'command' },
  // In Play, on the session player, as Legend Lore's collections take them.
  { id: 'command.next',          keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'commandPlay' },
  { id: 'command.prev',          keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'commandPlay' },
  { id: 'command.play',          keys: { mac: 'P / Space', other: 'P / Space' }, label: 'Launch, or stop, the beat', scope: 'commandPlay', switch: true },
  // In Play, on the board: the toolbar's tools on Miro's letters (board
  // toolbar design §3.5). A tool that makes something hands back to Select.
  { id: 'command.boardSelect',   keys: { mac: 'V',    other: 'V' },             label: 'Select and move cards', scope: 'commandPlay' },
  { id: 'command.boardHand',     keys: { mac: 'H',    other: 'H' },             label: 'Pan, over the cards too', scope: 'commandPlay' },
  { id: 'command.boardNote',     keys: { mac: 'D',    other: 'D' },             label: 'Place a note where you click', scope: 'commandPlay' },
  { id: 'command.boardText',     keys: { mac: 'T',    other: 'T' },             label: 'A text card where you click', scope: 'commandPlay' },
  { id: 'command.boardSticky',   keys: { mac: 'N',    other: 'N' },             label: 'A sticky where you click', scope: 'commandPlay' },
  { id: 'command.boardLine',     keys: { mac: 'L',    other: 'L' },             label: 'A line from one card to another', scope: 'commandPlay' },
  { id: 'command.boardFrame',    keys: { mac: 'F',    other: 'F' },             label: 'A frame, clicked or dragged to size', scope: 'commandPlay' },
  { id: 'command.boardGroup',    keys: { mac: '⌘G',   other: 'Ctrl+G' },        label: 'Frame the selected cards', scope: 'commandPlay' },
  { id: 'command.boardUngroup',  keys: { mac: '⇧⌘G',  other: 'Ctrl+Shift+G' },  label: 'Remove the frames, keep the cards', scope: 'commandPlay' },
  { id: 'command.boardUndo',     keys: { mac: '⌘Z',   other: 'Ctrl+Z' },        label: 'Undo', scope: 'commandPlay' },
  { id: 'command.boardRedo',     keys: { mac: '⇧⌘Z',  other: 'Ctrl+Shift+Z' },  label: 'Redo', scope: 'commandPlay' },
  { id: 'command.boardDuplicate', keys: { mac: '⌘D',  other: 'Ctrl+D' },        label: 'Duplicate the selection', scope: 'commandPlay' },
  { id: 'command.boardFitAll',   keys: { mac: '⌥1',   other: 'Alt+1' },         label: 'Fit the whole board', scope: 'commandPlay' },
  { id: 'command.boardFitSelection', keys: { mac: '⌥2', other: 'Alt+2' },      label: 'Fit the selection', scope: 'commandPlay' },
  { id: 'command.boardFitLive',  keys: { mac: '⌥3',   other: 'Alt+3' },         label: 'Fit the live cards', scope: 'commandPlay' },
  { id: 'command.boardFill',     keys: { mac: '⇧⌘F',  other: 'Ctrl+Shift+F' },  label: 'Board fills the rack, and back', scope: 'commandPlay' },

  // Context menu (when open)
  { id: 'contextMenu.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'contextMenu' },
  { id: 'contextMenu.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'contextMenu' },
  { id: 'contextMenu.openSub',   keys: { mac: '→ / L', other: '→ / L' },        label: 'Open the submenu', scope: 'contextMenu' },
  { id: 'contextMenu.closeSub',  keys: { mac: '← / H', other: '← / H' },        label: 'Close the submenu', scope: 'contextMenu' },
  { id: 'contextMenu.activate',  keys: { mac: '↵',    other: 'Enter' },         label: 'Choose', scope: 'contextMenu' },

  // Search results list
  { id: 'results.next',          keys: { mac: '↓ / J', other: '↓ / J' },        label: 'Down a row', scope: 'searchResults' },
  { id: 'results.prev',          keys: { mac: '↑ / K', other: '↑ / K' },        label: 'Up a row', scope: 'searchResults' },
  { id: 'results.home',          keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: 'First row', scope: 'searchResults' },
  { id: 'results.end',           keys: { mac: 'End / ⌥↓', other: 'End' },           label: 'Last row', scope: 'searchResults' },
  { id: 'results.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: 'Open the file', scope: 'searchResults' },
  // No switch flag: the search rows draw no S/M squares — the lit state
  // materializes as a scope-bar chip instead.
  { id: 'results.solo',          keys: { mac: 'S',    other: 'S' },             label: 'Solo: search only this', scope: 'searchResults' },
  { id: 'results.mute',          keys: { mac: 'M',    other: 'M' },             label: 'Mute: drop from search', scope: 'searchResults' },
  { id: 'results.toggleSelect',  keys: { mac: 'X',    other: 'X' },             label: "Tick the row's checkbox", scope: 'searchResults', switch: true },
  { id: 'results.info',          keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: 'Show info', scope: 'searchResults' },
  { id: 'results.exit',          keys: { mac: 'Esc',  other: 'Esc' },           label: 'Leave the search', scope: 'searchResults' },

  // Modal — excluded from the cheat sheet by KeyboardHelpOverlay's
  // SCOPE_ORDER, which must keep omitting 'modal'. Defined anyway so the commit
  // switch's face and the dialog's matcher read the chord from one place
  // instead of hardcoding a glyph in each.
  { id: 'confirm.commit',        keys: { mac: '⌘⌫',   other: 'Del' },           label: 'Commit a destructive confirmation', scope: 'modal' },
  // Must stay Enter: the safe commit fires via native <button> activation
  // (focus sits on the button), not a dispatched chord — see confirmKeys.ts.
  { id: 'confirm.commitSafe',    keys: { mac: '↵',    other: 'Enter' },         label: 'Commit a confirmation',             scope: 'modal' },
];

const BY_ID = new Map(KEYBINDINGS.map(k => [k.id, k]));

// The scopes the sheet shows as live for a focus path (focus.ts): global
// always, either tool's while one has the keyboard, Legend Lore's bar
// whenever it does, the scope of the region that does, and Command's view. A menu can't be open under the sheet, so its scope
// never is; the modal one isn't on the sheet.
export function liveScopes(path: FocusPath): Set<KeyScope> {
  const live = new Set<KeyScope>(['global']);
  if (path.tool === 'command' || path.tool === 'legend-lore') live.add('tool');
  if (path.tool === 'command') {
    live.add('command');
    live.add(path.region === 'play' ? 'commandPlay' : 'commandPrep');
  }
  if (path.tool === 'legend-lore') {
    live.add('searchInput');
    const region: Record<string, KeyScope> = {
      tree: 'fileTree',
      systems: 'systemsView',
      search: 'searchResults',
      collections: 'collections',
      filters: 'filterPanel',
    };
    if (path.region && region[path.region]) live.add(region[path.region]);
  }
  return live;
}

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
// key, so menus frame it in brackets. Modifier chords (⌘O) and named keys (Home)
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

// Delete is the one binding whose key genuinely differs by platform: ⌘⌫ is the
// mac move-to-trash convention, Del the Windows/Linux one. Bare ⌫ stays inert on
// mac (it's a text-editing key there, not a file-manager one), and Shift is
// rejected everywhere — Shift+Del means "delete permanently" in file managers,
// which is not what either delete path does. Named keys can't round-trip through
// eventMatchKey (single characters only), so this is its own predicate and the
// menus show the chord as a hint they don't dispatch.
//
// `mac` is a parameter rather than a closed-over constant so tests can exercise
// both platforms without a real navigator.
export function isDeleteChord(event: ChordEvent, mac = isMac): boolean {
  if (event.shiftKey || event.altKey) return false;
  if (mac) return (event.metaKey || event.ctrlKey) && event.key === 'Backspace';
  return !event.metaKey && !event.ctrlKey && event.key === 'Delete';
}

// First/last row of a list. Home/End everywhere; on mac ⌥↑/⌥↓ too — laptop
// keyboards there have no Home/End keys, and ⌥↑/⌥↓ is the list-view
// convention. Not elsewhere: on Windows Alt+↑ is Explorer's "up one level".
// Cmd/Ctrl combinations are someone else's chord (⌘⌥↑/↓ walks the dock).
// Callers must test this ahead of their plain ↑/↓ step, which would
// otherwise swallow the ⌥ arrows.
export function jumpEdge(event: ChordEvent, mac = isMac): 'first' | 'last' | null {
  if (event.metaKey || event.ctrlKey) return null;
  if (event.key === 'Home') return 'first';
  if (event.key === 'End') return 'last';
  if (mac && event.altKey && !event.shiftKey) {
    if (event.key === 'ArrowUp') return 'first';
    if (event.key === 'ArrowDown') return 'last';
  }
  return null;
}

// aria-keyshortcuts for a destructive commit. keyShortcut() derives from
// `match`, and named keys can't round-trip through eventMatchKey (single
// characters only) — so this binding has no `match` and needs its own.
export function commitKeyShortcut(mac = isMac): string {
  return mac ? 'Meta+Backspace' : 'Delete';
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

export interface SystemsRowScopeAction {
  axis: 'file' | 'system';
  kind: 'solo' | 'mute';
}

// S/M dispatch for a focused systems-view row. Bare letters act on the
// row's file (the folder/file axis — the tree's "act on the row you're
// on" grammar); ⇧S/⇧M lift to the row's group on the systems axis. The
// system axis stays mute-only for the untagged bucket (#307): ⇧S is
// inert there, while bare S still solos the untagged file itself. A
// null return covers both "not my chord" and that deliberate inertness —
// callers let the event through either way. Meta/Ctrl/Alt combinations
// are someone else's chord (⌘S is sync). Callers must additionally
// check `!event.isComposing`, same as eventMatchKey — ChordEvent can't
// see composition state.
export function systemsRowScopeKey(
  event: ChordEvent,
  untagged: boolean,
): SystemsRowScopeAction | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (key !== 's' && key !== 'm') return null;
  const kind = key === 's' ? 'solo' : 'mute';
  if (!event.shiftKey) return { axis: 'file', kind };
  if (kind === 'solo' && untagged) return null;
  return { axis: 'system', kind };
}

export interface DigitChord {
  digit: number;
  shift: boolean;
  alt: boolean;
}

// Cmd/Ctrl + a digit key, read from event.code: ⇧ turns '1' into '!' and ⌥
// into '¡' on a US mac, and AZERTY needs ⇧ to type a digit at all, so
// event.key can't identify the key across the chords that share it. Top row
// only — the numpad isn't a place anyone reaches for a transport. Callers
// decide what ⇧/⌥ mean.
export function digitChord(event: ChordEvent): DigitChord | null {
  if (!(event.metaKey || event.ctrlKey)) return null;
  const m = /^Digit([1-9])$/.exec(event.code);
  if (!m) return null;
  return { digit: Number(m[1]), shift: event.shiftKey, alt: event.altKey };
}

// The display chord for track-select slot N, for tooltips and the badges
// the collections panel wears during an @-pick.
export function slotChord(n: number): string {
  return isMac ? `⌘${n}` : `Ctrl+${n}`;
}

// The match key for a binding id, or '' when the binding has no accelerator.
export function matchKey(id: string): string {
  return BY_ID.get(id)?.match ?? '';
}
