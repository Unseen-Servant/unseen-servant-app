# Command — design

**Date:** 2026-10-11
**Status:** the model, the vault layout and session management were agreed in conversation on 2026-10-11, and the open questions were settled the same day before phase 3 (§10); track identity followed on 2026-10-14. Phases 0–2 done 2026-10-11, phases 3–5 on 2026-10-12 (§9); where the build departed from this doc, the text below says so.
**Objective:** specify Command, the workstation's second tool (architecture doc §6 Step 4), before any code: what the vault looks like on disk, how sessions work, what Prep and Play show, and where each piece lives across the three layers.

---

## 0. TL;DR

- **Ableton Live for prep and play.** Tracks are kinds of material (PCs, Secrets, Locations, NPCs, Monsters, Traps, Treasures — editable), notes are clips, beats are scenes. Prep builds; Play runs the table: launch a beat and its notes light up, improvise by launching more.
- **The vault is folders of Markdown, and nothing else is truth.** A campaign is a folder in a user-chosen root, a track is a folder in the campaign, a note is any `.md` file in a track. Beats and sessions are notes too. Open the root in Obsidian and everything reads, links and edits.
- **References are `[[wikilinks]]` by note name**, in frontmatter lists Command owns: a beat lists its notes, a session lists its beats. Nothing stores ids, paths or copies.
- **Play state never touches notes.** What's live is sidecar state; only story facts are written: a note marked spent.
- **Spent replaces carry-forward for notes.** Any note can be spent (secret revealed, treasure given, beat played, NPC dead); an unspent note is simply still bright next session. Nothing carries forward, plans included: a new session plans nothing, and the last one's unspent beats wait under *not in this session* (2026-10-15; it used to start with them).
- **The campaign is the unit**, as a project folder is Live's: everything a campaign uses lives in its folder, so the folder is complete on its own. Gathered material waits on the campaign's shelf (§3.6); reuse across campaigns is copying from another campaign.
- **Same app, same look.** A panel per `src/lib/shell/PANELS.md`; vault I/O and state in `sidecar/command/` (architecture D2, §4 Q4); one sidecar event stream relayed by Rust to every window; Legend Lore's vocabulary (arm, play, pigments, lamps, dim) means the same thing here.

---

## 1. What the two earlier attempts teach

Two implementations of this tool exist: `~/code/unseen-app-desktop` (Electron + React + Lexical, "Unseen Servant" v0.2–0.3) and `~/code/unseen-command` (Tauri + Svelte + CodeMirror spike, March 2026). Both had the beat model — a beat is the set of active notes, and launching it activates exactly those notes — and the model held up. What failed, and the rule here that answers it:

| Failure | Rule here |
|---|---|
| Two sources of truth: a `.unseen` / `campaign.toml` state file beside the folders. Files added outside the app never appeared; a note dragged to another column moved in state but not on disk | §3.1 — folders are the only truth; the index is in memory and rebuilt from disk |
| Beats stored copies or generated ids, left stale by renames and deletes; ids regenerated on every scan | §3.3 — wikilinks by name; Command's renames rewrite links |
| `active:` written into every note on each launch — churn under iCloud and Obsidian sync | §3.5 — play state lives in the sidecar, never in notes |
| Autosave wrote to the *currently selected* file rather than the one it loaded (`Misty Vale/NPCs/Innkeeper.md` holds another character's sheet) | §3.5 — a save carries the path and hash it loaded |
| Notes without frontmatter were invisible | §3.2 — any `.md` is a note; frontmatter is optional |
| A selected beat rewrote itself on every toggle | §5.3 — launching is not editing: arm to edit |
| The play view hardcoded `PCs` and `Locations` | §5.2 — Play is generic over tracks |
| Lexical's WYSIWYG round-trip was lossy | §7 — CodeMirror on the raw source |

---

## 2. Vocabulary

| Ableton Live | Command | On disk |
|---|---|---|
| Project folder | Campaign | `<root>/<Campaign>/` |
| Track | Track | a folder in the campaign |
| Clip | Note | a `.md` file in a track folder |
| Scene | Beat | a note in `Beats/` listing its notes |
| Live Set | Session | a note in `Sessions/` listing its beats |
| Playing clips | Live set | sidecar state, never in notes |
| Session View / Arrangement View | Prep / Play | — |
| Browser: Current Project | Shelf | `Shelf/` in the campaign |

The views are renamed because "session" already means the game session. Live's mapping is also inverted relative to the table: Live's Session View is its improvisation surface, and at the table improvising happens during Play. So Play carries a compact launch grid as well as the arrangement.

One structural break from Live: a Live scene is a row with one clip per track, but a beat holds three NPCs and two secrets, and the same NPC appears in many beats. So beats are not rows. Each note appears once, in its track's column; a beat is a selection over them, and launching it lights its notes across the columns.

---

## 3. The vault

### 3.1 Layout

```
<root>/                                  user-chosen (dev: ~/Unseen Servant)
  Curse of Strahd/                       campaign = any non-dot folder in the root
    .unseen/command.json                 presentation only: track, note and beat order, pigments
    PCs/ Secrets/ Locations/ NPCs/ Monsters/ Traps/ Treasures/      tracks
      NPCs/Ismark Kolyanovich.md         a note
      NPCs/Vallaki/Lady Wachter.md       a subfolder groups notes inside a track
    Beats/
      Ambush on the road.md              a beat
    Sessions/
      Session 13.md                      a session
      Session 13.canvas                  its board (§5.2), JSON Canvas
    Shelf/
      Fire Drake.md                      gathered, not on a track yet (§3.6)
```

- **Root.** Chosen in settings and persisted by the sidecar (§6.1), so the watcher and MCP know it with no window open. Until the GM chooses one, it's `~/Unseen Servant` (§3.7). Every non-dot folder in it is a campaign; a folder created in Finder is a campaign.
- **Tracks.** Every non-dot folder in a campaign except the reserved `Beats/`, `Sessions/` and `Shelf/`. A new campaign gets PCs, Secrets, Locations, NPCs, Monsters, Traps and Treasures plus the three reserved folders, in that order: the GM's chain of thought in prep, after the Lazy DM's checklist (who the characters are, what they could learn, where, from whom, what stands in the way, what they win; its strong start and scenes are beats). *Reordered and Traps added on 2026-10-12.* Adding a track is making a folder, in Command or anywhere else. Notes anywhere under a track folder belong to it; subfolders show as groups within the column.
- **Loose notes** directly in a campaign folder are notes without a track: linkable and editable, not drawn in the grid. The shelf sidebar lists them under the shelf (§3.6).
- **`.unseen/command.json`** holds only presentation (track order, each folder's note order, the order of beats outside a plan, a pigment per track). It travels with the campaign and stays hidden in Finder and Obsidian (a dot-folder, the `.obsidian/` precedent). It never holds membership, so drift is harmless: a track it doesn't know gets defaults, and a stale entry is ignored.

**Rejected:** a `campaign.toml` or `.unseen` state file holding categories and beats (both earlier apps, §1); track order in a campaign note's frontmatter (nested maps render badly in Obsidian's Properties, and order isn't content); a folder per session holding its beats (carrying a beat forward would move files, where with `Beats/` it is a list edit — §4).

### 3.2 Notes

- A note is any `.md` file. Its **name** is the filename stem, as in Obsidian. Frontmatter is optional, and keys Command doesn't own are left alone.
- **Names are unique within their kind**, compared case-insensitively (as the default macOS file system and Obsidian's link resolution compare them): a note's among the notes (the tracks', the Shelf's, loose ones), a beat's among the beats, a session's among the sessions. So a beat may share a note's name, as a scene named after its place does (2026-10-19; until then names were unique across the campaign). Command refuses to create, rename or move into a clash within a kind; a clash made outside Command is flagged, and links to that name show as ambiguous.
- Non-`.md` files are not notes. (Images in Play: phase 3b, §9.)

### 3.3 Links

- References are wikilinks: `[[Name]]`, with optional `|alias` and `#heading`; `[[Folder/Name]]` is accepted, and names the note whose path ends in it. Resolution is by name within the campaign, and by kind (2026-10-19): a beat's `notes` resolve among the notes, a session's `beats` among the beats, and any other link names a note before a beat, and a beat before a session.
- Command writes a link by name, or by the note's path in the campaign (`[[Locations/Svalich Road]]`) when another note shares the name, since Obsidian may open either at a bare link. A bare link written before the name was shared stays bare: Command still reads it by kind.
- An unresolved link is drawn in dashed parchment, the app's "prospective, not yet real" idiom (`--outline-drop`), and offers to create the note.
- Renaming a note in Command rewrites every link to it across the campaign — frontmatter lists and bodies — keeping alias and heading. A link another note of the kind it names also answers to (two notes named alike, the second made outside Command) is ambiguous and points at neither, so a rename leaves it as it is: renaming one Ismark doesn't claim the bare `[[Ismark]]` links that may be meant for the other, while `[[NPCs/Ismark]]` follows (2026-10-14). A beat named after a note is no clash: renaming the beat rewrites the plans that list it, and renaming the note rewrites the beats' `notes` and the links in text (2026-10-19). Moving a note to another track changes only the links that spell its path. A rename in Finder breaks links, which show as unresolved; Obsidian's renames update links when its *Automatically update internal links* option is on.

### 3.4 Frontmatter Command owns

| Key | On | Value |
|---|---|---|
| `notes` | beat | list of links: the beat's notes |
| `beats` | session | ordered list of links: the session's plan |
| `date` | session | the session's date; sessions are ordered by it (ties by name) |
| `spent` | any note | the date it was spent; absent means unspent |
| `source` | a note sent from Legend Lore | the PDF page it came from, as a `file://` URL with `#page=N` (§8) |

```yaml
---
notes: ["[[Ismark Kolyanovich]]", "[[Svalich Road]]", "[[Wolves]]", "[[Ravens watch]]"]
---
Dusk. The wolves come out of the treeline…
```

A note's track is the folder it lives in, so a beat carries no per-track keys and renaming a track rewrites nothing. Obsidian shows `notes` and `beats` as lists of links in Properties, and `date` and `spent` as dates.

### 3.5 Writing discipline

1. **Surgical.** Command changes only the keys above, appends the GM's jots to a session note, and writes the notes it creates. Body text it didn't author is never rewritten; frontmatter round-trips with key order, quoting and comments preserved.
2. **Atomic.** Write a temp file in the same folder, then rename it over the original.
3. **Optimistic.** Every save carries the path and the content hash it was loaded from. If the file changed on disk since, the sidecar refuses (409) rather than overwriting, and the editor shows the conflict (§7).
4. **Deletes go to the OS trash**, through the `trash` crate Legend Lore already uses — never an unlink.
5. **Play state is not written.** The live set, the armed beat and launches live in the sidecar (§6.2). Only spends reach disk.
6. **Boards keep Obsidian's shape.** A session's board (§5.2) is written in Obsidian's own canvas layout: tab-indented, one node per line. Every node, edge and field Command didn't touch is kept, so a board Obsidian wrote comes back byte for byte.
   - A card names its note by path from the root, as Obsidian does with the root as its vault. A campaign-relative path (a vault opened on the campaign folder) also resolves.
   - Command's renames and moves rewrite these paths in every `.canvas` in the campaign, as they rewrite links.

### 3.6 The Shelf

*Decided on 2026-10-12, replacing the shared Library proposed on 2026-10-11.*

The campaign is the unit. Everything a campaign uses lives in its folder, so a campaign folder is complete on its own, like a Live project after *Collect All and Save*. The one exception is a sent note's `source`, which points at a PDF in the GM's Legend Lore library.

- **The shelf is the campaign's bin.** `<Campaign>/Shelf/` is reserved like `Beats/` and `Sessions/`. It holds material gathered but not filed on a track yet: Legend Lore clippings, ideas, homebrew drafts. In Live's terms it's the browser's *Current Project*, not the *User Library*.
- **Shelf notes are campaign notes.** They can be linked, their names are unique among the notes, and a beat or the board uses them as they are. Filing one on a track is a move, not a copy. Within one campaign nothing is copied, because every beat links the same note.
- **Send to Command lands on the shelf by default** (§8), so a clipping doesn't need a track while the GM is researching. The tracks stay offered for when the GM already knows.
- **Reuse is copying from another campaign.** The sidebar browses another campaign's shelf and tracks, and copies a note onto this campaign's shelf. The copy is this campaign's own: spendable, editable at the table, never linked back. Its `spent` mark is left behind, since that was the other table's. A GM who wants a common stock makes a campaign for it ("Homebrew") and copies from there.
- **On screen** it's a sidebar in Prep, at the left of the grid, toggled like Legend Lore's collections sidebar (⌘B). It shows this campaign's shelf, then its loose notes, and a picker browses another campaign. With a beat armed, a click on a shelf note adds it to the beat, as in the grid.

*Rejected:* a shared `Library/` at the root that campaigns link into, resolving a campaign's own note first. One note shared by every table means an edit at one table changes the others, `spent` can't live on it, and links need resolution order, overriding and renames across campaigns. It would also have been a second "library" beside Legend Lore's.

*Parked:* beats on the shelf, so a reusable encounter would copy with its notes.

*As built (phase 5):*
- **On disk.** `Shelf/` is made with each new campaign, and on first use in one started by hand: creating, sending or moving a note there makes it.
- **The sidebar** is 11rem wide. Tracks keep their width when it opens, and the grid scrolls to reach the ones it pushes off (§5.1). It's open until hidden, by a latch at the left of the bar, where Legend Lore's panel keys sit (its `LatchKey`, the book-bookmark glyph since 2026-10-17, when the box-archive glyph went to spent; dimmed and inert in Play, so nothing beside it moves) or ⌘B, which Legend Lore's collections sidebar also uses.
- **Its rows** are the grid's, with the same marks. Their menu files a note on any track; the grid's menu moves a note to the shelf.
- **Copying.** A copied note keeps its name, so a name another note has is refused and not renumbered: two notes of one name would make its links ambiguous. Shelf notes count as cards in Play and as notes for MCP, and `create_note` takes `"Shelf"`.
- **Places** (2026-10-17). With one campaign the picker held only the shelf it was showing, so *Copy from* now also lists folders the GM adds, as Live's browser lists the folders added to its Places: an Obsidian vault, a homebrew folder. *Add folder…* at its foot picks one with the native picker and browses it. One in the campaigns folder is refused, since its campaigns are listed already. A place's notes show under the folders they're in, and a click copies one onto the shelf as a campaign's note is copied, `spent` left behind; its `Beats/` and `Sessions/` are notes like any, not a campaign's. *Forget this folder*, in the picker while browsing one, drops it from the list and touches nothing on disk. Places are the machine's, kept in `command_settings.json` beside the root, never in a campaign, so the campaign folder stays complete on its own. Nothing watches them: a place is read each time it's picked.

### 3.7 Opening a campaign

*Decided and built on 2026-10-12.* Command opens on a blank **Untitled** campaign, as Live opens on an empty set, unless it has one to reopen (2026-10-14, below). The campaign key in Command's bar is a switcher, like Obsidian's for vaults. It's a key in a latch's well. The name is the switcher's pick, so it sits on the raised fill as the current view segment and tab do, and sinks to the well's floor while the menu is open (round 4 of https://claude.ai/artifact/HkutuQKTBCW31P58sTzBLg). Round 3's key standing proud of the bar was the one control in either tool not cut into the plate, and it read as foreign. Until 2026-10-14 it was a keycap in a well split by a groove into the switcher and a pen-to-square key; the pen's job moved into the switcher's menu. The session key beside it is drawn the same, and its menu already held *Edit session note*. Its well holds a second key, a `+` on the floor that starts the next session from the bar (2026-10-14; the menu keeps *New session*); with no session the well holds one `+ session` key, on the floor. Between the two, Legend Lore's path mark `›` says the session is the campaign's, in grey, printed on the panel as a faceplate prints its signal flow; it's not a key. The names on the keys are lit, in primary ink, as the current tab and view segment are, because they show what's in effect; `+ session` stays grey like any key that's off. This replaces the campaign list that filled the body when nothing was open.

- **Untitled is a real folder**, made at launch in the root with the default tracks. Every sidecar route needs the campaign folder to exist, so a campaign kept only in memory would need a special case in each, and in Send to Command and MCP too.
- **The name marks it:** `Untitled`, or `Untitled 2` and on (`vault.is_untitled`). The key shows it in italic. *Rename campaign* in the switcher (*Name campaign* while it's Untitled) turns the key into the inline name field, for any campaign, and Enter renames the folder.
- **Leaving a blank Untitled removes it.** Switching away, *New campaign*, choosing another root, or quitting does it. Blank means no files besides Finder's `.DS_Store` and `.unseen/command.json`. Removal unlinks only those and deletes only empty folders, so a note that lands meanwhile stops it rather than going with it. An Untitled with anything in it stays, as an ordinary campaign that happens to be called Untitled.
- **Launch reuses a blank Untitled** that a crash or a failed discard left behind. Otherwise it makes the first free name.
- **Launch reopens the last campaign** (2026-10-14): the one open when the app quit, if it's still in the root. The sidecar keeps its name (`last_campaign` in `command_settings.json`) from Rust's context pushes, and `POST /reopen` answers it, or a blank Untitled as before. A blank Untitled goes with the app, so a fresh one takes its place, as it does for a campaign renamed or removed in Finder meanwhile.
- **The switcher** lists every campaign in the root, with the open one lit (a menu pip), then *New campaign*, which opens a fresh Untitled, the same as a first launch, and, as in the session's menu, what acts on the open one: *Rename campaign*, *Show in Finder*, and *Move to Trash* under a rule. **Right-click** on the key manages the open campaign (Rename, Show in Finder, Move to Trash), as right-click manages a track or a note. Moving a campaign to the Trash opens a fresh Untitled, so Command is never left on nothing.
- **The root defaults to `~/Unseen Servant`**, made on first launch, so launch never stops to ask. Settings → Command changes it: Command closes the open campaign (a blank Untitled goes) and opens a fresh Untitled in the new folder.

- **The macOS File menu** offers the same: *New Campaign* (⇧⌘N, because ⌘N is Legend Lore's new collection and a menu shortcut takes the key from every window), *Open Campaign ▸* with the open one ticked, *Show Campaigns Folder* and *Change Campaigns Folder…*, above File's own *Close Window* (`file_menu.rs`, built on Tauri's default menu). New and Open bring Command forward: its own window if it's popped out, otherwise its tab. It's macOS only, because elsewhere an app menu is a bar inside every window.

*Rejected:* a campaign list in the body at launch (two ways in for one job, and a screen that wasn't the console); bracketed `[open]` `[new]` actions with nothing open; a type-to-filter name field. All are in the brainstorm artifact: https://claude.ai/artifact/4mr8d5i4rSxEHwujZ6faaB.

---

## 4. Sessions

A session owns its **plan** (`beats`, in order). It kept a log too, until 2026-10-18 (lifecycle 3). The rest of the table's state is on the notes themselves (`spent`), which is why notes need no carry-forward: a secret not yet revealed is just an unspent note in Secrets, still bright next session.

```markdown
---
date: 2026-10-18
beats: ["[[The mists close in]]", "[[Ambush on the road]]", "[[Tser Pool camp]]"]
---
Prep notes, reminders…

- the party insulted the burgomaster
```

**Lifecycle**

1. **`[new session]`** creates `Sessions/Session N.md` — N one more than the highest number in an existing session's name; renameable afterwards — with `date` set to today, and makes it the active session (`src-tauri/src/app_context.rs`). It plans nothing, and has no board until the GM arranges one (2026-10-15): every beat starts out spent or not in this session, so a copied board's cards would be notes no beat of it holds. Until then its plan started with the previous session's unspent beats and its board as a copy of the previous one. Renaming a session renames its board, and trashing a session trashes its board.
2. **Prep** edits the plan (add, remove, reorder beats) and the beats themselves. Beats in no plan stay in `Beats/` as potential scenes and can be pulled into one.
3. **Play** writes the GM's jots to the session note (§5.2), and nothing else. *Until 2026-10-18* it also appended a log under `## Log` as things happened: a beat launched (`▶`), a note spent or un-spent. The log was dropped then; lines already written stay in session notes as plain text, and nothing reads them.
4. **There is no end-of-session state.** The live set persists until something else is launched, so a session that stops on a cliffhanger resumes there.

Further rules:

- **Spending is manual by default, beats included:** launching a beat doesn't spend it. A setting, *spend beats on launch* (default off), makes a launch spend the beat. The UI says "spent" for every note, beats included: it's one word for one key (§10).
- **The active session** defaults to the latest by `date` when a campaign opens.

---

## 5. Views

### 5.1 Prep

- **The grid.** One column per track, in campaign order, each listing **every** note in the track (subfolders as groups). The beat launcher column sits at the right: the active session's plan in order, then the unscheduled, unspent beats in `Beats/`.
- **Arming a beat** (Legend Lore's arm glyph and `E`) makes a click on a note toggle its membership in that beat — the same gesture as curating into an armed collection. Disarmed, a click selects the note and a double-click opens it in the editor, as rows do in Legend Lore; armed, the click also selects it.
- **Marks.** Notes in the selected beat are lit; notes used anywhere in the session's plan carry a quieter mark; spent notes are dimmed, and their row keeps its spend key showing: the shut box (Font Awesome's `box-archive`) in a transport well, in the transport's grey whether spent or not, which every other note and beat row, in Prep and in Play's session player, shows while hovered or selected (a beat's also while armed or live), and whose click spends or unspends; on a beat it's the last key before the count (2026-10-17; a check mark before). To fit it, the tracks' and the shelf's note rows are divs that answer as buttons. *Since 2026-10-15* a track's spent notes leave its rows for a container docked at the column's foot, `spent` with its count and a caret, folded for the sitting until opened, as the session planner's spent group is, and on every track, with none spent too, so the columns end alike; open, it takes up to half the column and scrolls. A spent note there still drags to another track, but not among its own folder's rows, and a reorder keeps its saved place so unspending puts it back. The shelf keeps its spent notes in place.
- **The editor** is a right-hand inspector on the vellum surface showing the selected note (§7), and `[close]` gives its width back to the grid. Its title is the note's name field, as Obsidian's inline title: a click renames any note there, a beat or a session included. A session's board follows its note (`board.follow_rename`), and renaming the active session points the workstation at the new name, since it holds sessions by name. Right-click *Rename* on a row stays, for renaming without opening, and **R** renames the selected note or beat in its row, as Legend Lore's R does the focused one (2026-10-14). **A** marks the note or beat under the pointer spent, or unspent, in Prep and in Play, a row or a card, as Legend Lore's A shelves a collection (2026-10-17); every *Mark spent* item shows it. The menu item sits where Legend Lore's does, just above *Show in Finder* and *Move to Trash*, with its `[R]`, which it shows without taking while the menu is open, as the collections menu does; a right-click selects the row, as it focuses one in Legend Lore, so the key and the menu act on the same row. `?` or ⌘/ opens Legend Lore's shortcut sheet in Command too, with a Command section. Every rename, here and in Legend Lore, ends as Finder's does (2026-10-13, `ui/RenameField`): Enter or a click away commits, Escape backs out, and a refused name keeps the field with the reason under it; naming something new still cancels on a click away. The name is typed where it was read, in its face and size (a plate's ledger label in its true case), the row keeping its height, lamp, marks and count, and only its keys stepping aside; the campaign's field takes just its key's face. *Decided on 2026-10-11 in the app at 1280×800, over Live's bottom detail view, because notes are prose and need height more than width.*
- *The inspector plate, 2026-10-15:* the editor's head is Legend Lore's search inspector plate (`InspectorPlate`), level with the track and beat plates at their 1.65rem: the track in the row voice, its pigment as a small square where the system's shield stands, the master rule, then the group in small caps › the note's name in Almendra at the plate's 0.8rem, still the rename field. On the right, the save state and the spent date as tertiary readouts, then `[source]` and `[close]` as plate buttons. The spent checkbox is gone: the rows' menus mark it. The text's inset matches the plate's, so the path sits over the note. *Mocked in the full window against two richer versions (an "in beats" chip row, and the search inspector's hit lane ticking each `[[link]]`); the plate alone was chosen.* `[source]` doesn't cite a page: the source URL carries the PDF's physical page, and Legend Lore leads with the printed one.
- **Actions:** `[new note]` per column, `[new track]`, `[new beat]`, `[new session]`; rename, move to another track and delete (to the trash) from a note's context menu.
- *Tracks, as built 2026-10-12:* a column's nameplate is its handle, as a collection's row is in Legend Lore. It drags to reorder the tracks, with the collections' drop line turned on its side and the dragged column at 40%; dropped on `+ track` it goes last. Held near either edge of the grid, a dragged track scrolls it that way, faster nearer the edge, since the webview doesn't. The order is kept in `.unseen/command.json`, and each nameplate numbers its track by its place in it, as a mixer numbers its channels, in the count's small grey figures at the plate's other end: moving a track renumbers the plates. A note's slot is Ableton's clip square, lit as one of the splash's lamps (2026-10-13): one flat cell on every row, dark until a planned beat holds the note, half-lit parchment then, lit parchment while the selected beat does, and blinking lit under the pointer while a beat is armed, as a splash lamp blinks while its step runs. It sits under the track's number, and the note's name under the track's. Under a track's notes, and the shelf's, an empty row names a new note in place: a note row with no name, its lamp showing dark only under the pointer (since 2026-10-15, at all times), and naming it keeps a note row's height (2026-10-13; it was a `+ note` row). Since 2026-10-15 it's selected as a note row is: a click rings it and a double-click, or R on it, names the note. It names without a field of its own, as the session planner's new beat does: the row is dressed as the open, selected note it becomes (parchment wash, rule and ink in the ring), with an italic *Note name…* until something is typed; the dashed box is gone from notes. Every note row, the empty one and a new note's field, in the tracks and on the shelf, is ruled by a hairline at its foot in the columns' divider grey, a ledger's lines, drawn over the row so it keeps its 1.65rem; the first note sits flush under the plate (2026-10-15). A double-click on the name renames the track in place; right-click has *New note*, *Rename*, *Show in Finder* and *Move to Trash*. `+ track` names a new one at the end; since 2026-10-15 its column dresses as the track it becomes while it's named, a track's width with the next number and the plate's lettering, with no field of its own. Tracks are one fixed width, 10rem, with the shelf open or closed, so the grid scrolls rather than squeezing them: at 1280px seven tracks don't all show beside the beats.
- *As built (phase 2):* *Superseded where it differs by* Beat states, 2026-10-14, below. selecting a beat lights its notes, and a double-click opens it in the editor (its `notes` list updates live as membership changes). *Since 2026-10-12 the lit beat sticks:* it's the last beat clicked, until another is, it's clicked again, or Esc (which puts out the arm first, then the lit beat, then the selection), so selecting or opening its notes one by one leaves them lit. Its count badge turns parchment, and a track holding any of its notes counts those in place of its total, on the lit beat's parchment count badge, so a column says where to look, below the fold too; a track holding none keeps its total. Marked, never dimmed: dimming is Legend Lore's grammar for what's playing. Rows take Legend Lore's states: a latched grey-step hover, a ring on the selected row, the parchment wash and rule on the one open in the editor; a new beat lands armed and selected, as a new collection does in Legend Lore; a note started while a beat is armed lands in it; Escape disarms; the session switcher sits beside the campaign's in the bar. The inspector closes (`[close]`) and gives its width back, so with no note open all six default tracks and the launcher fit at 1280×800.
- *As built, 2026-10-12:* *Superseded where it differs by* Beat states, 2026-10-14, below. the beat column works as Legend Lore's collections panel. The arm key moved to the row's end, where a collection's transport is: hidden at rest, shown on the hovered or selected row, kept while armed. A beat's note count is the collection's LED readout, and its menu starts with *Arm*. The new-beat row is Legend Lore's ghost track, named in place after the plan with the arm key it will land with. Spent beats outside the plan are put away, as archived collections are, until `[show spent]` on the nameplate. A click still selects and lights rather than listing the beat's notes under it: the grid already lists them.
- *Dragging, as built 2026-10-12, as in Legend Lore's collections panel:* beats drag between plan rows to reorder the plan or to join it at that place. Dropped on a group's title, which lights as a beat does under a note, a beat changes group: on the session's it joins the end of the plan, on *not in this session* it leaves the plan. The beats not in this session take drops between their rows as the plan does: one of them moves there, and a plan entry leaves the plan and lands there. That order the campaign keeps in `.unseen/command.json` beside the track order, the same for every session; a rename keeps a beat's place, and beats it doesn't name follow by name. A note dragged from the grid or the shelf joins the beat it's dropped on, or, dropped on the new-beat row, starts a beat with it. Between any group's rows (a track's notes, or a subfolder's), in its own column or another, a note lands where the line shows, as beats do, the dragged row at 40%: among its own group's it reorders them, among another's it moves to that folder in that place, and a shelf note is filed there. Dropped on the rest of another track's column, lit with the same dashed outline, it moves to that track (2026-10-12). A track's note, or a loose one, dropped anywhere on the shelf moves back onto it, the shelf lit with the same outline; the shelf sorts by name, so it has no line (2026-10-14). Browsing another campaign, the shelf takes no drop. Held near the grid's edge it scrolls the grid as a dragged track does, and near a column's top or bottom, that column. The order the campaign keeps in `.unseen/command.json` by folder, a rename keeps a note's place and a renamed track keeps its notes' order, and notes it doesn't name follow by name. Nothing that drags carries a grip, in Command or in Legend Lore's collections, as a Mac list's rows don't: the drag shows itself by the fading row or column, the line and the outline, and a grip's slot cost names a tenth of a column's width. A nameplate's tooltip says it drags (2026-10-12). In the editor a dragged note drops as its `[[link]]`. Every drag, here and in Legend Lore, is carried by hand: the closed-hand cursor and a translucent copy of the row, never macOS's arrow or green copy badge (`ui/grab.ts`, 2026-10-14).
- *Launching from Prep, 2026-10-12:* *Replaced by* Beat states, 2026-10-14, below: Prep no longer launches. each beat row carries a collection's whole transport, the arm key and a play key. The play key launches the beat, and on the live beat it's the lit ■ that stops the live set. A launch from Prep isn't logged in the session, as a spend from Prep isn't; *spend beats on launch* still applies. While anything is live, Prep's notes outside the live set dim to 45%, the grid's and the shelf's, as Legend Lore's tree does while a collection plays, and hover brings one back to 70% (2026-10-12): the launch shows in Prep, not only in Play and to Claude. The column is 15rem, room for a name beside the transport and the count.
- *Selection and groups, 2026-10-12:* *Superseded where it differs by* Beat states, 2026-10-14, below. one row is selected at a time, a note's or a beat's. A click on anything else in Prep, or Esc with nothing armed, drops the selection; the editor, menus and fields don't count as elsewhere. Arming a beat selects it without opening it in the editor, as arming a collection opens nothing, and a new beat, from the new-beat row or *Write this beat*, lands armed and selected without opening either; a double-click opens it. Note rows are square, as beat rows are, and so are Legend Lore's file-tree and systems-view rows, so every list row in the app ends on a straight edge. An armed beat keeps its notes lit whatever is selected, so adding notes shows the beat filling. A beat open in the editor carries no mark of its own. The live beat wears a playing collection's left edge, a 3px purple rule over an 8% parchment wash, in Prep and in Play's arrangement alike; an armed beat wears the armed collection's, the same rule over a 25% wash. The column heads both of its groups, the session's name over the plan and *not in this session* over the rest, each with its count; with no session it's one list under the plate. Each title folds its group with a caret, as Legend Lore's filter sections fold, for the sitting only; a folded group holding the armed or the live beat lights their section lamp on its title.
- *The beats key, 2026-10-12:* the beat column hides and shows from a latch at the right of the bar, on the side the column opens, between the Prep/Play switch and the window's key, with Font Awesome's `list-ol` (the column is the session's plan, in order). Like the shelf's, it's dimmed and inert in Play. Its lamp lights while a beat is armed or live, as the collections lamp answers for the mix, so a hidden column still says so. Hiding the column disarms the beat and lets go of a selected one, as closing Legend Lore's collections panel disarms. Its plate and key name it the *session planner* (2026-10-15, briefly *beat planner*): it's where a session's plan is made.
- *Beat states, 2026-10-14:* an audit of what a beat's states show found three pointers to "this beat" (selected, lit, armed), two views deciding differently whether anything was live, and spent beats that could leave the column armed or live. The rule now is three facts and two pointers. **Facts.** Every beat is in one of three groups, each titled and folding as before: the session's plan, *not in this session*, and *spent*, the spent beats no plan holds, folded by default. The spent group replaces `[show spent]`, so no beat ever leaves the column; a folded group still lights its section lamp over the armed or the live beat. A spent beat in the plan stays in the plan, ticked: it's the record of the session. A beat is live when the live set holds notes and was launched from it. The sidecar keeps that true: a set emptied of notes stops and forgets its beat, and a note or beat that's gone (trashed here, deleted in Finder or Obsidian) leaves the set when it's next read. **Pointers.** One focused beat: a click focuses it, ringed with its notes lit and its count in parchment, and a click on it again lets go; selecting a note leaves it focused, so its notes can be read one by one, and so does a click on empty space. A right-click focuses too, so the menu and the keys act on the beat it shows. Armed is a flag on the focused beat, never a beat of its own: arming focuses, disarming keeps the focus, and focusing another beat disarms. Esc disarms, then lets go of the beat, then of the note. R renames the row clicked last. **Prep doesn't launch.** Prep arranges and Play runs: a beat row in Prep has only its arm key, and the live beat, wherever it shows, has the lit ■ that stops the set, in Prep and in Play's arrangement alike (a second ▶ no longer relaunches it and logs it twice). Prep's notes don't dim for the live set. **One cue per state:** the ring (focused), the purple rule over a 25% wash (armed), the lit ■ (live), the half-lit square on its notes (planned), dimmed with a shut box and restored on hover (spent, in Prep and Play). A beat's count is the notes it lights, not its links, so it agrees with the track plates.

### 5.2 Play

- **The board** fills the centre. There is one per session, `Sessions/Session 13.canvas`, in JSON Canvas 1.0, so Obsidian Canvas opens it. It holds the session's notes (the union of its planned beats' notes) plus anything launched, as cards the GM moves, resizes and connects.
  - *Decided on 2026-10-12: one board per session, not a canvas per beat.* Launching lights cards where they are, as Live's Session View lights clips, instead of swapping the whole surface. A note in three beats is one card. Beats keep owning their notes, so the board holds only placement, size and connections, and can't disagree with a beat about membership.
- **Cards** render their note read-only on the vellum surface, and a card's size decides how much of the note shows. Each card has a spend key, the shut box in the play key's well, the same grey spent or not, since the spent card dims (2026-10-17; a checkbox before). A note never placed is auto-placed by track beside what the GM arranged, so a board nobody touched still reads. The board's first change (a move, a resize, a line, a removal) places every card where it sits, so a card moved after moves alone (2026-10-17). *Until then* only the moved card was placed, and the auto-placed ones, laid out from the placed ones' edge, all moved with it.
- **Connections** are lines between cards. They mean nothing to Command yet. *Decided on 2026-10-12. What following one could do, like Live's follow actions, comes later.*
- **At the table the board needs no handling.** Launching frames the live cards. Dragging and connecting are allowed but never required; arranging happens before the session, in Play with nothing launched.
- **Editing in Play.** Cards are read-only. A card's `[edit]` opens its note in the same right-hand editor as in Prep, closed until asked for, for a quick change mid-session such as Ismark turning hostile.
- **The arrangement** runs down one side: the session's plan with spent beats ticked.
- **Launching what isn't on the board.** Typing outside the editor opens a find line on the board, listing the campaign's matching notes. Launching one puts it on the board, auto-placed. This replaces the compact grid planned before the board, since the board already holds the session's notes. *Removed on 2026-10-17:* Play plays what the board holds, the session's planned notes and anything live; a note outside the plan joins a beat in Prep first, or Claude adds it (`add_to_live_set`).
- **A jot bar** in the board's bottom-left corner adds a line to the session note. Long text wraps and the bar grows up from the corner. Enter writes `- text`, untimed, at the end of the note's text, and clears the bar for the next. The GM keeps notes in the session note rather than reading back a log. A pen key (Font Awesome's `pen-to-square`) beside the bar, or ⌘O, opens the session note in the inspector, from Prep or Play, the editor and the bar included (2026-10-17). *Until then (removed earlier on 2026-10-17, with the log's display below):* a jot line under the log appended a timestamped line to the log.
- **The card tray** (2026-10-18) holds the live set as a hand of cards, docked under the board, as a deckbuilder's hand sits under its table. The board is where the session's notes are arranged, and the tray is what's in play now, readable at a glance and in one place whatever the board's zoom. It shows only while something is live, in the live set's order, so a note played on its own joins at the end. Each card is a board card's face (`CardFace`), at a reading width that fits five across a 1280px window. Past what fits, the cards overlap evenly, so every one stays in view with its pigment and the start of its title. The card under the pointer is the one whose strip the pointer is on, so moving along the hand steps through every card. That card comes to the front, whole, and a note longer than the tray grows up over the board. Its board card is outlined. Clicking cards picks them: a picked card takes the accent rule and rises a step in the hand, as a card readied to play, and the hand stays as it was. The plate's `[select]` then lays the picked cards side by side, sharing the tray's width, with the rest on their side as spines, one click from joining them; `[deselect]` puts them back in the hand, still picked (2026-10-18: a click first laid them out at once, and the user asked for the step between; the keys first read `[spread]`/`[gather]`). A new live set (a launch, a stop, a note played or taken out) clears the picks. The plate (*in play*, the count, the live beat) folds the tray, as the session player's does, and the fold holds across Tab. Folded, the plate holds a nameplate per card in its track's pigment. Pointing at one brings its card up above it, and clicking one opens the tray with that card picked. Launching still frames the live cards on the board. Mocked in the full window first (https://claude.ai/artifact/DC5ZAAiXzbN1gNSq97tPpJ): a fanned hand (Slay the Spire) and a rail of nameplates lost to the docked tray, which keeps the rail as its folded state and the fan's whole hand as its overlap.
- *As built (phase 3):*
  - **Layout.** The board fills the view, and the note editor opens on the right as in Prep. The arrangement, named the *session player* (2026-10-17), is a 15rem box over the board's top-left corner, the session planner's width, edged and lifted as a menu is and only as tall as the plan, scrolling past the board's height. Launching and the frame key fit the cards to the board beside the box, a grid square clear of it. Its plate folds the list (2026-10-17), as a group's title does in Prep, the caret where other plates start their title: folded, only the live beat's row shows, and with nothing live only the plate. The fold holds across Tab, for the sitting. *Until 2026-10-17* it was a column down the left under a plate named *play*.
  - *Removed on 2026-10-17:* the log followed the plan, newest at the bottom, then the jot line (*Write in the log…*), and a day's version docked it in Prep under the session planner too. Neither was what the GM wanted. The log was still written to the session note, where Obsidian showed it and Claude read it (`current_session`), but Command didn't show it. Since 2026-10-18 it isn't written either (§4).
  - **The plan works as Legend Lore's collections panel** (2026-10-16): rows of a note row's height, the name first, a collection's transport at the row's end (hidden at rest, shown on the hovered or focused row, kept while live) and its LED count of the notes the beat lights. A click focuses a beat, ringed; ↑↓ or J/K step the focus, and P or Space launches the focused beat or stops it while it's live, as they do a collection (J/K and P since 2026-10-17, when the find line stopped taking letters). A double-click opens the beat in the editor, and right-click focuses it and opens its menu, the transport first: *Launch*/*Stop*, *Frame the live cards*, then *Mark spent* and *Edit beat*. The live beat's ■ is the only stop, and the live beat's row wears a playing collection's highlight, the 8% parchment wash under a 3px purple rule (2026-10-17, asked for over beat states' one cue per state), and the session planner's live beat in Prep the same; an armed beat's 25% wash wins over it, as in Legend Lore. Beside each play key, shown with it, a frame key (Font Awesome's `expand`) frames the beat's cards, and on the live beat the live set's (on every beat since 2026-10-17; before, on the live beat only). The board gives these keys up: no moving a focused card by arrow, no Space to pan.
  - *Replaced on 2026-10-16:* a transport strip floated over the board's top edge (an amber lamp, the live beat's name, the count, `[frame]`, `[capture]`, `[stop]`), and the plan's rows put the play key first and the launch times after the name. The times are the log's. A click on a beat name framed its cards. Where the strip said what typing does, a legend is printed in the board's corner, and since the find line went (2026-10-17) only on an empty board: *Plan beats in Prep to put their notes here*. The legend went on 2026-10-17, after the jot bar took the corner.
  - **The board** is graph paper (2026-10-16), the old-school dungeon map's: Svelte Flow's line background, 24px squares in `--bg-header`, scaling with the zoom.
  - **Cards.** Each card's play key is Legend Lore's transport key, so it lights purple while the note plays, and the card itself takes the parchment rule and glow. The head reads as a row (2026-10-17): the title on the left, then the track, the source key when there's one, the play key and the spend key at the right end; the play key used to lead, before the title. The head takes its track's pigment as the track's plate does in Prep, the title in bold ink, and its keys keep the plain head's ground so the pigment doesn't show through their wells, as a pigmented plate's count badge does. The track's name is set in a well like theirs, bold. Double-click or the card's menu opens the note in the editor, and its links open the note they name.
  - **Gestures.** Moving, resizing, connecting and deleting (Delete or Backspace, lines always, cards only when nothing would put them back) go out as board operations, drawn at once. The board opens framed on the live cards the first time in a sitting, and after that where it was left (2026-10-17): Tab to Prep and back no longer reframes it. A card whose note is gone shows dashed.
  - **Canvas extras.** Obsidian's text, link and group nodes render and can be moved. Since 2026-10-19 a line draws its own arrowheads in its own path, Obsidian's too. *Until then* they weren't drawn: Svelte Flow names markers after their colour, and a token colour (`var(…)`) inside `url(#…)` isn't safe in WebKit.
  - *The board's toolbar, as built 2026-10-19* (step 1 of [the toolbar's design](2026-10-19-command-board-toolbar-design.md)): Command now makes text cards, stickies (a text card with a pigment), frames (groups) and labelled lines too, through the sidecar's `add` and `set` operations and `connect`'s new fields. Select, Hand, Text, Sticky, Line and Frame sit on Miro's letters in a column under the expand key; a text card, a frame's name and a line's label are edited in place by double-click, a frame carries the cards wholly inside it, ⌘G frames the selection, and every board edit can be undone (⌘Z, ⇧⌘Z) for as long as the board is open. *Step 2, the same day:* the Note tool (D) places any note of the campaign where the board is clicked, named in a field with the editor's completion; a selection bar over selected text cards, stickies and frames, or a selected line, offers the track menu's pigment row, and on a line its ends and label; ⌘D duplicates text cards, stickies and frames (a frame with what's inside it but its notes); ⌥1 and the toolbar's fit key show the whole board, and ⌥2 the selection.
  - **Attribution.** Svelte Flow's credit stays in the corner, quiet: its authors ask that only subscribers hide it.

### 5.3 Launching

- **Launching a beat** makes the live set exactly its notes. Only Play launches (2026-10-14, §5.1).
- **Launching a note** adds it to the live set; launching a live note again takes it out. This is improvising: it changes the live set only, never the beat the set came from.
- *Capture, removed on 2026-10-16:* `[capture]` saved the live set as a new beat, named by the GM, after the last launched beat in the plan. Naming a beat mid-session is the friction the table doesn't take, and what it bought, relaunching an improvised scene, is rare.
- **Stop** clears the live set.

**Tab switches between Prep and Play** in one Command panel, as in Live. Legend Lore uses Tab to switch between tree and systems, and the two don't collide:
- Each panel's window handler returns early while its panel is inactive (PANELS.md; `LegendLorePanel`'s handler starts with `if (!active) return`), so Tab does whatever the visible panel defines.
- As in Legend Lore, Tab keeps its usual meaning in the editor, in text fields and in menus.
- In phase 3, `view.toggle` in `src/lib/shell/keybindings.ts` gets a label that covers both tools.

Two panels, with Play on a second screen, wait until play at the table asks for them. Nothing in phase 3 rules them out.

### 5.4 Visual language

Nothing new beyond the grid cell. Each meaning maps to an existing token or idiom:

| Meaning | Treatment |
|---|---|
| Track identity | a pigment from Legend Lore's palette, chosen from the track's menu (2026-10-14): it fills the nameplate, the name in ink as Legend Lore's selected index cell, never glowing. A track without one is a plain nameplate |
| Note in the live set | parchment rule and `--glow-accent` on the card; its play key lit purple, as Legend Lore's transport |
| Prep / Play | a picker in Command's bar, Legend Lore's view switch rule for rule: table-columns and play glyphs, the current segment raised, never purple (one view is always on) |
| Armed beat | Legend Lore's arm glyph in `--text-active` |
| Live beat | its key lit as a stop ■, in Prep and Play (2026-10-14) |
| Spent | `--opacity-out-of-scope` plus a check; hover restores |
| Unresolved link, missing note | dashed parchment, `--outline-drop` |
| Actions | lowercase brackets: `[new beat]`, `[read]` |

---

## 6. Architecture

Placement follows the architecture doc (D2, D4, D5, §4 Q4).

### 6.1 Sidecar — `sidecar/command/`

- **`router.py`** with `build_router(...)`, mounted in `server.py` beside Legend Lore's.
- **Settings** in `command_settings.json` in the data dir — the root folder and *spend beats on launch* — following `search_settings.json`.
- **Index:** *as built, no cache at all:* every read scans the campaign folder (tracks, notes with track and group, ambiguous names), and a rename scans the notes' text for links. A few hundred notes take a fraction of a second; a cache — in memory, then SQLite — only when a measurement asks for one. Phase 2 parses every note's frontmatter on each read, leniently — one broken block doesn't hide the campaign.
- **Watcher:** `watchfiles` on the root. Changes update the index and go out on the event stream. Command's own writes take the same path, so there is one way a change becomes visible.
- **Writer:** §3.5 — atomic writes, the hash check, link rewriting on rename. *As built (phase 2):* frontmatter is never re-serialised. `command/frontmatter.py` replaces only the lines of the one key it writes, then parses the result back (PyYAML) and refuses unless that key holds exactly what was written and every other key is unchanged. `ruamel.yaml` was dropped: it re-indents sequences document-wide, which touches keys Command doesn't own.
- **Event stream:** `GET /command/events`, server-sent events: `vault` (campaign, changed paths), `live` (a snapshot with `seq`) and, since 2026-10-19, `session` (an agent's ask to open one, §6.2).

### 6.2 Live state

The live set lives in the sidecar, because MCP has to read it (D5): per campaign, `{seq, beat, notes}` — the launched beat, if any, and the notes now live. It is persisted to the data dir on every change, so a crash mid-session restores it. The armed beat and the selection are per-panel UI state, not live state.

The active campaign and session stay owned by Rust (`app_context.rs`, unchanged). Rust pushes them to the sidecar on every change and whenever the sidecar (re)starts, so MCP can answer "current session" with no window open.

*Since 2026-10-19* MCP can ask Rust to open a session of the open campaign (`set_active_session`, `create_session`). `POST /command/context/session` publishes a `session` event on the stream Rust relays; the relay calls `app_context::open_session`, which switches only while that campaign is still the open one, then broadcasts to every window and pushes the context back. The tool waits until the sidecar's context shows the session, so its reply is true. Rust still owns the context: the sidecar only asks.

### 6.3 Rust — `src-tauri/src/command.rs`

- Proxy commands over the routes, as `legend_lore.rs` does.
- **The event relay:** after boot, one task subscribes to `/command/events` (reusing `SseFrames` from `legend_lore.rs`) and re-emits `command://vault` and `command://live` to every window, reconnecting when the sidecar restarts. A `session` event opens that session instead (§6.2).
- Deletes through `trash::delete`.

### 6.4 Frontend — `src/lib/command/`

- `CommandPanel.svelte` replaces the placeholder: the Prep/Play switch, taking `active` and `windowKey` per PANELS.md.
- The live set is a `rustMirror` (`command://live` plus a pull command); `vault` events refetch what they name. *As built:* not a `rustMirror`, which mirrors one global snapshot with no arguments, and live sets are per campaign. `CommandPanel` pulls the open campaign's set (`command_get_live`) on entering it and on a refresh, and keeps a `command://live` snapshot when it's that campaign's and its `seq` is newer.
- *As built, confirmed on 2026-10-11:* the campaign and session switchers sit in Command's own bar, not in shell chrome. The tab strip exists only in the main window, so a shell picker would leave a popped-out Command unable to switch. The campaign name opens the switcher, and right-click opens its own menu (§3.7). The TEMP picker in `PanelHost.svelte` is gone; the active campaign itself still lives in `app_context.rs`.
- *As built, 2026-10-12 (§3.7):* Rust opens a campaign at boot (Untitled, or since 2026-10-14 the last one open), before any window asks what's open. Every campaign switch goes through `switch_campaign_with`, which holds an async lock across the switch and the discard of the campaign left behind. Without the lock, a *New campaign* right after leaving a blank Untitled could be handed that same folder just before the discard removes it. The discard also runs on `RunEvent::Exit`, before the sidecar stops.
- `<ConfirmDialog />` moved from Legend Lore's panel to the two window hosts (`PanelHost`, `StandaloneFrame`), one per window, so a popped-out Command can ask.
- The campaigns folder is chosen in Settings → Command (`command_choose_root`, the native picker). Until then it's the default (§3.7).

---

## 7. Editor

CodeMirror 6 on the raw Markdown source. The spike validated it; the Electron app's WYSIWYG round-trip was lossy, and fidelity to the user's file is the point. It is styled with the app's fonts (Almendra headings, Crimson body), has `[[` autocomplete over the campaign's note names, and shows frontmatter as source.

- Autosave is debounced and flushed on switching notes. A save carries the path and hash captured when the note loaded, never "whatever is selected now".
- On a `vault` event for the open note, a clean buffer reloads silently; a dirty one keeps the buffer and shows the conflict with `[reload]` and `[keep mine]`.

Play renders notes with `svelte-exmarkdown` (already a dependency) plus a wikilink plugin; a link opens its note in Prep.

*Reading mode, 2026-10-15:* the inspector reads a note rendered as well as editing its source, Obsidian's reading view: `[read]` on the plate, `[edit]` to go back, or ⌘E from anywhere in the panel, the editor included. Rendering is a board card's (`bodyOf`, `linkify`, GFM), so it never writes and the source stays the one thing edited; a link no note answers to is dashed, as in the editor, and a click on a link follows it there. It's set in the editor's face, size and inset, so a toggle changes the markup and not the page. The mode stays with the window as notes open, as a tab keeps Obsidian's; a new note opens to edit. The editor stays mounted while hidden, keeping its undo and caret. Headings in the editor are Almendra at every level now: a CodeMirror tag takes only its most specific rule, so each level's size had been dropping the face.

---

## 8. Cross-tool (phase 4)

- **MCP tools** in `mcp_server.py`, over the Command routes (D5). A starting list: campaigns, current session (plan and log), live set (with note bodies), read note, find notes, create a note in a track, add to the live set, spend. The Servant gets exactly these.
- **Send to Command** from a Legend Lore hit creates a note in a chosen track of the active campaign, or from phase 5 on its shelf (the default). The note holds the quoted text and a `source` pointing at the PDF and page; in Play, its card opens Legend Lore at that page. Routed through Rust (D4: no drag and drop across windows).

*As built (phase 4, 2026-10-12):*

- **The active campaign reaches the sidecar.** Rust pushes `{seq, campaign, session}` to `PUT /command/context` on every change (`app_context.rs`) and whenever the event relay connects, since a restarted sidecar knows nothing. The newest `seq` wins. MCP tools act on that campaign unless given `campaign=`, and on its open session, else the latest.
- **The tools** are `campaign_overview` (the campaigns, then one's tracks, notes, beats and sessions by name; it replaced `list_campaigns` on 2026-10-19), `current_session` (plan with each beat's notes, what's live; any session by name since 2026-10-19), `live_set` (each live note's full text), `read_note` (with the note's hash) and `find_notes` (by name or text), `create_note` (into a track only), `edit_note` (the text below the frontmatter, hash-checked through `PUT /note`'s `keep_frontmatter`; since 2026-10-19), `create_beat` (notes that exist, the scene's text, optionally the end of a session's plan) and `add_to_beat`, `set_active_session` and `create_session` (which opens what it makes, §6.2), `plan_beat` (add, move to a 1-based position, or take out, dangling entries included; all since 2026-10-19), `add_to_live_set` and `spend`. (Until 2026-10-18 `current_session` read the session log too, and `spend` wrote to it.)
  - Notes are named as a wikilink names them. An ambiguous name asks for the path. A tool that takes a note looks among the notes, and one that takes a beat among the beats, so a beat named after its place needs no path there (2026-10-19).
  - With the app closed, they say so instead of "nothing open".
  - The server introduces itself as *Unseen Servant* now that it serves both tools. The Claude Desktop config key is unchanged, so no migration is needed.
  - A real stdio MCP client lists all twenty tools.
- **Send to Command** is a submenu on a search hit's menu (beside *Collection*), listing the open campaign's tracks. With no campaign open, it says so.
  - Legend Lore calls `command_send_targets` and `command_send` in Rust and nothing else of Command.
  - The note is named after the section's heading, with characters a name can't hold dropped and a clash numbered. It holds the section's text, then a link back citing book and printed pages.
  - Its `source` is the PDF page's `file://` URL: clickable in Obsidian, and machine-specific, like the library it points into.
- **Opening the source.** "Opens Legend Lore at that page" became opening the PDF at that page in the system viewer, which is what Legend Lore does with a hit, since Legend Lore has no viewer of its own. It's reachable from a book key on the card, *Open source* in the card's menu, and `[source]` in the editor's head (in Prep too).

---

## 9. Phases

All on the `workstation` integration branch; Command ships when `workstation` is promoted (v4.0.0, architecture §6).

| # | Phase | Delivers | Verify |
|---|---|---|---|
| 0 | Dev data | `~/Unseen Servant` cleared of the Electron app's `Campaigns/` and `Library/` (moved aside, not deleted) | the root holds only campaigns — **done 2026-10-11**: moved to `~/Unseen Servant (Electron)/`, Misty Vale copied back as the dev fixture |
| 1 | Vault — **done 2026-10-11** | settings, scan and index, watcher, writer, event relay; the campaign picker; the Prep grid of tracks; the editor; create, rename, move and delete for notes, tracks and campaigns | pytest: scan, link resolution, rename rewriting, byte-preserving round trip, 409 on a stale hash. By hand, with the root open in Obsidian: an edit on either side shows up on the other; a rename in Command updates the links Obsidian shows |
| 2 | Beats and sessions — **done 2026-10-11** | `Beats/`, the launcher column, arming and membership, sessions, plan order, `[new session]` carry-forward, spent | pytest: carry-forward rules; `notes`, `beats` and `spent` round trips |
| 3 | Play — **done 2026-10-12** | the session board (read and write JSON Canvas, path rewriting, carry-forward; Svelte Flow surface with move, resize, connect, auto-place), live state and its persistence, launch, stop, capture (removed 2026-10-16), editing from a card, the arrangement, the log, jots (removed 2026-10-17), Tab between Prep and Play, *spend beats on launch* and the Command pane in settings | kill the app mid-session, relaunch, and the live set is back; the log reads correctly in Obsidian; a board arranged in Command opens in Obsidian Canvas, and one written by Obsidian round-trips byte for byte |
| 3b | Images ([#407](https://github.com/Unseen-Servant/unseen-servant-app/issues/407)) | `![[map.png]]` embeds on cards: the asset protocol scoped at runtime to the campaigns folder, embeds resolved by name. The CSP already allows `asset:` images | a map embedded in a note shows on its card |
| 4 | Cross-tool — **done 2026-10-12** | MCP tools, Send to Command, opening Legend Lore from a card | architecture Step 4: an MCP client lists Command's tools beside Legend Lore's; Send to Command round-trips a search hit |
| 5 | Shelf — **done 2026-10-12** | `Shelf/` reserved; the shelf sidebar in Prep (this campaign's shelf and loose notes, another campaign to copy from), filing to a track and back, Send to Command defaulting to the shelf, MCP reaching it (§3.6) | pytest: resolution order and shadowing, a Library rename rewriting every campaign, `spent` refused on a Library note |

---

## 10. Decisions and open questions

Settled on 2026-10-11, before phase 3:

1. **Library:** settled as a shared `Library/` at the root on 2026-10-11, then replaced on 2026-10-12 by each campaign's shelf (item 9).
2. **Editor placement:** the right-hand inspector, closable (§5.1). Play opens a note in the same place for a quick edit, and cards stay read-only (§5.2).
3. **Images in Play:** a follow-up once the core Play loop works (phase 3b, §9), not part of phase 3.
4. **Wording:** "spent" everywhere, beats included: one word for one key.
5. **Prep and Play:** one panel, and Tab switches between them (§5.3). Two panels only if play at the table asks for them.
6. **Switchers:** the campaign and session switchers stay in Command's bar (§6.4).
7. **Play is a board** (2026-10-12): one per session, in JSON Canvas (§5.2). The GM moves, resizes and connects cards, Miro-style.
8. **Connections are lines** for now (§5.2). Giving them meaning in Play comes later.
9. **The campaign is the unit, and gathered material waits on its shelf** (2026-10-12, §3.6). Reuse across campaigns is copying; there's no shared library. The name is *Shelf*, because "library" is Legend Lore's. Send to Command defaults to the shelf. Beats on the shelf are parked.
10. **Opening a campaign** (2026-10-12, §3.7): launch opens a blank Untitled (since 2026-10-14, the last campaign open when there is one), and the campaign key is an Obsidian-style switcher with *New campaign* at the bottom. The root defaults to `~/Unseen Servant`, the key's pen names Untitled, and *New campaign* opens a fresh Untitled rather than asking for a name first.
11. **Track identity** (2026-10-14, §5.4): tracks take a pigment from Legend Lore's palette, kept in `.unseen/command.json` and following renames, filling the nameplate.
12. **Beat states** (2026-10-14, §5.1): three groups (plan, not in this session, spent), one focused beat with an arm flag, and launching only in Play.

Open:

1. **Beat identity** (2026-10-12): whether beats take a pigment, as collections do, so a note's row shows the planned beats that hold it in place of today's outlined square. Deferred to its own pass, with where the pigment is kept (presentation, so `.unseen/command.json`, following renames). Beats need a glyph of their own for it, not Legend Lore's gem.

---

## 11. Not doing

- Templates per track, initiative or HP tracking, a player-facing display, AI features inside Command (the Servant reaches Command through MCP).
- Importing the Electron app's `.unseen` beats.
- A library shared by campaigns (§3.6): reuse is copying from another campaign.
- An Obsidian plugin: Obsidian is a peer editor of the same files, nothing more.

---

## 12. Related

- [2026-09-24-unseen-servant-workstation-architecture.md](2026-09-24-unseen-servant-workstation-architecture.md) — D2–D6 and §4 Q4, which this doc builds on.
- [2026-10-18-command-mcp-tools-design.md](2026-10-18-command-mcp-tools-design.md) — the MCP tools' audit and the plan that extends §8.
- [2026-10-19-command-board-toolbar-design.md](2026-10-19-command-board-toolbar-design.md) — the board's creation toolbar, after Miro's, which extends §5.2.
- `src/lib/shell/PANELS.md` — the panel contract Command's UI follows.
