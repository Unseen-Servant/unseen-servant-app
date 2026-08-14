# What Building an Agent Revealed About Retrieval

**Date:** 2026-08-14
**Status:** Findings. Input to the search-quality workstream.
**Origin:** The [Unseen Servant](../design/2026-08-09-unseen-servant-design.md)
agent harness, built end to end and then paused. The harness itself works; what
it exposed is that retrieval is not yet good enough to carry it.

## The reframe

An agent is a harsher retrieval evaluator than the UI, and a more honest one.

The search view gives results to a human who scans a ranked list, reads the tier
badges as a rough hint, ignores the obvious junk, and clicks the one that looks
right. Almost all of that is *the GM compensating for retrieval*. None of it is
available to a 2.3B model: it consumes the whole result set as flat context, has
no positional intuition, cannot tell a plausible-but-wrong section from the right
one, and has no way to skip anything.

So the agent measures a property the eval harness does not: **is the retrieval
output sufficient on its own?** nDCG@10 says the right chunk is *in* the list.
The agent asks whether the list, as a whole, is something you could answer from
without already knowing the answer.

That is the durable finding. It outlives the agent work: it is a lens for the
search workstream regardless of whether the Servant is ever resumed.

## Measurements

Ten GM-phrased questions against the real library — 6 books, 24,866 chunks — at
`n_results=15`, on `main` (`0cd0643`). Reproduce with
`sidecar/evals/library_probe.py`.

| Query | strong | good | weak |
|---|---|---|---|
| falling damage | 12 | 1 | 2 |
| how does grappling work | 7 | 4 | 4 |
| rules for surprise in combat | 9 | 1 | 5 |
| what happens at zero hit points | **15** | 0 | 0 |
| how do I roll initiative | 12 | 2 | 1 |
| encumbrance and carrying capacity | 5 | 2 | 8 |
| rules for underwater combat | 4 | 5 | 6 |
| how does darkvision work | 9 | 6 | 0 |
| sneak attack damage | 5 | 2 | 8 |
| what does a critical hit do | **15** | 0 | 0 |
| **total (150 results)** | **93 (62%)** | 23 (15%) | 34 (23%) |

### 1. Tier calibration carries almost no information

62% of everything returned is `strong`, and two queries returned 15/15 strong. A
label applied to nearly two thirds of results does not discriminate.

This is survivable in the UI — rank order still sorts the list, and the GM reads
top-down. It is not survivable for an agent: the tiers are the only per-result
quality signal in the tool output, and "everything is strong" tells the model
nothing about which of fifteen passages to trust. The
`--- Results below this line scored poorly ---` divider in `mcp_server.py`
inherits the same problem.

Worth checking whether the thresholds were calibrated against the 3-book eval
corpus, where the score distribution is much narrower than a real library's.

### 2. Section headings are damaged, and they are in the retrieval path

Over the same 150 results: **51% carry inline markup** (`<mark>`, `<u>`, `**`)
and **10% contain kerning-split words**. It shows up in the top hits, not just
the tail:

```
how does grappling work        → Dexterit y > Grappling
what happens at zero hit points→ Healin g > Death Saving Throws
how do I roll initiative       → Dexterit y > Initiative
```

This is not cosmetic. `section_heading` is prepended to the embedded text
(`chunker._embed_text`, worth +0.184 MRR@5 per the original spike) *and* to the
cross-encoder input (`server._search_sync`). So a damaged breadcrumb degrades
both the vector and the rerank score. Roughly half the corpus is embedded with
corrupted breadcrumbs.

### 3. The heading hierarchy is often wrong

Beyond the character damage, the parents are frequently incorrect:

```
Dexterit y > Critical Hits          (critical hits are not under Dexterity)
Healin g > Underwater Combat        (nor underwater combat under Healing)
CONTENTS > FALLING                  (the table of contents as a parent section)
```

`CONTENTS > …` in particular suggests heading promotion is latching onto a
table-of-contents page and treating it as a section ancestor. Since the
breadcrumb is exactly the signal the cross-encoder uses to tell a rule
definition from a keyword-dense stat block, a wrong parent is worse than no
parent.

### 4. What is *not* broken

Top-hit ranking held up: all ten first results were the correct passage. The
problem is not "search can't find it" — it is that the surrounding fourteen
results are undifferentiated, and the metadata that would differentiate them is
corrupted. That is a useful narrowing: the work is in **calibration and chunk
metadata**, not in the embedding model or the ranker.

## Suggested issues

1. **Recalibrate relevance tiers against the real library.** 62% strong is not a
   signal. Include the MCP weak-divider, which shares the thresholds.
2. **Fix section-heading extraction.** Strip inline markup and repair kerning
   splits before the heading reaches `_embed_text` — this is in the embed path,
   so it needs a re-index to take effect.
3. **Fix heading-hierarchy promotion.** Investigate `promote_markdown` treating
   table-of-contents entries as section ancestors.
4. **Grow the eval corpus past three books.** Every defect here is invisible at
   that size, which is the same limitation the rerank ablation ran into.
5. **Add an answerability metric to the eval harness** — can a small model answer
   correctly from the returned set alone? That is the agent's contribution as an
   evaluator, and it does not require the agent to ship.

## What the agent work established, so it need not be re-derived

- **A 2.3B model can drive the tool loop reliably.** 24/24 tool-call recall,
  24/24 usable arguments, 0/8 over-calls on conversational turns, 3/3 grounded
  answers, ~62 tok/s. Details in the design doc's Findings.
- **Greedy decoding is required, not preferred.** At the model's shipped defaults
  the tool-call decision is stochastic and the generated queries pick up filler.
- **Ollama runs both models concurrently** — 3.08 GB combined, no eviction.
- **The bottleneck is retrieval, not generation.** A grounded answer took 8.6s
  end to end, of which ~7s was the search.

## What is on disk

- `worktree-unseen-servant` — the full harness, seven phases, all tests passing.
  Rebase onto `main` before resuming; it is ~130 commits behind, and
  `fix(window): drop tauri-plugin-window-state` touches window handling the
  Servant's second window interacts with.
- `sidecar/evals/library_probe.py` — the measurement above, kept because the
  search workstream needs a real-library probe and the eval harness only grades
  the 3-book corpus.
