# Headings from the PDF outline

**Date:** 2026-09-27 · **Status:** draft for approval, amended 2026-09-27 after a survey of Jerome's 3,293-PDF collection (§2.1: size-relative gate, collection-wide validation); supported by the heading ablation (roadmap `2026-09-26-search-ux-informed-retrieval.md` §10: headings are a strong ranking signal, and entity names and correct ancestors are what matter)
**Context:** roadmap `../roadmap/2026-09-26-search-ux-informed-retrieval.md` item 3, measured in its §9: 122 of 240 sampled units (51 %; ≈ 33 % of the library by volume) carry a wrong or misleading heading path. The path is shown as the result's title and prepended to the text that is embedded and reranked, so a wrong path misleads twice.

---

## 1. Goal

Build each unit's heading path from the publisher's PDF outline when the book has a trustworthy one, keep font-detected headings only as detail *inside* an outline entry, and stop promoting lines that are not headings. General rules only: nothing keyed to a book, a system or a title.

**Success criteria**

- The mis-heading rate on the held-out sample (§6) drops for every outlined book, with no book worse; books without an outline are no worse.
- Retrieval: the corpus suite and the library tier do not regress in any scope against `2026-09-26-v2-cue-strip` / `2026-09-26-v2-library-cue-strip`; every per-query loss is explained.
- On the stratified 40-book collection sample (§6), the mis-heading rate drops in both outline bands and is no worse in the unplaceable-outline and no-outline bands.
- `breadcrumb_qa` flaw counts and the extraction golden pages do not regress (they are tripwires, not the target).

**Non-goals** (each a recorded follow-up, not an oversight):

- **Books without a usable outline** get only the junk filter. They hold about a quarter of the collection's text (§2.1: 13 % of pages have no outline, 11 % have one that does not match its pages); SRD 5.1's unclosed parents such as "Ability Scores and Modifiers" are this class. A font-side fix for them is the next heading item.
- **Scanned books** (454 PDFs, 14 % of books, 1.8 % of pages) have no text layer, so nothing in them is searchable today; #392.
- Sidebars that the outline does not list (the Bestiary's Random Encounter / Adventure Seed boxes); any change to chunk sizes or the parents grouping.

## 2. What the outlines look like

Measured with `Document.get_toc(simple=False)` on the six library books and the eval corpus:

| book | pages | entries | depth | title on its page (exact) | y-position | box entries |
|---|---|---|---|---|---|---|
| OSRIC 2E | 412 | 1,228 | 6 | 97 % | 0 % | 4 |
| Dragonbane Rulebook | 132 | 659 | 5 | 73 % | 99 % | 101 |
| Dragonbane Adventures | 120 | 444 | 5 | 53 % | 86 % | 55 |
| Dragonbane Bestiary | 156 | 360 | 3 | 71 % | 99 % | 11 |
| Wight-Box | 153 | 192 | 4 | 49 % | 100 % | 1 |
| Basic Fantasy (corpus) | 208 | 519 | 3 | 100 % | 100 % | 1 |
| SRD 5.2.1 (corpus) | 364 | 520 | 4 | 94 % | 98 % | 0 |
| OSRIC (corpus) | 404 | 780 | 5 | 98 % | 0 % | 0 |
| YZE SRD (corpus) | 45 | 326 | 4 | 83 % | 98 % | 49 |
| SRD 5.1, Black Hack, Cairn | — | 0–2 | — | no usable outline | | |

The low exact matches are mostly systematic, not broken outlines: Dragonbane titles carry editorial prefixes the page does not print ("NPC: Master Ulvar", "Table: Rumors", "Monster: Okvid the Troll", "Map: The Roof"), and Wight-Box titles are usually present word for word but not as one phrase (two-column interleaving). A handful are absent from the page entirely.

### 2.1 Across the collection

The same reading (`evals/.eval_data/outline_survey/survey.py`, read-only, results kept locally) over all 3,293 PDFs in Jerome's collection (178,489 pages, ~30 game lines):

| | books | pages |
|---|---|---|
| outline passing the draft gate (≥ 20 entries, ≥ 2 levels, ≥ 70 % placed) | 865 (26 %) | 114,711 (64 %) |
| outline with < 20 entries | 495 (15 %) | 23,238 (13 %) |
| outline flat, or < 70 % placeable | 113 (3.5 %) | 13,981 (8 %) |
| no outline | 1,366 (41 %) | 23,258 (13 %) |
| scan, no text layer | 454 (14 %) | 3,301 (1.8 %) |

By books fewer than half have an outline, but by volume 85 % of the text is in books that do: core books, bestiaries and anthologies ship outlines, while the books without one average 17 pages (maps, handouts, sheets, zines). Where an outline passes the size and depth checks it is almost always placeable (median 97 % of entries; only 47 books fail on placement). Coverage varies by line and publisher (Savage Worlds 65 % of books, OSRIC 68 %, WFRP 58 %; FLAIL 3 %, Shadowdark 16 %).

Gate options, measured on the same data (share of all pages whose book uses its outline):

| gate | pages |
|---|---|
| draft: ≥ 20 entries, ≥ 2 levels, ≥ 70 % placed | 64.3 % |
| ≥ 5 entries and ≥ 1 per 10 pages, ≥ 2 levels | 65.0 % |
| ≥ 5 entries, any depth | 73.8 % |
| **≥ 5 entries, any depth, entries span ≥ 50 % of the book** | **73.6 %** |
| any outline that places ≥ 70 % (the ceiling) | 74.0 % |

The draft's ≥ 20-entry and ≥ 2-level requirements cost ten points of coverage for no stated safety: a coarse or flat outline still supplies chapter boundaries, which is what closes stale parents, and detected headings still add the detail below it. The one real danger of a small outline is one that lists only front matter ("Cover, Credits, Contents"), whose last entry would stay open over the whole book — the span rule rejects those (6 books). A stricter "no gap over 25 % of the book" rule would drop 103 books, 26 of them deep outlines, and is not needed: an unsubdivided long chapter is still the right parent for what is inside it.

## 3. Design

Everything lives in `promote_headings.py` (the `toc_then_font` strategy becomes `outline`), plus two small chunker changes. The chunker's heading stack stays: the design only changes which lines are headings and what level each gets, and the stack then does the right thing by construction.

### 3.1 Trust gate (per book)

Use the outline only when all hold; otherwise fall back to today's `toc_then_font` unchanged (§2.1 for the measurements behind each):

- **at least 5 entries** (not counting the lone book-title entry that `build_toc_levels` already discounts), at any depth;
- **placement rate ≥ 70 %**: entries that §3.2 can place on their page or an adjacent one;
- **the entries span at least half the book** (first to last entry page ≥ 50 % of the page count), so a front-matter-only outline cannot leave its last entry open over the rest.

### 3.2 Placing an entry

For each outline entry, strip a leading `Label:` prefix of one or two words (`NPC:`, `NPCs:`, `Monster:`, `Table:`, `Map:`, `Sidebar:`) and match the rest on its page, then the page after, then the page before (the existing `build_toc_levels` order), by token overlap ≥ 50 % of the title's tokens:

1. **against the page's detected heading lines** (today's matching, extended from depth 1 to every depth) — the line takes the entry's level;
2. **else against the page's body lines** — the line is *promoted* to a heading at the entry's level. This is what recovers missed entry headings ("the thunderstroke spell filed under RESURRECTION");
3. **else the entry is unplaced** and skipped (counted in the report). No heading is invented at an arbitrary position: a wrong position is worse than a missing heading.

The y-position the outline carries is not needed for this and is not used; OSRIC has none, and text matching already works there.

### 3.3 Levels

- An outline entry at relative depth *d* gets level *d*.
- **Box entries are leaves:** an entry whose title had a `Label:` prefix, or whose title contains the word "table", gets the deepest level in use, so it is closed by the next heading of any kind and can never parent what follows. This generalises the reason `toc_then_font` ignored depth ≥ 2 (Basic Fantasy's "Cloud Dragon Age Table" parenting every later monster) into a rule instead of a blanket exclusion.
- **Detected headings the outline does not list** keep their font-cluster order but are shifted below the outline: level = (outline depth in use) + (their font-cluster level). They are therefore always children of the current outline entry and are always closed by the next outline entry — a "MENTALISM" can no longer stay open over the Gear chapter, and a "Level 5 Cleric Spells" cannot run to the end of the book.
- A flat (one-level) outline works the same way: its entries take level 1 and every detected heading sits at level 2 or deeper.
- The chunker's `_HEADING_RE` accepts `#{1,9}` instead of `#{1,6}` (OSRIC's outline is 5 relative levels deep, plus detected detail below it).

### 3.4 Junk filter (all books)

`is_junk_heading` also rejects, for every book with or without an outline:

- **attribution lines** — starting with a dash (`-`, `–`, `—`) followed by text containing a comma ("– Kaspert Woodshot, gamekeeper");
- **label–value lines** — two or more `Word: value` pairs ("Ferocity: 2 Size: Small");
- **sentences** — ending in `.`, `?` or `!`, or wrapped in quotes ("wights.", "Is the dungeon to the north of here?").

A rejected line stays in the text as body; it just stops being a heading. An outline-placed line (§3.2) is never rejected by this filter: the publisher's outline outranks the heuristics.

### 3.5 Report

The existing promotion report gains, per book: whether the outline was trusted, the placement rate, entries placed as existing headings vs promoted body lines vs unplaced, box entries, and junk rejections by rule. Printed during indexing like today's `[cleanup]` / promotion lines.

## 4. Pipeline and reindex

`CHUNKER_VERSION` → `structure_aware-v4`, so every book shows as outdated and Jerome reindexes when he chooses. Nothing else about indexing changes.

## 5. Risks

- **A wrong outline is now trusted.** The gate (§3.1) and the box-entry rule (§3.3) are the defences; the held-out judging, the collection sample (§6) and the corpus suite (which includes Basic Fantasy) are the checks.
- **Small outlines are trusted too.** 254 books enter through the relaxed gate (median 36 pages, 14 entries). Their own band in the collection sample (§6) checks them.
- **Over-promotion of body lines (§3.2 step 2)** — e.g. an entry title that also appears in an earlier sentence on the same page. Mitigation: prefer a line that is short (≤ 12 words) and whose tokens the title covers; report counts per book.
- **Box entries' text continues after the box** until the next heading, under the box's name. Accepted; measured.

## 6. Validation

**Pre-registered now, before any code:** the held-out sample is drawn with `random.Random(20260928)` — 40 units per book from the current library store, **disjoint** from the §9 sample — and stored locally beside it (`evals/.eval_data/heading_audit/`). Nobody reads it before the change is built.

After the change and Jerome's reindex:

1. **Development set** — the §9 sample's texts, located in the new index by their opening text, re-judged with the same rubric.
2. **Held-out set** — the `20260928` texts judged twice with the same rubric, old heading and new heading, so the comparison is on texts the design never saw.
3. **Retrieval** — the corpus suite (fresh index, `--hybrid`) against `2026-09-26-v2-cue-strip`, the library tier against `2026-09-26-v2-library-cue-strip`; per-query losses explained.
4. **Collection sample** — generalisation beyond the six indexed books. **Pre-registered now:** 40 books drawn with `random.Random(20260929)` from the survey (text layer, ≥ 8 pages), 10 per band — deep outline, small or flat outline, unplaceable outline, no outline — stored as `evals/.eval_data/heading_audit/collection_books_20260929.json` and not opened before the change is built. Headings come from chunking alone (no embedding, no Ollama), so each book is chunked with the old and the new pipeline, the same seeded units are drawn from each, and old and new headings are judged with the §9 rubric.
5. **Tripwires** — `breadcrumb_qa` per-book flaw counts and the extraction golden pages.

## 7. Commit sequence

1. Held-out sample and collection book sample drawn and stored (local only); this note committed.
2. Junk filter (§3.4) with tests — useful alone, affects books without an outline too.
3. Outline placement, levels and the gate (§3.1–3.3, 3.5) with tests on synthetic outlines; `CHUNKER_VERSION` bump.
4. Corpus suite and tripwires on a fresh eval index; then, after Jerome's reindex, the heading judging and the library tier; roadmap §9 and CHANGELOG.
