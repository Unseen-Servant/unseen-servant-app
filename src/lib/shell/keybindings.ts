// Single source of truth for app keybindings.
//
// The handlers hardcode the chord checks for speed and clarity — keys.ts
// for the chords that work whichever tool has the keyboard, each tool's
// own window listener for the rest — but every binding is also registered
// here so tooltips and the `?` help overlay can stay in sync. When you add
// a chord to a handler, add (or update) its entry here and reuse
// `chordHint(id)` in the corresponding button's `title` attribute. Its
// label is a message in messages/en.json; entries that word a key the same
// share one message.

import { m } from '../paraglide/messages';
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
  label: () => string;
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
  { id: 'settings.open',         keys: { mac: '⌘,',   other: 'Ctrl+,' },        label: m.keys_open_settings, scope: 'global' },
  { id: 'sidebar.toggle',        keys: { mac: '⌘B',   other: 'Ctrl+B' },        label: m.keys_show_or_hide_sidebars, scope: 'tool' },
  { id: 'focus.dock',            keys: { mac: '⌘⌥←',  other: 'Ctrl+Alt+←' },    label: m.keys_focus_panel_to_left, scope: 'global' },
  { id: 'focus.files',           keys: { mac: '⌘⌥→',  other: 'Ctrl+Alt+→' },    label: m.keys_focus_panel_to_right, scope: 'global' },
  { id: 'focus.dockDown',        keys: { mac: '⌘⌥↓',  other: 'Ctrl+Alt+↓' },    label: m.keys_focus_panel_below, scope: 'global' },
  { id: 'focus.dockUp',          keys: { mac: '⌘⌥↑',  other: 'Ctrl+Alt+↑' },    label: m.keys_focus_panel_above, scope: 'global' },
  { id: 'view.toggle',           keys: { mac: 'Tab',  other: 'Tab' },           label: m.keys_flip_view, scope: 'tool' },
  { id: 'rack.view',             keys: { mac: '1–8',  other: '1–8' },           label: m.keys_bring_up_rack_view_n, scope: 'global' },
  { id: 'collections.slot',      keys: { mac: '⌘1–9', other: 'Ctrl+1–9' },      label: m.keys_play_collection_n_alone_or, scope: 'global' },
  { id: 'collections.slotMix',   keys: { mac: '⌘⇧1–9', other: 'Ctrl+Shift+1–9' }, label: m.keys_mix_collection_n_in_or, scope: 'global' },
  { id: 'sync.run',              keys: { mac: '⌘R',   other: 'Ctrl+R' },        label: m.keys_re_detect_library_changes, scope: 'global' },
  { id: 'sync.commit',           keys: { mac: '⌘S',   other: 'Ctrl+S' },        label: m.keys_sync_ticked_files, scope: 'global' },
  { id: 'search.focus',          keys: { mac: '⌘K',   other: 'Ctrl+K' },        label: m.keys_focus_search, scope: 'global' },
  { id: 'filter.toggle',         keys: { mac: '⌘F',   other: 'Ctrl+F' },        label: m.keys_show_or_hide_filters_panel, scope: 'global' },
  { id: 'scope.bypass',          keys: { mac: 'B',    other: 'B' },             label: m.keys_bypass_scope_console, scope: 'global', switch: true },
  // Not a chord of its own — one line teaching the idiom every transport
  // key shares, so the sheet doesn't have to repeat it on eight labels.
  { id: 'help.overlay',          keys: { mac: '? / ⌘/', other: '? / Ctrl+/' },  label: m.keys_show_this_sheet, scope: 'global' },
  { id: 'app.escape',            keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_cancel_close_or_step_back, scope: 'global' },

  // Search input
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: m.keys_search_then_focus_first_result, scope: 'searchInput' },
  { id: 'search.intoBrowse',     keys: { mac: '↓',    other: '↓' },             label: m.keys_move_down_into_view, scope: 'searchInput' },
  { id: 'search.exit',           keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_leave_search, scope: 'searchInput' },

  // File tree (when a row is focused)
  { id: 'tree.next',             keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'fileTree' },
  { id: 'tree.prev',             keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'fileTree' },
  { id: 'tree.home',             keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: m.keys_jump_to_first_row, scope: 'fileTree' },
  { id: 'tree.end',              keys: { mac: 'End / ⌥↓', other: 'End' },           label: m.keys_jump_to_last_row, scope: 'fileTree' },
  { id: 'tree.expand',           keys: { mac: '→ / L', other: '→ / L' },        label: m.keys_expand_row, scope: 'fileTree' },
  { id: 'tree.collapse',         keys: { mac: '← / H', other: '← / H' },        label: m.keys_collapse_row, scope: 'fileTree' },
  { id: 'tree.collapseAll',      keys: { mac: '⇧← / ⇧H', other: 'Shift+← / Shift+H' }, label: m.keys_collapse_whole_tree, scope: 'fileTree' },
  { id: 'tree.toggleSelect',     keys: { mac: 'X',    other: 'X' },             label: m.keys_tick_row_checkbox, scope: 'fileTree', switch: true },
  { id: 'tree.tickRange',        keys: { mac: '⇧X',   other: 'Shift+X' },       label: m.keys_tick_from_last_tick_to, scope: 'fileTree', switch: true },
  { id: 'tree.activate',         keys: { mac: '↵',    other: 'Enter' },         label: m.keys_open_file_or_fold_folder, scope: 'fileTree' },
  { id: 'tree.open',             keys: { mac: '⌘O',   other: 'Ctrl+O' },        label: m.keys_open_file, scope: 'fileTree', match: 'meta+o' },
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: m.keys_rename_row, scope: 'fileTree', match: 'r' },
  { id: 'tree.delete',           keys: { mac: '⌘⌫',   other: 'Del' },           label: m.keys_move_row_to_trash, scope: 'fileTree' },
  { id: 'tree.contextMenu',      keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: m.keys_open_row_menu, scope: 'fileTree' },
  { id: 'tree.solo',             keys: { mac: 'S',    other: 'S' },             label: m.keys_solo_row_search_it_alone, scope: 'fileTree', match: 's', switch: true },
  { id: 'tree.mute',             keys: { mac: 'M',    other: 'M' },             label: m.keys_mute_row_drop_it_from, scope: 'fileTree', match: 'm', switch: true },
  { id: 'tree.hide',             keys: { mac: '.',    other: '.' },             label: m.keys_hide_row_or_unhide_it, scope: 'fileTree', match: '.' },
  { id: 'info.show',             keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: m.keys_show_file_info, scope: 'fileTree', match: 'meta+i' },

  // Systems view (when a row is focused)
  { id: 'systems.expand',        keys: { mac: '→ / L', other: '→ / L' },        label: m.keys_expand_row, scope: 'systemsView' },
  { id: 'systems.collapse',      keys: { mac: '← / H', other: '← / H' },        label: m.keys_collapse_row, scope: 'systemsView' },
  { id: 'systems.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: m.keys_open_file, scope: 'systemsView' },
  { id: 'systems.rename',        keys: { mac: 'R',    other: 'R' },             label: m.keys_rename_row, scope: 'systemsView' },
  { id: 'systems.toggleSelect',  keys: { mac: 'X',    other: 'X' },             label: m.keys_tick_row_checkbox, scope: 'systemsView', switch: true },
  { id: 'systems.tickRange',     keys: { mac: '⇧X',   other: 'Shift+X' },       label: m.keys_tick_from_last_tick_to, scope: 'systemsView', switch: true },
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: m.keys_solo_row_search_it_alone, scope: 'systemsView', switch: true },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: m.keys_mute_row_drop_it_from, scope: 'systemsView', switch: true },
  { id: 'systems.soloGroup',     keys: { mac: '⇧S',   other: 'Shift+S' },       label: m.keys_solo_whole_system, scope: 'systemsView', switch: true },
  { id: 'systems.muteGroup',     keys: { mac: '⇧M',   other: 'Shift+M' },       label: m.keys_mute_whole_system, scope: 'systemsView', switch: true },
  { id: 'systems.info',          keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: m.keys_show_file_info, scope: 'systemsView' },

  // Collections panel (when a row is focused)
  { id: 'collections.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'collections' },
  { id: 'collections.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'collections' },
  { id: 'collections.home',      keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: m.keys_jump_to_first_row, scope: 'collections' },
  { id: 'collections.end',       keys: { mac: 'End / ⌥↓', other: 'End' },           label: m.keys_jump_to_last_row, scope: 'collections' },
  { id: 'collections.expand',    keys: { mac: '→ / L', other: '→ / L' },        label: m.keys_expand_row, scope: 'collections' },
  { id: 'collections.collapse',  keys: { mac: '← / H', other: '← / H' },        label: m.keys_collapse_row, scope: 'collections' },
  { id: 'collections.toggle',    keys: { mac: '↵',    other: 'Enter' },         label: m.keys_fold_or_unfold_collection, scope: 'collections' },
  { id: 'collections.openFile',  keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: m.keys_open_file, scope: 'collections' },
  { id: 'collections.removeFile', keys: { mac: '⌘⌫',  other: 'Del' },           label: m.keys_remove_file, scope: 'collections' },
  { id: 'collections.play',      keys: { mac: 'P / Space', other: 'P / Space' }, label: m.keys_play_collection_or_stop_it, scope: 'collections', switch: true },
  { id: 'collections.mute',      keys: { mac: 'M',    other: 'M' },             label: m.keys_mute_row_drop_it_from, scope: 'collections', switch: true },
  { id: 'collections.rename',    keys: { mac: 'R',    other: 'R' },             label: m.keys_rename_row, scope: 'collections' },
  { id: 'collections.arm',       keys: { mac: 'E',    other: 'E' },             label: m.keys_arm_collection_or_disarm_it, scope: 'collections', switch: true },
  { id: 'collections.archive',   keys: { mac: 'A',    other: 'A' },             label: m.keys_archive_or_restore_collection, scope: 'collections' },
  { id: 'collections.delete',    keys: { mac: '⌘⌫',   other: 'Del' },           label: m.keys_delete_collection, scope: 'collections' },
  { id: 'collections.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_release_list, scope: 'collections' },
  { id: 'collections.new',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: m.keys_create_collection_ready_to_name, scope: 'global' },

  // Filters panel (while the pane holds focus)
  { id: 'filterPanel.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'filterPanel' },
  { id: 'filterPanel.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'filterPanel' },
  { id: 'filterPanel.home',      keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: m.keys_jump_to_first_row, scope: 'filterPanel' },
  { id: 'filterPanel.end',       keys: { mac: 'End / ⌥↓', other: 'End' },           label: m.keys_jump_to_last_row, scope: 'filterPanel' },
  { id: 'filterPanel.expand',    keys: { mac: '→ / L', other: '→ / L' },        label: m.keys_expand_row, scope: 'filterPanel' },
  { id: 'filterPanel.collapse',  keys: { mac: '← / H', other: '← / H' },        label: m.keys_collapse_row, scope: 'filterPanel' },
  // Channel rows (curation, system) answer with their M; view rows have no M,
  // so this hits their single switch instead. One key, "do this row's thing".
  { id: 'filterPanel.toggle',    keys: { mac: 'X',    other: 'X' },             label: m.keys_tick_row_checkbox, scope: 'filterPanel', switch: true },
  { id: 'filterPanel.solo',      keys: { mac: 'S',    other: 'S' },             label: m.keys_solo_row_search_it_alone, scope: 'filterPanel', switch: true },
  { id: 'filterPanel.mute',      keys: { mac: 'M',    other: 'M' },             label: m.keys_mute_row_drop_it_from, scope: 'filterPanel', switch: true },
  { id: 'filterPanel.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_release_list, scope: 'filterPanel' },

  // Command, in Prep (on the selected row). No `match`: Command's menus show
  // the hint without taking the key, as the collections menu does, and 'r'
  // is tree.rename's.
  { id: 'command.rename',        keys: { mac: 'R',    other: 'R' },             label: m.keys_rename_row, scope: 'commandPrep' },
  // The list grammar, on the selection (keybindings audit §4): what the
  // tree's rows answer, Command's answer too.
  { id: 'command.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: m.keys_open_row_in_inspector, scope: 'commandPrep' },
  { id: 'command.newNote',       keys: { mac: '⌘N',   other: 'Ctrl+N' },        label: m.keys_create_note_beside_selection, scope: 'commandPrep' },
  { id: 'command.newBeat',       keys: { mac: '⇧⌘N',  other: 'Ctrl+Shift+N' },  label: m.keys_create_beat_armed_ready_to, scope: 'commandPrep' },
  { id: 'command.arm',           keys: { mac: 'E',    other: 'E' },             label: m.keys_arm_beat_or_disarm_it, scope: 'commandPrep', switch: true },
  { id: 'command.tick',          keys: { mac: 'X',    other: 'X' },             label: m.keys_toggle_note_in_armed_beat, scope: 'commandPrep' },
  { id: 'command.delete',        keys: { mac: '⌘⌫',   other: 'Del' },           label: m.keys_move_row_to_trash, scope: 'commandPrep' },
  { id: 'command.contextMenu',   keys: { mac: '⇧F10', other: 'Shift+F10 / Menu' }, label: m.keys_open_row_menu, scope: 'commandPrep' },
  // Prep's lists — the shelf, the tracks, the beats — are its regions:
  // the arrows step the one the selection is in, or the one last clicked
  // into, and ⌘⌥←/→ walk between them. The vi letters are free here.
  { id: 'command.listNext',      keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'commandPrep' },
  { id: 'command.listPrev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'commandPrep' },
  { id: 'command.listHome',      keys: { mac: 'Home / ⌥↑', other: 'Home' },     label: m.keys_jump_to_first_row, scope: 'commandPrep' },
  { id: 'command.listEnd',       keys: { mac: 'End / ⌥↓', other: 'End' },       label: m.keys_jump_to_last_row, scope: 'commandPrep' },
  { id: 'command.trackAcross',   keys: { mac: '→ ← / L H', other: '→ ← / L H' }, label: m.keys_step_across_to_next_track, scope: 'commandPrep' },
  { id: 'command.lists',         keys: { mac: '⌘⌥← →', other: 'Ctrl+Alt+← →' }, label: m.keys_step_shelf_tracks_beats, scope: 'commandPrep' },
  // In Prep and Play, on the row or card under the pointer, else the
  // selected one, as Legend Lore's A shelves a collection. No `match`, as R.
  { id: 'command.spend',         keys: { mac: 'A',    other: 'A' },             label: m.keys_spend_or_unspend_row_at, scope: 'command' },
  // In Prep: Live's Insert Audio and MIDI Track, as a note or an image
  // track, after the selected note's track, else at the end.
  { id: 'command.insertNoteTrack',  keys: { mac: '⌘T',  other: 'Ctrl+T' },       label: m.keys_insert_note_track, scope: 'commandPrep' },
  { id: 'command.insertImageTrack', keys: { mac: '⇧⌘T', other: 'Ctrl+Shift+T' }, label: m.keys_insert_image_track, scope: 'commandPrep' },
  // In Prep and Play, from the editor too: Obsidian's reading-view key.
  { id: 'command.read',          keys: { mac: '⌘E',   other: 'Ctrl+E' },        label: m.keys_read_note_rendered_or_edit, scope: 'command' },
  // In Play: the jot bar, from the editor too. ⇧⌘J in Prep and Play, from
  // the editor and the jot bar too; ⌘O is the selection's, as in the tree.
  { id: 'command.jot',           keys: { mac: '⌘J',   other: 'Ctrl+J' },        label: m.keys_jot_line_to_session_note, scope: 'commandPlay' },
  { id: 'command.sessionNote',   keys: { mac: '⇧⌘J',  other: 'Ctrl+Shift+J' },  label: m.keys_open_session_note, scope: 'command' },
  { id: 'command.editorEscape',  keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_leave_editor_note_stays_open, scope: 'command' },
  // In Play, on the session player, as Legend Lore's collections take them.
  { id: 'command.next',          keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'commandPlay' },
  { id: 'command.prev',          keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'commandPlay' },
  { id: 'command.play',          keys: { mac: 'P / Space', other: 'P / Space' }, label: m.keys_launch_beat_or_stop_it, scope: 'commandPlay', switch: true },
  { id: 'command.nextBeat',      keys: { mac: '⇧Space', other: 'Shift+Space' }, label: m.keys_launch_next_beat, scope: 'commandPlay' },
  { id: 'command.playerOpen',    keys: { mac: '↵',     other: 'Enter' },         label: m.keys_open_beat_in_inspector, scope: 'commandPlay' },
  // In Play, on the board: the toolbar's tools on Miro's letters (board
  // toolbar design §3.5). A tool that makes something hands back to Select.
  { id: 'command.boardSelect',   keys: { mac: 'V',    other: 'V' },             label: m.keys_select_and_move_cards, scope: 'commandPlay' },
  { id: 'command.boardHand',     keys: { mac: 'H',    other: 'H' },             label: m.keys_pan_board_over_cards_too, scope: 'commandPlay' },
  { id: 'command.boardNote',     keys: { mac: 'D',    other: 'D' },             label: m.keys_place_note_where_you_click, scope: 'commandPlay' },
  { id: 'command.boardText',     keys: { mac: 'T',    other: 'T' },             label: m.keys_place_text_card_where_you, scope: 'commandPlay' },
  { id: 'command.boardSticky',   keys: { mac: 'N',    other: 'N' },             label: m.keys_place_sticky_where_you_click, scope: 'commandPlay' },
  { id: 'command.boardLine',     keys: { mac: 'L',    other: 'L' },             label: m.keys_draw_line_from_one_card, scope: 'commandPlay' },
  { id: 'command.boardFrame',    keys: { mac: 'F',    other: 'F' },             label: m.keys_draw_frame_click_or_drag, scope: 'commandPlay' },
  { id: 'command.boardGroup',    keys: { mac: '⌘G',   other: 'Ctrl+G' },        label: m.keys_frame_selected_cards, scope: 'commandPlay' },
  { id: 'command.boardUngroup',  keys: { mac: '⇧⌘G',  other: 'Ctrl+Shift+G' },  label: m.keys_remove_frames_keep_cards, scope: 'commandPlay' },
  { id: 'command.boardUndo',     keys: { mac: '⌘Z',   other: 'Ctrl+Z' },        label: m.keys_undo_last_change, scope: 'commandPlay' },
  { id: 'command.boardRedo',     keys: { mac: '⇧⌘Z',  other: 'Ctrl+Shift+Z' },  label: m.keys_redo_last_change, scope: 'commandPlay' },
  { id: 'command.boardDuplicate', keys: { mac: '⌘D',  other: 'Ctrl+D' },        label: m.keys_duplicate_selection, scope: 'commandPlay' },
  { id: 'command.boardDelete',   keys: { mac: '⌫',    other: 'Backspace / Del' }, label: m.keys_delete_selected_cards, scope: 'commandPlay' },
  { id: 'command.boardFitAll',   keys: { mac: '⌥1',   other: 'Alt+1' },         label: m.keys_fit_whole_board_in_view, scope: 'commandPlay' },
  { id: 'command.boardFitSelection', keys: { mac: '⌥2', other: 'Alt+2' },      label: m.keys_fit_selection_in_view, scope: 'commandPlay' },
  { id: 'command.boardFitLive',  keys: { mac: '⌥3',   other: 'Alt+3' },         label: m.keys_fit_live_cards_in_view, scope: 'commandPlay' },
  { id: 'command.boardFill',     keys: { mac: '⇧⌘F',  other: 'Ctrl+Shift+F' },  label: m.keys_fill_rack_with_board_and, scope: 'commandPlay' },

  // Context menu (when open)
  { id: 'contextMenu.next',      keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'contextMenu' },
  { id: 'contextMenu.prev',      keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'contextMenu' },
  { id: 'contextMenu.openSub',   keys: { mac: '→ / L', other: '→ / L' },        label: m.keys_open_submenu, scope: 'contextMenu' },
  { id: 'contextMenu.closeSub',  keys: { mac: '← / H', other: '← / H' },        label: m.keys_close_submenu, scope: 'contextMenu' },
  { id: 'contextMenu.activate',  keys: { mac: '↵',    other: 'Enter' },         label: m.keys_choose_item, scope: 'contextMenu' },

  // Search results list
  { id: 'results.next',          keys: { mac: '↓ / J', other: '↓ / J' },        label: m.keys_move_down_row, scope: 'searchResults' },
  { id: 'results.prev',          keys: { mac: '↑ / K', other: '↑ / K' },        label: m.keys_move_up_row, scope: 'searchResults' },
  { id: 'results.home',          keys: { mac: 'Home / ⌥↑', other: 'Home' },          label: m.keys_jump_to_first_row, scope: 'searchResults' },
  { id: 'results.end',           keys: { mac: 'End / ⌥↓', other: 'End' },           label: m.keys_jump_to_last_row, scope: 'searchResults' },
  { id: 'results.open',          keys: { mac: '↵ / ⌘O', other: 'Enter / Ctrl+O' }, label: m.keys_open_file, scope: 'searchResults' },
  // No switch flag: the search rows draw no S/M squares — the lit state
  // materializes as a scope-bar chip instead.
  { id: 'results.solo',          keys: { mac: 'S',    other: 'S' },             label: m.keys_solo_row_search_it_alone, scope: 'searchResults' },
  { id: 'results.mute',          keys: { mac: 'M',    other: 'M' },             label: m.keys_mute_row_drop_it_from, scope: 'searchResults' },
  { id: 'results.toggleSelect',  keys: { mac: 'X',    other: 'X' },             label: m.keys_tick_row_checkbox, scope: 'searchResults', switch: true },
  { id: 'results.info',          keys: { mac: '⌘I',   other: 'Ctrl+I' },        label: m.keys_show_file_info, scope: 'searchResults' },
  { id: 'results.exit',          keys: { mac: 'Esc',  other: 'Esc' },           label: m.keys_leave_search, scope: 'searchResults' },

  // Modal — excluded from the cheat sheet by KeyboardHelpOverlay's
  // SCOPE_ORDER, which must keep omitting 'modal'. Defined anyway so the commit
  // switch's face and the dialog's matcher read the chord from one place
  // instead of hardcoding a glyph in each.
  { id: 'confirm.commit',        keys: { mac: '⌘⌫',   other: 'Del' },           label: m.keys_commit_destructive_confirmation, scope: 'modal' },
  // Must stay Enter: the safe commit fires via native <button> activation
  // (focus sits on the button), not a dispatched chord — see confirmKeys.ts.
  { id: 'confirm.commitSafe',    keys: { mac: '↵',    other: 'Enter' },         label: m.keys_commit_confirmation,             scope: 'modal' },
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
