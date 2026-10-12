# Command — design

**Date:** 2026-10-11
**Status:** the model, the vault layout and session management were agreed in conversation on 2026-10-11, and the open questions were settled the same day before phase 3 (§10) — all but track identity, which waits for Play on screen. Phases 0–2 done 2026-10-11, phase 3 on 2026-10-12 (§9); where the build departed from this doc, the text below says so.
**Objective:** specify Command, the workstation's second tool (architecture doc §6 Step 4), before any code: what the vault looks like on disk, how sessions work, what Prep and Play show, and where each piece lives across the three layers.

---

## 0. TL;DR

- **Ableton Live for prep and play.** Tracks are kinds of material (PCs, NPCs, Locations, Secrets, Monsters, Treasures — editable), notes are clips, beats are scenes. Prep builds; Play runs the table: launch a beat and its notes light up, improvise by launching more, capture the result as a new beat.
- **The vault is folders of Markdown, and nothing else is truth.** A campaign is a folder in a user-chosen root, a track is a folder in the campaign, a note is any `.md` file in a track. Beats and sessions are notes too. Open the root in Obsidian and everything reads, links and edits.
- **References are `[[wikilinks]]` by note name**, in frontmatter lists Command owns: a beat lists its notes, a session lists its beats. Nothing stores ids, paths or copies.
- **Play state never touches notes.** What's live is sidecar state; only story facts are written: a note marked spent, the session log, a captured beat.
- **Spent replaces carry-forward for notes.** Any note can be spent (secret revealed, treasure given, beat played, NPC dead); an unspent note is simply still bright next session. Only a session's plan carries forward: a new session starts with the previous one's unspent beats.
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
| A selected beat rewrote itself on every toggle | §5.3 — launching is not editing: arm to edit, capture to keep an improvisation |
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
| Live Set | Session | a note in `Sessions/` listing its beats, with its log |
| Playing clips | Live set | sidecar state, never in notes |
| Recording into the Arrangement | Log | the `## Log` section of the session note |
| Session View / Arrangement View | Prep / Play | — |

The views are renamed because "session" already means the game session. Live's mapping is also inverted relative to the table: Live's Session View is its improvisation surface, and at the table improvising happens during Play. So Play carries a compact launch grid as well as the arrangement.

One structural break from Live: a Live scene is a row with one clip per track, but a beat holds three NPCs and two secrets, and the same NPC appears in many beats. So beats are not rows. Each note appears once, in its track's column; a beat is a selection over them, and launching it lights its notes across the columns.

---

## 3. The vault

### 3.1 Layout

```
<root>/                                  user-chosen (dev: ~/Unseen Servant)
  Curse of Strahd/                       campaign = any non-dot folder in the root
    .unseen/command.json                 presentation only: track order, pigments
    PCs/ NPCs/ Locations/ Secrets/ Monsters/ Treasures/      tracks
      NPCs/Ismark Kolyanovich.md         a note
      NPCs/Vallaki/Lady Wachter.md       a subfolder groups notes inside a track
    Beats/
      Ambush on the road.md              a beat
    Sessions/
      Session 13.md                      a session
      Session 13.canvas                  its board (§5.2), JSON Canvas
  Library/                               shared across campaigns (§3.6, phase 5)
    NPCs/ Monsters/ …                    tracks, as in a campaign
```

- **Root.** Chosen in settings and persisted by the sidecar (§6.1), so the watcher and MCP know it with no window open. Every non-dot folder in it except `Library/` is a campaign; a folder created in Finder is a campaign.
- **Tracks.** Every non-dot folder in a campaign except the reserved `Beats/` and `Sessions/`. A new campaign gets PCs, NPCs, Locations, Secrets, Monsters and Treasures plus the two reserved folders. Adding a track is making a folder, in Command or anywhere else. Notes anywhere under a track folder belong to it; subfolders show as groups within the column.
- **Loose notes** directly in a campaign folder are notes without a track: linkable and editable, not drawn in the grid.
- **`.unseen/command.json`** holds only presentation (track order, a pigment per track). It travels with the campaign and stays hidden in Finder and Obsidian (a dot-folder, the `.obsidian/` precedent). It never holds membership, so drift is harmless: a track it doesn't know gets defaults, and a stale entry is ignored.

**Rejected:** a `campaign.toml` or `.unseen` state file holding categories and beats (both earlier apps, §1); track order in a campaign note's frontmatter (nested maps render badly in Obsidian's Properties, and order isn't content); a folder per session holding its beats (carrying a beat forward would move files, where with `Beats/` it is a list edit — §4).

### 3.2 Notes

- A note is any `.md` file. Its **name** is the filename stem, as in Obsidian. Frontmatter is optional, and keys Command doesn't own are left alone.
- **Names are unique within a campaign**, compared case-insensitively (as the default macOS file system and Obsidian's link resolution compare them). Command refuses to create or rename into a clash; a clash made outside Command is flagged, and links to that name show as ambiguous.
- Non-`.md` files are not notes. (Images in Play: phase 3b, §9.)

### 3.3 Links

- References are wikilinks: `[[Name]]`, with optional `|alias` and `#heading`; `[[Folder/Name]]` is accepted. Resolution is by name within the campaign.
- An unresolved link is drawn in dashed parchment, the app's "prospective, not yet real" idiom (`--outline-drop`), and offers to create the note.
- Renaming a note in Command rewrites every link to it across the campaign — frontmatter lists and bodies — keeping alias and heading. Moving a note to another track changes no link. A rename in Finder breaks links, which show as unresolved; Obsidian's renames update links when its *Automatically update internal links* option is on.

### 3.4 Frontmatter Command owns

| Key | On | Value |
|---|---|---|
| `notes` | beat | list of links: the beat's notes |
| `beats` | session | ordered list of links: the session's plan |
| `date` | session | the session's date; sessions are ordered by it (ties by name) |
| `spent` | any note | the date it was spent; absent means unspent |

```yaml
---
notes: ["[[Ismark Kolyanovich]]", "[[Svalich Road]]", "[[Wolves]]", "[[Ravens watch]]"]
---
Dusk. The wolves come out of the treeline…
```

A note's track is the folder it lives in, so a beat carries no per-track keys and renaming a track rewrites nothing. Obsidian shows `notes` and `beats` as lists of links in Properties, and `date` and `spent` as dates.

### 3.5 Writing discipline

1. **Surgical.** Command changes only the keys above, appends to a session's log, and writes the notes it creates. Body text it didn't author is never rewritten; frontmatter round-trips with key order, quoting and comments preserved.
2. **Atomic.** Write a temp file in the same folder, then rename it over the original.
3. **Optimistic.** Every save carries the path and the content hash it was loaded from. If the file changed on disk since, the sidecar refuses (409) rather than overwriting, and the editor shows the conflict (§7).
4. **Deletes go to the OS trash**, through the `trash` crate Legend Lore already uses — never an unlink.
5. **Play state is not written.** The live set, the armed beat and launches live in the sidecar (§6.2). Only spends, the log and captured beats reach disk.
6. **Boards keep Obsidian's shape.** A session's board (§5.2) is written in Obsidian's own canvas layout: tab-indented, one node per line. Every node, edge and field Command didn't touch is kept, so a board Obsidian wrote comes back byte for byte.
   - A card names its note by path from the root, as Obsidian does with the root as its vault. A campaign-relative path (a vault opened on the campaign folder) also resolves.
   - Command's renames and moves rewrite these paths in every `.canvas` in the campaign, as they rewrite links.

### 3.6 The Library

*The folder was decided on 2026-10-11. The rules below are proposed and will be confirmed when phase 5 starts.*

Material the GM reuses across campaigns lives once, in `<root>/Library/`, instead of being copied into each campaign: a recurring NPC, a homebrew monster, house rules. The Electron app's Library held SRD reference copied into campaigns. Legend Lore covers rules reference now, so this Library holds the GM's own material.

- **Layout.** The name `Library/` is reserved. It is never a campaign, and no campaign can take the name. It holds tracks the way a campaign does, but no `Beats/` or `Sessions/`, because those belong to a campaign.
- **Links.** A campaign's `[[Name]]` resolves to the campaign's own note first, then to the Library's. So adding a note to the Library never changes what an existing link opens.
  - A campaign adapts a shared note by copying it in, with *Copy to campaign*. Its links then open the copy, and other campaigns keep the original.
  - Obsidian treats the root as one vault and has its own rule for duplicate names, so in Obsidian a shadowed name can open the other note.
- **Renames.** Renaming a Library note rewrites links in the Library and in every campaign that doesn't have its own note of that name.
- **Not spendable.** `spent` is a fact about one campaign's table, so Command never writes it to a Library note. To spend one, copy it into the campaign first. Launching a Library note is fine, because the live set isn't written to notes.
- **On screen.** The Library opens from the campaign menu as its own grid of tracks, with no launcher. In a campaign's grid, each column ends with a collapsed `library` group holding the Library notes of the same track, so arming works on them as on any note. The exact form will be decided in the app.

---

## 4. Sessions

A session owns two things: its **plan** (`beats`, in order) and its **log**. The rest of the table's state is on the notes themselves (`spent`), which is why notes need no carry-forward: a secret not yet revealed is just an unspent note in Secrets, still bright next session.

```markdown
---
date: 2026-10-18
beats: ["[[The mists close in]]", "[[Ambush on the road]]", "[[Tser Pool camp]]"]
---
Prep notes, reminders…

## Log
- 19:42 ▶ [[Ambush on the road]]
- 20:15 spent [[Ravens watch]]
- 20:22 the party insulted the burgomaster
- 20:31 captured [[Bildrath's shop]]
```

**Lifecycle**

1. **`[new session]`** creates `Sessions/Session N.md` — N one more than the highest number in an existing session's name; renameable afterwards — with `date` set to today, and makes it the active session (`src-tauri/src/app_context.rs`). Its plan starts with the previous session's planned beats that aren't spent, in their order. The previous session is the latest by `date`. Its board starts as a copy of the previous board, without the cards of spent notes and their connections. Renaming a session renames its board, and trashing a session trashes its board.
2. **Prep** edits the plan (add, remove, reorder beats) and the beats themselves. Beats in no plan stay in `Beats/` as potential scenes and can be pulled into one.
3. **Play** appends to the log as things happen: a beat launched (`▶`), a note spent or un-spent, an improvised beat captured, a one-line jot.
4. **There is no end-of-session state.** A session with a log has been played. The live set persists until something else is launched, so a session that stops on a cliffhanger resumes there.

Further rules:

- **Spending is manual by default, beats included:** launching a beat doesn't spend it. A setting, *spend beats on launch* (default off), makes a launch spend the beat. The UI says "spent" for every note, beats included: it's one word for one key (§10).
- **Command only ever appends to the log.** It writes under the last `## Log` heading, adding the heading at the end of the note if there is none. The Play arrangement parses lines shaped `- HH:MM <verb> [[Name]]`; a line the GM has edited into another shape shows as a jot.
- **The active session** defaults to the latest by `date` when a campaign opens.

---

## 5. Views

### 5.1 Prep

- **The grid.** One column per track, in campaign order, each listing **every** note in the track (subfolders as groups). The beat launcher column sits at the right: the active session's plan in order, then the unscheduled, unspent beats in `Beats/`.
- **Arming a beat** (Legend Lore's arm glyph and `E`) makes a click on a note toggle its membership in that beat — the same gesture as curating into an armed collection. Disarmed, a click selects the note for editing.
- **Marks.** Notes in the selected beat are lit; notes used anywhere in the session's plan carry a quieter mark; spent notes are dimmed with a check.
- **The editor** is a right-hand inspector on the vellum surface showing the selected note (§7), and `[close]` gives its width back to the grid. *Decided on 2026-10-11 in the app at 1280×800, over Live's bottom detail view, because notes are prose and need height more than width.*
- **Actions:** `[new note]` per column, `[new track]`, `[new beat]`, `[new session]`; rename, move to another track and delete (to the trash) from a note's context menu.
- *As built (phase 2):* selecting a beat also opens it in the editor (its `notes` list updates live as membership changes); a new beat lands armed and selected, as a new collection does in Legend Lore; a note started while a beat is armed lands in it; Escape disarms; the session switcher sits beside the campaign's in the bar. The inspector closes (`[close]`) and gives its width back, so with no note open all six default tracks and the launcher fit at 1280×800.

### 5.2 Play

- **The board** fills the centre. There is one per session, `Sessions/Session 13.canvas`, in JSON Canvas 1.0, so Obsidian Canvas opens it. It holds the session's notes (the union of its planned beats' notes) plus anything launched, as cards the GM moves, resizes and connects.
  - *Decided on 2026-10-12: one board per session, not a canvas per beat.* Launching lights cards where they are, as Live's Session View lights clips, instead of swapping the whole surface. A note in three beats is one card. Beats keep owning their notes, so the board holds only placement, size and connections, and can't disagree with a beat about membership.
- **Cards** render their note read-only on the vellum surface, and a card's size decides how much of the note shows. Each card has a spend check. A note never placed is auto-placed by track beside what the GM arranged, so a board nobody touched still reads; moving the card places it.
- **Connections** are lines between cards. They mean nothing to Command yet. *Decided on 2026-10-12. What following one could do, like Live's follow actions, comes later.*
- **At the table the board needs no handling.** Launching frames the live cards. Dragging and connecting are allowed but never required; arranging happens before the session, in Play with nothing launched.
- **Editing in Play.** Cards are read-only. A card's `[edit]` opens its note in the same right-hand editor as in Prep, closed until asked for, for a quick change mid-session such as Ismark turning hostile.
- **The arrangement** runs down one side: the session's plan with spent beats ticked, log entries interleaved at the times they happened, and captured beats inserted where they happened. It is the session as played, and the recap for next time.
- **Launching what isn't on the board.** Typing outside the editor opens a find line on the board, listing the campaign's matching notes. Launching one puts it on the board, auto-placed. This replaces the compact grid planned before the board, since the board already holds the session's notes.
- **A jot line** appends a timestamped line to the log.
- *As built (phase 3):*
  - **Layout.** The arrangement is a 14rem column on the left: the plan, each beat with its play key and the times the log says it was launched; then the log, newest at the bottom; then the jot line. The board fills the rest, and the note editor opens on the right as in Prep.
  - **Transport strip.** It floats over the board's top edge: an amber lamp, the beat the live set came from (or "improvised"), the count, then `[frame]`, `[capture]` and `[stop]`.
  - **Cards.** Each card's play key is Legend Lore's transport key, so it lights purple while the note plays, and the card itself takes the parchment rule and glow. Double-click or the card's menu opens the note in the editor, and its links open the note they name.
  - **Gestures.** Moving, resizing, connecting and deleting (Delete or Backspace, lines always, cards only when nothing would put them back) go out as board operations, drawn at once. The board opens framed on the live cards. A card whose note is gone shows dashed.
  - **Canvas extras.** Obsidian's text, link and group nodes render and can be moved. Arrowheads on Obsidian-made edges aren't drawn: Svelte Flow names markers after their colour, and a token colour (`var(…)`) inside `url(#…)` isn't safe in WebKit. Lines are lines for now.
  - **Attribution.** Svelte Flow's credit stays in the corner, quiet: its authors ask that only subscribers hide it.

### 5.3 Launching

- **Launching a beat** makes the live set exactly its notes, and logs it.
- **Launching a note** adds it to the live set; launching a live note again takes it out. This is improvising: it changes the live set only, never the beat the set came from.
- **`[capture]`** saves the live set as a new beat, named by the GM, inserted in the plan after the last launched beat, and logs it.
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
| Track identity | *open until Play is on screen (§10).* Tracks are plain nameplates. In Legend Lore a pigment gem marks a curated set, which here is a beat rather than a track. If tracks take a pigment, it is a strip on the nameplate |
| Note in the live set | parchment rule and `--glow-accent` on the card; its play key lit purple, as Legend Lore's transport |
| Prep / Play | a picker in Command's bar, Legend Lore's view-switch recipe: the current segment raised, never purple (one view is always on) |
| Armed beat | Legend Lore's arm glyph in `--text-active` |
| Spent | `--opacity-out-of-scope` plus a check; hover restores |
| Unresolved link, missing note | dashed parchment, `--outline-drop` |
| Actions | lowercase brackets: `[new beat]`, `[capture]` |

---

## 6. Architecture

Placement follows the architecture doc (D2, D4, D5, §4 Q4).

### 6.1 Sidecar — `sidecar/command/`

- **`router.py`** with `build_router(...)`, mounted in `server.py` beside Legend Lore's.
- **Settings** in `command_settings.json` in the data dir — the root folder and *spend beats on launch* — following `search_settings.json`.
- **Index:** *as built, no cache at all:* every read scans the campaign folder (tracks, notes with track and group, ambiguous names), and a rename scans the notes' text for links. A few hundred notes take a fraction of a second; a cache — in memory, then SQLite — only when a measurement asks for one. Phase 2 parses every note's frontmatter on each read, leniently — one broken block doesn't hide the campaign.
- **Watcher:** `watchfiles` on the root. Changes update the index and go out on the event stream. Command's own writes take the same path, so there is one way a change becomes visible.
- **Writer:** §3.5 — atomic writes, the hash check, link rewriting on rename. *As built (phase 2):* frontmatter is never re-serialised. `command/frontmatter.py` replaces only the lines of the one key it writes, then parses the result back (PyYAML) and refuses unless that key holds exactly what was written and every other key is unchanged. `ruamel.yaml` was dropped: it re-indents sequences document-wide, which touches keys Command doesn't own.
- **Event stream:** `GET /command/events`, server-sent events: `vault` (campaign, changed paths) and `live` (a snapshot with `seq`).

### 6.2 Live state

The live set lives in the sidecar, because MCP has to read it (D5): per campaign, `{seq, beat, notes}` — the launched beat, if any, and the notes now live. It is persisted to the data dir on every change, so a crash mid-session restores it. The armed beat and the selection are per-panel UI state, not live state.

The active campaign and session stay owned by Rust (`app_context.rs`, unchanged). Rust pushes them to the sidecar on every change and whenever the sidecar (re)starts, so MCP can answer "current session" with no window open.

### 6.3 Rust — `src-tauri/src/command.rs`

- Proxy commands over the routes, as `legend_lore.rs` does.
- **The event relay:** after boot, one task subscribes to `/command/events` (reusing `SseFrames` from `legend_lore.rs`) and re-emits `command://vault` and `command://live` to every window, reconnecting when the sidecar restarts.
- Deletes through `trash::delete`.

### 6.4 Frontend — `src/lib/command/`

- `CommandPanel.svelte` replaces the placeholder: the Prep/Play switch, taking `active` and `windowKey` per PANELS.md.
- The live set is a `rustMirror` (`command://live` plus a pull command); `vault` events refetch what they name. *As built:* not a `rustMirror`, which mirrors one global snapshot with no arguments, and live sets are per campaign. `CommandPanel` pulls the open campaign's set (`command_get_live`) on entering it and on a refresh, and keeps a `command://live` snapshot when it's that campaign's and its `seq` is newer.
- *As built, confirmed on 2026-10-11:* the campaign and session switchers sit in Command's own bar, not in shell chrome. The tab strip exists only in the main window, so a shell picker would leave a popped-out Command unable to switch. The campaign name opens a menu: other campaigns, new, rename, reveal, close, change folder, trash. The TEMP picker in `PanelHost.svelte` is gone; the active campaign itself still lives in `app_context.rs`.
- `<ConfirmDialog />` moved from Legend Lore's panel to the two window hosts (`PanelHost`, `StandaloneFrame`), one per window, so a popped-out Command can ask.
- The campaigns folder is chosen from Command's empty state and its campaign menu (`command_choose_root`, the native picker). A Command pane in `SettingsModal` waits for phase 3's *spend beats on launch*.

---

## 7. Editor

CodeMirror 6 on the raw Markdown source. The spike validated it; the Electron app's WYSIWYG round-trip was lossy, and fidelity to the user's file is the point. It is styled with the app's fonts (Almendra headings, Crimson body), has `[[` autocomplete over the campaign's note names, and shows frontmatter as source.

- Autosave is debounced and flushed on switching notes. A save carries the path and hash captured when the note loaded, never "whatever is selected now".
- On a `vault` event for the open note, a clean buffer reloads silently; a dirty one keeps the buffer and shows the conflict with `[reload]` and `[keep mine]`.

Play renders notes with `svelte-exmarkdown` (already a dependency) plus a wikilink plugin; a link opens its note in Prep.

---

## 8. Cross-tool (phase 4)

- **MCP tools** in `mcp_server.py`, over the Command routes (D5). A starting list: campaigns, current session (plan and log), live set (with note bodies), read note, find notes, create a note in a track, add to the live set, spend. The Servant gets exactly these.
- **Send to Command** from a Legend Lore hit creates a note in a chosen track: in the active campaign, or from phase 5 in the Library. The note holds the quoted text and a `source` pointing at the PDF and page; in Play, its card opens Legend Lore at that page. Routed through Rust (D4: no drag and drop across windows).

---

## 9. Phases

All on the `workstation` integration branch; Command ships when `workstation` is promoted (v4.0.0, architecture §6).

| # | Phase | Delivers | Verify |
|---|---|---|---|
| 0 | Dev data | `~/Unseen Servant` cleared of the Electron app's `Campaigns/` and `Library/` (moved aside, not deleted) | the root holds only campaigns — **done 2026-10-11**: moved to `~/Unseen Servant (Electron)/`, Misty Vale copied back as the dev fixture |
| 1 | Vault — **done 2026-10-11** | settings, scan and index, watcher, writer, event relay; the campaign picker; the Prep grid of tracks; the editor; create, rename, move and delete for notes, tracks and campaigns | pytest: scan, link resolution, rename rewriting, byte-preserving round trip, 409 on a stale hash. By hand, with the root open in Obsidian: an edit on either side shows up on the other; a rename in Command updates the links Obsidian shows |
| 2 | Beats and sessions — **done 2026-10-11** | `Beats/`, the launcher column, arming and membership, sessions, plan order, `[new session]` carry-forward, spent | pytest: carry-forward rules; `notes`, `beats` and `spent` round trips |
| 3 | Play — **done 2026-10-12** | the session board (read and write JSON Canvas, path rewriting, carry-forward; Svelte Flow surface with move, resize, connect, auto-place), live state and its persistence, launch, stop, capture, editing from a card, the arrangement, the log, jots, Tab between Prep and Play, *spend beats on launch* and the Command pane in settings | kill the app mid-session, relaunch, and the live set is back; the log reads correctly in Obsidian; a board arranged in Command opens in Obsidian Canvas, and one written by Obsidian round-trips byte for byte |
| 3b | Images | `![[map.png]]` embeds on cards: the asset protocol scoped at runtime to the campaigns folder, embeds resolved by name. The CSP already allows `asset:` images | a map embedded in a note shows on its card |
| 4 | Cross-tool | MCP tools, Send to Command, opening Legend Lore from a card | architecture Step 4: an MCP client lists Command's tools beside Legend Lore's; Send to Command round-trips a search hit |
| 5 | Library | `Library/` reserved, campaign-first resolution, the Library's grid and its group in campaign columns, *Copy to campaign*, renames across campaigns (§3.6) | pytest: resolution order and shadowing, a Library rename rewriting every campaign, `spent` refused on a Library note |

---

## 10. Decisions and open questions

Settled on 2026-10-11, before phase 3:

1. **Library:** a shared `Library/` folder at the root (§3.6). The alternatives were templates per track (still under not doing, §11) and treating Legend Lore as the library; Legend Lore stays the rules reference.
2. **Editor placement:** the right-hand inspector, closable (§5.1). Play opens a note in the same place for a quick edit, and cards stay read-only (§5.2).
3. **Images in Play:** a follow-up once the core Play loop works (phase 3b, §9), not part of phase 3.
4. **Wording:** "spent" everywhere, beats included: one word for one key.
5. **Prep and Play:** one panel, and Tab switches between them (§5.3). Two panels only if play at the table asks for them.
6. **Switchers:** the campaign and session switchers stay in Command's bar (§6.4).
7. **Play is a board** (2026-10-12): one per session, in JSON Canvas (§5.2). The GM moves, resizes and connects cards, Miro-style.
8. **Connections are lines** for now (§5.2). Giving them meaning in Play comes later.

Open:

1. **Track identity** (§5.4): whether tracks take a pigment, kept in `.unseen/command.json`. This will be decided once Play is on screen, by whether a beat's cards need telling apart by track at a glance.
2. **The Library's rules** (§3.6): proposed, to be confirmed when phase 5 starts.

---

## 11. Not doing

- Templates per track, initiative or HP tracking, a player-facing display, AI features inside Command (the Servant reaches Command through MCP).
- Importing the Electron app's `.unseen` beats.
- An Obsidian plugin: Obsidian is a peer editor of the same files, nothing more.

---

## 12. Related

- [2026-09-24-unseen-servant-workstation-architecture.md](2026-09-24-unseen-servant-workstation-architecture.md) — D2–D6 and §4 Q4, which this doc builds on.
- `src/lib/shell/PANELS.md` — the panel contract Command's UI follows.
