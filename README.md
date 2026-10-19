# Unseen Servant

> A local-first desktop workstation for TTRPG Game Masters. It reimagines the
> VTT experience for live play at the table and invites GMs to embrace
> improvisation with flexible session prep.

<!-- TODO: hero screenshot — Legend Lore search beside Command's Play board -->

Search every rulebook you own by meaning, prep your sessions as scenes, and run
them at the table, all from one window. Your PDFs never leave your machine, and
your campaigns are plain Markdown files that stay yours.

**Download for macOS and Windows at [unseenservant.games](https://unseenservant.games)**, where the guides live too.

---

## Two tools, one rack

### Legend Lore: your PDF library, searchable

- Point it at the folder of PDFs you already have and tick the books to index.
  Nothing is copied or moved.
- Ask in plain words ("how does grappling work") and land on the passage, with
  its book and page. Results read **strong / good / weak**, so noise looks like
  noise.
- Misspell freely: "owlber" finds the owlbear, corrected against your own
  library's words.
- Narrow a search to a game system or a collection of books, open the PDF at the
  cited page, or send the passage to Command as a note that cites it.

### Command: prep and run your sessions

- A campaign is a folder of notes sorted into tracks: PCs, Secrets, Locations,
  NPCs, Monsters, Traps and Treasures to start, all yours to change.
- Gather notes into beats, the scenes you might run, and plan a session from
  them. Nothing is a script: whatever you don't use is still there next time.
- At the table, Play lays the session's notes out as cards on a board. Launch a
  beat and its cards light up; mark a secret told or an NPC dead as spent.
- Jot during play into the session note, which also logs every launch and spend.

### The Servant: bring your own AI (optional)

Connect any AI agent that speaks MCP (Model Context Protocol) and it can search
your library and read and write your campaigns: look up a rule, see what's in
play, file a new NPC. **Help → Guides → Servant** copies the config. What its
tools return goes to the agent's model, which may run in the cloud; the PDFs
themselves stay on your machine.

---

## Your files stay yours

- **Local-first.** Indexing and search run on your machine, through
  [Ollama](https://ollama.com). The only download is a 23 MB reranking model,
  on your first search.
- **No lock-in.** Campaigns are Markdown files and session boards are
  [JSON Canvas](https://jsoncanvas.org), so [Obsidian](https://obsidian.md)
  opens the same folder. Stop using Unseen Servant and everything is still
  there, readable.

---

## Get started

You need macOS on Apple Silicon or 64-bit Windows 10/11, plus about 1.2 GB of
disk for the search model.

1. **Install Unseen Servant** from [unseenservant.games](https://unseenservant.games)
   or [GitHub Releases](https://github.com/Unseen-Servant/unseen-servant-app/releases).
   - **macOS:** open the `.dmg` and drag Unseen Servant to Applications.
   - **Windows:** run the `.exe` installer. The installer isn't code-signed
     yet, so SmartScreen may say "Windows protected your PC": choose
     **More info → Run anyway**.
2. **Install [Ollama](https://ollama.com)** and open it. Then, once, in a
   terminal:

   ```bash
   ollama pull bge-m3
   ```

   In Ollama's settings, set **Context length** to 8k or more, so long sections
   are searched in full.
3. **Open Unseen Servant**, choose the folder that holds your PDFs, tick the
   books to index, and sync.
4. **Search.** **Help → Guides** walks through each tool, and the full manual
   is on [unseenservant.games](https://unseenservant.games).

To build it yourself instead, see [Build from source](CONTRIBUTING.md#build-from-source).

---

## Contributing

Bug reports, stability fixes and portability work are the most welcome help.
New features are not, unless discussed first: Unseen Servant has one designer.
[CONTRIBUTING.md](CONTRIBUTING.md) covers what's in scope, how to report a bug,
and how to build from source.

---

## Credits

Unseen Servant borrows its ideas from:

- **[Ableton Live](https://www.ableton.com/live/)**: Command's tracks, beats and
  sessions, and campaigns that open like Live sets.
- **[Obsidian](https://obsidian.md)** and **[JSON Canvas](https://jsoncanvas.org)**:
  a campaign is a folder of plain files that other tools open too.
- **The Lazy DM checklist** from [Sly Flourish](https://slyflourish.com)'s
  *Return of the Lazy Dungeon Master*, by Mike Shea: Command's starting tracks
  follow it.

It is built on [Tauri](https://tauri.app), [Svelte](https://svelte.dev),
[CodeMirror](https://codemirror.net), [Svelte Flow](https://svelteflow.dev),
[PyMuPDF](https://pymupdf.readthedocs.io), [Ollama](https://ollama.com) with
[BGE-M3](https://huggingface.co/BAAI/bge-m3),
[fastembed](https://github.com/qdrant/fastembed) and
[ONNX Runtime](https://onnxruntime.ai) with an MS MARCO MiniLM cross-encoder,
[SymSpell](https://github.com/wolfgarbe/SymSpell),
[sqlite-vec](https://github.com/asg017/sqlite-vec),
[Font Awesome](https://fontawesome.com), and the Crimson Text and Almendra
typefaces. [ACKNOWLEDGEMENTS.txt](ACKNOWLEDGEMENTS.txt) lists every component
with its licence, and ships in the app under **Help → About**.

Unseen Servant is not affiliated with or endorsed by any project or product
named here.

---

## License

Copyright © 2026 Jerome Solis, doing business as Unseen Servant Games.

Unseen Servant is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. See [LICENSE](LICENSE).

The AGPL covers the code, not the Unseen Servant name or logo: they are
trademarks of Unseen Servant Games (AGPL §7(e)), so a fork must use its own
name and logo.

Contributions require the [Contributor License Agreement](CLA.md); the CLA
Assistant bot asks you to sign it on your first pull request.
