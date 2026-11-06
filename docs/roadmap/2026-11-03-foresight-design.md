# Foresight (2026-11-03)

**Status:** designed 2026-11-01–03 and mocked inside the full app on 2026-11-03 (a scratch copy, not in the repo). Built 2026-11-03–05: steps 1 to 3, then step 4 (Help → Guides → Foresight, a glossary group, the shortcut sheet's Foresight section, the CHANGELOG). Two words are under review (§12).

## 0. TL;DR

Foresight is the workstation's turn tracker, a fifth tool in the rack beside Legend Lore, Command and Augury. It keeps who acts in what order, whose turn it is, the round, and whatever else the GM wants to keep per row. It looks like a step sequencer: one step per combatant, played top to bottom by a playhead that marks the turn, each loop a round. An encounter is a note in the campaign. Its table is the tracker, the text around it is the GM's cheat sheet, and Foresight owns two frontmatter keys, `round` and `turn`. Beats hold encounters as they hold any note, a note dropped on Foresight joins as a combatant, and clearing an encounter spends it.

---

## 1. Why

- **Every fight needs the same three things kept:** the order, whose turn it is, and a few numbers or words per creature. On paper or in another app, they sit outside the workstation and forget the campaign.
- **Encounters are prepared and improvised.** A GM builds one ahead for a beat, or in seconds at the table when the party picks a fight nobody planned.
- **What was fought stays.** A cleared encounter is still a note in the campaign, readable in Obsidian or any text editor.

## 2. Rules

1. **General, not one game's.** No column behaves differently because of its name, and nothing is inferred from a stat: HP is a default column, not a rule. Order is the rows' order, set by hand, so any initiative method works, or none. Foresight does not know AC, conditions, death saves or durations.
2. **An encounter is a note.** Beats, Play, spending, renames, links, Obsidian and the Servant's note tools work on it with no change (§3).
3. **The app's instrument panel.** Plates, keys in wells, lamps, readouts. Every part is an idiom the rack already has (§4).
4. **Narrow.** 270 px wide, Augury's width, so the two stack in one column. Legend Lore (560), Command (420) and that column fit a 1280 px window.
5. **Written as it happens.** Every change is written to the note at once, so a crash mid-fight loses nothing.

---

## 3. An encounter is a note

```markdown
---
round: 3
turn: "Goblin 2"
---
Goblins hide in the ditch; the boss stays on the ridge.

| Combatant                | HP    | Remarks    |
|--------------------------|-------|------------|
| [[Goblin boss]]          | 12/21 | frightened |
| [[Kira]]                 |       |            |
| [[Goblin\|Goblin 2]]     | 7/7   |            |
| ~~[[Goblin\|Goblin 1]]~~ | 0/7   |            |
```

- **A note is an encounter when its frontmatter has `round`.** Foresight owns `round` and `turn`, as Command owns `notes`, `beats`, `date`, `spent` and `source` (Command design §3.4). A stat block with a table of its own is not mistaken for one.
- **The first table in the body is the tracker.** Its first column holds the rows' names, whatever its header says; the header row is the column list. Foresight rewrites only that table and its two keys. Text around the table is the GM's, and stays.
- **A name may be a link** to its note: a stat block in Monsters, a PC in PCs. A second row from the same note is an alias, `[[Goblin\|Goblin 2]]` (in a table the alias pipe is escaped, Obsidian's convention, which Command's links already read), so every copy links to the one stat block. Command's renames rewrite links in bodies, so the table follows.
- **Names are unique within an encounter.** A repeated name takes the next number (*Goblin 2*, *Goblin 3*). `turn` names the row whose turn it is.
- **Out of the fight** is the name struck through (§7).
- **New encounters** are `Encounter N` in an *Encounters* track, N one more than the highest number in an existing encounter's name, as sessions are numbered. The track is a note track, made the first time it is needed, with no pigment. The GM can move an encounter anywhere; Foresight opens it wherever it is.
- **Writes follow Command's discipline** (Command design §3.5): atomic, hash-checked, frontmatter edited key by key. A change made in Obsidian while the encounter is open reaches Foresight through the vault watcher.

---

## 4. The panel

```
┌──────────────────────────────────────┐
│ ENCOUNTER 4      ◀ 3 ▶ ▣         ⧉   │  head: name, turn well (round between the arrows, spend), window key
├──────────────────────────────────────┤
│    COMBATANT      HP  REMARKS      + │  plate: the columns
│ 01 Goblin boss  12/21 frightened     │
│ 02 Kira                              │
│ 03 Goblin 2       7/7              M │  ← the turn: Legend Lore's playing highlight
│ 04 Goblin 1       0/7              M │  ← out: down the ramp, M lit red
│    Combatant name…                   │  the empty row
└──────────────────────────────────────┘
```

- **The head** is Augury's bar: 40 px on `--bg-header`. The encounter's name sits at the left in Augury's set-name voice (`.readout-label`, parchment). The turn well holds ◀, the round, ▶, a faint rule, then the spend key (Command's box-archive). The window key ends the bar. There is no *New* key (§8).
- **The round** is one or more of Augury's seven-segment lamps, small, between the arrows, as Augury's display sits between its own. With no ghost digit ahead of it: beside the name, an unlit leading 8 read as "Encounter 4 83" in the mock.
- **The plate** is a `.nameplate` naming the columns in `.ledger-label`, with `+` at its end (§6).
- **A row** is 1.65rem, ruled at its foot as Command's note rows are: its step number in small grey figures (as Command numbers its tracks), the name, one cell per column, and the M key in its own slot at the end.
- **The turn** wears Legend Lore's playing highlight (`CollectionsPanel .row-container.playing`), the one Command's live beat wears.
- **The M key** is Legend Lore's mute (`.sm-btn`, `.mute-on`). It shows while lit, on the turn's row and under the pointer, as Command's spend key shows on a row only while spent, hovered or focused. Its slot is always kept, so nothing moves.
- **The empty row** at the foot names a new row in place, as Command's empty note row does: italic *Combatant name…*, no field of its own.
- **The status bar** gets a section: `Round 3 · Goblin 2`, so the turn shows from a view without Foresight in it.
- **Size:** `rackMin` 270×280, not compact: it fills its slot's height, and its rows scroll. Under Augury's 391 px box it keeps about 320 px in an 800 px window, eight rows and the empty one.

## 5. Turns and rounds

- **▶ and ⇧Space** pass the turn to the next row in the fight. Past the last, it wraps to the first and the round counts up.
- **◀** passes it back; before the first row it wraps to the last and the round counts down, never below 1.
- **Rows out of the fight are skipped.** If the row whose turn it is goes out, the turn passes on.
- **A row added, moved or taken out mid-round** leaves the turn with whoever has it.
- **A new encounter starts at round 1** with the turn on its first row.

## 6. Columns and cells

- **The first column is fixed:** always there, always first.
- **Every other column is the GM's**, edited on the plate with the idioms of Command's tracks: `+` names a new column at the end in place, a double-click renames one, a drag moves one, and right-click has *Rename* and *Remove*.
- **A new encounter takes the columns of the last one Foresight had open.** The very first starts with *HP* and *Remarks*. No settings, no templates.
- **Cells have no types.** A cell holds a whole number, a number with a max (`12/21`), or text.
  - A click on a cell opens it in place. In a cell holding a number, `−7` or `+3` does the arithmetic (`12/21` → `5/21`), a bare number replaces it, and `n/max` sets a max. Anything else is text. No floor and no ceiling: the GM's numbers mean what the GM's game says.
  - Enter keeps the edit, Esc drops it.
- **A column whose filled cells are all numbers reads as figures:** right-aligned, in tabular readout digits, in parchment as data, its header right-aligned with them. Any other column is text, in secondary. This comes from what the cells hold, never from the column's name.

## 7. Out of the fight

- **The M key** (or M on the focused row) takes a row out of the fight, and back in. The row steps down the text ramp (it doesn't fade), its M stays lit red, and the turn skips it.
- **It is the GM's call, never a rule:** nothing goes out when a number reaches 0, since health may count up, come in tiers, or not be tracked at all.
- **On disk** the name is struck through: `~~Goblin 1~~`.

## 8. Starting, clearing, opening

- **An empty Foresight** is the bare instrument: the head with no name, the plate, the empty row. No hint lines (the first-run rule).
- **The first row added** to an empty Foresight makes `Encounter N` (§3) and opens it.
- **Clearing is spending.** The spend key sets the encounter note's `spent`, the same key Command's spend key sets, and empties Foresight. The note stays where it is, among its track's spent notes. One not yet fought stays unspent, like a secret not yet revealed. Un-spending is Command's.
- **Opening an encounter:** drop its note row or its card on Foresight (§9). Opening one while another is open just switches: both are notes, so nothing is lost.
- **Foresight remembers the open encounter per campaign** and follows the campaign open in Command (the app context), as Augury's Tracks set does.

## 9. The link with Command

- **A note dropped on Foresight joins as a row** linked to it: a track's row, a shelf row, a tray card or a board card. Dropped between rows, it lands there; elsewhere, at the end.
- **A track's nameplate dropped on Foresight adds all its notes,** so the PCs track brings the party in one move.
- **The same note dropped again** adds the next number as an alias (§3).
- **An encounter note dropped on Foresight opens it** (§8), whatever its track.
- **A board card** is Svelte Flow's to drag, and no drag event leaves the board, so past its edge the board speaks a card drag's events itself (`noteDrag.ts` `carryCards`, `dropCards`). Taken by Foresight, the card goes back to its place on the board.
- **These are the rack's first drops from one tool to another.** The drop reads Command's own drag payloads (`noteDrag.ts`, the track and card types), so later tools can take them the same way, such as a Legend Lore result dropped on Command. Drops don't cross windows (Command design D4), so when either tool is popped out:
  - **`[[` in the empty row** offers the campaign's note names, as Command's editor does;
  - **right-click on an encounter note** in Command has *Open in Foresight*, through Rust, as *Send to Command* crosses from Legend Lore.
- **A double-click on a linked name** opens its note in Command.
- **A beat holds an encounter** as it holds any note, and Play launches its card. Launching doesn't load it into Foresight: an encounter half fought would be replaced. The GM drops the card when the fight starts.

## 10. Keys, storage and architecture

- **Keys,** while Foresight has the keyboard: **⇧Space** passes the turn (in Command's Play it launches the next beat: the same "advance"); **↓/J and ↑/K** move the focused row, as on Command's session player; **M** takes the focused row out or back in; **⌘D** duplicates it with the next number and its cells; **R** renames it, as on Command's rows. Bare 1–8 stay the rack's.
- **Rows** drag to reorder (the row is the handle, `use:grab`). Right-click on a row: *Open note* (when linked), *Rename*, *Duplicate*, *Remove* (red).
- **The settings store** keeps the open encounter per campaign (`foresightOpen`) and the last encounter's columns (`foresightColumns`), per machine. Everything else is in the note.
- **The sidecar:** the encounter's reader and writer live beside Command's (`sidecar/command/encounter.py`, routes under `/api/command/encounter`), since an encounter is a note and shares the vault, the write lock, the hash check and the watcher. Parsing is lenient: a table Foresight can't read is shown as it is and left alone.
- **Rust:** `command_*_encounter` commands in `command.rs`, as Augury's `command_draw_tracks` lives there. *Open in Foresight* and opening a linked note cross windows as `command_send` does: `command_open_encounter` and `command_open_note` bring the tool forward and emit `foresight://open` or `command://open`. The campaign's index says which notes are encounters (`encounter`).
- **The frontend:** `src/lib/foresight/`, `panels.ts` and `panels.rs` (rack minimum, pop-out size), `PanelView`. The first launch's view 2 puts Foresight under Augury, beside Command.
- **The Servant** reads and edits encounters with the note tools it has (`read_note`, `find_notes`, `edit_note`, which keeps the frontmatter). Making one needs `round`, so an encounter tool waits (§14).

## 11. Order of work

1. **The panel and the note.** Foresight in the rack and as a pop-out, on the first launch's view 2. The sidecar's reader and writer with tests: `round`/`turn`, the first table, struck-through names, aliases, text around the table kept, hash-checked writes. The head, plate and rows; turn and round (▶ ◀ ⇧Space, wrap, skip); M; the status bar section. New encounter on the first row; clearing spends.
2. **Cells and columns.** Editing cells, the arithmetic, figures by content. `+`, renaming, moving and removing columns; columns carried to the next encounter. ↓/J ↑/K, R, ⌘D, row drag, the row menu.
3. **The link with Command.** Drops of notes, nameplates and encounter cards; aliases for repeats; `[[` in the empty row; double-click opens the linked note in Command; *Open in Foresight* through Rust.
4. **Help and keys.** Help → Guides → Foresight, a glossary group (encounter, turn, round, out of the fight), the shortcut sheet (⇧Space, M, ⌘D and Esc in a Foresight section, a line each on a cell's arithmetic and `[[`), the keys' hints, CHANGELOG.

## 12. Open

**Two words under review** (user, 2026-11-03). Foresight may run more than fights: a chase, a standoff, a heist against a clock, a domain turn. Both are working terms until then:

1. *Encounter*, for the note's default name (`Encounter N`) and its track.
2. *Combatant*, for the first column's header and the empty row.

**Filled in for this spec, not yet discussed:**

- *Open in Foresight* on an encounter note's right-click, for popped-out windows (§9).
- Launching a beat doesn't load its encounter (§9).
- The first launch's view 2 gains Foresight under Augury (§10).
- ↓/J ↑/K, R, ⌘D, the row menu, and Enter/Esc in cells (§6, §10).
- New encounters land in a track named *Encounters* even if the GM files old ones elsewhere (§3).
- No floor and no ceiling on numbers (§6).

**Filled in while building step 2 (2026-11-03), not yet discussed:**

- A bare number entered in a cell with a max keeps the max (`12/21`, then `15`, reads `15/21`); a cell is emptied to drop it. A number entered over text or nothing becomes the cell, `+3` as `3`.
- The first column's header renames like the others (it can't move or go), so the GM can call it *Name* while *Combatant* is under review; the next encounter takes it.
- Removing a column that holds cells asks first; an empty one goes at once.
- With Foresight empty, the plate edits the columns the next encounter will take.
- ↓/J ↑/K with no row selected start from the turn's row. Esc lets go of the selection.
- The row menu has *Rename* too; *Open note* waits for step 3.
- At 270 px the name column keeps 4.5rem and the text columns give way; a column of figures is 2.9rem.

**Filled in while building step 3 (2026-11-05), not yet discussed:**

- A nameplate brings the track's notes still to play, in its column's order: no spent notes, images or encounters.
- A repeat dropped comes in with empty cells; ⌘D is the way to copy them.
- `[[` offers notes, not beats, sessions, images or encounters. A name typed in brackets joins as a dropped note does, a typed alias is kept, and a link to no note stays a link.
- A spent encounter is refused: no outline, no *Open in Foresight*. Un-spending is Command's.
- *Open in Foresight* is on track and shelf rows. A right-click on a board note card stands it up, so a board card opens by being dropped.
- Several board cards carried together all join.
- An encounter renamed or moved, in Command, Finder or Obsidian, is followed: when its path is gone, Foresight reads the campaign's encounters for the hash it holds. If the note's text changed in the same move, nothing matches and Foresight empties. A rename while Foresight isn't running isn't followed either: the stored path finds nothing, and Foresight opens empty.
- The reader and writer in Command's sidecar package rather than a package of their own (§10).

**Filled in while building step 4 (2026-11-05), not yet discussed:**

- ↓/J ↑/K and R read the same as on Command's lists, so the sheet shows them once, under *Any list*, live while Foresight has the keyboard. Its own section holds what is Foresight's alone.
- ◀ has no key: only passing the turn forward does.

## 13. Settled (2026-11-01–03)

- The name: Foresight, after the divination spell, as the other tools are named after spells: knowing what comes next, the playhead's job (user, 2026-11-03). Death Ward was chosen first (2026-11-02) and dropped once the design centred on turns, not hit points. Scribe (not a spell; reads as a notes tool), Scrying (reads as search), Deathwatch (a Warhammer 40k trademark), Magic Circle and Guidance were weighed. Augury keeps its name (user, 2026-11-03).
- The essence: rows in turn order, whose turn, the round, and the GM's cells. No initiative numbers, no AC, no game's columns (user, 2026-11-02: "trim it down to the essence of running an encounter", "adapts to any GM workflow").
- The columns are the GM's (user, 2026-11-02).
- Out of the fight is the GM's key, not HP reaching 0 (user, 2026-11-02).
- An encounter is a note, not a new kind in a reserved folder: the tools are different ways to work the campaign's notes (user, 2026-11-02).
- Drops between tools are designed in, not around (user, 2026-11-02).
- A step sequencer in the app's idioms; the mock is "well aligned with the rest of the app's design" (user, 2026-11-03).
- No special treatment for HP: what a column holds decides how it reads (user, 2026-11-03).
- The round between ◀ and ▶; M shown only while lit, hovered or on the turn (mock, 2026-11-03).

## 14. Not doing, or not yet

- Rolling initiative, or any roll from Augury into a cell.
- Game rules: conditions and their durations, death saves, damage types, anything going out at 0.
- Any column treated by its name: health bars, low-HP colours, a known *HP*.
- Reading numbers out of a stat block note to fill a row.
- A player-facing display.
- Several encounters open at once.
- Loading an encounter when Play launches its beat.
- An MCP tool that makes encounters.
- Drag and drop across windows.
