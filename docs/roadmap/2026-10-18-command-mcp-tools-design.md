# Command MCP tools: audit and recommendations (2026-10-18)

**Status:** settled; being built in the order of §5. Step 1, removing the session log, landed in 8dd0673; steps 2–7 followed, the last on 2026-10-20. §1 and §2 record the tools as they were on 2026-10-18.

Draft 1 was by the main session; draft 2 was the critic's revision; this version folds in the owner's answers:
- **Sessions:** the agent can open a session in the app (`set_active_session`), and `create_session` opens what it creates.
- **Citations:** `cite_section` ships, citing PDF pages.
- **Editing:** `edit_note` may edit any note.
- **Session log:** dropped from the app; removing what's left of it came first (§5).
- **Moving:** the agent may move a note to another track.
- **Tracks:** the agent may create a new track.

Scope: the Command half of `sidecar/mcp_server.py` (8 tools). Legend Lore's six library tools are out of scope (page-label fixes are tracked separately).

Method:
1. Inventory every operation the app performs on a campaign: 38 Rust `command_*` commands over `sidecar/command/router.py`'s routes.
2. Map each operation to an MCP tool, or note that none exists.
3. Check the result against a real prep run (2026-10-18). An agent prepared the Isle of Mist finale of the Misty Vale campaign through MCP only. It wrote 50 notes and no beats.

The goal it's judged against: **an agent can prep a session end to end, and correct its own work.** Principles (CLAUDE.md, design `docs/roadmap/2026-10-11-command-design.md`):
- Ship less.
- The vault is Markdown and nothing else is truth.
- Writes are surgical, atomic and optimistic.
- Deletes go to the OS trash, through Rust only.
- Play state isn't written.

---

## 1. Inventory: what the app can do vs what MCP exposes

✔ exposed · ~ partly · ✘ missing · — not applicable

| Object | Read | Create | Change | Rename / move | Delete | Order / look |
|---|---|---|---|---|---|---|
| Campaign | ✔ `list_campaigns` (names, open one marked) | ✘ `/untitled` (the app never calls `POST /campaigns`) | — | ✘ `/campaigns/rename` | ✘ (Rust trash) | — |
| Open campaign and session | ~ every tool reads `GET /context` | — | ✘ `PUT /context` (Rust's push) | — | — | — |
| Track | ✘ `GET /tracks` (names leak only through `create_note`'s error) | ✘ `/tracks` | — | ✘ `/tracks/rename` | ✘ (Rust trash) | ✘ `/tracks/order`, `/tracks/pigment` |
| Note (incl. Shelf) | ✔ `read_note` (drops the hash the route returns), `find_notes` (20 hits, cut silently) ✘ list | ✔ `create_note` (no `source`; the app's Send to Command is `POST /send`) | ✘ `PUT /note` (hash) | ✘ `/notes/rename`, `/notes/move` | ✘ (Rust trash) | ✘ `/notes/order` |
| Beat | ~ `read_note` (raw frontmatter), `current_session` (planned ones) ✘ list | ✘ `POST /beats` (`create_note` refuses "Beats") | ✘ `/beats/members`; text as a note | (as note) | (as note) | ✘ `/beats/order` |
| Session: plan | ~ `current_session` (open, else latest) | ✘ `POST /sessions` | ✘ `/sessions/plan` (add, remove, move) | (as note) | (as note) | — |
| Session: log, jot | ~ `current_session` (log) | — | ✘ `/jot`; launch and spend append to the log | — | — | — |
| Spent | ~ `current_session`'s labels | — | ✔ `spend` | — | — | — |
| Live set | ✔ `live_set`, `current_session` | — | ✔ `add_to_live_set` ✘ take out (`/live/note live=false`), `/live/launch`, `/live/stop` | — | — | — |
| Board | ✘ `GET /board` | — | ✘ `POST /board` | — | — | — |
| Settings, places, copy-in | ✘ | ✘ `/notes/copy` | ✘ `/settings`, `/places` | — | — | — |

App internals with no MCP meaning: `/reopen`, `/campaigns/discard`, `/events`, `/locate`.

## 2. What hurt in the prep run

- **E1. No beats or plan.** An agent can write material but cannot assemble a session. `create_note("Beats", …)` is refused by design (`test_create_note_only_in_a_track`), and nothing replaces it.
- **E2. No way to list.** `find_notes("")` returns nothing. Enumerating meant searching for "e", which stops at 20 hits without saying so, on a campaign of 57 notes. Tracks were learned from `create_note`'s error message.
- **E3. No edit.** A wrong note can't be fixed, and a stub like Riddermound can't be filled. It has only an Electron-era header, and it's already spent.
- **E4. No session address.** `current_session` reads only the open (else latest) session. Another session's plan is reachable only as raw frontmatter through `read_note`.
- **E5. No citation.** All 50 notes cite pages in prose, and none carries `source`, so no Play card gets a book key. MCP prints only a book's filename, but the sidecar knows its path: `GET /api/section/{id}` returns it.
- **E6. Raw errors.** A name clash comes back as `Sidecar error: 409 — {"detail":"A note named 'X' already exists in this campaign"}`.
- **E7. Noisy snippets.** A snippet is cut around the first match anywhere in the file, so on Misty Vale's notes it opens with frontmatter (`--- name: … type: …`, `beats: - "[[…]]"`).

---

## 3. Recommendations

Two parts, each a partition of its own:
- **Part A, capabilities**, goes object by object. Each operation from §1 gets exactly one disposition here, including every change to an existing tool.
- **Part B, contract**, is the rules every Command tool keeps. It holds only work that spans tools; a single tool's share of a rule is listed in A, once.

Dispositions: **KEEP** · **CHANGE** (an existing tool) · **ADD** · **DEFER** (right, but a later pass) · **WON'T** (with a reason).

### A. Capabilities

#### A1. Campaign and its structure
- **A1.1 CHANGE** `list_campaigns` → `campaign_overview(campaign=None)`, which replaces it.
  - Its first line is today's `list_campaigns`: the campaigns, with the open one and its session marked. With nothing open, that's all it prints.
  - Then the structure, without text:
    - tracks in order, one line each, with their notes' names, spent ones marked;
    - the shelf and loose notes;
    - beats in their saved order, each with its notes and the sessions planning it;
    - sessions by date, with the planned count;
    - ambiguous names.
  - It's built on `GET /campaign` (`prep.index`). "Sessions planning it" is derived from it. There's no "played" mark: it came from the session log, which is gone. *Fixes E2.*
  - It replaces `list_campaigns` rather than joining it, so there's one first call, not two.
- **A1.2 ADD** `create_track(name, campaign=None)`: a new track at the end of the campaign's track order (`POST /tracks`). *(Owner's call.)*
  - The route already refuses reserved names (`Beats`, `Sessions`, `Shelf`) and any clash, ignoring case (`vault.create_track`).
  - A separate tool rather than a side effect of `create_note` or `move_note`, so a mistyped track name is refused instead of quietly becoming a new track.
- **A1.2b WON'T** create, rename or delete campaigns, or rename, delete, order or pigment tracks. These are the GM's, and a track rename rewrites links across the campaign.
- **A1.3 WON'T** switch the app's open campaign. A switch discards a blank Untitled, rebuilds the File menu, and pulls the GM's whole workspace away; the tools take `campaign=` instead. Opening a session within the open campaign is A4.4.

#### A2. Notes
- **A2.1 CHANGE** `read_note`: add a `hash:` line under the header. The route already returns the hash, and the tool drops it. `edit_note` needs it.
- **A2.2 CHANGE** `find_notes` (built 2026-10-20; a note found by its name alone shows its text's opening):
  - Take the snippet from the body. Matching still covers the frontmatter, which is how `find_notes("Ismark")` finds the beats that hold Ismark.
  - At 20 hits, say the list is cut and to narrow the query.
  - An empty query points to `campaign_overview`. *Fixes E7.*
- **A2.3 CHANGE** `create_note`:
  - Match the track case-insensitively, as the Shelf and note names already are.
  - Add `cite_section=<id from search_library>`. The tool reads `GET /api/section/{id}` for the PDF's path and first page, and the note gets the `source` and cite link that Send to Command writes. *Fixes E5.*
    - Route change: `POST /notes` takes optional `source` and `cite`, and builds them as `prep.receive` does. It keeps `/notes`' rules: a name clash or a bad character is refused. `/send` would rename silently instead: it numbers a clash and swaps bad characters for spaces.
    - The cite names PDF pages (owner's call: they're the more accurate). As built (2026-10-20), it reads *Book, PDF pp.120–121*, so it isn't taken for printed pages. Send to Command cites printed pages, so the two kinds of note cite differently; the book key opens the same page either way.
- **A2.4 ADD** `edit_note(name, content, hash)`: replace a note's text, hash-checked. *Fixes E3.*
  - Any note, the GM's included (owner's call).
  - `content` is the text below the frontmatter. The frontmatter is kept, so a beat's `notes`, a session's `beats` and `date`, `spent` and `source` stay with their own tools (B2.1).
  - If `content` opens with the note's frontmatter unchanged, the block is dropped and the edit goes through. A changed block is refused, and the refusal names the tool that changes that key.
  - It has one mode, the whole text. That fills a stub and fixes a line alike, and notes are short.
  - Route change: `PUT /note` gains this text-only mode and splices under the hash check. The sidecar already has the frontmatter parser (`frontmatter.split`), so it isn't copied into the MCP process.
  - The reply carries the new hash, so a second edit needs no read.
- **A2.5 ADD** `move_note(name, track)`: move a note to another track, or between the Shelf and a track (`/notes/move`). *(Owner's call.)*
  - It moves to an existing track (`create_track` makes a new one first, A1.2), and refuses `Beats` and `Sessions`.
  - The move rewrites path links (`[[Track/Name]]`) and every board that holds the note, as a drag in Prep does. The name is unchanged, so plain `[[Name]]` links aren't touched.
  - It replies with the new path.
- **A2.6 WON'T** rename, delete, or note order.
  - A rename rewrites links across the campaign; a name is the GM's.
  - Deletes go through Rust's trash (design §3.5.4).

#### A3. Beats
- **A3.1 ADD** `create_beat(name, notes=[], content="", session=None)`: a beat holding `notes`, with its scene in `content`. With `session`, it's appended to that session's plan (`POST /beats`).
  - Notes are named or given by path, and resolved as `read_note` resolves them. They must exist already, so notes come first.
  - Route change: `BeatCreate` and `prep.create_beat` take `content`, since a beat has a body (design §3.4).
  - The tool resolves `session` before posting. The route makes the beat before planning it, so a bad session would leave a beat behind, and a retry would then clash with it.
- **A3.2 ADD** `add_to_beat(name, beat, member=True)`: put a note in a beat, or take it out with `member=False` (`/beats/members`).
  - The name and order of its arguments follow `add_to_live_set(name)`, and the flag works like `spend(name, spent=False)`.
  - It replies with the beat's notes after the change.
- **A3.3 WON'T** beat order (presentation, `/beats/order`).

#### A4. Sessions
- **A4.1 CHANGE** `current_session(campaign=None, session=None)`: read any session by name. The default stays the open session, else the latest. Its Log section goes with the log (§5). *Fixes E4.*
- **A4.2 ADD** `create_session(campaign=None)`: the next `Session N`, dated today, with nothing planned (`POST /sessions`), opened in the app through A4.4, as the app's **+ New session** opens it.
  - The reply gives the new session's name, and says whether the app opened it (it can't when the app isn't running).
  - Each call makes another session.
- **A4.3 ADD** `plan_beat(name, planned=True, position=None, session=None)`: put a beat in a session's plan, or take it out with `planned=False` (`/sessions/plan`). The session defaults to the open one (B1.3).
  - `position` is 1-based, as `current_session` numbers the plan. A beat already in the plan moves there; with no position, it goes at the end.
  - The tool computes the route's `at` and `expect` from the plan it has just read.
  - It finds plan entries by their link, so it can remove one whose beat is gone. Misty Vale's Session 2 plans `[[beat 2]]` and `[[beat 3]]`, and `Beats/` is empty.
  - It replies with the plan after the change.
- **A4.4 ADD** `set_active_session(session)`: open a session of the open campaign in the app. *(Owner's call.)*
  - The path:
    1. A new sidecar route publishes an "open session" event on the stream Rust already relays (`command.rs:909`).
    2. A new branch in the relay calls the existing switch (`app_context.rs`'s `set_session` and `broadcast`).
    3. Every window follows, and Rust pushes the context back to the sidecar.
  - The tool waits until `GET /context` shows the session, with a short timeout, so its reply is true. With no app listening, it says so.
  - The open campaign's sessions only (A1.3).
- **A4.5 WON'T** the board. It's spatial arrangement in JSON Canvas, done by the GM's hand. Play auto-places what a plan holds.
  - *Lifted 2026-10-20*, once the GM had board tools of their own: `arrange_board`, `frame_cards`, `connect_cards` and `add_text` wrap them (the board toolbar's design, `2026-10-19-command-board-toolbar-design.md` §6, step 4).

#### A5. Play
- **A5.1 KEEP** `live_set`.
- **A5.1b CHANGE** `spend`: it stops writing to the session log (the log is gone, §5). It's a plain spent mark, as in Prep.
- **A5.2 CHANGE** `add_to_live_set(name, live=True)`: `live=False` takes the note out (`/live/note`). Every other agent write can be reversed (B2.2); this is the one that can't yet.
- **A5.3 DEFER** `launch_beat` (`/live/launch`), `stop` (`/live/stop`) and `jot` (`/jot`). They belong to play at the table, not prep, so they go in a Play pass. During prep, the session note's own text is written with `edit_note`.

#### A6. Settings, places, copy-in
- **A6.1 WON'T** any of it. App configuration stays in the app. To reuse another campaign's note, the agent can `read_note(campaign=…)`, then `create_note`.

### B. Contract (applies to every Command tool)

#### B1. Addressing
- **B1.1 KEEP:** notes, beats and sessions are named as a wikilink names them, with the path to disambiguate. The campaign defaults to the open one.
- **B1.2** Names match case-insensitively everywhere, tracks included (A2.3).
- **B1.3** The session defaults to the open one, else the latest, for reads and plan writes alike. That's safe because `create_session` and `set_active_session` change what's open in the app (A4.2, A4.4). `create_beat` plans only when given a session.

#### B2. Writes
- **B2.1** After creation, each key Command owns (`notes`, `beats`, `date`, `spent`, `source`) has one writer: its own tool. `edit_note` writes text only. `date` has no tool: it's the GM's.
- **B2.2** Every write can be reversed through the same tool: `spent=`, `member=`, `planned=`, `live=`, or another edit. Creating can't be: only the GM trashes, through Rust.
- **B2.3** Writes are optimistic. Text is checked by hash (`edit_note`), and plans by `expect`, which `plan_beat` computes. Membership, spend and the live set are single-key writes under the sidecar's lock.
- **B2.4** Membership, adding to a plan, spend and the live set are idempotent, because the routes check first. Creating isn't, so a retried create meets the note it already made (B3.2).
- **B2.5 KEEP, extended:** every write replies with what it left: the path, the new hash after an edit, and a beat's notes or a plan after a change.

#### B3. Errors
- **B3.1 CHANGE:** unwrap sidecar errors to their `detail` in `SidecarClient` (`get`, `post`, and a new `put`). *Fixes E6.*
- **B3.2 CHANGE:** each of the three refusals names a next step:
  - Name clash: "A note named X already exists (path). If you just made it, it's there: read_note it. Otherwise pick another name." This covers retries.
  - Stale hash: "X changed since you read it. read_note it again."
  - Stale plan: "Session N's plan changed. current_session(session=…) and retry."

#### B4. Output
- **B4.1 KEEP:** plain text, compact, one item per line.
- **B4.2** Lists carry names, never note text, and a capped list says it's cut (A2.2). `campaign_overview` prints one line per track, so a 500-note campaign comes to a few thousand tokens. **DEFER** a `track=` filter until a real campaign needs one.

#### B5. Guidance
- **B5.1 CHANGE** the server instructions to add a prep recipe:
  1. `campaign_overview`, then `current_session` for the plan.
  2. Write notes into tracks, each citing the section it came from. When no track fits, `create_track` if the material is a kind the campaign will keep using (Factions, say), else the Shelf.
  3. `create_session` if the next session doesn't exist yet (it opens in the app), or `set_active_session` to open the one that does.
  4. `create_beat` in play order, one at a time. The plan takes beats in the order calls arrive, so parallel calls scramble it.
  5. Fix with `edit_note`, `move_note`, `add_to_beat` and `plan_beat`. Renames and deletes are the GM's: say what should change.
  - Names are unique within their kind: a beat may share a note's name, never another beat's (design §3.2, since 2026-10-19).
- **B5.2 CHANGE:** each new tool's docstring names its neighbour (`create_beat` → `plan_beat`, `read_note` → `edit_note`).

---

## 4. A 12-beat session, call by call

| Step | Calls | Count |
|---|---|---|
| Look | `campaign_overview()`, `current_session()` | 2 |
| Research | `search_library`, `get_section` (Legend Lore) | — |
| Write | `create_note(track, name, content, cite_section=…)` per note, in parallel | ~30 |
| Fill | `read_note` + `edit_note` per existing note (Riddermound, an NPC) | ~4 |
| Session | `create_session()` → Session 4, opened in the app | 1 |
| Beats | `create_beat(name, notes=[…], content=…, session="Session 4")`, one at a time | 12 |
| Check | `current_session()` | 1 |

That's about 50 calls. One call per note and one per beat is the floor, and everything else adds 8. A correction costs one call (`add_to_beat`, `plan_beat`, `move_note`) or two (`read_note` + `edit_note`).

Where the agent can still get stuck:
- **Beats take 12 turns.** The plan is ordered, so beats are made one at a time. A whole-plan setter would cut that to one call. **DEFER** until a run shows the turns hurt.
- **Some mistakes wait for the GM:** a wrong name, or a note that shouldn't exist. The agent says what to change.
- **A beat can't hold a note that isn't written yet.** The route refuses, so notes come first.

---

## 5. Net result

### First: remove what's left of the session log (its own commit, done in 8dd0673)
The app no longer showed the log, but it still wrote and read it:
- Play launches write `▶ [[beat]]` (`PlayView.svelte:226` → `router.py:597`).
- Play spends write `spent [[X]]` (`CommandPanel.svelte:545` → `router.py:560`).
- MCP `spend` writes them, and `current_session` prints a Log section.
- The Help guide still says spends go under `## Log` (`CommandGuide.svelte:57`).
- `prep.index` parses the log (`prep.py:90`, `log.parse`), and `types.ts` types it.
- Design §4 describes it.

Existing `## Log` sections in old session notes stay on disk as plain text. Jot stays: it writes the session note's own text, not log lines.

### Then the MCP work
- **Command tools: 8 → 16** (22 with Legend Lore's six).
  - Added: `create_track`, `edit_note`, `move_note`, `create_beat`, `add_to_beat`, `create_session`, `set_active_session`, `plan_beat`.
  - `campaign_overview` replaces `list_campaigns`.
  - New params: `current_session(session)`, `create_note(cite_section)`, `add_to_live_set(live)`. `spend` stops logging.
- **Sidecar route changes: four.** Three are optional fields: `BeatCreate.content`, the text-only mode of `PUT /note`, and `NoteCreate.source`/`cite`. The fourth is a new route that publishes the "open session" event.
- **Rust:** one new branch in the event relay (`command.rs`), calling `app_context`'s existing session switch.
- **`SidecarClient`** gains `put` and unwraps `detail`.
- **Tests:** in `tests/test_mcp_command.py`, update the `COMMAND` set and add one test per new tool. Also test that:
  - `edit_note` refuses a stale hash, and keeps a beat's `notes`;
  - `create_beat` with a bad session makes nothing;
  - `plan_beat` removes a dangling entry;
  - `move_note` refuses `Beats` and `Sessions`;
  - `create_track` refuses a reserved name and a clash in another case;
  - `set_active_session` with no app listening says so.

  The Rust branch gets a unit test beside `app_context`'s.
- **Docs:** design §8's tool list and its "fourteen tools", plus §6.2 (MCP can now ask Rust to open a session).
- **Order of work:**
  1. Remove the session log (above).
  2. B3, and `campaign_overview`.
  3. `read_note`'s hash, and `edit_note`.
  4. `create_beat`, `add_to_beat`.
  5. `set_active_session`, `create_session`, `plan_beat`, `current_session(session)`. Then, asked for after the step, names unique within their kind, so a beat may be named after its place (design §3.2, §3.3).
  6. `create_track` and `move_note`, plus the small changes: `find_notes`, `create_note`'s track case, `add_to_live_set`.
  7. `cite_section`.
- **Deferred:** `launch_beat`, `stop` and `jot` (a Play pass); a whole-plan setter; `campaign_overview(track=)`.

## 6. Open questions

None. Every disposition above is settled.
