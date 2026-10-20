# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- **Images on the board.** A note's embedded images (`![[map.png]]`, as Obsidian writes them, with `|300` for a width) show on its card in Play and when you read it in the inspector; one naming no image in the campaign shows its name, dashed. Drop an image from Finder on a board to put it there: it's copied into the campaign's `Shelf/` folder, so the campaign keeps everything it uses. An image Obsidian Canvas put on a board shows as itself, and renaming its track or the campaign keeps it on the board
- **Images are clips.** An image in a track or on the shelf shows in Prep beside the notes, named with its extension as Obsidian links it (`[[Barovia.png]]`). Put it in a beat, play it and its card shows the picture, on the board and in the tray; double-click it to see it in the inspector. It renames, moves and copies from another campaign as a note does, and isn't spent: spend the beat that shows it. Claude finds images by name, puts them in beats and in play, and says an image has no text to read

### Changed

- **Claude sees a campaign's shape in one call.** `campaign_overview` replaces `list_campaigns`: the campaigns, then the open one's tracks with their notes, the shelf, beats with their notes and the sessions planning them, and how many beats each session plans, by name only. A refused request now reads as the reason alone, and a note name already in use says where that note is
- **Claude can correct a note.** `edit_note` replaces a note's text and keeps its frontmatter, so a beat keeps its notes and a spent mark stays. It's checked against the hash `read_note` now shows, so it never overwrites a change you made since Claude read the note
- **Claude can make beats.** `create_beat` makes a scene from notes already written, with the scene's text, and can add it to the end of a session's plan; `add_to_beat` puts a note in a beat or takes it out
- **Claude can plan a session.** `create_session` starts the next session and opens it in the app, `set_active_session` opens one that exists, and `plan_beat` puts a beat in a plan, moves it or takes it out, including an entry whose beat is gone. `current_session` reads any session by name
- **A beat can share a note's name.** Name the scene on the Svalich Road after the road: a name now only has to be unique among the notes, among the beats and among the sessions. Where a name is shared, Command links the note by its path (`[[Locations/Svalich Road]]`) so Obsidian opens the right file, and a link in a note's text opens the note
- **The board has a toolbar.** A column of tools on Play's board, after Miro's: any note of the campaign placed where you click, by name (`D`), text cards and stickies (`T`, `N`), frames that carry the cards inside them (`F`, or `⌘G` around the selected cards), lines between cards and frames (`L`, or from their anchor points), and a hand to pan over the cards (`H`). Double-click a text card, a frame's name or a line to write in it, and `⌘Z` undoes any change to the board. A bar over the selection colours stickies, text cards, frames and lines from the pigments, and sets a line's arrowheads. `⌘D` duplicates text cards, stickies and frames, and `⌥1` and `⌥2` show the whole board or the selection. Everything is saved in the session's canvas as Obsidian Canvas writes it
- **Arrowheads show on the board**, including those on lines Obsidian drew
- **Arrange a board by beat.** The key at the foot of the board's toolbar gives each planned beat a frame with its notes, in plan order, and puts the notes several beats share in a frame named Throughout. Launching a beat then shows its frame. A board you haven't touched already lays its cards out by beat instead of by track
- **Claude can work on a board.** `arrange_board` frames a session's planned beats as the Arrange key does, `frame_cards` gathers notes into a named frame, `connect_cards` draws a labelled line between two notes' cards, and `add_text` puts a text card beside a note or under the board. The cards you see stay where they are
- **Claude can file notes.** `create_track` makes a track and `move_note` moves a note to another track or the shelf. `create_note` takes a track's name in any case, `find_notes` quotes each note's text rather than its frontmatter and says when it lists only the first 20, and `add_to_live_set` can take a note out of play
- **Claude's notes cite their book.** `create_note` takes the id of the search result a note draws on, and the note cites the book and its PDF pages, so its card in Play opens the book there, as a note sent from Legend Lore does

### Removed

- **The session log.** Launching a beat or marking a note spent no longer writes a line under `## Log` in the session note. Lines already written stay in your notes as plain text. The jot bar still writes to the session note, now always at the end of its text. For Claude, `current_session` no longer reports a log and `spend` no longer logs

### Fixed

- **The card tray** no longer brings up its last card when the pointer is over the tray's empty end

## [4.0.0] - 2026-10-17

**Unseen Servant is now a workstation with two tools.** Legend Lore is joined by Command, a session tool for running the table, and both live in one window, the rack. Your library, index and collections carry over as they are: nothing needs re-indexing.

### Added

- **Command, a session tool laid out like Ableton Live.** A campaign is a folder of Markdown notes. Tracks are kinds of material (PCs, Secrets, Locations, NPCs, Monsters, Traps and Treasures to start, all editable), notes are the material, beats are scenes that gather notes from any track, and a session plans beats and keeps a log. It's all plain files in `~/Unseen Servant` (change the folder under Settings → Command), so Obsidian opens, reads and edits the same campaign
- **Prep** lays out a column per track beside the session planner. Arm a beat and click notes to put them in it, as you curate a collection; drag notes between tracks, beats into and out of the plan, and tracks into a new order. Each track can take a pigment. The inspector edits a note's Markdown with `[[` completion, or reads it rendered (`⌘E`)
- **Play** runs the table on a board for each session, saved as a JSON Canvas that Obsidian Canvas opens: the session's notes as cards you place, size and connect. The session player over the board launches beats (`J`/`K` to step, `P` or `Space` to launch or stop), lighting their cards and framing them, and a jot bar writes to the session note (`⌘O` opens it). The expand key gives the board the whole rack
- **Spent instead of carry-forward.** Mark any note or beat spent (`A`, or the box key on its row or card) when a secret is revealed, a treasure given or an NPC dies. Spent notes dim and fold into a container at the foot of their track; anything unspent is still there next session. A setting spends a beat when it launches (off by default)
- **Each campaign has a shelf** (`⌘B`) for material gathered but not yet filed on a track, and notes can be copied onto it from another campaign
- **Send to Command** from a search hit's menu puts the section's text in a note on the open campaign's shelf or one of its tracks, citing the book and printed page; the note's source key opens the PDF at that page
- **Campaigns open like Live sets.** Command reopens the campaign you left, or starts on a blank *Untitled* that goes away if you leave it empty. The campaign key switches, renames and trashes campaigns, and on macOS the File menu has New Campaign (`⇧⌘N`) and Open Campaign
- **Claude can follow the table.** The MCP server gains eight Command tools: list campaigns, read the current session and what's live, read and find notes, create a note, add to the live set and mark spent. The Claude Desktop entry stays as it is
- **Pop a tool out into its own window** with the key beside its header (right of Legend Lore's search bar), and dock it back the same way

### Changed

- **One rack replaces the window.** The main window holds eight views, picked with `1`–`8` or the keys in its bar. Press a tool's key to add it to the view, carry the key onto a slot's edge to split it or onto its middle to swap, and drag the rails between tools to resize them. A view can lock its tools in place. On first launch Legend Lore has view 1 and Command view 2
- **The rack bar is the title bar** on macOS, the traffic lights at its left and the Unseen Servant mark at its right, and the status bar under the rack serves every tool
- **The window opens maximized** and no longer remembers its last size
- **Nine pigments, a sword-and-sorcery cabinet**, for collections and tracks: Kermes, Madder, Realgar, Ochre, Malachite, Azurite, Lapis, Orchil and Murex. Existing collections move to their nearest successor on their own, and the pigment menu is one row of picks
- **Every rename ends as Finder's does:** Enter or a click away keeps the new name, `Esc` backs out, and a name that can't be used keeps the field open with the reason. The name is typed where it was shown, in its own face and size
- Selected text and the caret are parchment
- Rows drag without a grip, carried by a closed hand and a faded copy of the row
- Every list row and panel plate is one height across both tools, and list rows end square
- Horizontal scrollbars are as thin as the vertical ones

### Fixed

- Clicks inside a rename field stay in the field
- Renaming a book to nothing, or to its own name, leaves it as it was
- A book or folder can be renamed by a change of case alone
- A collection with `?`, `#`, `%` or `/` in its name can be renamed
- A renamed book keeps its collection gems
- A renamed collection keeps its ring and stays open

## [3.1.2] - 2026-10-03

### Changed

- **Enter lands on the results.** Submitting a search moves focus to the first result as soon as the list arrives (with no hits it stays in the bar so you can retype). `Esc` from the results leaves search in one press, and the arrows no longer cross between the bar and the list. `⌘K` is the way back to the bar, and it selects the query so typing replaces it and `→` edits it
- **A row shows every collection it belongs to**, up to five gems: coloured collections first, then the uncoloured ones in plain ink, instead of one gem and a `+N`

## [3.1.1] - 2026-10-01

### Fixed

- **The macOS app starts its indexer again.** In 3.1.0 the sidecar quit at launch while opening the library store, so search and indexing never came up. Coming from 3.0, re-index your library after updating (see 3.1.0)

## [3.1.0] - 2026-09-30

**Re-index your library after updating.** The index moves to a new store, and the old one is removed the first time the app starts, so search returns nothing until you re-index. Library settings lists every file as needing it. Your PDFs, collections and game-system settings are untouched.

### Added

- **Pick a collection from the search bar with `@`.** Type `@` and a few letters: the Collections panel narrows to the matches and rings the one `↵` will play. `↵` plays it alone, `⇧↵` adds it to the mix, and the `@`-word is never searched, so scope and question go in one breath (`⌘K`, `@mon ↵`, `troll regeneration ↵`)
- **`⌘1`–`⌘9` play a collection from anywhere.** Collection N in the panel's current order plays alone (press again to stop it); `⌘⇧1`–`⌘⇧9` add it to the mix or take it out
- **Find a book by name.** Start the search bar with `/` and the tree or systems view narrows to the books and folders whose names hold every word you type, opening the folders on the way to each match. `↓` or `↵` jumps to the first match; `Esc` drops the filter
- **The inspector's scrollbar maps the section.** A tick marks every place the query's words appear and an edge mark shows the passage that matched; click the mark, or press `G` in the results, to scroll back to the match
- **Filter panel sections fold.** Curation, Game systems and Hidden items fold shut from their header or with `←`/`→`, and so do the systems view's groups. A folded section with a solo, mute or view switch on inside lights a lamp so it isn't forgotten
- A "Dim weak matches" setting under General → Search results (on by default)
- An embedder lamp in the status bar, between the sidecar and MCP lamps: lit when the embedding model is ready, dim when the runtime answers but the model is missing
- More keys: `↵` opens the focused file or folds a folder in every list, `⇧X` ticks every row from the last tick to here, `⌥↑`/`⌥↓` jump to the first or last row on a Mac, and `⌘/` opens the shortcut sheet even from the search bar

### Changed

- **The whole index is one file.** Books, sections, text, embeddings and the keyword index live together in a single SQLite file in the app's data directory, and every change to a book (indexing, renaming, retagging, removing) is saved in one step, so an interrupted operation can no longer leave parts of the index disagreeing
- **Removing a book gives the disk space back straight away.** The Compact button and its "reclaimable" readout are gone because there is nothing left to compact
- **Searching inside a collection or game system is faster, and stays fast as the library grows.** A scoped search reads only the selected books instead of the whole library
- Renaming or moving a file or folder, and changing a book's game-system tags, are instant regardless of book size
- The app is smaller: the sidecar no longer ships ChromaDB
- **Naming a game system in a search no longer skews it.** "dragonbane fireball" used to rank Dragonbane's Dragon monster first, because the system's name was searched as if it were part of the question. A named system now only puts that system's books first, so questions that name a system find the right section far more often
- **Search while you type understands an unfinished word.** Results as you type used to "correct" the word you were still typing into a different one ("grapp" became "grasp", "wea" became "sea"); the last word is now completed from your own books instead ("grapp" → "grapple", "against poi" → "poison"), so the list shows what you're heading for. Pressing Enter searches exactly what you typed
- **Indexing progress says what it's doing.** The status bar reads "Indexing 4 of 12 · Player's Handbook" instead of a file and chunk tally, with a small meter showing how far into a long book it is, and the summary counts books ("Added 3 books, removed 1"). Failed books stay listed until you dismiss them; hover the note to see which ones and why
- **Unseen Servant opens on a splash that shows the cold start.** It comes up before any tool window, with a lamp for each part as it starts: settings, sidecar and library store, then Legend Lore's embedder, reranker, spelling vocabulary and library folder. If one fails (the embedder isn't running, the library drive isn't mounted) the splash names it before the tools open anyway. The splash closes on its own and can no longer be clicked or keyed away, and the Legend Lore window no longer carries one of its own
- **Collections wear a gem instead of a ribbon.** Panel rows, file rows, scope chips and menus draw a gem in the collection's pigment, and the header's collections key shows a gem too. The context menu's `Ribbon` submenu is now `Gem`, still named for the glyph on the row. Loose draws only the gem's outline, dashed, so the dashes don't break up the facets
- **Tab switches between the tree and systems view**, replacing `⌘1`/`⌘2`, which now play collections; `⌘1`–`⌘9` no longer jump to a search result. Collapse the whole tree with `⇧←` or `⇧H`
- **Results lead with the section that matched.** Each card names its book and system above the section title, cites the printed page, and lights your query's words in the snippet. Book names drop `.pdf`, and the relevance gauge has one cell per tier. The weak-matches divider is gone; weak results stay dimmed
- **The inspector reads like a page.** The section's path and `[open p.N]` stay pinned above the text, your query's words are lit, prose keeps a readable line length, and the matched passage is marked by a rule in the margin
- **Fewer stray section headings.** Bold quote attributions, stat lines ("Ferocity: 2 Size: Small") and sentences are no longer promoted to headings, which cleans up bestiaries and OSR books most (it changes about a third of the Dragonbane Bestiary's and Wight-Box's passages)
- **The search view waits for a query.** `⌘K` or an `@`-pick no longer blanks the tree; results take its place on the first keystroke that leaves something to search
- **The sync prompt says what changed**: "2 moved, 1 missing on disk, 3 to add" instead of "3 disk changes", and its action reads `[sync]`
- The header's Collections and Filters keys light a lamp while anything in their panel is engaged, even with the panel closed
- The collections panel ends in an empty "New collection" track; click it or press `⌘N` to name one in place. A click on a collection row opens its books
- Game systems wear a shield instead of a die. Collections come in six new pigments chosen to stay clear of the interface's own colours; existing collections move to their nearest successor on their own
- The status bar counts "books" rather than "PDFs indexed"

### Fixed

- Two PDFs with the same filename in different folders no longer both take the game-system tags you give one of them, and the status bar counts them as two books
- A damaged collections, manifest or custom game-systems file no longer stops the sidecar from starting or breaks its panel; it is set aside as `<name>.corrupt-<timestamp>` for repair and the app starts with an empty one (a set-aside manifest means the next sync re-indexes)
- When the embedder isn't running, search, sync and Claude say "Embedder not running" instead of "[Errno 61] Connection refused"
- A sync the sidecar refuses shows its reason instead of "Sync completed but no result received"
- Result rows cite the printed page, matching the inspector, instead of the PDF page
- Renaming a folder keeps it expanded, focused and hidden
- A shift-click or `⇧X` range ticks only the rows the tree shows, not hidden or filtered-out files between them
- Right-clicking another row while a context menu is open opens a fresh menu for that row
- Deeply nested folders no longer drift further right with every level
- While the arrow keys move the cursor, the row under a resting pointer no longer lights up beside it
- On Windows, paths reach the app with `/` separators, which folder selection, hidden folders, and renaming or deleting a folder rely on

## [3.0.0] - 2026-09-24

**The app is now Unseen Servant.** Legend Lore is its PDF search tool; the window keeps that name, the app in your dock, tray and Applications folder is Unseen Servant. Your index and settings move to the new data directory on first launch. Re-run the MCP setup in Getting Started so Claude Desktop points at the renamed app.

Search is rebuilt from the index up. **Re-index your library after updating** — Library settings lists the files still indexed with the older pipeline. Until a file is re-indexed it keeps working, but without whole sections, keyword matching or printed page numbers.

### Added

- **Hybrid keyword search, on by default.** Exact-term matches now sit alongside meaning-based ones, so rare names, stat codes and a book's own jargon find their page even when the embedding misses them. The toggle has left the Experimental group; a settings file saved by an earlier version that only recorded the old default comes back on
- **Results are whole sections.** A hit returns the section it belongs to rather than an isolated 1,000-character slice, so a stat block, a spell or a table arrives in one piece instead of split across three results, and one section never fills the list twice
- **Editions collapse into one result.** When the same passage appears in several books — the SRD 5.1 and 5.2.1, say — you get one result with a `+1 edition` chip, and the inspector lists the other books under "also in"
- **The inspector jumps to the match.** The passage that matched is highlighted and scrolled into view, and Markdown tables render as tables
- **Citations use the printed page number.** TTRPG PDFs carry covers and front matter, so PDF page 312 is often printed as 276; results and Claude's citations now lead with the number on the paper, with the PDF page alongside
- **Claude gets two new tools.** `get_section` fetches a whole section by id and `get_pages` reads a page range straight from a book, so Claude can drill in from a search hit instead of searching again
- Year Zero Engine, The Black Hack and Cairn join the default game systems

### Changed

- **Search is about three times faster.** A quantised reranker cuts a typical query from over a second to about a third of one, on the same hardware. The new model (about 23 MB) downloads once, the first time the app starts
- **Naming a game system puts its books first.** "grapple dnd 5e" leads with your D&D 5e books; the rest follow in their own order instead of being dropped
- **Fewer results claim to be strong matches.** Relevance tiers are recalibrated on human-judged results, so "strong" now means the answer is very likely there — about a quarter of results earn it, down from over half
- **Section titles are clean.** Headings no longer carry stray markup, letter-spaced small caps ("S P E L L S"), or a page footer masquerading as a chapter, which also sharpens what search matches on
- **Spell correction reads the words around a typo.** It picks the correction that fits the neighbouring words in your own books ("thief skill", "chain mail") and in ordinary English questions ("how does"), cutting wrong corrections by a third to a half. Game-system names are never corrected — "dnd" no longer becomes "and"
- **Claude's search answers are compact.** `search_library` returns 8 results with a short matched passage and a pointer to the full section, keeping answers small enough for local models; `full_text=True` restores whole sections under an 8,000-character budget
- The first search after the app has sat idle no longer pays a slow warm-up, and each search reads settings once instead of on every step

### Fixed

- A dropped connection to the embedding model mid-index is retried instead of aborting the whole book — large books such as OSRIC hit it reliably
- A search result's page range covers only the pages its text is on, not the whole run of pages around it

## [2.3.0] - 2026-08-14

### Changed

- The filter console's `[clear all]` is now `[reset]`, and it answers for the whole panel: every solo and mute, plus the focus lens, show-hidden and hide-unindexed switches below it, which it used to leave lit. It sits dim until something is actually engaged. Files you've hidden by hand stay hidden — the Hidden items section keeps its own Clear for those
- **Search is `⌘K`, the Filters panel is `⌘F`.** Search moves to the chord command bars everywhere use, which frees `F` for the thing it actually reads as: filtering. `⌘⇧F` no longer does anything
- **A search result is a row like any other.** Results now drag onto a collection, open the same context menu the tree and systems view use, take a filing checkbox while a collection is armed, and answer `j`/`k`, `Home`/`End`, `⌘O`, `⌘I` and bare `S`/`M`. Rename is the one verb withheld — a result row has nowhere to host the field
- **The dock stays keyboard-live while you search.** The two sides arbitrate who holds the keys — entering search or clicking the results points them at the file side, and the `⌘⌥` chords cross between the two — instead of search taking the keyboard whole. Entering search also clears stale carets in the dock, so no focus ring claims the arrows act somewhere they don't
- **One Collection submenu, filed beside Game system.** Add and Remove were two triggers describing one axis, and a partly-filed folder showed up in both at once. They collapse into a single submenu of togglable rows whose pip reads all, some, or none — a half-filled folder tops up rather than emptying. `C` opens it, and it stays open while you file, so filing a book into three collections is one right-click instead of three. The menu regroups around that: Get info joins Open and Reveal, Re-index moves down beside Rename, and Delete gets its own section
- **Pigment is now Ribbon**, named for the glyph actually on the row — and `Ribbon > None` reads correctly where `Pigment > None` did not. Rename and Archive take the object noun the way Delete always had, while Arm, Play and Mute stay bare mixer verbs; Solo and Mute drop "this file" so every toggle row names its object the same way; and "New collection" loses its ellipsis, since the naming happens in place rather than on another surface
- Game system labels in the menus take primary ink instead of parchment. Parchment marked "this system has a pigment" back when that varied; it has been universal since, so the warm ink signalled nothing on a cool grey menu. The die still marks the axis, exactly as a collection's sigil does
- Clicking a filter row focuses it, the way clicking a collections row already did
- A collection's expanded file rows join the keyboard model: `j`/`k` walk them, `⌘⌫` removes one and hands focus to its sibling, `⌘O` opens it, and `←` hops back to the collection head
- **Every confirmation is the app's own.** Deleting a file or folder and re-indexing a single file raised a system dialog in the operating system's chrome; they now use the same prompt the rest of the app does, so the same `⌘⌫` looks the same in the file tree as it does in the collections panel
- Deleting a custom game system, and resetting a customized built-in to its defaults, now ask first — neither did
- **Danger red means one thing again.** Cancel and Discard no longer turn red under the pointer — hovering only brightens — so red marks the action that actually destroys something. The Danger Zone's two-step arms with a tinted wash instead of filling solid red, matching the mute button
- **Dialog actions are bracketed text** — `[Cancel]`, `[Delete]` — the affordance the app already spends on `[Compact]` and `[R]`, instead of a checkmark or cross beside the label. Icon-only buttons keep their glyph; the two are alternative markers, not a pair
- The Game Systems editor's footer is one family of buttons instead of three
- Dialogs fade and scale in rather than appearing instantly, and hold still if your system asks for reduced motion. Their close × is a lighter glyph that no longer outshines the rest of the title bar, and every dialog now draws from one set of width and padding steps
- The keyboard shortcut sheet brackets its single-key chords — `[R]`, `[X]` — the way the menus already do, so a lone letter reads as a key rather than a stray capital
- A file's Info dialog is titled with the filename, with its full path beneath it, and the game system moves out of the cramped five-column readout onto its own line where a multi-system file fits
- **Tap latches, hold is momentary.** Holding `S`, `M` or `P` engages it only while the key is down and puts it back when you let go, the way a hardware transport works — peek at one book alone mid-search without dismantling a scope you spent prep time building. Tapping still latches, exactly as before
- **`B` bypasses the whole scope console** — every indexed file back in scope, for A/B'ing a thin result against your own filters. Hold to peek or tap to latch. Nothing is cleared: the chips dim rather than disappear, so you can see what's being passed through, and a `BYPASS` lamp shows in the status bar. Not remembered across launches
- **The scope bar names itself and carries the bypass switch.** It used to render empty until something narrowed — present but blank, and nothing you could learn from. It now always shows a `Scope` nameplate, a `B` switch beside it, and, when nothing is narrowed, the number of files a search would run against. The switch sits inert until there's a scope to bypass
- Engaging a solo or mute snaps — one bright frame as the switch reaches its position
- **The systems view's rows are channels.** Every file row in the by-system view carries its own S/M pair beside the system's, so the view works as the asset library it is: solo or mute one book without leaving it. Bare `S`/`M` on a focused row act on the file; `⇧S`/`⇧M` still throw the system's switches, and holding any of them stays momentary. Untagged books can finally be soloed — individually, as files
- **A muted book dims where it stands.** Muting a single file in the by-system view now dims that row — in every system it appears under — and soloing one file dims its shelf-mates, so the view reads scope at the row the way the tree does, instead of only at the whole system. The focus lens likewise hides out-of-scope rows, not just whole systems
- **The systems view's channel switches sit on the strip.** They used to be laid out invisible and painted only when you reached the row, so a file row spent its switch column on switches it refused to draw and the ribbon strip hung short of the right edge. They rest in tertiary ink now and dress up under the pointer — nothing appears or moves. Group headers and file rows share one switch column, and a system's count readout is sized to the largest count on screen, so a header stops sliding as its shelf grows

### Fixed

- A hidden file shown under "Show hidden items" no longer fades almost to nothing in the by-system view when it is also out of scope — the two dims were multiplying. Hidden wins, as it always has in the file tree
- **Bypass now reaches every dim it should.** While `B` is engaged the systems view no longer keeps muted and non-soloed groups dimmed (or hidden, under the focus lens), and a soloed Collected/Loose bucket no longer keeps rows out of the systems view — search already saw all of it; now the browsing surfaces agree. The S/M buttons stay lit through it, as before
- The scope bar's `hidden shown`, `indexed only` and `lens on` chips no longer dim under bypass — bypass doesn't suspend those switches, and the dim claimed it did
- Pressing `B` over an empty console no longer lights the `BYPASS` lamp for nothing — the key now refuses exactly what the scope bar's inert switch refuses
- Soloing combinations that intersect to nothing — a system solo with no file under a soloed folder, say — now say "Nothing under the soloed items." instead of a generic no-results message beside a meter reading "of 0 files"
- The hits meter no longer claims its count came from your scope while the scope is bypassed — the number was already the whole library, but the tooltip said otherwise
- Enter no longer commits a destructive prompt when Cancel is focused. Destructive prompts open on Cancel so that Enter from muscle memory is harmless, and that focus is now visible — it was being drawn without a ring whenever the prompt was raised by mouse
- Opening a search result opens the book it came from. Results were matched back to disk by filename, so two books sharing a name — the same supplement under two systems, say — could open the wrong one. They open by path now, and the filename scan survives only as a fallback for a file that moved since it was indexed
- The collections list no longer reshuffles between reads. The order came back from Rust differently on every call, and every surface sorted before drawing, so nothing showed it — until the Collection submenu started staying open and visibly reordered its rows under the cursor after each toggle
- The scope bar no longer thickens, shoving the tree down, when its first chip lands. The row reserves a chip's height whether or not one is there
- Filter, tree and systems rows no longer hold a highlight the pointer has left — they latch hover on a real pointer entry, the fix the collections panel already had for itself

## [2.2.0] - 2026-08-11

### Added

- **Arm a collection** — a record-arm (●) beside play and mute on every collection row. Arming points the file tree at that collection: click a book to file or unfile it on the spot, tick a folder to enrol everything indexed beneath it. No Save, no Cancel, and no view switch. `E` arms and disarms, `Esc` leaves
- **Drag books and folders onto a collection** — from the file tree or the systems view, onto a collection row, its expanded file list, or "+ New collection…" to seed a fresh one named after what you dragged. Folders drag as a unit and their count is named before and after the drop
- Collection membership shows in the tree and systems view as a pigment ribbon strip on file rows — up to two, plus a `+N` that accounts for the rest
- A hover × on the panel's expanded file rows removes that book from the collection
- Every collection row reads out its file count, in the same inverted LED box the filter console uses per channel
- Play and Mute join the collection's context menu, which now leads with the transport — Arm, Play, Mute — before the track's properties
- `⌘⌫` (`Del` off mac) deletes the focused row in both the file tree and the collections panel

### Changed

- **Naming a new collection happens in the "+ New collection…" box** — the box becomes the name field in place, and committing promotes it to a row in the list, created, focused and armed. `⌘N`, the box itself, a folder's context menu and a drop onto it all land there, the last two pre-filling the field with the folder's name. No draft row, no Save, no Cancel, and nothing exists until you commit, so Esc costs nothing. The box also shows its `⌘N` chord
- Editing a collection's files no longer goes through the context menu, and curating is not modal: search, scope chips, out-of-scope dimming, and disk-change detection all stay live throughout
- Membership writes are coalesced and strictly serialized, so a long curation sweep is a handful of writes rather than one per click, and a failed write reverts to the last saved state instead of half-applying
- **Row keys are consistent across the panes.** `R` renames in every pane that has something to rename (new in the collections panel), and `X` ticks the row's checkbox wherever a row has one
- **A file-tree row has one checkbox, and arming changes what it means.** Unarmed it marks the file for indexing, in parchment — the colour this app reserves for content and data. Armed it files the file into the collection being curated, in purple — the colour reserved for a mode you switched on, and the same box the systems view has always shown. Rows with nothing indexed under them show the box disabled while armed, since a collection can't hold them. Shift-click extends a range, as it already did for indexing
- **Search no longer blocks the sidecar.** Each query runs on a worker thread, at most four at once, so health checks, MCP heartbeats and everything else answer in milliseconds while a search is in flight instead of waiting it out
- The embedding model is kept warm — one token re-embedded every four minutes, so an idle bge-m3 isn't unloaded and the first search after a lull doesn't pay a full model load. `OLLAMA_KEEPALIVE_INTERVAL_SECONDS=0` turns it off
- The window opens at 940×600 — the width where all three panes just fit — and remembers its size across launches in logical pixels, so a size saved on one display comes back right on another
- The status bar moved onto the header plate and the search bar is recessed into the panel surface, so the two bars bracketing the workspace match and the header's two inlays share one depth
- The search bar shows its focus chord while empty, and the view switch keeps a dimmed mark on the view you'd return to while search is up
- The Loose curation row draws a dashed ribbon where it used to hold an empty spacer
- MCP server migrated to mcp 2.0 (`FastMCP` → `MCPServer`) — the same four tools with the same arguments
- Refreshed Rust, npm, and sidecar dependencies

### Removed

- `Space` and `Enter` as row actions in the file tree, systems view and filter panel, and `Enter` in the collections panel. `Space` still runs a collection's play/stop transport, and `Enter` still submits a search, opens a search result, activates a context-menu item, and commits any text field. Use `R` to rename, `X` to tick a checkbox, `⌘O` to open a file, and `→`/`←` to walk folders
- `⌘↵` (Save in-progress collection) — there is nothing left to save
- `F2` as a second spelling of rename — `R` renames in every pane

### Fixed

- Systems view: a game system's "select all" checkbox no longer latches. Unticking the last file in a system left its header still showing selected
- Creating a collection no longer switches the main pane to the systems view and leaves it there permanently — a bug that persisted across restarts for anyone who worked in tree view
- A trackpad flick no longer rubber-bands the whole app and uncovers a dark band at the window edge
- The filter panel's lens checkboxes light purple again instead of parchment — purple is the colour this app reserves for a mode you switched on
- The search bar's clear button draws as × in the app's own face, instead of falling through to a system font

## [2.1.0] - 2026-08-09

### Added

- Relevance tiers — results read as **strong / good / weak** instead of a raw "% match", with weak matches dimmed below a floor so noise reads as noise
- Table row-linearization: tables are split into per-row embed units, so a lookup lands on the exact row of a spell or equipment table, with a coverage-ratio tripwire that flags lossy table parses
- Spell correction: misspelled query tokens are rewritten against your library's own vocabulary ("owlber" → "owlbear") before searching, and results say what was corrected
- Game-system soft-boost — naming a system in the query ("fireball in 5e") lifts that system's results without hiding the rest of the library
- Startup probe that detects silent Ollama embed truncation and warns in the sidecar logs
- General settings tab with sidecar-wide search-pipeline knobs, including a candidate pool preset from Fastest (10) to Exhaustive (200)
- Solo/mute/play scope doctrine: a mixer-style filter console, a play/stop transport on collections, archive as shelving, and a focus lens that hides out-of-scope items
- Scope bar with system and collection chips, pinned above the scrolling tree and systems views
- Full console recall — solo, mute, play, and lens state persist across launches
- Stateful search view: focusing the search bar opens it, and Escape, a view switch, or ⌘J / ⌘T step back out
- Pane focus model for keyboard navigation, with keyboard chords shown on menu rows
- Space as the primary action on a focused row, X to toggle the indexing checkbox, ⌘⇧F for the Filters panel, and ⌘⌥↑/↓ to move within the left dock
- "Hide unindexed items" switch with a matching indexed-only scope chip
- Window opens at 1280×800 and remembers its geometry across launches
- Retrieval eval harness with answer-chunk grading, per-query latency, and a recorded baseline
- Experimental, default-off search flags: `hybrid` (BM25) and `variant_expansion`

### Changed

- Shared header voice classes, an LED pip in place of the menu checkmark, and menu geometry driven by tokens and real measurements
- Game systems go monochrome — color is now reserved for collections — over a manuscript-pigment palette
- Amethyst re-grounded as the active hue and vermilion as danger, with a brighter tertiary text token for WCAG contrast on the app background
- Mono font, radii, and modal shadow moved onto tokens; stylelint now forbids raw colors in component styles
- Filter console and collections became docked sibling panels, with a view-switch picker in the header
- MCP: near-miss filter values (typos, partial names) resolve to the closest match instead of failing silently; `list_collections` reports file counts and descriptions; results carry match tiers
- Sidecar hard-cap splitter cuts on row boundaries instead of mid-row
- Tag metadata updates are batched past ChromaDB's write cap
- Accessibility: menu roles and `aria-checked`, chords exposed via `aria-keyshortcuts` rather than the accessible name, and view rows as `role=checkbox` buttons

### Fixed

- Untagged-mute drop and same-named-file scoping leaks
- A saved tag no longer rolls back when the status refresh fails
- Tauri errors now include the sidecar response body
- File renames migrate path solos and mutes like every other path set
- Only one menu stays open at a time, and Escape no longer closes the docked filter panel
- Archived collections stay off both collection submenus
- Context-menu actions no longer fire against a nulled menu state
- Empty-state messaging is centralized and truthful on every surface

## [2.0.2] - 2026-07-02

### Changed

- Migrate the sidecar to uv and Python 3.12
- Drop cross-platform smoke jobs from CI and document the billable-minutes budget policy
- Refresh Rust, npm, and sidecar dependencies

### Fixed

- Raise the MCP client timeout
- Skip the English-only reranker on non-ASCII queries

## [2.0.1] - 2026-05-11

### Changed

- Upload release assets to R2 via a new publish-release workflow
- Include the version in R2 download filenames

### Fixed

- Add `--collect-all pymupdf`/`pymupdf4llm` to the release build, fixing a sidecar crash on import
- Apply sidecar entitlements at bundle time
- Bundle sidecars via externalBin instead of a resources glob
- Use the cargo `TARGET` in build.rs instead of `TAURI_ENV_TARGET_TRIPLE`

## [2.0.0] - 2026-05-10

### Security

- Enable a Content-Security-Policy for the app window
- Scope sidecar CORS to known Tauri origins

### Added

- Cross-encoder re-ranking of search candidates for sharper relevance (fastembed ONNX)
- Section-aware result expansion in search
- DAW-style solo and mute filters for game systems (per session, not persisted)
- Game system submenu in the right-click menu for tagging PDFs
- Keyboard `?` overlay listing all shortcuts
- Action keys (R/F/./M/C) on focused entries in the systems view
- Launch splash screen
- Ollama-down state surfaced in the results pane
- Deselect folder action in library settings
- Settings store schema validation, with a missing-folder toast at startup

### Changed

- Bump default search results from 5 to 15
- Include section headings in re-ranking input
- Pin cosine distance and clamp relevance scores to [0, 1]
- Clearer in-flight UX while a fresh search runs
- Filter menu: solo with the `S` key, keep keystrokes inside the menu, and hide curation and narrowing in tree view
- Migrate Modal and ConfirmDialog to the native `<dialog>` element and shrink-wrap height by default
- Plain Enter from a text input now saves in edit dialogs
- Bigger "+ tag" chip and viewport-clamped context-menu submenus that flip upward when there's more room above
- Streamline onboarding to folder + Ollama setup in a framed control-panel layout
- Restructure the Setup tab into a Help center
- Surface the Unseen Servant homepage in About
- Status bar polish: drop the license and guide icons, add a divider
- Sidecar now binds an ephemeral port behind a readiness gate, with reliable Windows process cleanup, and MCP re-resolves the port per request
- Cap the Ollama embed timeout and tighten streaming lock release
- Atomic re-index that drains embeddings on failure
- Validate rename inputs and make collection rename atomic
- Path-gated CI jobs (sidecar/rust/frontend) that cancel superseded runs
- Bundle PyMuPDF data files in the PyInstaller sidecar binary

### Fixed

- Coerce null section heading and game system to strings in search results
- Drop a brittle sidecar-connected pre-check that blocked searches
- Bind filter-menu label clicks to the checkbox instead of the solo button
- Focus the dialog element instead of the first focusable child when a modal opens
- Stop stranding keyboard focus on a hover-opened submenu trigger
- Preserve scroll position and row focus during rename (on open, save, and Esc)
- Show an actionable error when a file's cached path is stale on rename
- Stash the sidecar failure payload so a late-mounting UI still sees the error
- Clear the missing-folder toast once settings load successfully

## [1.1.5] - 2026-03-15

### Changed

- Remove stale MSI references from the release workflow and docs
- Update app identifier

### Fixed

- Fix pre-release version builds by dropping the MSI bundle target

## [1.1.4] - 2026-03-14

### Security

- Bump pypdf to 6.8.0 — limits allowed `/Length` value of streams, improves ASCIIHexDecode filter performance

### Added

- Dependabot config for automated dependency updates
- CI workflow for sidecar tests

### Changed

- Bump FastAPI from 0.134.0 to 0.135.1
- Bump ChromaDB from 1.5.2 to 1.5.5
- Bump GitHub Actions: checkout v6, setup-python v6, setup-node v6
- Updated license modal and sync metadata

### Fixed

- Fix flaky rename detection test using isolated subdirectory

## [1.1.3] - 2026-03-14

### Added

- Getting Started onboarding guide with Ollama health check
- Folder rename and delete with child propagation
- Direct sidecar calls for file rename and delete

### Fixed

- Fix release artifact rename to match Tauri output filenames
- Fix Getting Started modal title font to match License modal
- Restore mcpServers wrapper in MCP config copy output
- Coach MCP agent to search before assuming game systems are unavailable

## [1.1.2] - 2026-03-13

### Fixed

- Fix sidecar crash in production builds by adding codesign entitlements

## [1.1.1] - 2026-03-13

### Fixed

- Add timeouts to release workflow to prevent runaway builds

## [1.1.0] - 2026-03-12

### Added

- File selection highlight and right-click context menu
- Auto-sync renames, deleted files, and stale paths without user intervention
- Renamed PDF detection to avoid redundant re-indexing
- Reclaimable space tooltip and one-click database compaction
- Auto-sync interval and manual sync button in status bar
- Apple code signing and Windows build support

### Changed

- Redesigned status bar: consolidated actions, added icons and tooltips
- Shrunk header and made UI labels non-selectable
- Lifted expand state to page level to preserve tree across reloads
- Random batch sizes in sync progress for organic UI feel

### Fixed

- Fix chunk ID collisions with atomic writes
- Fix MCP binary not executable
- Fix WebKit accent-color rendering quirk with custom CSS checkbox
- Prevent text selection on right-click in file tree

## [1.0.1] - 2026-03-07

### Added

- License viewer accessible from the status bar
- LICENSE file bundled in the app distribution

### Fixed

- Corrected package.json license field from MIT to proprietary

## [1.0.0] - Unreleased

### Added

- Folder browser with recursive PDF tree, lazy loading, and persistent selection
- PDF indexing via ChromaDB with Ollama local embeddings (nomic-embed-text)
- Semantic search across indexed PDF library
- Game system tagging (D&D 5e, Pathfinder, etc.) with clickable badges
- Real-time sync progress with SSE streaming
- Double-click to open PDFs in system viewer
- MCP server with 7 tools for Claude Desktop integration
- One-click MCP config copy to clipboard
- System tray with background operation
- macOS .dmg distribution via GitHub Releases
