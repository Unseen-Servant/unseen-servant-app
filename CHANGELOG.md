# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed

- **Cards stand over the board.** In Play, a right-click on a card in the card tray or on the board shows it in the middle of the dimmed board, in place of its menu; a click on the board puts it back
- **Tray cards move by drag.** In Play, a drag along the card tray puts a card in a different place in the live set
- **Cards answer with the hand tool.** On the board, with the hand tool, a note or image card still plays, opens and stands; a drag still pans and moves nothing

## [4.3.0] - 2026-10-25

Legend Lore no longer deletes library files: it removes books from the index and leaves the files on disk. Users do not need to index their books again.

### Changed

- **Legend Lore does not delete files.** _Remove from index_ (`⌘⌫`) replaces _Delete file_ and _Delete folder_: the book leaves the index and its collections, and the file stays on disk

## [4.2.0] - 2026-10-24

Search now works without other software. The app contains the search models and the program that runs them, so users do not install Ollama or download a model. The licence changes to the GNU AGPL 3.0 or later. Users do not need to index their books again.

### Changed

- **Search does not need Ollama.** The app runs the bge-m3 model itself, and existing indexes stay valid
- **The reranker is in the app.** Search uses it from the first launch, without a download
- **The licence is the GNU AGPL 3.0 or later.** Help → About opens the licence file in the app, not the old licence page on the website
- **The acknowledgements are in the app.** A new row in Help → About opens the list of components the app uses, with their licences

## [4.1.0] - 2026-10-21

This release adds images, a toolbar for the Play board, a card tray, keys for every list in Command, and sixteen MCP tools that let an AI agent prepare a session. Help is in the status bar again. Legend Lore now reports problems (Ollama not running, a scanned PDF, a slow sidecar start) instead of failing without a message. Users do not need to index their books again.

### Added

- **Images on the board.** A note's embedded images (`![[map.png]]`, `|300` sets a width) show on its card in Play and in the inspector. An image dropped from Finder on a board is copied into the campaign's `Shelf/` folder, so the campaign keeps every file it uses
- **Images in tracks and beats.** An image in a track or on the shelf shows in Prep beside the notes. A beat can hold an image, and its card shows the picture on the board and in the tray. Images rename, move and copy like notes, but cannot be spent. An AI agent can find images by name and put them in beats
- **Image tracks.** A track holds images or notes, not both; the shelf holds both. _Insert image track_ (`⇧⌘T`) and _Insert note track_ (`⌘T`) add tracks. A double-click on the empty row, or a drop from Finder, adds pictures. A folder of images made in Finder becomes an image track
- **New campaigns start with a Maps image track**, after the checklist's note tracks. In older campaigns, the checklist tracks stay note tracks
- **The Legend Lore tree shows the library's images.** Maps and handouts show with a picture glyph and are not indexed. _Send to Command_ copies an image to the shelf or to an image track. _Hide images_, under _Hidden items_ in the filters, removes them from the tree
- **A card tray under the Play board** shows the live set as cards that stay readable at any board zoom. `[spread]` shows the selected cards side by side, and `[gather]` puts them back. `⌘B` folds the tray and the session player
- **Help is in the status bar.** The help key, and Help → Unseen Servant Help on macOS, open Help → Guides. Guides adds _Using Command_ and _Servant_ (the AI agent setup). A new _Troubleshooting_ page lists each problem, the messages the app shows for it, and the fix. Reference adds a glossary. With no library folder, Legend Lore shows an empty console with a `[choose library folder]` key, not a first-run page
- **The shelf copies from other folders.** _Copy from_ lists the other campaigns, then folders outside the campaigns folder that the user adds. These folders belong to the machine, not to a campaign
- **Command's lists use the same keys as Legend Lore's rows.** The arrows (or `H`/`J`/`K`/`L`) move the selection, `↵` or `⌘O` opens it, `E` arms a beat, `X` puts a note in the armed beat, `A` spends, and `⌘⌫` moves to the Trash. In Play, `⇧Space` launches the next beat, and `P` or `Space` stops the live beat. The shortcut sheet lists all keys
- **The app-wide shortcuts work in Command.** `⌘K`, `⌘,`, `⌘1`–`9`, `⌘R`, `⌘S`, `⌘F`, `⌘N` and `B` work when Command has the keyboard. At the edge of a tool, `⌘⌥` with an arrow moves to the next tool
- **One shortcut sheet** (`?`, `⌘/`) per window, grouped by place. Shortcuts that do not work from the current place show in dimmer text

### Changed

- **`campaign_overview` replaces `list_campaigns`.** The agent gets the campaigns and the open campaign's tracks, notes, shelf, beats and sessions in one call. A refused request now gives only the reason
- **An AI agent can edit a note.** `edit_note` replaces a note's text and keeps its frontmatter. It does not overwrite changes that the user made after the agent read the note
- **An AI agent can make beats.** `create_beat` makes a beat from existing notes and can add it to a session's plan. `add_to_beat` adds a note to a beat or removes it
- **An AI agent can plan sessions.** `create_session` starts the next session, `set_active_session` opens a session, and `plan_beat` adds, moves or removes a beat in a plan. `current_session` reads any session by name
- **A beat can have the same name as a note.** A name must be unique only among notes, among beats and among sessions. Where names are shared, Command links the note by its path (`[[Locations/Svalich Road]]`), so Obsidian opens the correct file
- **The Play board has a toolbar.** It adds notes (`D`), text cards (`T`), stickies (`N`), frames (`F`, or `⌘G` around a selection), lines (`L`) and a pan hand (`H`). `⌘Z` undoes board changes, and a bar over the selection sets colours and arrowheads. The board is saved in Obsidian Canvas format
- **The board shows arrowheads**, also on lines drawn in Obsidian
- **A board can be arranged by beat.** A key at the bottom of the toolbar gives each planned beat a frame with its notes, in plan order. Notes that several beats share go in a frame named Throughout. Launching a beat shows its frame
- **An AI agent can arrange a board.** `arrange_board` frames the planned beats, `frame_cards` puts notes in a frame, `connect_cards` draws a line between two cards, and `add_text` adds a text card. Cards that the user placed do not move
- **An AI agent can file notes.** `create_track` makes a track, and `move_note` moves a note to a track or the shelf. `find_notes` shows note text without frontmatter and tells when it shows only the first 20
- **Notes from an AI agent cite their book.** `create_note` takes a search result's id, and the note cites the book and PDF pages, so its card opens the book at that page
- **Lists end on an empty row.** The session planner and Legend Lore's collections end on a blank row, as tracks do. A double-click or `R` on that row names a new beat or collection. A click selects a collection row, and a second click opens its books
- **The keyboard focus shows on the tool's frame.** The frame of the tool that has the keyboard is one grey lighter. The rack bar no longer raises that tool's key
- **The lock belongs to the view.** One lock beside the view picker keeps the view's tools in place. It replaces the lock key of each tool
- **The campaigns folder has its own Settings section**, set like the library folder
- **Some shortcuts changed after a review.** `⇧⌘J` opens the session note and `⌘J` goes to the jot bar, so `⌘O` always means open. `G`, `⌘⇧O`, `⌥⌘R`, `⌘⇧.` and `C` are removed; their menu items stay. `⌘S` and `⌘F` do not work in the note editor
- **The MCP server is named Unseen Servant.** The copied config entry is _Unseen Servant_. Old entries continue to work, and the new entry replaces the old one

### Removed

- **The session log.** Launching a beat or spending a note no longer writes a line under `## Log`. Old lines stay in the notes as text. The jot bar still writes to the session note, at the end

### Fixed

- **Legend Lore with Ollama not running or without bge-m3.** Search names the missing model instead of a server error. A sync checks the embedder first, so it fails at once instead of after minutes. A stopped sidecar shows as _SIDECAR · NOT RUNNING_
- **A scanned PDF** with no text is unticked after it fails, so the app does not offer it again at each check
- **Cancelling the library folder dialog** no longer shows an error
- **The sidecar has one minute to start.** If it crashes, the app shows the end of its log instead of staying offline for the session
- **The sidecar stops with the app.** After a crash or a force quit, it no longer keeps the library store open
- **The reranker model is in the data folder.** It was in the system temp folder, which macOS empties, and search then ran without ranking. The first launch after this update downloads the model again (about 23 MB). A failed load shows on the lamp
- **Moving a card on the Play board moves only that card**
- **Returning to Play with Tab shows the board at once**
- **The drag image** follows the pointer and does not wrap its text
- **Tab switches the tree and systems views** also with no library folder

## [4.0.0] - 2026-10-17

Unseen Servant is now a workstation with two tools. Command, a new tool to prepare and run sessions, joins Legend Lore, and both tools share one window, the rack. Libraries, indexes and collections stay as they are. Users do not need to index their books again.

### Added

- **Command, a tool to prepare and run sessions.** A campaign is a folder of Markdown notes. Tracks are kinds of material (PCs, Secrets, Locations, NPCs, Monsters, Traps and Treasures by default), notes are the material, beats are scenes that use notes from any track, and a session plans beats. All files are in `~/Unseen Servant` (Settings → Command changes the folder), so Obsidian can open and edit the same campaign
- **Prep** shows one column per track beside the session planner. A user arms a beat and clicks notes to add them, and can drag notes, beats and tracks. Each track can have a pigment. The inspector edits a note's Markdown with `[[` completion, or shows it rendered (`⌘E`)
- **Play** shows a board for each session, saved as JSON Canvas, so Obsidian Canvas opens it. The session player launches beats (`J`/`K` to step, `P` or `Space` to launch or stop) and frames their cards. A jot bar writes to the session note (`⌘O` opens it)
- **Notes and beats can be spent.** A note or beat is marked spent (`A`) when a secret is revealed, a treasure given or an NPC dies. Spent notes dim and fold at the bottom of their track, and unspent notes stay for the next session. A setting spends a beat when it launches (off by default)
- **Each campaign has a shelf** (`⌘B`) for material that is not yet on a track. Notes can be copied to it from another campaign
- **Send to Command** from a search result puts the section's text in a note on the shelf or a track, with a citation of the book and printed page. The note's source key opens the PDF at that page
- **Campaigns open as they were left.** Command opens the last campaign, or a blank _Untitled_ campaign that is removed if it stays empty. The campaign key switches, renames and deletes campaigns. On macOS, the File menu has New Campaign (`⇧⌘N`) and Open Campaign
- **An AI agent can follow the session.** The MCP server adds eight Command tools: list campaigns, read the current session and the live set, read and find notes, create a note, add to the live set, and mark spent
- **A tool can open in its own window** with the key beside its header, and dock back the same way

### Changed

- **One window, the rack, holds the tools.** It has eight views, selected with `1`–`8` or the keys in its bar. A tool's key adds it to the view; slots split, swap and resize. A view can lock its tools. At first launch, Legend Lore is in view 1 and Command in view 2
- **The rack bar is the title bar** on macOS. The status bar under the rack serves all tools
- **The window opens maximized** and does not remember its last size
- **Nine new pigments** for collections and tracks: Kermes, Madder, Realgar, Ochre, Malachite, Azurite, Lapis, Orchil and Murex. Existing collections change to the nearest new pigment
- **All renames work the same way.** Enter or a click outside keeps the new name, and `Esc` cancels. If the name is not valid, the field stays open and shows the reason
- Selected text and the caret are parchment
- Rows drag without a grip
- All list rows and panel plates have the same height in both tools
- Horizontal scrollbars are as thin as vertical scrollbars

### Fixed

- Clicks in a rename field stay in the field
- Renaming a book to an empty name or to its own name does not change it
- A book or folder can be renamed with only a change of letter case
- A collection with `?`, `#`, `%` or `/` in its name can be renamed
- A renamed book keeps its collection gems
- A renamed collection keeps its ring and stays open

## [3.1.2] - 2026-10-03

### Changed

- **Enter moves to the results.** After a search, focus goes to the first result; with no results, it stays in the search bar. `Esc` in the results leaves search, and `⌘K` goes back to the search bar and selects the query
- **A row shows all its collections**, up to five gems, instead of one gem and a `+N`

## [3.1.1] - 2026-10-01

### Fixed

- **The macOS app starts its indexer again.** In 3.1.0, the sidecar stopped at launch, so search and indexing did not work. Users who update from 3.0 must index their library again (see 3.1.0)

## [3.1.0] - 2026-09-30

Users must index their library again after this update. The index moves to a new store, and the app removes the old store at first start, so search returns no results until the books are indexed again. Library settings shows each file that needs it. PDFs, collections and game-system settings do not change.

### Added

- **`@` in the search bar selects a collection.** The Collections panel shows the matches. `↵` plays the collection alone, and `⇧↵` adds it to the mix. The `@` word is not searched, so the scope and the question go in one line
- **`⌘1`–`⌘9` play a collection from anywhere**, in the panel's order. `⌘⇧1`–`⌘⇧9` add it to the mix or remove it
- **A book can be found by name.** A search that starts with `/` filters the tree or systems view to books and folders whose names contain all the words
- **The inspector's scrollbar marks the query.** Ticks show where the query's words are, and a mark shows the matched passage. A click on the mark, or `G` in the results, scrolls back to it
- **Filter panel sections fold.** A folded section with an active solo, mute or view switch shows a lamp
- A "Dim weak matches" setting under General → Search results (on by default)
- An embedder lamp in the status bar. It is lit when the model is ready, and dim when the runtime answers but the model is missing
- More keys: `↵` opens a file or folds a folder in every list, `⇧X` ticks a range, `⌥↑`/`⌥↓` go to the first or last row on a Mac, and `⌘/` opens the shortcut sheet from the search bar

### Changed

- **The index is one file.** Books, sections, text, embeddings and the keyword index are in one SQLite file. Each change to a book is saved in one step, so an interrupted operation cannot leave the index inconsistent
- **Removing a book frees disk space at once.** The Compact button is removed because it is not necessary
- **Search in a collection or game system is faster**, and stays fast as the library grows. It reads only the selected books
- Renaming or moving a file or folder, and changing a book's game-system tags, are instant
- The app is smaller: the sidecar no longer includes ChromaDB
- **A game system name in a search no longer changes what the search means.** Before, "dragonbane fireball" ranked Dragonbane's Dragon monster first. Now a system name only puts that system's books first
- **Search while typing completes the last word.** It used to correct an unfinished word to a different word ("grapp" to "grasp"). Now it completes the word from the user's books ("grapp" to "grapple"). Enter searches the exact text
- **Indexing progress shows the book.** The status bar shows "Indexing 4 of 12 · Player's Handbook" and a meter for long books, and the summary counts books. Failed books stay in the list until the user dismisses them, with the reason on hover
- **A splash shows the app's start.** It has a lamp for each part: settings, sidecar, library store, embedder, reranker, spelling vocabulary and library folder. If a part fails, the splash names it, then the tools open. The splash closes by itself
- **Collections show a gem instead of a ribbon.** The `Ribbon` submenu is now `Gem`. Loose shows a dashed outline
- **Tab switches between the tree and systems view.** `⌘1`/`⌘2` now play collections. `⇧←` or `⇧H` collapses the tree
- **Results show the matched section first.** Each card names its book and system, cites the printed page and highlights the query's words. Book names do not show `.pdf`
- **The inspector is easier to read.** The section path and `[open p.N]` stay at the top, the query's words are highlighted, lines have a readable length, and a rule in the margin marks the matched passage
- **Fewer wrong section headings.** Quote attributions, stat lines ("Ferocity: 2 Size: Small") and sentences are no longer headings. This changes bestiaries and OSR books most (about a third of the passages in the Dragonbane Bestiary and Wight-Box)
- **The search view waits for a query.** `⌘K` or an `@` selection does not hide the tree; results replace it at the first keystroke
- **The sync prompt shows what changed**, for example "2 moved, 1 missing on disk, 3 to add". Its action is `[sync]`
- The Collections and Filters keys show a lamp when something in their panel is active, also when the panel is closed
- The collections panel ends with an empty "New collection" row. A click or `⌘N` names a collection there. A click on a collection row opens its books
- Game systems show a shield instead of a die. Collections have six new pigments that are different from the interface colours, and existing collections change to the nearest new pigment
- The status bar counts "books", not "PDFs indexed"

### Fixed

- Two PDFs with the same file name in different folders no longer share game-system tags, and the status bar counts them as two books
- A damaged collections, manifest or custom game-systems file no longer stops the sidecar. The app moves it to `<name>.corrupt-<timestamp>` and starts with an empty file. After a manifest is moved, the next sync indexes again
- When the embedder is not running, search, sync and the agent say "Embedder not running" instead of "[Errno 61] Connection refused"
- A sync that the sidecar refuses shows the reason instead of "Sync completed but no result received"
- Result rows cite the printed page, as the inspector does
- Renaming a folder keeps it expanded, focused and hidden
- A shift-click or `⇧X` range ticks only the rows that the tree shows
- A right-click on another row while a context menu is open opens a new menu for that row
- Deeply nested folders no longer move further right at each level
- When the arrow keys move the cursor, the row under a still pointer no longer highlights
- On Windows, paths use `/` separators, which folder selection, hidden folders and folder rename or delete need

## [3.0.0] - 2026-09-24

The app is now named Unseen Servant, and Legend Lore is its PDF search tool. At first launch, the app moves the index and settings to the new data folder. Users must set up MCP again in Getting Started, so that the AI agent finds the renamed app.

Search is rebuilt, and users must index their library again after this update. Library settings lists the files indexed with the old pipeline. These files work until they are indexed again, but without whole sections, keyword search or printed page numbers.

### Added

- **Keyword search, on by default.** Exact terms now match together with meaning, so rare names, stat codes and game terms find their page when the embedding does not. The setting is no longer experimental
- **Results are whole sections.** A result is the full section, not a 1,000-character piece, so a stat block, spell or table is one result. A section shows only once in the list
- **Editions show as one result.** When the same passage is in several books (for example the SRD 5.1 and 5.2.1), the app shows one result with a `+1 edition` chip. The inspector lists the other books under "also in"
- **The inspector goes to the match.** It highlights the matched passage and scrolls to it. Markdown tables show as tables
- **Citations use the printed page number.** Results and the agent's citations show the number printed on the page first, and the PDF page beside it
- **Two new tools for AI agents.** `get_section` gets a whole section by id, and `get_pages` reads a page range from a book
- Year Zero Engine, The Black Hack and Cairn are added to the default game systems

### Changed

- **Search is about three times faster.** A quantised reranker reduces a typical query from more than one second to about a third of a second. The new model (about 23 MB) downloads once, at the first start
- **A game system name puts its books first.** "grapple dnd 5e" shows D&D 5e books first, then the other results
- **Fewer results show as strong matches.** The relevance tiers are calibrated on results that people judged. About a quarter of results are "strong" now, down from more than half
- **Section titles are clean.** Headings no longer contain markup, spaced small caps ("S P E L L S") or page footers. This also improves search
- **Spell correction uses the nearby words.** It selects the correction that fits the words around the typo, in the user's books and in common English, with a third to a half fewer wrong corrections. Game-system names are not corrected ("dnd" no longer becomes "and")
- **Search results for AI agents are short.** `search_library` returns 8 results with a short passage and a link to the full section, which suits local models. `full_text=True` returns whole sections, up to 8,000 characters
- The first search after the app is idle is no longer slow

### Fixed

- If the connection to the embedding model drops during indexing, the app tries again instead of stopping the book. Large books such as OSRIC had this problem
- A result's page range shows only the pages that contain its text

## [2.3.0] - 2026-08-14

### Changed

- **`[clear all]` is now `[reset]`.** It resets the whole filter panel: all solos and mutes, the focus lens, show-hidden and hide-unindexed. It is dim when nothing is active. Files hidden by hand stay hidden
- **Search is `⌘K`, and the Filters panel is `⌘F`.** `⌘⇧F` is removed
- **Search results work like other rows.** A result can be dragged to a collection, opens the same context menu, can be filed while a collection is armed, and uses the row keys. Results cannot be renamed
- **The dock keeps the keyboard during search.** Search and the dock share the keyboard, and the `⌘⌥` chords move between them
- **One Collection submenu.** Add and Remove are now one submenu, with a mark for all, some or none. `C` opens it, and it stays open, so a book can be filed into several collections at once. Get info is next to Open and Reveal, Re-index is next to Rename, and Delete has its own section
- **Pigment is now Ribbon**, the name of the mark on the row. Menu items name their objects the same way
- Game system labels in menus use the primary text colour instead of parchment
- A click on a filter row focuses it
- A collection's expanded file rows work with the keyboard: `j`/`k` move, `⌘⌫` removes, `⌘O` opens and `←` goes back to the collection
- **All confirmations use the app's dialog.** Deleting a file or folder and re-indexing a file no longer show a system dialog
- Deleting a custom game system, and resetting a changed built-in system, now ask for confirmation
- **Red is only for destructive actions.** Cancel and Discard no longer turn red on hover. The Danger Zone shows a tint when armed, not solid red
- **Dialog actions are bracketed text**, for example `[Cancel]` and `[Delete]`
- The Game Systems editor's footer uses one button style
- Dialogs fade in, except when the system asks for reduced motion. The close × is lighter, and all dialogs use the same widths and padding
- The shortcut sheet brackets single-key shortcuts, for example `[R]` and `[X]`
- A file's Info dialog shows the file name as its title and the full path below it. The game system is on its own line
- **A tap latches and a hold is momentary.** Holding `S`, `M` or `P` applies it only while the key is down. A tap latches, as before
- **`B` bypasses the scope.** All indexed files are in scope while it is on, and the filters stay as they are. A hold is momentary and a tap latches. A `BYPASS` lamp shows in the status bar. It resets at each launch
- **The scope bar always shows.** It has a `Scope` nameplate, the `B` switch and, when nothing is narrowed, the number of files that a search uses
- Solo and mute switches flash once when they engage
- **Each row in the systems view has solo and mute switches.** `S`/`M` act on the file and `⇧S`/`⇧M` on the system. Books without a game system can now be soloed
- **A muted book dims in the systems view**, in every system that lists it. Soloing a file dims the other files. The focus lens hides out-of-scope rows
- **The systems view's switches always show**, in tertiary colour, and highlight on hover. Rows no longer move when counts change

### Fixed

- A hidden file shown with "Show hidden items" no longer fades almost completely in the systems view when it is also out of scope
- **Bypass removes all scope dims.** While `B` is on, the systems view no longer dims or hides muted and non-soloed groups
- The scope bar's `hidden shown`, `indexed only` and `lens on` chips no longer dim during bypass
- `B` with no active scope no longer lights the `BYPASS` lamp
- When soloed items have no files in common, the app says "Nothing under the soloed items." instead of a generic message
- The hits meter no longer says that its count comes from the scope during bypass
- Enter no longer confirms a destructive prompt when Cancel has focus. These prompts open on Cancel, and the focus ring now shows
- Opening a search result opens the correct book. Results matched files by name, so two books with the same name could open the wrong one. They now match by path
- The collections list no longer changes order between reads
- The scope bar no longer grows when its first chip shows
- Filter, tree and systems rows no longer stay highlighted after the pointer leaves

## [2.2.0] - 2026-08-11

### Added

- **Arm a collection.** Each collection row has a record-arm key (●). When a collection is armed, a click on a book in the tree files or unfiles it, and ticking a folder files all its indexed books. `E` arms and disarms, and `Esc` leaves
- **Drag books and folders to a collection**, from the tree or the systems view. A drop on "+ New collection…" makes a new collection named after the dragged item
- File rows in the tree and systems view show their collections as pigment ribbons, up to two and a `+N`
- An × on hover removes a book from a collection in the panel's file list
- Each collection row shows its file count
- Play and Mute are in the collection's context menu
- `⌘⌫` (`Del` on other systems) deletes the focused row in the file tree and the collections panel

### Changed

- **New collections are named in the "+ New collection…" box.** The box becomes the name field, and the collection is created, focused and armed when the name is committed. `Esc` cancels, and nothing is created
- Editing a collection's files no longer uses the context menu, and search and the other panels stay usable during curation
- Collection changes are saved in batches and in order. A failed save goes back to the last saved state
- **Row keys are the same in all panes.** `R` renames and `X` ticks the checkbox
- **A tree row has one checkbox.** When no collection is armed, it marks the file for indexing (parchment). When a collection is armed, it files the file in that collection (purple). Rows with no indexed files show a disabled box while a collection is armed
- **Search no longer blocks the sidecar.** Each search runs on a separate thread, up to four at a time, so other requests answer at once
- The embedding model stays loaded: the app embeds one token every four minutes, so the first search after a pause is not slow. `OLLAMA_KEEPALIVE_INTERVAL_SECONDS=0` turns it off
- The window opens at 940×600 and remembers its size, also across displays
- The status bar is on the header plate, and the search bar is set into the panel
- The empty search bar shows its shortcut, and the view switch marks the view to go back to
- The Loose curation row shows a dashed ribbon

### Removed

- `Space` and `Enter` as row actions in the file tree, systems view and filter panel, and `Enter` in the collections panel. `Space` still plays or stops a collection, and `Enter` still submits a search, opens a result, selects a menu item and commits a text field. `R` renames, `X` ticks, `⌘O` opens and `→`/`←` move through folders
- `⌘↵` (save collection), because there is nothing to save
- `F2` to rename; `R` renames in all panes

### Fixed

- Systems view: a game system's "select all" checkbox now clears when the last file is unticked
- Creating a collection no longer switches the main pane to the systems view permanently
- A trackpad flick no longer moves the whole app and shows a dark band at the window edge
- The filter panel's lens checkboxes are purple again, not parchment
- The search bar's clear button shows × in the app's font

## [2.1.0] - 2026-08-09

### Added

- Relevance tiers: results show **strong / good / weak** instead of a "% match", and weak matches below a limit are dimmed
- Tables are split into one embedding unit per row, so a search finds the exact row of a spell or equipment table. A check flags tables that do not parse fully
- Spell correction: misspelled words in a query are corrected from the library's own words ("owlber" to "owlbear") before the search, and the results show the correction
- A game system named in the query ("fireball in 5e") moves that system's results up without hiding the others
- A check at startup finds Ollama embeddings that are cut short and writes a warning in the sidecar log
- A General settings tab with search settings, including the size of the candidate pool, from Fastest (10) to Exhaustive (200)
- Solo, mute and play for scope: a filter console with solo and mute, play and stop on collections, archive for collections not in use, and a focus lens that hides out-of-scope items
- A scope bar with system and collection chips, above the tree and systems views
- Solo, mute, play and lens settings are kept across launches
- The search view opens when the search bar has focus. Escape, a view switch, ⌘J or ⌘T closes it
- Keyboard navigation between panes, with shortcuts shown in menus
- Space runs the main action of a focused row, X toggles the indexing checkbox, ⌘⇧F opens the Filters panel, and ⌘⌥↑/↓ move in the left dock
- A "Hide unindexed items" switch, with an indexed-only scope chip
- The window opens at 1280×800 and remembers its size and position
- Experimental search flags, off by default: `hybrid` (BM25) and `variant_expansion`

### Changed

- Menus show an LED mark instead of a checkmark, and headers share one style
- Game systems have no colour; colour is only for collections, from a palette of manuscript pigments
- Amethyst is the colour for active states and vermilion for danger. Tertiary text is brighter for WCAG contrast
- The filter console and collections are panels side by side, with a view picker in the header
- MCP: a filter value with a typo or a partial name now matches the closest value instead of failing without a message. `list_collections` shows file counts and descriptions, and results include match tiers
- The sidecar cuts long tables between rows, not in the middle of a row
- Tag updates are sent in batches below ChromaDB's write limit
- Accessibility: menus have roles and `aria-checked`, shortcuts use `aria-keyshortcuts`, and view rows are `role=checkbox` buttons

### Fixed

- The untagged mute and files with the same name no longer leak out of the scope
- A saved tag no longer reverts when the status refresh fails
- Tauri errors include the sidecar's response
- Renaming a file moves its solos and mutes to the new path
- Only one menu is open at a time, and Escape no longer closes the docked filter panel
- Archived collections do not show in the collection submenus
- Context-menu actions no longer run against a cleared menu state
- Empty-state messages come from one place and are correct on all surfaces

## [2.0.2] - 2026-07-02

### Fixed

- The MCP client timeout is longer
- The English-only reranker is skipped for queries with non-ASCII characters

## [2.0.1] - 2026-05-11

### Fixed

- The sidecar no longer crashes at start in release builds

## [2.0.0] - 2026-05-10

### Security

- A Content-Security-Policy protects the app window
- Sidecar CORS accepts only the known Tauri origins

### Added

- A cross-encoder reranks search candidates for better relevance (fastembed ONNX)
- Search results expand to the surrounding section
- Solo and mute filters for game systems (per session, not saved)
- A Game system submenu in the right-click menu to tag PDFs
- A `?` overlay that lists all shortcuts
- Action keys (R/F/./M/C) on focused entries in the systems view
- A launch splash screen
- The results pane shows when Ollama is not running
- A Deselect folder action in library settings
- The settings store is validated, and a message shows at startup if the folder is missing

### Changed

- Search returns 15 results by default instead of 5
- The reranker also reads section headings
- Cosine distance is fixed, and relevance scores are limited to [0, 1]
- The app shows more clearly that a new search is running
- Filter menu: `S` solos, keys stay in the menu, and curation and narrowing are hidden in tree view
- Dialogs fit the height of their content
- Enter in a text field saves edit dialogs
- The "+ tag" chip is bigger, and context submenus stay in the window and open upward when there is more space above
- Onboarding has two steps, the folder and Ollama, in a control-panel layout
- The Setup tab is now a Help center
- About shows the Unseen Servant homepage
- The status bar no longer has the license and guide icons, and has a divider
- The sidecar uses a free port and starts after a readiness check. Windows process cleanup is reliable, and MCP finds the port for each request
- The Ollama embed timeout has a limit, and streaming releases its lock sooner
- Re-indexing is atomic and stops embeddings cleanly on failure
- Rename inputs are validated, and collection rename is atomic

### Fixed

- Null section headings and game systems show as text in search results
- A sidecar check that blocked searches is removed
- A click on a filter-menu label ticks the checkbox, not the solo button
- A dialog focuses itself, not its first control, when it opens
- Keyboard focus no longer stays on a submenu that opened on hover
- Rename keeps the scroll position and row focus (on open, save and Esc)
- Rename shows a clear error when a file's cached path is out of date
- The sidecar error is kept, so a UI that loads late still shows it
- The missing-folder message clears when settings load

## [1.1.5] - 2026-03-15

### Changed

- The app identifier changed

## [1.1.4] - 2026-03-14

### Changed

- Updated the license dialog and sync metadata

## [1.1.3] - 2026-03-14

### Added

- A Getting Started guide that checks Ollama
- Folder rename and delete, with changes to the files inside
- File rename and delete go directly to the sidecar

### Fixed

- The Getting Started dialog title uses the same font as the License dialog
- The copied MCP config has its `mcpServers` wrapper again
- The MCP agent searches before it says that a game system is not available

## [1.1.2] - 2026-03-13

### Fixed

- The sidecar no longer crashes in production builds; it has codesign entitlements

## [1.1.1] - 2026-03-13

No changes for users.

## [1.1.0] - 2026-03-12

### Added

- Selected files are highlighted, and files have a right-click menu
- Sync handles renamed, deleted and moved files automatically
- A renamed PDF is detected, so it is not indexed again
- A tooltip shows the space that can be reclaimed, and one click compacts the database
- Sync runs at an interval, and the status bar has a sync button
- The macOS app is signed, and a Windows build is available

### Changed

- The status bar has fewer actions, with icons and tooltips
- The header is smaller, and UI labels cannot be selected
- The tree keeps its expanded folders across reloads
- Sync progress uses random batch sizes, so it looks natural

### Fixed

- Chunk IDs no longer collide, and writes are atomic
- The MCP binary is executable
- Custom checkboxes no longer show a WebKit accent-color problem
- A right-click in the file tree no longer selects text

## [1.0.1] - 2026-03-07

### Added

- A license viewer in the status bar
- The app includes the LICENSE file

### Fixed

- The package.json license field is proprietary, not MIT

## [1.0.0] - Unreleased

### Added

- A folder browser with a recursive PDF tree, lazy loading and a saved selection
- PDF indexing with ChromaDB and local Ollama embeddings (nomic-embed-text)
- Semantic search across the indexed PDF library
- Game system tags (D&D 5e, Pathfinder and others), shown as clickable badges
- Live sync progress with SSE streaming
- A double-click opens a PDF in the system viewer
- An MCP server with 7 tools for AI agents
- One click copies the MCP config to the clipboard
- A system tray icon, so the app runs in the background
- A macOS .dmg on GitHub Releases
