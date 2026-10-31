# Unseen Servant Development Guide

## Product Vision

Unseen Servant is a local-first, desktop workstation for tabletop RPG Gamemasters (GMs). It reimagines the VTT experience for live play at the table and invites GMs to embrace improvisation with flexible session prep.

### Target User

A TTRPG Gamemaster who:

- Owns a large PDF library (hundreds to thousands of rulebooks, supplements, and adventures)
- Needs to find specific rules, tables, or lore quickly during session prep and live play
- Wants AI assistance to find rules and to prepare sessions from published or homebrew content
- Values privacy and authors' copyrights: the library stays on their machine, not in the cloud

### Core Philosophy

1. **Local-first**: All content and inference stay on the GM's machine, with the limits and tradeoffs that brings. No PDFs leave it.
2. **No platform or format lock-in**: Everything a GM builds stays readable on their machine after they stop using Unseen Servant. Obsidian is the model here.
3. **Enabler for improvisation**: Many design elements come from DAWs and the other tools musicians use to play live. A GM's work in prep and at the table has much in common with theirs.

---

## Related repositories

unseen-servant-site is private for now.

- **[unseen-servant-spikes](https://github.com/Unseen-Servant/unseen-servant-spikes)**: research spikes. Their FINDINGS inform key architectural decisions here. Docs that cite a spike link its FINDINGS and still state the outcome.
- **unseen-servant-site**: the landing page, which distributes the app. Its product description must match the app's actual features.

---

## Continuous Integration

### What runs when

- **PR + push to `main` (`ci.yml`):** Linux-only, path-gated on PR.
- **Tag push `v*` (`release.yml`):** the macOS + Windows build, codesign, and draft GitHub Release. This _is_ the cross-platform validation — there is none on main. Publishing the draft runs `publish-release.yml`, which copies it to R2.

### Rules for changing CI

1. **No macOS/Windows jobs on PR or push-to-main.** They are slow. Before adding one, answer "what will this catch that Linux + the next release tag won't?" — the answer needs to justify slower feedback on every push.
2. **Release-time regressions are acceptable.** If a cross-platform bug only surfaces at tag push, fix forward and bump the patch version. Re-tagging an unpublished draft once is fine; if a second fix lands, bump the patch.
3. **Local validation is the dev's responsibility.** Before tagging a release that touches build config, `src-tauri/`, sidecar deps, the models or the build scripts, run `npm ci`, `bash scripts/build-sidecar.sh`, `bash scripts/build-llama-server.sh`, `node scripts/fetch-models.mjs`, then `npm run tauri build` locally.

### Commit workflow

Solo dev, trunk-based without PRs: commit directly to `main` and push. CI runs the full Linux suite on every push to main — check that it's green before tagging a release. Releases are `v*` tags cut from main whenever the tree is in a good state.

PRs are the exception, not the rule — reserve them for changes that benefit from a review pass or CI-before-merge (e.g. risky CI or build-config changes). When a PR is used, keep it single-purpose and don't stack it on another open PR.

Branches are named `type/short-name`, the type matching the commit's: `feat/`, `fix/`, `hotfix/`, `refactor/`, `ci/`, `chore/`, `docs/` (e.g. `feat/i18n-shell`).

---

## Writing Voice

The CHANGELOG and the GitHub release notes use Simplified Technical English.

- Short declarative sentences, present tense, active voice. Instructions are imperatives.
- Say what changed and what it gives users. Leave out rationale and internals; the how-to belongs in Help → Guides.
- Speak of users in the third person, never "you" or "your": "existing indexes stay valid", "users do not need to index their books again".
- Use plain verbs ("is in the app", "does not need"). No slogans, taglines or bold headline sentences.
- Each release opens with one summary paragraph, then one line per change: a bold lead and one clause. CI, dependency and build-tooling changes stay out.
- The release notes are the CHANGELOG section: set the draft with `gh release edit vX.Y.Z --notes-file`.

---

## Guidelines

- **Ship less:** nothing beyond the request — no speculative features, abstractions, or configurability.
- **Surgical changes:** every changed line traces to the request. Match the surrounding style; remove what your own change orphaned, and mention unrelated dead code rather than deleting it.

---

## Design Conventions

Tokens live in `src/app.css` `:root`, and the app code is the source of truth. The look is an old-school instrument panel, not SaaS: panels are headed by flat **plates** (`.nameplate`), controls are **keys** set in **wells** (`--bg-app` with a `--border-subtle` edge), state shows on **lamps** (small LEDs, a dark slot when off), and labels read like **readouts**. Fantasy flavor stays quiet — glyphs and warm materials, never ornament (no rivets, engraving, gradients, or display fonts).

- **Reuse before writing CSS:** the `app.css` primitives (`.action-btn`, `.plate-btn`, `.sm-btn`, `.nameplate`, `.menu-row`, `.app-checkbox`) and `src/lib/ui/` (`ActionButton`, `LatchKey`, `CommitSwitch`, `RenameField`, `ConfirmDialog`).
- **Color is meaning:** purple (`--text-active`, `--bg-active`) is a mode the user switched on; parchment/brass (`--text-accent`) is content or data; amber (`--text-connected`) is a lamp reporting connectivity; red (`--text-danger`) is removal or destruction, a hue swap on the same shape. A key's raised fill (`--bg-header`) marks what is open — a view, not a mode; the tool with the keyboard shows it on its frame edge (`--border-frame-keyed`), not on a key.
- **Text ramp:** `--text-primary` / `--text-secondary` / `--text-tertiary` carry rank. Unavailable steps down the ramp rather than fading. Don't narrow the steps to chase contrast: the secondary/tertiary gap is what separates `.readout-label` from `.ledger-label`.
- **Glow, hover, press:** glows (`--glow-active`, `--glow-accent`) mark activated states only. Hover never glows or adds a hue — it brightens or fills a grey step. Press is a 0.97 scale tick.
- **No filled-rectangle buttons:** actions are text or icons that gain color, glow, or brackets.
- **Bracket labels are lowercase:** `[sync]`, `[copy MCP config]` — proper nouns and acronyms keep their capitals, so write the label lowercase rather than `text-transform` it.
- **Copy lives in `messages/en.json`** (Paraglide, compiled to the git-ignored `src/lib/paraglide`): components call `m.key()`; tables hold the message function (`label: m.key`) and call it at render; inline emphasis is message markup (`{#em}…{/em}`) rendered with `ParaglideMessage`. Tool names, the wordmark, key names and `console` logs stay in code; a trailing key hint (`(S)`, `chordHint()`) is added after the message, never written into it. Counts take a plural variant (`local countPlural = count: plural`), never `n === 1 ? '' : 's'`. The native menus in `src-tauri/` are not in it yet.
- **Type:** serif throughout — Crimson Text body, Almendra headings — with `--font-mono` for code-flavored affordances and `--font-readout` (IBM Plex Mono, the site's mono) for a readout that spells words. Titles and labels take a header voice (`.section-title`, `.ledger-label`, `.readout-label`, `.micro-label`) rather than a new size. Numeric readouts use `tabular-nums`.
- **One row height:** every plate and clickable list row is 1.65rem, in every tool.
- **Drags:** the row is the handle (no ⠿ grips), and drag sources use `use:grab` (`src/lib/ui/grab.ts`), never `draggable`.
- **Drive the existing surface:** a new input acts on what is already on screen (dim, ring, badges) rather than opening a popover that lists it again.
- **One vocabulary across tools:** an idiom ported from Legend Lore to Command copies its geometry, colors, and side effects verbatim. A panel's key sits on the side the panel opens.
- **Tokens only:** every color, radius, and shadow comes from a token in `src/app.css` — add one rather than a raw value. Tint washes use `color-mix(in srgb, var(--token) N%, transparent)`. Stylelint (`npm run lint:css`) enforces the color rule.
