# Command images (2026-10-20)

**Status:** settled 2026-10-20 (§12). Steps 1–3 built 2026-10-20 (#407, images as clips, image tracks); step 4 to come. Extends [#407](https://github.com/Unseen-Servant/unseen-servant-app/issues/407), phase 3b of the [Command design](2026-10-11-command-design.md) (§9), and lifts two of its exclusions (§8).

## 0. TL;DR

Images become clips. An image file in a track or on the shelf is a campaign note of its own type, named by its file name with the extension (`Barovia.png`), as Obsidian links an attachment. Beats list it, Play launches it, and the board and the card tray show it, with no new key on disk. A track can be an image track, as Ableton has audio tracks beside MIDI ones. The kind is presentation, kept in `.unseen/command.json`, and a folder holding only images reads as one by default. Legend Lore's tree lists the library's images, and Send to Command copies one into the campaign.

---

## 1. Why

- **Maps and handouts** are what a GM most wants on the table (#407).
- **#407 shows images inside things:** embeds on a note's card, image nodes on a board. An image there can't join a beat, so launching a scene can't bring up its map.
- **A GM's library holds loose images** beside its PDFs: map packs, handouts, portraits. Legend Lore's tree lists only PDFs (`list_files` in `src-tauri/src/legend_lore.rs`), so the app can't reach them.

## 2. Rules

1. **Folders stay the only truth.** An image is a clip because it's a file in a track's folder. A track's kind never hides a file: a PNG in `NPCs/` shows in NPCs, and a note in `Maps/` shows in Maps.
2. **No new frontmatter.** A beat lists an image in `notes`, as `[[Barovia.png]]`, which Obsidian's Properties shows as a link.
3. **The campaign is the unit.** An image brought in from anywhere (Legend Lore, Finder, the picker) is copied into the campaign, never linked out.
4. **Images aren't spent.** An image has no frontmatter to hold `spent`, and a story fact can't go in `command.json`, which holds presentation only. The GM spends the beat that shows it, or the note the handout reveals.

---

## 3. The model

### 3.1 On disk

```
Curse of Strahd/
  .unseen/command.json             "kinds": {"Maps": "image"}
  Maps/                            an image track
    Barovia.png
    Castle Ravenloft/              a subfolder groups images, as it groups notes
      Ground floor.jpg
  NPCs/
    Ismark Kolyanovich.md
    Ismark portrait.png            an image on a note track: still a clip
  Shelf/
    Tarokka spread.webp
  Beats/
    Ambush on the road.md          notes: ["[[Svalich Road]]", "[[Barovia.png]]"]
```

- **Image types** are #407's: png, jpg/jpeg, gif, webp and svg.
- **Where an image is a clip:** under a track's folder or `Shelf/`, at any depth. An image loose in the campaign folder is listed under the shelf, as a loose note is. Images in `Beats/` and `Sessions/` are attachments only: embeds resolve them (#407), and no list shows them.
- **Its name** is the file name with the extension. Names are unique among the notes and compared case-insensitively, as a note's are (design §3.2). The extension rules out a clash with a note's name, so only two images named alike can clash.

### 3.2 The track's kind

- `command.json` gains `kinds`, `{track: "image" | "note"}`, beside `pigments`. A track rename carries its kind, as it carries its pigment (`rename_track`).
- **The default:** with no entry, a track whose folder holds images and no notes is an image track, and any other is a note track. A `Maps/` folder filled in Finder reads right with nothing saved, and an empty track is a note track until the GM says otherwise.
- **Choosing it:** the track's menu gains a *Kind* pick row above *Pigment*, with two picks: Notes and Images. A pick writes the entry. A new image track is `+ track`, then Images. *As built, revised the same day:* the kind is chosen when a track is inserted, as a Live track's is: `+ track` opens *Insert note track* (⌘T) and *Insert image track* (⇧⌘T), and a track's menu offers the same, inserting after that track; the keys insert after the selected note's track, else at the end. A track's kind isn't changed afterwards in the app, as a Live track's isn't. In an image track the menu's *New note* is *Add images…*.
- **What it changes:** what the column makes, not what it holds. An image track's empty row is `+ image` (§4); a note track's names a new note, as today.
- **Filing follows the kind** (2026-10-20): Command puts an image only in an image track and a note only in a note track, as Live keeps audio clips off MIDI tracks. A row's *Move to* lists the tracks of its kind, a dragged row lights only those columns, and the sidecar refuses a move, a new note or an added image that would mismatch, so MCP can't make one either. The shelf holds both, as Live's browser does. A mismatch made in Finder still shows, and moves within its own track.

*Rejected:*
- A kind that decides membership, so an image track lists only images. Files would go missing from the grid, the first failure of the earlier apps (design §1).
- Images as a kind apart from notes, with names of their own. A beat's `notes` resolve among the notes (design §3.3), so beats would have to resolve two kinds.
- A sidecar `.md` beside each image to hold `spent`. That puts two files where one is meant, and the extra note would show in the grid.

### 3.3 Beats, launching, the board

- **Membership:** with a beat armed, a click on an image row adds `[[Barovia.png]]` to its `notes`, as for any note. The image's lamp lights as a note's does, and the beat's count includes it, since the count is what the beat lights.
- **Launching:** the live set holds `Maps/Barovia.png` as it holds a note's path (`live.py` is unchanged). The image's board card lights, and it joins the tray.
- **The board:** an image card is a JSON Canvas `file` node naming the image by its path from the root, which is what Obsidian writes when an image is dropped on a canvas (#407 step 4). A session's board shows its planned beats' images as it shows their notes, auto-placed.
- **Renames, moves, trash:** Command renames, moves and trashes images as it does notes. A rename keeps the extension: the field edits the stem, as Legend Lore's file rename does. It rewrites the `[[links]]` and `![[embeds]]` that name the image, and every `.canvas` path, keeping the extension.

---

## 4. Prep

- **Rows:** a note row's height, lamp and states. The name shows with its extension, the extension one step down the text ramp, so an image reads as one in a note track without a glyph.
- **No spend:** an image row has no spend key, A does nothing on it, and its menu has no *Mark spent*.
- **The inspector:** a selected image opens under the inspector plate: track, group › name as the rename field, `[close]`. Below the plate, the image is fitted to the panel's width on the vellum. There's no `[read]`/`[edit]` and no save state.
- **Adding images:**
  - An image track's empty row is `+ image`. A click opens the native picker (images only, several at once) and copies the files into the track, numbering any clash.
  - Images dropped from Finder on an image track's column are copied into it, and on the shelf onto the shelf (2026-10-20); a note track's column takes none. Added images, picked or dropped, join the armed beat if there is one, as a note started then does.
  - Send to Command from Legend Lore (§6), and #407's drop from Finder onto the board.
- **The shelf sidebar** lists its images. *Copy from* lists another campaign's images, and a place's, and copies their bytes onto the shelf, as it copies notes.

## 5. Play

- **The image card:** a note card's head (the name, the track's pigment, the play key; no spend key, no source key) over the image, fitted inside the card and letterboxed on the vellum.
- **Its size:** the default card's (260×180), wherever it's placed: by the app, the sidecar's `settle` and `arrange`, or MCP. The GM resizes it.
- **The menu:** *Show image* opens it in the inspector; *Play* and *Remove from board* are as for any card.
- **The tray:** an image's face at the tray's reading width. Picking it lays it out as any card.
- **The Note tool (D):** its completion lists images too.

## 6. Legend Lore

- **The tree lists images.** `list_files` keeps image types beside PDFs and marks them, with `is_image` on `FileItem` in Rust and in `types.ts`. The `/` filter finds them by name.
- **An image row** is a file row with:
  - Font Awesome's `image` glyph where the book is;
  - an empty slot where the checkbox is, as a file row keeps a slot for the caret;
  - no S/M keys and no grab, since index, scope and collections are the PDFs';
  - never dimmed out of scope (`isRowOutOfScope` already asks for indexed material).
- **Opening:** a double-click opens it in the system viewer, as a PDF opens.
- **Its menu** keeps what acts on the file itself, and adds Send to Command. Indexing, stats, collections and system tags don't show.
- **Send to Command** is a hit's submenu: Shelf, then the open campaign's tracks. Rust's `command_send_image(track, path)` asks the sidecar's `POST /send-image`, which copies the file (image types only, numbered on a clash with `free_name`) and answers with its path. Command hears of it from the watcher.
- **No thumbnails** in the tree, so the asset protocol's scope stays the campaigns folder, and the library is never served to the webview.
- **Hide images**, a row in the filter panel's *Hidden items* section after *Hide out-of-scope items*, takes them out of the tree, for a library whose token packs would bury the books. It's a lens checkbox like its neighbours:
  - Off by default, so images show.
  - Kept in the panel's store as `hideImages`, beside `hideUnindexed`.
  - It lights the section's lamp while folded, and the panel's reset clears it.
  - It's a row for J/K (`view:hideImages` in `filterRows.ts`).
  - A folder holding only images hides with them.
- ***Hide unindexed items* leaves images alone.** An image is never indexed, so that switch would otherwise hide every one. It goes on meaning books the library knows nothing about, and *Hide images* alone hides images. A folder holding images stays while they show.

## 7. MCP

Nothing new:

- The tools that take a note by name take an image by name: `create_beat`, `add_to_beat`, `add_to_live_set`, `move_note`, `frame_cards` and `connect_cards`.
- `campaign_overview` lists images under their tracks.
- `read_note`, `edit_note` and `spend` refuse an image, saying it's an image.
- `live_set` lists a live image by name, with no text.
- `find_notes` matches images by name only.

## 8. Changes to #407

- **Lifted from its "Not in this issue":** listing images in the shelf sidebar. Also its line that Command "still doesn't rename or delete images itself".
- **Kept:** its index of the campaign's images "wherever they sit". Embeds resolve against all of them; clips are the ones in tracks and on the shelf (§3.1).
- **Still out:** thumbnails or a cache, images in the Prep editor's source, PDF embeds.

## 9. Sidecar

- **`vault.py`:**
  - `_is_image_file`. The walk behind `scan` yields notes and images, and `NoteEntry` gains `type` (`"note"` | `"image"`). An image's name keeps its extension, where `_stem` drops `.md`.
  - `note_path` accepts images; what reads text checks the type.
  - `rename_note` keeps an image's extension. `_retarget` and `_relocate` carry any extension, and `_relocate` moves images as well as notes, so a track rename carries them.
  - `track_kinds` and `save_track_kind` beside the pigments' pair, and `rename_track` carries the kind.
  - Copying image bytes, for the picker, Send to Command, *Copy from* and #407's Finder drop.
- **`board.py`:** `note_of` accepts images.
- **`router.py`:** `POST /send-image`, `POST /images` (the picker's files, and #407's drop), and the track kind's route beside the pigment's.
- **`spend`** refuses an image.
- **Tests:**
  - The scan's types and names.
  - The inferred and stored kinds, and a kind following a rename.
  - An image's rename keeping its extension and rewriting links, embeds and canvas paths.
  - A track rename carrying its images.
  - Send-image's copy and numbering.
  - `spend` refused on an image.

## 10. Order of work

1. **#407 as written:** the asset protocol scoped to the campaigns folder, the image index, embeds, image nodes, renames carrying images, and the drop from Finder onto the board.
2. **Images as clips:** the vault (§3.1, §3.3, §9), Prep's rows and the inspector's image view, beats and launching, the board's and the tray's image face, spend refused, MCP (§7).
3. **Image tracks:** `kinds`, the menu's *Kind* row, `+ image` and the picker.
4. **Legend Lore:** image rows in the tree, *Hide images*, and Send to Command.

Each step updates the Command design (§3, §5), Help → Guides (Command, and Legend Lore for step 4) and the CHANGELOG.

## 11. Not doing, or not yet

- **Not yet:**
  - Maps inside PDFs: a page's embedded image, or the page rendered, through PyMuPDF. Passed on 2026-10-20 (§12).
  - Sizing a card to its image.
  - Thumbnails in the grid's rows or the tree.
  - A player-facing display (design §11).
- **Not doing:**
  - Spending images (rule 4).
  - Images linked from outside the campaign (rule 3).

## 12. Settled (2026-10-20)

1. **Images aren't spendable** (rule 4).
2. **A track's kind** is stored in `.unseen/command.json`, with a default inferred from the folder (§3.2).
3. **Maps inside PDFs** wait (§11).
4. **Legend Lore's filter panel gets *Hide images*** (§6), off by default, rather than waiting on a count of the real library's images.
