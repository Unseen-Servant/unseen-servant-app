# Unseen Servant Development Guide

## Product Vision

Unseen Servant is a local-first, desktop workstation for tabletop RPG Gamemasters (GMs). It reimagines the VTT experience for live play at the table and invites GMs to embrace improvisation with flexible session prep.

### Target User

A TTRPG Gamemaster who:

- Owns a large PDF library (hundreds to thousands of rulebooks, supplements, and adventures)
- Needs to find specific rules, tables, or lore quickly during session prep and live play
- Wants AI assistance for finding rules, preparing live sessions from either published or homebrewed content.
- Values privacy, their library stays on their machine, not in the cloud, and respectful of authors' copyrights.

### Core Philosophy

1. **Local-first**: All content and inference work are done locally on a machine, which means dealing with all the limitation and tradeoffs that it brings. No PDFs leave the GM's machine.
2. **No platform or format lock-in**: All the content that GMs are building remains accessible and readable on their machines after they are done using Unseen Servant. Obsidian is the obvious inspiration here.
3. **Enabler for improvisation**: Many design elements take inspiration from DAWs and other tool used by musicians for live session. I see many similarity with a GM's role and responsibilities during prep and live play.

---

## Related repositories

- **unseen-legend-lore-experiments** ('~/code/unseen-legend-lore-experiments', private) - Research spikes for Legend Lore. _Relationship:_ FINDINGS inform key architectural decision in Legend Lore. Docs that cite a spike's FINDINGS carry the outcome themselves; the spike code is not public.
- **unseen-servant-site** ('~/code/unseen-servant-site') - Landing page of Unseen Servant. _Relationship:_ the app is distributed through the landing page. Product description needs to match actual code and features.

---

## Continuous Integration

The repo is public, so GitHub Actions minutes are free, macOS and Windows included. CI still keeps the cross-platform builds off the everyday path by choice: they are slow, and Linux plus the next release tag catches what they would.

### What runs when

- **PR + push to `main` (`ci.yml`):** Linux-only, path-gated on PR.
- **Tag push `v*` (`release.yml`):** the macOS + Windows build, codesign, and draft GitHub Release. This _is_ the cross-platform validation — there is none on main. Publishing the draft runs `publish-release.yml`, which copies it to R2.

### Rules for changing CI

1. **No macOS/Windows jobs on PR or push-to-main.** If you're tempted to add one, the question is "what will this catch that Linux + the next release tag won't?" — and the answer needs to justify slower feedback on every push.
2. **Release-time regressions are acceptable.** If a cross-platform bug only surfaces at tag push, fix forward and bump the patch version. Re-tagging an unpublished draft once is fine; if a second fix lands, bump the patch.
3. **Local validation is the dev's responsibility.** Before tagging a release that touches build config, `src-tauri/`, sidecar deps, or the build scripts, run `npm run tauri build` and `bash scripts/build-sidecar.sh` locally.

### Commit workflow

Solo dev, trunk-based without PRs (since 2026-07-03): commit directly to `main` and push. CI runs the full Linux suite on every push to main — check that it's green before tagging a release. Releases are `v*` tags cut from main whenever the tree is in a good state.

PRs are the exception, not the rule — reserve them for changes that benefit from a review pass or CI-before-merge (e.g. risky CI or build-config changes). When a PR is used, keep it single-purpose and don't stack it on another open PR.

Branches are named `type/short-name`, the type matching the commit's: `feat/`, `fix/`, `hotfix/`, `refactor/`, `ci/`, `chore/`, `docs/` (e.g. `feat/i18n-shell`).

---

## Guidelines

- **Ship less:** nothing beyond the request — no speculative features, abstractions, or configurability.
- **Surgical changes:** every changed line traces to the request. Match the surrounding style; remove what your own change orphaned, and mention unrelated dead code rather than deleting it.

---

## Design Conventions

Tokens live in `src/app.css` `:root`; the app code is the source of truth (the claude.ai/design "Unseen Servant" project follows it). The look is an old-school instrument panel, not SaaS: panels are headed by flat **plates** (`.nameplate`), controls are **keys** set in **wells** (`--bg-app` with a `--border-subtle` edge), state shows on **lamps** (small LEDs, a dark slot when off), and labels read like **readouts**. Fantasy flavor stays quiet — glyphs and warm materials, never ornament (no rivets, engraving, gradients, or display fonts).

- **Reuse before writing CSS:** the `app.css` primitives (`.action-btn`, `.plate-btn`, `.sm-btn`, `.nameplate`, `.menu-row`, `.app-checkbox`) and `src/lib/ui/` (`ActionButton`, `LatchKey`, `CommitSwitch`, `RenameField`, `ConfirmDialog`).
- **Color is meaning:** purple (`--text-active`, `--bg-active`) is a mode the user switched on; parchment/brass (`--text-accent`) is content or data; amber (`--text-connected`) is a lamp reporting connectivity; red (`--text-danger`) is removal or destruction, a hue swap on the same shape. A key's raised fill (`--bg-header`) marks what is open — a view, not a mode; the tool with the keyboard shows it on its frame edge (`--border-frame-keyed`), not on a key.
- **Text ramp:** `--text-primary` / `--text-secondary` / `--text-tertiary` carry rank. Unavailable steps down the ramp rather than fading. Don't narrow the steps to chase contrast: the secondary/tertiary gap is what separates `.readout-label` from `.ledger-label`.
- **Glow, hover, press:** glows (`--glow-active`, `--glow-accent`) mark activated states only. Hover never glows or adds a hue — it brightens or fills a grey step. Press is a 0.97 scale tick.
- **No filled-rectangle buttons:** actions are text or icons that gain color, glow, or brackets.
- **Bracket labels are lowercase:** `[sync]`, `[copy MCP config]` — proper nouns and acronyms keep their capitals, so write the label lowercase rather than `text-transform` it.
- **Copy lives in `messages/en.json`** (Paraglide, compiled to the git-ignored `src/lib/paraglide`): components call `m.key()`; tables hold the message function (`label: m.key`) and call it at render; inline emphasis is message markup (`{#em}…{/em}`) rendered with `ParaglideMessage`. Tool names, the wordmark, key names and `console` logs stay in code. Migrated so far: `src/lib/shell/`.
- **Type:** serif throughout — Crimson Text body, Almendra headings — with `--font-mono` for code-flavored affordances. Titles and labels take a header voice (`.section-title`, `.ledger-label`, `.readout-label`, `.micro-label`) rather than a new size. Numeric readouts use `tabular-nums`.
- **One row height:** every plate and clickable list row is 1.65rem, in every tool.
- **Drags:** the row is the handle (no ⠿ grips), and drag sources use `use:grab` (`src/lib/ui/grab.ts`), never `draggable`.
- **Drive the existing surface:** a new input acts on what is already on screen (dim, ring, badges) rather than opening a popover that lists it again.
- **One vocabulary across tools:** an idiom ported from Legend Lore to Command copies its geometry, colors, and side effects verbatim. A panel's key sits on the side the panel opens.
- **Tokens only:** every color, radius, and shadow comes from a token in `src/app.css` — add one rather than a raw value. Tint washes use `color-mix(in srgb, var(--token) N%, transparent)`. Stylelint (`npm run lint:css`) enforces the color rule.
