# Keybindings audit and layout proposal

2026-10-21, after the focus/keybinding unification (71f665f..e7de811). The
dispatcher (`keys.ts`) now runs every key by place — overlay, region, tool,
global — so the question is no longer *who* gets a key but whether the keys
read as one instrument across Legend Lore and Command. This audits what is
bound, critiques it, proposes the layout, and names the Command actions that
deserve a key.

## 1. What is bound today

Counted from `keybindings.ts` (86 entries) against the handlers.

| Layer | Chords | Notes |
|---|---|---|
| Rack (host) | `1`–`8` views · `⌘⌥←→↑↓` cross the rail · `?` `⌘/` sheet · `⌘,` settings · Esc | PanelHost / StandaloneFrame |
| Transport (global, from either tool) | `⌘1`–`9` play one collection · `⇧⌘1`–`9` mix · `B` bypass · `⌘K` search · `⌘F` filters · `⌘N` collection · `⌘R` re-detect · `⌘S` sync · `⌘⇧.` hidden · `⌘⇧O` reveal | Legend Lore binds them at `global` |
| Either tool, its own | `Tab` view flip · `⌘B` sidebar · `⌘I` info (Legend Lore only) | listed as `global` on the sheet |
| Legend Lore lists | `↓↑` `J K` · `Home End` `⌥↑↓` · `→←` `L H` · `⇧←` · `↵` · `⌘O` · `⌘⌫` · `⇧F10` · `⌥⌘R` reveal | tree, systems, collections, filters, results |
| Legend Lore row verbs | `R` rename · `S M` solo/mute (hold = momentary) · `X ⇧X` tick · `P Space` play · `E` arm · `A` shelve · `.` hide · `C` collection · `G` back to match | per row kind |
| Search bar | `↵` `@` `/` `↓` Esc | |
| Command, Prep | `R` rename · `A` spend (under the pointer) · `⌘T ⇧⌘T` tracks · `⌘E` read · `⌘O` session note | the selection is click-only |
| Command, Play | `↓↑ J K` player · `P Space` launch · `V H D T N L F` board tools · `⌘G ⇧⌘G` · `⌘Z ⇧⌘Z` · `⌘D` · `⌥1 ⌥2` fit · `⌫ Del` cards | board letters are Miro's |
| Menus | `↓↑ J K` · `→← L H` · `↵` · Esc · the row verbs as accelerators | |
| Confirm | `⌘⌫` commits a removal · `↵` an activation | |

Mouse-only in Command, no chord: new note, new beat, new session, new
campaign, open a note or beat (double-click), arm a beat (click `●`), put
a note in the armed beat (click), move a plan row, Move to Trash, Show in
Finder, Add to session, Take out of play, frame the live cards, expand the
board, fold the player or the tray, the jot bar, arrange by beat, the
selection bar (colour, label, ends), context menus.

## 2. Findings

Two are bugs from the unification, fixable in a line each; the rest are
grammar.

1. **`⌘S`, `⌘F`, `⌘R` fire from Command's note editor.** Global chords are
   not gated on typing, and CodeMirror's default keymap claims none of
   them, so `⌘S` while writing a note syncs the library and `⌘F` opens
   Legend Lore's filters. Before step 2 they were simply dead there. Fix:
   `⌘S` and `⌘F` stand down in the editor (`ctx.editor`); `⌘R` stays taken
   (it must, or the webview reloads) but inert. `⌘1`–`9` and `B` are fine:
   the editor doesn't use them and the transport is meant to work from
   anywhere; `B` is already gated on typing.
2. **`⌘O` means two things.** Legend Lore: open the focused file. Command:
   open the session note. One chord, one meaning: `⌘O` should open the
   selected note or beat in the inspector, and the session note move.
3. **Three targeting models inside Command.** `R` acts on the selection,
   `A` on the row under the pointer, `P` on the player's own caret; Prep's
   `focusedBeat` is a third token beside `selected`. Legend Lore has one
   rule: a key acts on the caret, and hover yields to the keyboard. Command
   should say the same: the selection is the caret; `A` takes the pointer's
   row when the pointer is live and the selection otherwise.
4. **Prep has no keyboard navigation.** Nothing moves the selection but a
   click. Every Legend Lore list answers `↓↑ J K`, `Home End`, `↵`, `⌘⌫`.
5. **`H` and `L` collide across tools.** Legend Lore: collapse and expand
   (vi). Command's board: hand and line (Miro). Both are conventions worth
   keeping, and they never meet (the board is Play's). Accept it, scoped:
   in Prep `H L` stay free for the list grammar; in Play they are the
   board's, and the player keeps only `J K`.
6. **The sheet mislabels scopes.** `sidebar.toggle`, `view.toggle` and
   `info.show` sat under Global; the first two are "either tool", the
   last is the file views'. (`⌘N` stays global: it works from Command.)
   And the `command` scope is one block for Prep, Play and the board, so
   `liveScopes` can't narrow it: the first real consumer for Command
   regions. *Done 2026-10-21 with finding 1.*
7. **`⌥⌘R` reveal was dead** until step 2 (the `⌘R` branch swallowed it).
   Fixed; noting so the sheet's entry is believed.
8. **Hold-to-peek is Legend Lore's alone.** `S M P B` latch on tap and are
   momentary on hold. Command's `P` launches, which has no "peek". Fine,
   but the sheet's "hold rather than tap" line should say which keys.

## 3. The layout

One instrument, five layers, each with a fixed grammar. A key keeps its
meaning in every tool that has the concept; a tool without the concept
leaves the key unbound rather than reusing it.

**Rack** — `1`–`8` views; `⌘⌥` arrows walk regions and cross rails; `Tab`
flips the tool's two views; `⌘B` the tool's sidebar (shelf, collections;
in Play, the player and the tray); `⌘,` `?` `⌘/`; Esc pops one level.

**Transport** — the collection slots, bypass, sync, search, filters. Work
from anywhere, editor excluded for the two that type (`⌘S` `⌘F`).

**List grammar** — every list in either tool: `↓↑` (`J K`), `Home End`
(`⌥↑↓`), `→←` (`L H` where free), `↵` open or fold, `⌘O` open, `R` rename,
`⌘⌫` delete with confirm, `X` tick, `⇧F10` menu, `⌥⌘R` reveal, Esc release.

**Row verbs** — the switches: `S M` solo/mute, `P Space` play/launch, `E`
arm, `A` shelve/spend, `X` tick, `.` hide, `C` collection. Hold peeks where
the verb is a state.

**View letters** — the board's `V H D T N L F`, `⌘G ⌘D ⌘Z`, `⌥1 ⌥2`: a
mode's own alphabet, live only on that view.

Reserved: `⌘Z` in Legend Lore (deliberate), `⌘W ⌘Q ⌘H ⌘M` (window),
`⌘E` in text fields (macOS Use Selection for Find — why Command's `⌘E`
stands down in a name field), `⌃⌘F` (fullscreen).

## 4. Command: proposed bindings

Parity means the key already does this in Legend Lore.

| Key | Where | Action | Parity |
|---|---|---|---|
| `↓ ↑` `J K` | Prep lists, tray | move the selection within its list | tree, collections |
| `→ ←` | grid | the same row in the next or previous track | — (Live's session view) |
| `Home End` `⌥↑↓` | every list | first / last | all lists |
| `↵` | Prep, player | open the selected note or beat in the inspector; on the player, edit the beat | tree `↵` opens |
| `⌘O` | Prep, Play | open the selection (replaces session note) | tree `⌘O` |
| `⌘J` | Play | focus the jot bar; `↵` writes, Esc leaves | — |
| `⇧⌘J` | Prep, Play | open the session note (was `⌘O`) | — |
| `⌘N` | Prep | new note in the selected note's track, the shelf when the shelf is selected, ready to name | `⌘N` collection, ready to name |
| `⇧⌘N` | Prep | new beat, armed, ready to name | the collection is "created armed" |
| `E` | Prep | arm / disarm the selected beat | collections `E` |
| `X` | Prep | put the selected note in the armed beat, or take it out | tree `X` while armed |
| `⌘⌫` | Prep | Move to Trash the selected note, beat or track, with the confirm | tree, collections |
| `⌥⌘R` | Prep, Play | Show in Finder | tree |
| `⇧F10` | Prep, player | context menu on the selection | tree |
| `A` | Prep, Play | spend the pointer's row when hover is live, else the selection | finding 3 |
| `⌘B` | Play | fold / unfold the player and the tray together | `⌘B` sidebar, per view |
| `⌥3` | Play | frame the live cards | `⌥1 ⌥2` fit family |
| `⇧⌘F` | Play | fill the rack with the board, and back | F for fill; `⌘F` stays filters |
| Esc | editor | leave the editor for the list, keeping the note open | search bar Esc |
| `⌘⌥←→` | Prep | the selection moves shelf → grid → beats, to each list's remembered row; at the ends, the rail | dock → files → the rail |

The last row is what Command regions are for: a region is a list with a
remembered row, and `⌘⌥` arrows and the sheet's Command block are its
consumers. Build the regions with the navigation, not before.

**Left unbound on purpose.** New session and new campaign (once a sitting,
from the bar), switching campaign or session (a pick, not a chord), move a
plan row (a drag; `⌥↑↓` are Home/End), arrange by beat (a one-shot before
the session), the selection bar's colour, label and ends (a pick), the
tray's side-by-side read (a selection of several). Launching in Prep stays
out: Prep doesn't launch (beat states, 6ce64de).

**Open.** A single "next beat" key for live play (today `J` then `P`); `N`
is the sticky and `→` would be the grid's. `⇧Space` is free. Decide at the
table, not here.

## 5. Order of work

1. The two one-line fixes (finding 1), and the sheet's scope labels
   (finding 6). *Done.*
2. `⌘O` / `⌘J` / `⇧⌘J`, `↵`, `⌘N` / `⇧⌘N`, `E`, `X`, `⌘⌫`, `⌥⌘R`, `⇧F10`,
   `A`'s fallback: the Prep verbs on the existing selection. No new state.
   *Done, 8baf638.*
3. Prep navigation (`↓↑ J K`, `→←`, `Home End`) with per-list remembered
   rows, then Command regions, `⌘⌥←→` inside Command, and the sheet's
   Command block split by view. *Done, ee89387.*
4. Play's `⌘B`, `⌥3`, `⇧⌘F`, editor Esc. *Done.*

All four shipped 2026-10-21. Still open from §2: a "next beat" key, and
the chords dead in the main window while Legend Lore is popped out.
