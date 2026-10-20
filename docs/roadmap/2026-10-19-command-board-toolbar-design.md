# Command board toolbar (2026-10-19)

**Status:** settled 2026-10-19 (§8). Step 1 of §6 is built; steps 2–4 aren't. Extends the Command design's §5.2 (Play), whose board "renders Obsidian's groups and text, and lines are lines for now".

## 0. TL;DR

Play's board gets a creation toolbar modelled on Miro's: a column of tool keys with Miro's letters, a small bar over the selection for colour and line ends, in-place editing, and undo. It offers only what JSON Canvas 1.0 can hold (note cards, text, stickies, labelled lines, frames), so every board stays an Obsidian Canvas. The GM gets these tools first; MCP wraps the same sidecar operations afterwards.

---

## 1. Why

- **The board today** can move, resize, connect two cards with a plain line, and remove a card or a line. It shows groups, text cards and line labels that Obsidian made, but Command can't make or change them (§5.2).
- **The Session 4 board** (Misty Vale, built on 2026-10-19 by writing the canvas directly) showed what a readable board needs: a frame per scene, labelled lines between causes and clues, and notes laid out beside their places. A GM can't make or edit any of that in the app.
- **Flexibility:** GMs arrange boards in different ways: a dungeon map, a relationship web, a scene per row, a corner of reminders. A small set of general tools serves all of these better than a fixed layout.

## 2. Rules

1. **Only what JSON Canvas holds.** A tool whose output Obsidian Canvas couldn't open isn't offered. That rules out shapes, the pen and comments (§7).
2. **The table comes first.** Play's keys keep priority: J/K step through the plan, P and Space launch, A spends. Arranging happens before the session; at the table the board still needs no handling (§5.2).
3. **The GM's tools come first.** Each tool is one or more sidecar board operations. MCP later wraps those same operations and adds none of its own.
4. **One vocabulary.**
   - The tools live in a well of keys, and a current pick shows raised, as in the bar's wells.
   - Colours come from Legend Lore's pigments (`palette.ts`), as tracks' do.
   - Names are edited in place, as with `RenameField`.
   - Menus are `CommandMenu`.
5. **Every board edit can be undone**, including gestures that already exist today (move, resize, connect, remove).

---

## 3. The toolbar

### 3.1 Placement and look

```
 ┌ session player ┐                              [⤢]  ← expand key (exists)
 │ 1 Isle of Mist │                              ┌──┐
 │ 2 Cadal's …    │                              │ ↖ │ V  select
 └────────────────┘                              │ ✋ │ H  hand
                                                 │ ▤ │ D  note
                     the board                   │ T │ T  text
                                                 │ ▢ │ N  sticky
                                                 │ ╱ │ L  line
                                                 │ ⬚ │ F  frame
                                                 ├──┤
                                                 │ ↶ │ ⌘Z undo
                                                 │ ↷ │ ⇧⌘Z redo
                                                 │ ⛶ │ ⌥1 fit all
                                                 └──┘
 [jot bar ……………………] [✎]
```

- **Where:** a vertical column on the board's right edge, under the expand key.
  - Miro puts its toolbar on the left, but Play's left edge already holds the session player (top) and the jot bar (bottom).
  - On the right, nothing has to move, and it lines up with the expand key (§8).
- **Keys:**
  - Icon-only, each 1.65rem square (the one row height). All the tool keys share one well, as the view switch's do.
  - The undo, redo and fit keys sit in a second well below.
  - Each tooltip names the tool and its key (`chordHint`).
- **The current tool:**
  - Its key is raised (`--bg-header`), as the bar's wells raise their pick.
  - While any tool but Select is current, its lamp is lit purple: it's a mode, since it changes what a click or a drag on the board does. Hand counts.
  - Select is the resting tool and has no lamp.
  - **Icons** (Font Awesome Free 7.3.1): arrow-pointer, hand, font, note-sticky, diagram-project (Line) and object-group (Frame; 7.x has no vector-square), with rotate-left and rotate-right for undo and redo.
- **One shot:** a creation tool makes one thing, then hands back to Select, as Miro's do. Esc returns to Select at any time.
- **Cursor:** a crosshair while a creation tool is armed.
- **Shown** in Play only, in the expanded board too. It isn't foldable in v1; it's narrow.

### 3.2 Tools

Each line gives the key, the tool, its Miro equivalent, what it does, and what it writes in JSON Canvas.

| Key | Tool | Miro | A click or drag makes | JSON Canvas |
|---|---|---|---|---|
| V | **Select** | Select | Click selects; drag a card moves it; drag the empty board pans, as today; Shift+drag draws a marquee, as today. | — |
| H | **Hand** | Hand | Every drag pans, over cards too, so a crowded board can be moved around without nudging anything. | — |
| D | **Note** | Card | Click: a name field at that point, with the editor's `[[` completion over the campaign's notes. Enter places that note's card there. A note already on the board moves there (one card per note). | `file` node |
| T | **Text** | Text | Click: a text card, typed in place, Markdown, unboxed. | `text` node, no colour |
| N | **Sticky** | Sticky note | Click: a square coloured card, typed in place, in the last colour used (Ochre at first). | `text` node with `color` |
| L | **Line** | Connection line | Drag from any card (or frame) to another: a line. Any part of the card starts it, not only its handles. It has no arrowheads by default, as today. | `edge` |
| F | **Frame** | Frame | Drag a rectangle: a frame, with its name field open. | `group` node |

- **Below the tools:**
  - **Undo** (⌘Z) and **Redo** (⇧⌘Z). Miro keeps these at the bottom left, where Play has the jot bar.
  - **Fit all** (⌥1): the whole board, clear of the session player, as the frame key fits a beat.
- **Zoom** stays as it is (pinch, or scroll with the modifier), plus ⌘+, ⌘− and ⌘0 for 100%.
- **Note** is what makes a board flexible beyond the session's own notes: PCs (as the GM placed them on Session 3's board), reference notes, a note for later. A placed note that no beat holds can be removed again, as today (`removable`).

### 3.3 The selection bar (Miro's context menu)

A slim well of keys floats above the selection while Select is the tool, and carries only what needs swatches or a toggle:

- **Text, sticky, frame:** a colour row (nine pigments, plus none). For a sticky, "none" turns it into a text card.
- **Line:**
  - The colour row.
  - An ends key that cycles none → arrow at the end → arrows at both ends.
  - A label key, which opens the field on the line.
- **Note cards:** no bar. Their head already carries the track's pigment, and their actions stay in the card menu (Edit note, Play, Spend, Open source, Remove from board).

Actions stay in the right-click menu: Rename (frame), Duplicate (⌘D; text, sticky and frame), Remove frame, Delete. Delete and Backspace remove as today.

### 3.4 Editing in place

- **Text and sticky:** a double-click edits the text in an autosizing field on the card. Esc or a click elsewhere commits. A card left empty is removed, as in Miro. Rendered, its `[[links]]` follow as a card's do (`linkify`).
- **Frame name:** a double-click on the label opens a `RenameField` on it; Enter commits.
- **Line label:** a double-click on the line opens a field at its midpoint. An empty label clears it.

### 3.5 Keys

All of these are scoped to the board: Play, with the board focused and nothing being typed. They're registered in `keybindings.ts`, so Help → Keys lists them.

| Key | Action | Notes |
|---|---|---|
| V H D T N L F | Tools (§3.2) | Miro's letters. D is Miro's Card. |
| Esc | Back to Select; cancels a field or a gesture | as `app.escape` |
| ⌘Z, ⇧⌘Z | Undo, redo board edits | The editor's own ⌘Z is unaffected. |
| ⌘D | Duplicate a text card, sticky or frame (with what's inside it) | A note has one card per board. |
| ⌘G | Frame the selection | Miro's Group |
| ⇧⌘G | Remove the selected frame, keeping its cards | Miro's Ungroup |
| ⌥1, ⌥2 | Fit all, fit the selection | |
| ⌘+, ⌘−, ⌘0 | Zoom in, out, to 100% | |
| Delete, Backspace | Remove, as today | |

**Miro keys not taken:**
- P (pen) and Space+drag (pan): P and Space launch beats.
- S, R and O (shapes), E (eraser), C (comment): §7.
- M (minimap), G (grid) and ⌘K (command palette): §7.

None of the letters above clashes with Command's (R, A, J, K, P, Space) or with the global B.

---

## 4. Behaviour

- **Frames hold what lies wholly inside them**, measured when a drag starts.
  - Moving a frame moves its contents, as Obsidian does.
  - A card dropped wholly inside a frame joins it.
  - Resizing a frame moves nothing. Frames may nest.
  - Removing a frame keeps its cards (§8).
  - Positions stay absolute, as JSON Canvas keeps them: the board doesn't use Svelte Flow's `parentId` sub-flows, whose positions are relative.
- **Stacking:** frames sit behind cards (as now). Among frames, the smaller sits in front, so a frame inside another can still be grabbed.
- **Colours** are written as the pigment's hex, so Obsidian shows the same colour. A file Obsidian wrote with a preset (`"1"`–`"6"`) shows the nearest pigment and keeps its preset until the GM recolours it.
- **Arrowheads** are drawn by the line's own path, not by SVG markers. Markers are why arrowheads aren't drawn today (§5.2): a token colour inside `url(#…)` isn't safe in WebKit. Arrows Obsidian drew then show too.
- **Renames:** text cards' `[[links]]` are rewritten when a note is renamed, as `canvas.rewrite` already does. Frame names and line labels are plain text and aren't rewritten.
- **Undo:**
  - Each gesture is one step: one batch of operations, kept with its inverse, per board, in memory only.
  - Switching sessions clears it. An undo naming something Obsidian has since removed is skipped, as operations already are.
- **The table:** nothing here changes launching, framing a beat, or the card tray. A tool can be armed while a beat is live.
- **Ops in flight:** a gesture's write still goes out as it does today (`onOps`), and the board re-derives from what comes back.

## 5. Sidecar (`board.apply`)

- **New `add`** {id, type: `text` | `group` | `link`, x, y, width, height, text | label | url, color?}. Note cards keep `place`.
- **`connect`** gains optional `label`, `color`, `fromEnd` and `toEnd` (`"none"` | `"arrow"`). With none given it still writes `toEnd: "none"`.
- **New `set`** {id, …fields} changes or clears (null) one node's or line's fields, from a whitelist:
  - a text card's `text` and `color`;
  - a frame's `label` and `color`;
  - a link's `url`;
  - a line's `label`, `color`, `fromEnd` and `toEnd`.

  Fields not in the list are kept untouched, as everything Obsidian wrote is.
- **Moving a frame** with its contents is one batch of `frame` operations, written once.
- **Undo** uses the same operations:
  - Restoring a removed card is `place` or `add` with its old id and fields.
  - Restoring a removed line is `connect` with its old id.
  - Restoring a changed field is `set` with the old value.
- **Checks:**
  - A colour is `#rrggbb` or `"1"`–`"6"`.
  - Ids are checked as now.
  - A text card's text is capped (16 KiB).
- **Tests:**
  - Each operation.
  - Unknown fields survive.
  - A board Obsidian wrote comes back byte for byte after an edit to one node.

## 6. Order of work

1. **Frames, labels, text.**
   - Sidecar `add`, `set` and the new `connect` fields.
   - Select, Hand, Text, Sticky, Line (with labels) and Frame.
   - In-place editing, undo and redo, and the keys.
   - This is what the Session 4 board needed.
2. **Note, colours, line ends.** The Note tool; the selection bar's colours and ends, with arrowheads drawn; duplicate; fit all and fit the selection.
3. **Arrange by beat**, Miro's templates in Command's terms:
   - A menu key at the toolbar's foot lays the board out as one frame per planned beat, in plan order. Each frame holds its beat's notes; a note held by several beats sits with the first.
   - It asks first and can be undone.
   - The same order replaces today's auto-placement by track for cards never placed (§5.2), so an untouched board reads in play order.
4. **MCP:** `connect_cards(a, b, label)`, `frame_cards(label, notes)`, `add_text(text, near)` and `arrange_board()`. They wrap 1–3, and the audit's "won't" on the board is lifted (`2026-10-18-command-mcp-tools-design.md`).

Each step updates design §5.2, Help → Guides → Command, and the CHANGELOG.

## 7. Not doing, or not yet

- **Not doing:**
  - Shapes, the pen and eraser, comments, tables, mind maps and stamps. JSON Canvas has no type for them, so Obsidian couldn't open them (rule 1).
  - Templates beyond Arrange (step 3).
- **Not yet:**
  - Lock (⇧⌘L), align and distribute, front/back keys, the grid toggle and snapping, the minimap, the command palette. Each waits until a real board asks for it.
  - Uploading images: phase 3b (§9 of the Command design). Once Play draws images, the Note tool places them too.

## 8. Settled (2026-10-19)

1. **Side:** the right edge, under the expand key. The left, as in Miro, would have moved the session player and the jot bar.
2. **Select's drag on the empty board:** pans, as today. The table pans more than it selects; Shift+drag draws the marquee.
3. **Removing a frame** keeps its cards, text cards and stickies included.
