# v2 Retrieval Phase 0 — Measurement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the v2 retrieval number trustworthy before any pipeline change: a fair re-baseline (tags + edition-twin rule + payload budget column), a breadcrumb-quality axis, a local-only real-library query tier, a scored v2 blind round with readability, and a verdict on the three unexplained YZE misses.

**Architecture:** Every change is harness-side (`evals/`) or a thin adapter method on `evals/engines/v2.py` that calls the production sidecar's existing HTTP endpoints or functions in-process. No sidecar code changes, no reindex of any user library, no change to extraction. Each suite writes a committed `evals/baselines/<date>-v2-<name>.{json,md}` pair, the same convention every earlier rung used.

**Tech Stack:** Python 3.12 under `uv --project sidecar` (v2 engine: FastAPI TestClient, ChromaDB, Ollama bge-m3 for retrieval runs only), `pytest` for `evals/tests` (run under `sidecar-v3` env in CI, pure-Python tests), PyYAML, PyMuPDF (`fitz`) for PDF text oracles.

**Spec:** `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §4 Phase 0 (items 0.1–0.7) and §1.4–1.8 for the diagnosis each item answers.

## Global Constraints

- Extraction output is untouched: nothing in this plan changes `sidecar/` behaviour. The v2 adapter may only *call* existing sidecar functions and endpoints.
- Knobs stay explicit: every retrieval run pins `SearchOptions`; a baseline records what it measured (`run_eval.py` rule).
- The corpus gate stays: retrieval/extraction/breadcrumb runs call `require_corpus()` and refuse on hash drift. The library tier is the only suite that does not, because it has no committed corpus.
- Real-library PDFs are never committed; `library.yaml` carries SHA-256 + anchors only.
- One commit per task, with its baseline files when the task produces one. Commit messages end with the Co-Authored-By / Claude-Session trailer used in this repo.
- Tests: `uv run --project sidecar-v3 pytest evals/tests` must stay green (it runs in CI). Tests that need the v2 sidecar env are marked and run with `uv run --project sidecar pytest evals/tests -m sidecar_v2` locally only.
- Retrieval runs need Ollama up with `bge-m3` (`OLLAMA_CONTEXT_LENGTH=8192`). Breadcrumb-QA, library resolution and all unit tests do not.
- Jerome triggers every retrieval baseline run (each builds a fresh 7-book index, ~30–45 min on v2). The plan marks those steps **[Jerome runs]**.

---

## File map

| file | responsibility | task |
|---|---|---|
| `evals/run_eval.py` | `SYSTEM_TAGS`; tag wiring in `run()`; list-valued `doc`; new suites `breadcrumb-qa`, `library`; `top3_fit@8k` in per-query metrics | 1, 2, 3, 5, 6 |
| `evals/engines/v2.py` | `tag_systems()`, `chunks()`, `pipeline_identity()` adapter methods | 1, 5, 6 |
| `evals/engines/base.py` | document the two optional adapter methods on the `Engine` protocol docstring | 1, 5 |
| `evals/retrieval/grade.py` | `doc_filename` accepts a set; `top3_fit@8k` | 2, 3 |
| `evals/retrieval/metrics.py` | `top3_fit@8k` in `COST_METRICS` + report width | 3 |
| `evals/retrieval/report.py` | HTML inspector metric list | 3 |
| `evals/retrieval/verify_anchors.py` | list-valued `doc`; `--library` mode (PDF-only oracle) | 2, 6 |
| `evals/retrieval/queries.yaml` | q043/q044 `doc` lists | 2 |
| `evals/retrieval/breadcrumb_qa.py` (new) | pure heading-flaw grading, aggregate, report | 5 |
| `evals/retrieval/library.yaml` (new) | local-only tier: docs by SHA-256, queries | 6 |
| `evals/library.py` (new) | resolve library docs against a v2 index manifest; select runnable queries | 6 |
| `sidecar/evals/library_probe.py` | use the shared heading-flaw function | 5 |
| `evals/tests/test_run_eval.py`, `test_retrieval_grade.py`, `test_breadcrumb_qa.py` (new), `test_library.py` (new), `test_verify_anchors.py` (new) | unit tests | all |
| `evals/README.md` | document the new suites and flags | 5, 6, 7 |
| `evals/baselines/<date>-v2-phase0b.*`, `…-breadcrumb-qa.*`, `…-phase0b.blind.*`, `…-library.*` | committed numbers | 4, 5, 6, 7 |
| `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §8 | decision-log rows from Tasks 4 and 8 | 4, 8 |

---

### Task 1: Tag the eval corpus for v2 so the soft-boost can fire

The v2 eval index has no game-system tags for 5 of 7 books (`game_systems.py` knows no OSRIC, Basic Fantasy, Year Zero, Black Hack or Cairn), so `_system_boost_factors` in `sidecar/server.py` is a no-op for them. v3's rung 6 was given `SYSTEM_KEYWORDS`. This task gives v2 the same information through the product's own mechanism: a custom game system (tag + keywords) per book, then `set-game-systems` on the indexed file.

**Files:**
- Modify: `evals/run_eval.py` (after `SYSTEM_KEYWORDS`, and `run()`)
- Modify: `evals/engines/v2.py` (new method after `index()`)
- Modify: `evals/engines/base.py` (protocol docstring only)
- Test: `evals/tests/test_run_eval.py`

**Interfaces:**
- Produces: `run_eval.SYSTEM_TAGS: dict[str, tuple[str, list[str]]]` — doc id → (tag, keywords). Both SRDs map to the built-in tag `"D&D 5E"`.
- Produces: `V2Engine.tag_systems(filename: str, tag: str, keywords: list[str]) -> None`.
- Produces: `run(engine, queries, corpus, opts, do_index, tags: dict | None = None)` — new keyword argument; when `tags` is given and the engine has `tag_systems`, every needed doc is tagged after indexing and before warmup.

- [ ] **Step 1: Write the failing test for the tag wiring**

Append to `evals/tests/test_run_eval.py`:

```python
from evals.engines.base import SearchOptions, SearchResponse


class _TagRecorder:
    """Engine double: indexes nothing, records tag calls, answers empty."""

    def __init__(self):
        self.tagged: list[tuple[str, str, list[str]]] = []

    def index(self, _paths):
        return IndexReport(requested=1, indexed=0, skipped=1)

    def tag_systems(self, filename, tag, keywords):
        self.tagged.append((filename, tag, list(keywords)))

    def warmup(self, _opts):
        pass

    def search(self, _query, _opts):
        return SearchResponse(results=[], latency_ms=1.0)


def _corpus(tmp_path, *ids):
    return SimpleNamespace(documents=[
        SimpleNamespace(id=i, pdf_path=tmp_path / f"{i}.pdf") for i in ids
    ])


def _query(qid, doc, scope="cued"):
    return {"id": qid, "pair": qid, "style": "keyword", "category": "prose_rule",
            "scope": scope, "doc": doc, "query": "x", "anchors": ["x"]}


def test_run_tags_every_needed_doc_after_indexing(tmp_path):
    engine = _TagRecorder()
    corpus = _corpus(tmp_path, "osric_2e", "yze_srd")
    tags = {"osric_2e": ("OSRIC", ["osric"]), "yze_srd": ("Year Zero Engine", ["year zero", "yze"])}
    run(engine, [_query("q1", "osric_2e"), _query("q2", "yze_srd")], corpus,
        SearchOptions(), do_index=True, tags=tags)
    assert sorted(engine.tagged) == [
        ("osric_2e.pdf", "OSRIC", ["osric"]),
        ("yze_srd.pdf", "Year Zero Engine", ["year zero", "yze"]),
    ]


def test_run_skips_tagging_when_engine_lacks_the_hook(tmp_path):
    class NoTag:
        def index(self, _paths):
            return IndexReport(requested=1, indexed=0, skipped=1)

        def warmup(self, _opts):
            pass

        def search(self, _query, _opts):
            return SearchResponse(results=[], latency_ms=1.0)

    result = run(NoTag(), [_query("q1", "osric_2e")], _corpus(tmp_path, "osric_2e"),
                 SearchOptions(), do_index=True, tags={"osric_2e": ("OSRIC", ["osric"])})
    assert result["per_query"][0]["hit_rank"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_run_eval.py -v -k tag`
Expected: FAIL — `run() got an unexpected keyword argument 'tags'`.

- [ ] **Step 3: Add `SYSTEM_TAGS` and the wiring in `run_eval.py`**

Directly after the `_system_map` function:

```python
# The same information as SYSTEM_KEYWORDS, in the shape the v2 product stores
# it: a tag per book (custom systems for the five books game_systems.py does
# not know; the built-in "D&D 5E" for both SRDs) plus the keywords that make
# detect_systems_in_query recognise the tag in a query. Without this the v2
# eval index is untagged and _system_boost_factors is a no-op on 5 of 7 books
# (roadmap §1.5). Production wires the same thing to the user's tag lists.
SYSTEM_TAGS: dict[str, tuple[str, list[str]]] = {
    "bfrpg_4e": ("Basic Fantasy RPG", SYSTEM_KEYWORDS["bfrpg_4e"]),
    "black_hack_1e": ("The Black Hack", SYSTEM_KEYWORDS["black_hack_1e"]),
    "cairn_1e": ("Cairn", SYSTEM_KEYWORDS["cairn_1e"]),
    "srd_5_1": ("D&D 5E", SYSTEM_KEYWORDS["srd_5_1"]),
    "srd_5_2_1": ("D&D 5E", SYSTEM_KEYWORDS["srd_5_2_1"]),
    "osric_2e": ("OSRIC", SYSTEM_KEYWORDS["osric_2e"]),
    "yze_srd": ("Year Zero Engine", SYSTEM_KEYWORDS["yze_srd"]),
}
```

Change the `run` signature and add the tagging block right after the `if do_index:` block (before `print("warmup…")`):

```python
def run(engine, queries: list[dict], corpus, opts: SearchOptions, do_index: bool,
        tags: dict[str, tuple[str, list[str]]] | None = None) -> dict:
    doc_file = {d.id: d.pdf_path.name for d in corpus.documents}
    doc_pdf = {d.id: d.pdf_path for d in corpus.documents}
    needed = sorted({q["doc"] for q in queries if q["doc"] != "any"})

    if do_index:
        print(f"indexing {len(needed)} corpus PDFs (idempotent, one at a time)…", flush=True)
        ...  # existing loop unchanged, but iterate over `needed` defined above

    # Tag after indexing (set-game-systems rewrites the chunk metadata of an
    # indexed file) and before warmup, so the boost sees the tags on every run.
    tag_fn = getattr(engine, "tag_systems", None)
    if tags and tag_fn is not None:
        for d in needed:
            if d in tags:
                tag, keywords = tags[d]
                tag_fn(doc_file[d], tag, keywords)
                print(f"  tagged {d} as {tag!r}", flush=True)
```

In `main()`, pass the tags for v2:

```python
            result = run(engine, queries, corpus, opts, do_index=not args.no_index,
                         tags=SYSTEM_TAGS if args.engine == "v2" else None)
```

and record them in the retrieval `meta` dict:

```python
        "system_tags": _jsonable(SYSTEM_TAGS) if args.engine == "v2" else None,
```

- [ ] **Step 4: Add `tag_systems` to the v2 adapter**

In `evals/engines/v2.py`, after `index()`:

```python
    def tag_systems(self, filename: str, tag: str, keywords: list[str]) -> None:
        """Tag an indexed file with a game system through the product's own
        endpoints: create (or update) a custom system carrying the keywords
        that let ``detect_systems_in_query`` recognise it, then stamp the
        file's chunks + manifest entry. Idempotent."""
        client = self._ensure_client()
        body = {"tag": tag, "keywords": list(keywords)}
        resp = client.post("/api/custom-game-systems", json=body)
        if resp.status_code == 409:  # already created by an earlier doc sharing the tag
            resp = client.put(f"/api/custom-game-systems/{tag}", json=body)
        resp.raise_for_status()
        client.post(
            "/api/set-game-systems", json={"filename": filename, "game_systems": [tag]}
        ).raise_for_status()
```

In `evals/engines/base.py`, add to the `Engine` protocol docstring (no new abstract method — v3 lacks it and the runner probes with `getattr`):

```
    Optional adapter hooks the runner probes with ``getattr``:
      ``tag_systems(filename, tag, keywords)`` — stamp an indexed file with a
      game-system tag the way the product does (v2: custom system + tag).
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_run_eval.py -v`
Expected: all PASS, including the pre-existing `test_index_error_aborts_before_warmup`.

- [ ] **Step 6: Smoke the adapter against the real sidecar (needs the sidecar env, no Ollama query needed beyond indexing one small book)**

Run:

```bash
uv run --project sidecar python - <<'EOF'
from pathlib import Path
from evals.engines.v2 import V2Engine
from evals.corpus import require_corpus
c = require_corpus(); yze = next(d for d in c.documents if d.id == "yze_srd")
e = V2Engine(data_dir=Path("evals/.eval_data/v2-tagsmoke"))
print(e.index([yze.pdf_path]))
e.tag_systems(yze.pdf_path.name, "Year Zero Engine", ["year zero", "yze"])
r = e._ensure_client().get("/api/sources").json()   # {"sources": [{filename, game_system, game_systems, …}], "count": n}
print([(s["filename"], s["game_system"], s["game_systems"]) for s in r["sources"]])
e.close()
EOF
rm -rf evals/.eval_data/v2-tagsmoke
```

Expected: the printed tuple shows `('YZE-Standard-Reference-Document.pdf', 'Year Zero Engine', ['Year Zero Engine'])`.

- [ ] **Step 7: Commit**

```bash
git add evals/run_eval.py evals/engines/v2.py evals/engines/base.py evals/tests/test_run_eval.py
git commit -m "feat(evals): tag the v2 eval corpus so the system soft-boost can fire

v2's eval index carried no game-system tags for 5 of 7 books, so
_system_boost_factors was a no-op on every cued osric/bfrpg/yze/cairn/
black-hack query while v3's rung 6 had a keyword map. SYSTEM_TAGS gives
v2 the same information through its own custom-system + set-game-systems
endpoints. Roadmap 2026-09-02 §4 Phase 0.1."
```

---

### Task 2: Edition-ambiguous cued queries accept a list of docs

q043/q044 say "dnd 5e" and require SRD 5.1; the SRD 5.2.1 hit at rank 2 is graded a miss although it answers the question. A cued query's `doc` may now be a list; the right-file check accepts any listed file. Single-scope queries stay single-doc (the source filter needs one file).

**Files:**
- Modify: `evals/retrieval/grade.py:62-71`
- Modify: `evals/run_eval.py` (`run()` scope block, `needed`, `meta.docs`)
- Modify: `evals/retrieval/verify_anchors.py` (`main()` loop)
- Modify: `evals/retrieval/queries.yaml` (q043, q044)
- Test: `evals/tests/test_retrieval_grade.py`, `evals/tests/test_run_eval.py`, `evals/tests/test_verify_anchors.py` (new)

**Interfaces:**
- Produces: `grade.is_relevant(result, query, doc_filename: str | set[str] | None)` and `grade.grade_response(response, query, doc_filename: str | set[str] | None)` — a set means "any of these files".
- Produces: `run_eval.query_docs(q: dict) -> list[str]` — the query's doc ids as a list (`["any"]` → `[]`).
- Produces: `verify_anchors.verify_query(q, by_id) -> list[str]` — failure strings for one query (empty = verified); used again by Task 6.

- [ ] **Step 1: Write the failing grader tests**

Append to `evals/tests/test_retrieval_grade.py`:

```python
def _from(filename: str, text: str) -> SearchResult:
    return SearchResult(
        text=text, filename=filename, source=filename, section_heading="Magic Missile",
        page_start=1, page_end=1, relevance=1.0, tier="strong", reranked=False,
    )


def test_doc_set_accepts_any_listed_file():
    query = {"category": "exact_name", "anchors": ["magic missile", "1d4 1"]}
    response = SearchResponse(results=[
        _from("OSRIC.pdf", "magic missile 1d4 1"),
        _from("SRD_CC_v5.2.1.pdf", "magic missile 1d4 1"),
        _from("SRD_CC_v5.1.pdf", "magic missile 1d4 1"),
    ], latency_ms=1.0)
    rels = grade_response(response, query, {"SRD_CC_v5.1.pdf", "SRD_CC_v5.2.1.pdf"})["rels"]
    assert rels == [False, True, True]


def test_doc_string_still_means_exactly_one_file():
    query = {"category": "exact_name", "anchors": ["magic missile"]}
    response = SearchResponse(results=[_from("SRD_CC_v5.2.1.pdf", "magic missile")], latency_ms=1.0)
    assert grade_response(response, query, "SRD_CC_v5.1.pdf")["rels"] == [False]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_retrieval_grade.py -v -k doc_`
Expected: `test_doc_set_accepts_any_listed_file` FAILS with `TypeError: unhashable type: 'set'` or `[False, False, False]`.

- [ ] **Step 3: Make the grader accept a set**

Replace `is_relevant` and `_matched_anchors` in `evals/retrieval/grade.py`:

```python
def _allowed(doc_filename: str | set[str] | None) -> set[str] | None:
    """None = any file; a str = exactly that file; a set = any of those
    (edition twins such as SRD 5.1 / 5.2.1 for a 'dnd 5e' cue)."""
    if doc_filename is None:
        return None
    return {doc_filename} if isinstance(doc_filename, str) else set(doc_filename)


def is_relevant(result: SearchResult, query: dict, doc_filename: str | set[str] | None) -> bool:
    allowed = _allowed(doc_filename)
    if allowed is not None and result.filename not in allowed:
        return False
    return anchors_match(result.grading_text, query["anchors"])


def _matched_anchors(result: SearchResult, query: dict, doc_filename: str | set[str] | None) -> set[int]:
    allowed = _allowed(doc_filename)
    if allowed is not None and result.filename not in allowed:
        return set()
    return matched_anchor_indexes(result.grading_text, query["anchors"])
```

Update the `grade_response` signature to `doc_filename: str | set[str] | None` (body unchanged).

- [ ] **Step 4: Run the grader tests to verify they pass**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_retrieval_grade.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing runner test for list-valued `doc`**

Append to `evals/tests/test_run_eval.py`:

```python
from evals.engines.base import SearchResult
from evals.run_eval import query_docs


class _TwinEngine:
    """Returns the 5.2.1 twin at rank 1 and 5.1 at rank 2 for every query."""

    def index(self, _paths):
        return IndexReport(requested=1, indexed=0, skipped=1)

    def warmup(self, _opts):
        pass

    def search(self, _query, _opts):
        def hit(fn):
            return SearchResult(text="magic missile 1d4 1", filename=fn, source=fn,
                                section_heading="", page_start=1, page_end=1,
                                relevance=1.0, tier="strong", reranked=False)
        return SearchResponse(results=[hit("srd_5_2_1.pdf"), hit("srd_5_1.pdf")], latency_ms=1.0)


def test_query_docs_normalises_str_list_and_any():
    assert query_docs({"doc": "srd_5_1"}) == ["srd_5_1"]
    assert query_docs({"doc": ["srd_5_1", "srd_5_2_1"]}) == ["srd_5_1", "srd_5_2_1"]
    assert query_docs({"doc": "any"}) == []


def test_cued_query_with_doc_list_accepts_the_twin(tmp_path):
    corpus = _corpus(tmp_path, "srd_5_1", "srd_5_2_1")
    q = _query("q043", ["srd_5_1", "srd_5_2_1"])
    q["anchors"] = ["magic missile", "1d4 1"]
    result = run(_TwinEngine(), [q], corpus, SearchOptions(), do_index=False)
    assert result["per_query"][0]["hit_rank"] == 1


def test_single_scope_rejects_a_doc_list(tmp_path):
    corpus = _corpus(tmp_path, "srd_5_1", "srd_5_2_1")
    q = _query("q001", ["srd_5_1", "srd_5_2_1"], scope="single")
    with pytest.raises(SystemExit, match="single-scope"):
        run(_TwinEngine(), [q], corpus, SearchOptions(), do_index=False)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_run_eval.py -v -k "twin or query_docs or single_scope"`
Expected: FAIL — `ImportError: cannot import name 'query_docs'`.

- [ ] **Step 7: Implement list-valued `doc` in the runner**

In `evals/run_eval.py`, add after `_system_map`:

```python
def query_docs(q: dict) -> list[str]:
    """A query's doc ids. ``doc`` is a str, a list (edition twins for one
    cue — any listed file is the right file), or ``"any"`` (→ [])."""
    doc = q["doc"]
    if doc == "any":
        return []
    return list(doc) if isinstance(doc, list) else [doc]
```

In `run()`, replace `needed = sorted({q["doc"] for q in queries if q["doc"] != "any"})` with:

```python
    needed = sorted({d for q in queries for d in query_docs(q)})
```

Replace the scope block:

```python
        scope = q.get("scope", "cued")
        docs = query_docs(q)
        if scope == "single":
            if len(docs) != 1:
                raise SystemExit(f"{q['id']}: single-scope queries need exactly one doc (got {docs})")
            q_opts, grade_doc = replace(opts, source_filter=doc_file[docs[0]]), None
        elif scope == "uncued":
            q_opts, grade_doc = opts, None
        else:  # cued: the right file must win; a list means any listed file is right
            q_opts, grade_doc = opts, {doc_file[d] for d in docs} or None
```

In `main()`'s retrieval `meta`, replace `"docs": sorted({q["doc"] for q in queries if q["doc"] != "any"})` with `"docs": sorted({d for q in queries for d in query_docs(q)})`.

- [ ] **Step 8: Run the runner tests to verify they pass**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_run_eval.py -v`
Expected: all PASS.

- [ ] **Step 9: Write the failing `verify_anchors` test**

Create `evals/tests/test_verify_anchors.py`:

```python
"""verify_anchors: every anchor in ref ∧ PDF of the primary doc, and in the
PDF of every secondary (edition-twin) doc."""
from evals.retrieval.verify_anchors import verify_query


class _Text:
    def __init__(self, ref: str, pdf: str):
        self._ref, self._pdf = ref, pdf

    def ref_norm(self, _answer_ref):
        return self._ref

    def pdf_norm(self):
        return self._pdf

    def anchor_pages(self, _anchor):
        return [1]


def test_primary_needs_ref_and_pdf_secondary_needs_pdf_only():
    by_id = {
        "srd_5_1": _Text(ref="magic missile 1d4 1", pdf="magic missile 1d4 1"),
        "srd_5_2_1": _Text(ref="", pdf="magic missile 1d4 1"),
    }
    q = {"id": "q043", "category": "exact_name", "doc": ["srd_5_1", "srd_5_2_1"],
         "anchors": ["magic missile", "1d4 1"]}
    assert verify_query(q, by_id) == []


def test_secondary_missing_the_anchor_fails():
    by_id = {
        "srd_5_1": _Text(ref="magic missile", pdf="magic missile"),
        "srd_5_2_1": _Text(ref="", pdf="fireball"),
    }
    q = {"id": "q043", "category": "exact_name", "doc": ["srd_5_1", "srd_5_2_1"],
         "anchors": ["magic missile"]}
    fails = verify_query(q, by_id)
    assert fails and "srd_5_2_1" in fails[0]
```

- [ ] **Step 10: Run it to verify it fails**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_verify_anchors.py -v`
Expected: FAIL — `ImportError: cannot import name 'verify_query'`.

- [ ] **Step 11: Extract `verify_query` in `verify_anchors.py`**

Replace the body of `main()`'s per-query loop with a call to this new function (defined above `main`):

```python
def verify_query(q: dict, by_id: dict) -> list[str]:
    """Failure strings for one query (empty = fully verified).

    ``doc`` may be a list: the first doc is the primary and must hold every
    anchor in BOTH its reference and its PDF; each secondary (an edition
    twin) must hold every anchor in its PDF (its reference tree is a
    different edition, so ``answer_ref`` does not apply to it).
    """
    docs = q["doc"] if isinstance(q["doc"], list) else [q["doc"]]
    fails: list[str] = []
    primary = by_id.get(docs[0])
    if primary is None:
        return [f"unknown doc {docs[0]!r}"]
    ref_n = primary.ref_norm(q.get("answer_ref"))
    pdf_n = primary.pdf_norm()
    for a in q["anchors"]:
        in_ref, in_pdf = _hit(ref_n, a), _hit(pdf_n, a)
        if not (in_ref and in_pdf):
            where = "ref" if not in_ref else ""
            where += ("+" if where and not in_pdf else "") + ("pdf" if not in_pdf else "")
            fails.append(f"{a!r} (missing in {where})")
    for doc_id in docs[1:]:
        dt = by_id.get(doc_id)
        if dt is None:
            fails.append(f"unknown secondary doc {doc_id!r}")
            continue
        sec_pdf = dt.pdf_norm()
        for a in q["anchors"]:
            if not _hit(sec_pdf, a):
                fails.append(f"{a!r} missing in secondary {doc_id} pdf")
    if q["category"] == "cross_page":
        declared = _declared_pages(q.get("pages"))
        if not declared:
            fails.append("cross_page query has no valid declared pages")
        page_sets = [set(primary.anchor_pages(a)) & declared for a in q["anchors"]]
        spanned = set().union(*page_sets) if page_sets else set()
        straddles = declared <= spanned and any(
            page_sets[i] and page_sets[j] and page_sets[i].isdisjoint(page_sets[j])
            for i in range(len(page_sets))
            for j in range(i + 1, len(page_sets))
        )
        if not straddles:
            fails.append("cross_page anchors do NOT straddle a page break")
    return fails
```

`main()` becomes:

```python
def main() -> int:
    corpus = require_corpus()
    by_id = {d.id: DocText(d) for d in corpus.documents}
    queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
    total_fail = 0
    for q in queries:
        fails = verify_query(q, by_id)
        label = q["doc"] if isinstance(q["doc"], str) else "+".join(q["doc"])
        if fails:
            total_fail += 1
            print(f"✗ {q['id']:5} [{q['category']:17}] {label}")
            for f in fails:
                print(f"      {f}")
        else:
            print(f"✓ {q['id']:5} [{q['category']:17}] {label}")
    n = len(queries)
    print(f"\n{n - total_fail}/{n} queries fully verified (ref ∧ pdf).")
    if total_fail:
        print(f"✗ {total_fail} queries have unverified anchors — fix before committing.")
        return 1
    print("✓ all anchors verified in both reference and PDF.")
    return 0
```

(The `cross_note` page listing is dropped from the ✓ line; the straddle check itself is kept.)

- [ ] **Step 12: Run the verify test to verify it passes**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_verify_anchors.py -v`
Expected: PASS.

- [ ] **Step 13: Update q043 and q044 in `queries.yaml`**

Change both entries' `doc` line from `doc: srd_5_1` to:

```yaml
  doc: [srd_5_1, srd_5_2_1]   # "dnd 5e" names both SRD editions; either is the right file
```

Leave `answer_ref` (the 5.1 reference) as is: it verifies the primary.

- [ ] **Step 14: Re-verify every anchor against the corpus (sidecar env, no Ollama)**

Run: `uv run --project sidecar python -m evals.retrieval.verify_anchors`
Expected: `68/68 queries fully verified` and exit 0. If q043/q044 report `missing in secondary srd_5_2_1 pdf` for `120 feet` or `1d4 1`, the 5.2.1 wording differs — replace that anchor with an any-of list that holds in both PDFs (e.g. `["120 feet", "range 120"]`) and re-run until green.

- [ ] **Step 15: Commit**

```bash
git add evals/retrieval/grade.py evals/run_eval.py evals/retrieval/verify_anchors.py \
        evals/retrieval/queries.yaml evals/tests/test_retrieval_grade.py \
        evals/tests/test_run_eval.py evals/tests/test_verify_anchors.py
git commit -m "feat(evals): a cued query may list edition twins as its doc

'dnd 5e magic missile' was graded a miss when SRD 5.2.1 answered at rank 2.
doc: [srd_5_1, srd_5_2_1] makes either file the right file for cued
grading; verify_anchors checks the primary in ref+PDF and each secondary
in its PDF. Roadmap 2026-09-02 §4 Phase 0.3."
```

---

### Task 3: `top3_fit@8k` — track the small-model budget from the start

Phase 2 will add a `max_context_chars` packer; the eval needs the column before that so compactness is tracked, not discovered. The metric per query is 1.0 when the top-3 results (heading + text) fit inside 8 000 chars, else 0.0; the aggregate is the share of queries whose top-3 fits.

**Files:**
- Modify: `evals/retrieval/grade.py` (`grade_response`)
- Modify: `evals/retrieval/metrics.py` (`COST_METRICS`, `format_report` widths)
- Modify: `evals/run_eval.py` (`per_query` metrics)
- Modify: `evals/retrieval/report.py:129` (JS `METRICS`)
- Test: `evals/tests/test_retrieval_grade.py`

**Interfaces:**
- Produces: `grade.BUDGET_CHARS = 8000`, `grade.top3_fits(response, budget=BUDGET_CHARS) -> float`, key `"top3_fit@8k"` in `grade_response()` and in every per-query `metrics` dict; `metrics.COST_METRICS == ["payload_chars", "dup_sections@10", "top3_fit@8k"]`.

- [ ] **Step 1: Write the failing tests**

Append to `evals/tests/test_retrieval_grade.py`:

```python
from evals.retrieval import metrics
from evals.retrieval.grade import BUDGET_CHARS, top3_fits


def test_top3_fits_when_three_results_fit_the_budget():
    response = SearchResponse(results=[_result("a" * 2000)] * 3 + [_result("b" * 9000)], latency_ms=1.0)
    assert top3_fits(response) == 1.0


def test_top3_does_not_fit_when_the_third_result_overflows():
    response = SearchResponse(results=[_result("a" * 3000), _result("a" * 3000), _result("a" * 3000)],
                              latency_ms=1.0)
    assert top3_fits(response) == 0.0


def test_grade_response_reports_the_budget_column():
    query = {"category": "prose_rule", "anchors": ["kraken"]}
    response = SearchResponse(results=[_result("Kraken")], latency_ms=1.0)
    g = grade_response(response, query, None)
    assert g["top3_fit@8k"] == 1.0
    assert "top3_fit@8k" in metrics.COST_METRICS
    assert BUDGET_CHARS == 8000
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_retrieval_grade.py -v -k "top3 or budget"`
Expected: FAIL — `ImportError: cannot import name 'BUDGET_CHARS'`.

- [ ] **Step 3: Implement**

`evals/retrieval/grade.py` — add near the top (after `normalize`):

```python
BUDGET_CHARS = 8000  # the 4B-model context budget (roadmap §4 Phase 0.7 / Phase 2.2)


def top3_fits(response: SearchResponse, budget: int = BUDGET_CHARS) -> float:
    """1.0 when the top-3 results (heading + text) fit inside the budget.
    Tracks compactness before the Phase-2 packer exists, so 'payload shrank'
    and 'the answer still ships' are measured together."""
    top = response.results[:3]
    return 1.0 if sum(len(r.text) + len(r.section_heading) for r in top) <= budget else 0.0
```

and add to the dict returned by `grade_response`:

```python
        "top3_fit@8k": top3_fits(response),
```

`evals/retrieval/metrics.py`:

```python
COST_METRICS = ["payload_chars", "dup_sections@10", "top3_fit@8k"]
```

and in `format_report`, extend `widths` with `"top3_fit@8k": 13`.

`evals/run_eval.py`, in `run()`'s `per_query.append` metrics dict, add:

```python
                "top3_fit@8k": g["top3_fit@8k"],
```

`evals/retrieval/report.py` line 129:

```js
const METRICS = ["mrr@5","ndcg@10","recall@3","recall@5","recall@10","payload_chars","dup_sections@10","top3_fit@8k"];
```

- [ ] **Step 4: Run the whole eval test suite**

Run: `uv run --project sidecar-v3 pytest evals/tests -v`
Expected: all PASS. (Old baselines lack the column; `retrieval_regressions` only compares `mrr@5`/`recall@3`, so `--gate` against them still works.)

- [ ] **Step 5: Commit**

```bash
git add evals/retrieval/grade.py evals/retrieval/metrics.py evals/run_eval.py \
        evals/retrieval/report.py evals/tests/test_retrieval_grade.py
git commit -m "feat(evals): top3_fit@8k — the small-model budget as a tracked column

Share of queries whose top-3 (heading + text) fits 8 000 chars. Tracked
now so Phase 2's max_context_chars packer is measured against a number,
not an impression. Roadmap 2026-09-02 §4 Phase 0.7."
```

---

### Task 4: Re-baseline v2 as `phase0b` — the number to beat **[Jerome runs]**

Same pipeline, same queries; only the harness changed (tags, twin rule, budget column). This baseline replaces `2026-08-15-v2-phase0` as the reference every later rung gates against.

**Files:**
- Create: `evals/baselines/<date>-v2-phase0b.{json,md}` (+ gitignored `.results.json`, `.html`)
- Modify: `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §8 (one row)
- Modify: `evals/README.md` (baseline pointer)

- [ ] **Step 1: Run the baseline (Ollama up, ~30–45 min: fresh 7-book index)**

```bash
uv run --project sidecar python -m evals.run_eval --engine v2 --baseline phase0b
```

Expected console: `tagged osric_2e as 'OSRIC'` … for all 7 docs before `warmup…`; the by-scope table; `wrote evals/baselines/<date>-v2-phase0b.{json,md,results.json,html}`.

- [ ] **Step 2: Diff per query against 08-15**

```bash
uv run --project sidecar python - <<'EOF'
import json, glob
old = json.load(open("evals/baselines/2026-08-15-v2-phase0.json"))["per_query"]
new_path = sorted(glob.glob("evals/baselines/*-v2-phase0b.json"))[-1]
new = json.load(open(new_path))["per_query"]
o = {q["id"]: q for q in old}
for q in new:
    a, b = o[q["id"]]["hit_rank"], q["hit_rank"]
    if a != b:
        print(f"{q['id']} [{q['scope']:6}] {a} -> {b}  {q['query'][:50]}")
EOF
```

Expected: every changed line is a `cued` query (tags) or q043/q044 (twin rule). **Any `single` or `uncued` change is a bug in Task 1–3 — stop and fix before committing.** Cued MRR@5 is expected to rise from 0.519 (v3's boost rung moved cued by +0.166; v2's multiplicative boost is weaker, so anything ≥ +0.08 is in line).

- [ ] **Step 3: Record the verdict**

Append to the roadmap's §8 decision-log table:

```
| `phase0b` is the v2 number to beat (replaces 08-15 `phase0`) | same pipeline; the harness now tags the corpus, accepts SRD edition twins for "dnd 5e" cues, and reports `top3_fit@8k` — <cued 0.519 → X.XXX; all 0.701 → X.XXX; single/uncued unchanged> | — |
```

with the measured numbers. In `evals/README.md` "Baselines & the blind round", add one sentence: "The v2 reference for the 2026-09-02 roadmap is `<date>-v2-phase0b` (tags + twin rule + budget column); gate against it, not `2026-08-15-v2-phase0`."

- [ ] **Step 4: Commit**

```bash
git add evals/baselines/*-v2-phase0b.json evals/baselines/*-v2-phase0b.md \
        docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md evals/README.md
git commit -m "eval(evals): v2 phase0b — tagged corpus, twin rule, budget column

cued 0.519 → <x>, all 0.701 → <x>; single/uncued byte-identical to 08-15.
This is the number every Phase 1–3 rung gates against."
```

---

### Task 5: Breadcrumb QA — a heading-quality axis, no embedding

Measures what §1.5 found by hand: share of chunks whose `section_heading` carries markup, a stranded letter, small-caps mixed case, or a furniture root, plus the top roots per book so a reviewer sees "fOR fRee UpdateS…" at 27 % without opening an inspector. Pure functions over the chunker's output; seconds per corpus.

**Files:**
- Create: `evals/retrieval/breadcrumb_qa.py`
- Modify: `evals/engines/v2.py` (`chunks()`, `_import_sidecar` import list)
- Modify: `evals/engines/base.py` (protocol docstring)
- Modify: `evals/run_eval.py` (`--suite breadcrumb-qa`, `run_breadcrumb_qa`)
- Modify: `sidecar/evals/library_probe.py` (`heading_flaws` delegates to the shared module)
- Modify: `evals/README.md`
- Create: `evals/tests/test_breadcrumb_qa.py`
- Create: `evals/baselines/<date>-v2-breadcrumb-qa.{json,md}`

**Interfaces:**
- Produces: `breadcrumb_qa.FLAWS = ["markup", "split_letter", "mixed_case", "furniture_root", "no_heading"]`; `strip_markup(h: str) -> str`; `root_of(h: str) -> str`; `flaws(heading: str | None) -> set[str]`; `grade_doc(doc_id: str, chunks: list[dict]) -> dict`; `aggregate(rows: list[dict]) -> dict[str, dict]`; `format_report(summary) -> str`; `render_md(meta, result) -> str`.
- Produces: `V2Engine.chunks(pdf_path) -> list[dict]` with keys `section_heading, chunk_type, page_start, page_end, chars`.
- Consumes: `sidecar.server._extract_and_chunk(pdf_path, None, None)`.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_breadcrumb_qa.py`:

```python
"""Breadcrumb QA: the heading string that feeds the embedding and the reranker
(roadmap 2026-09-02 §1.5 / Phase 0.2). Pure; no corpus."""
from evals.retrieval import breadcrumb_qa as bq


def test_markup_is_detected_and_stripped():
    h = "**Casting Spells** > **<u>Magic Missile</u>**"
    assert "markup" in bq.flaws(h)
    assert bq.strip_markup(h) == "Casting Spells > Magic Missile"


def test_stranded_letter_is_a_split_word_but_a_and_I_are_not():
    assert "split_letter" in bq.flaws("**S eed** **<u>p</u>** > **Goblin**")
    assert "split_letter" in bq.flaws("Dexterit y > Grappling")
    assert "split_letter" not in bq.flaws("A Pit > I Rolled")


def test_small_caps_mixed_case_is_flagged():
    assert "mixed_case" in bq.flaws("chaRacteR RaceS > Elves")
    assert "mixed_case" not in bq.flaws("Character Races > Elves")
    assert "mixed_case" not in bq.flaws("THAC0 > Combat")


def test_furniture_root_is_flagged():
    assert "furniture_root" in bq.flaws("**fOR fRee UpdateS, eRRata and OtheR OSRIc SUppORt, VISIt:** > Falling")
    assert "furniture_root" in bq.flaws("CONTENTS > FALLING")
    assert "furniture_root" not in bq.flaws("Combat > Falling")


def test_missing_heading_is_its_own_flaw():
    assert bq.flaws(None) == {"no_heading"}
    assert bq.flaws("") == {"no_heading"}


def test_grade_doc_counts_and_top_roots():
    chunks = [
        {"section_heading": "**fOR fRee UpdateS** > A", "chunk_type": "prose", "page_start": 1, "page_end": 1, "chars": 100},
        {"section_heading": "**fOR fRee UpdateS** > B", "chunk_type": "prose", "page_start": 2, "page_end": 2, "chars": 100},
        {"section_heading": "Combat > Falling", "chunk_type": "prose", "page_start": 3, "page_end": 3, "chars": 100},
        {"section_heading": None, "chunk_type": "table", "page_start": 4, "page_end": 4, "chars": 100},
    ]
    g = bq.grade_doc("osric_2e", chunks)
    assert g["chunks"] == 4
    assert g["markup"] == 2 and g["furniture_root"] == 2 and g["no_heading"] == 1
    assert g["top_roots"][0] == ("fOR fRee UpdateS", 2)


def test_aggregate_rates_and_all_bucket():
    rows = [bq.grade_doc("a", [{"section_heading": "**X** > Y", "chunk_type": "prose",
                                "page_start": 1, "page_end": 1, "chars": 10}]),
            bq.grade_doc("b", [{"section_heading": "X > Y", "chunk_type": "prose",
                                "page_start": 1, "page_end": 1, "chars": 10}])]
    s = bq.aggregate(rows)
    assert s["a"]["markup_rate"] == 1.0 and s["b"]["markup_rate"] == 0.0
    assert s["all"]["chunks"] == 2 and s["all"]["markup_rate"] == 0.5
    assert "markup_rate" in bq.format_report(s)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_breadcrumb_qa.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.retrieval.breadcrumb_qa'`.

- [ ] **Step 3: Create `evals/retrieval/breadcrumb_qa.py`**

```python
"""Breadcrumb QA — is the section heading that feeds the embedding and the
reranker a usable topical label? (roadmap 2026-09-02 §1.5, Phase 0.2)

Measured by hand on the 08-15 v2 results: 84 % of returned chunks carried
Markdown markup in the breadcrumb, 27 % were rooted at OSRIC's running
footer, 11 % at the split word "S eed p" (= Speed). ``section_heading`` is
prepended to the embedded text (``chunker._embed_text``) and to the
cross-encoder input (``server._search_sync``), so damage here is a retrieval
defect. This axis grades every chunk the chunker produces — no embedding,
seconds per corpus — and is the gate Phase 1's heading work must clear.

Per chunk, a set of flaws:
- markup         — Markdown/HTML emphasis survived into the heading
- split_letter   — a letter stranded off a word ("Dexterit y", "S eed p")
- mixed_case     — small-caps font damage ("chaRacteR RaceS")
- furniture_root — the breadcrumb root is page furniture (running footer,
                   CONTENTS, a URL), not a section
- no_heading     — the chunk has no breadcrumb at all
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

FLAWS = ["markup", "split_letter", "mixed_case", "furniture_root", "no_heading"]

_MARKUP = re.compile(r"\*\*|__|</?[a-z][a-z0-9]*>|`")
# A stranded single letter, excluding the legitimate ones ("a", "I"). Matching
# the split ("word space short-word") finds ordinary English like "a pit".
_LONE_LETTER = re.compile(r"(?<![\w'])(?![aAI](?![\w']))[A-Za-z](?![\w'])")
# A lowercase run followed by an uppercase letter inside one word: a small-caps
# display font read back as mixed case. "THAC0" (all caps) does not match.
_MIXED_CASE = re.compile(r"\b[a-z]+[A-Z][A-Za-z]*\b")
_FURNITURE = re.compile(
    r"\bcontents\b|\berrata\b|for free updates|\bvisit:?\b|www\.|https?://|\bpage \d+\b",
    re.IGNORECASE,
)


def strip_markup(heading: str) -> str:
    return _MARKUP.sub("", heading or "").strip()


def root_of(heading: str) -> str:
    """The first breadcrumb segment, markup stripped."""
    return strip_markup((heading or "").split(" > ", 1)[0])


def flaws(heading: str | None) -> set[str]:
    if not heading or not heading.strip():
        return {"no_heading"}
    out: set[str] = set()
    if _MARKUP.search(heading):
        out.add("markup")
    clean = strip_markup(heading)
    if _LONE_LETTER.search(clean):
        out.add("split_letter")
    if _MIXED_CASE.search(clean):
        out.add("mixed_case")
    if _FURNITURE.search(root_of(heading)):
        out.add("furniture_root")
    return out


def grade_doc(doc_id: str, chunks: list[dict], top_n: int = 5) -> dict:
    """Flaw counts over one document's chunks, plus its most common roots."""
    counts = Counter()
    roots = Counter()
    for c in chunks:
        h = c.get("section_heading")
        counts.update(flaws(h))
        if h:
            roots[root_of(h)] += 1
    return {"doc": doc_id, "chunks": len(chunks), **{f: counts[f] for f in FLAWS},
            "top_roots": roots.most_common(top_n)}


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """Per-doc rollup plus 'all'; every flaw as a count and a rate."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r["doc"]].append(r)
        buckets["all"].append(r)
    out: dict[str, dict] = {}
    for doc, rs in buckets.items():
        n = sum(r["chunks"] for r in rs)
        row = {"chunks": n}
        for f in FLAWS:
            k = sum(r[f] for r in rs)
            row[f] = k
            row[f"{f}_rate"] = k / n if n else None
        out[doc] = row
    return out


def format_report(summary: dict[str, dict]) -> str:
    header = f"{'doc':<16}{'chunks':>8}" + "".join(f"{f + '_rate':>20}" for f in FLAWS)
    lines = [header, "-" * len(header)]
    for doc in sorted(d for d in summary if d != "all") + ["all"]:
        r = summary[doc]
        cells = "".join(
            f"{(format(r[f + '_rate'], '.3f') if r.get(f + '_rate') is not None else '—'):>20}"
            for f in FLAWS)
        lines.append(f"{doc:<16}{r['chunks']:>8}" + cells)
    return "\n".join(lines)


def render_md(meta: dict, result: dict) -> str:
    roots = []
    for r in result["docs"]:
        roots.append(f"- **{r['doc']}** ({r['chunks']} chunks): "
                     + "; ".join(f"`{root[:60]}` ×{n}" for root, n in r["top_roots"]))
    return "\n".join([
        f"# Breadcrumb QA — {meta['engine']} — {meta['name']}",
        "", f"Date: {meta['date']}",
        "Unit: every chunk the chunker emits; flaw = property of its section_heading",
        "", "## By doc", "```", format_report(result["by_doc"]), "```",
        "", "## Top roots per doc", *roots, "",
    ])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_breadcrumb_qa.py -v`
Expected: all PASS. If `test_small_caps_mixed_case_is_flagged` fails on `"THAC0 > Combat"`, the regex is matching a leading-uppercase token; keep `[a-z]+` as the mandatory prefix as written.

- [ ] **Step 5: Add `chunks()` to the v2 adapter**

In `evals/engines/v2.py`, add `_extract_and_chunk` to the `from server import (...)` list in `_import_sidecar` and to the returned dict (`"_extract_and_chunk": _extract_and_chunk`), then add after `extract()`:

```python
    def chunks(self, pdf_path: Path | str) -> list[dict]:
        """v2's real chunker output for one PDF (pymupdf4llm → promotion →
        cleanup → structure_aware), no Chroma/Ollama. What breadcrumb-qa
        grades: the heading each chunk would carry into the embedding."""
        if self._mods is None:
            self._mods = _import_sidecar()
        path = Path(pdf_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        chunks, _system, _systems, error = self._mods["_extract_and_chunk"](path, None, None)
        if error:
            raise RuntimeError(error)
        return [
            {"section_heading": c.section_heading, "chunk_type": str(c.chunk_type),
             "page_start": c.page_start, "page_end": c.page_end, "chars": len(c.text)}
            for c in chunks
        ]
```

Add to the `Engine` protocol docstring in `base.py` (same optional-hooks list as Task 1):

```
      ``chunks(pdf_path) -> list[dict]`` — the engine's chunker output
      (section_heading, chunk_type, page_start, page_end, chars) for the
      breadcrumb-qa suite; no embedding.
```

- [ ] **Step 6: Add the suite to `run_eval.py`**

Next to `run_corpus_qa`:

```python
# ── breadcrumb QA (roadmap 2026-09-02 Phase 0.2) ──────────────────────────

def run_breadcrumb_qa(engine, corpus) -> dict:
    """Chunk every corpus PDF (engine.chunks, no embedding) and grade each
    chunk's section_heading — the string the embedder and reranker see."""
    from evals.retrieval import breadcrumb_qa

    chunks_fn = getattr(engine, "chunks", None)
    if chunks_fn is None:
        raise SystemExit(f"engine {engine.name!r} has no chunks() hook; breadcrumb-qa needs it")
    rows = []
    for d in corpus.documents:
        print(f"chunking {d.id}…", flush=True)
        g = breadcrumb_qa.grade_doc(d.id, chunks_fn(d.pdf_path))
        rows.append(g)
        print(f"  {d.id}: {g['chunks']} chunks, markup {g['markup']}, split {g['split_letter']}, "
              f"furniture roots {g['furniture_root']}; top root {g['top_roots'][0] if g['top_roots'] else '—'}",
              flush=True)
    return {"by_doc": breadcrumb_qa.aggregate(rows), "docs": rows}
```

In `main()`: add `"breadcrumb-qa"` to the `--suite` choices and to the default-name dict (`"breadcrumb-qa": "breadcrumb-qa"`); in the `try:` dispatch add

```python
        elif args.suite == "breadcrumb-qa":
            result = run_breadcrumb_qa(engine, corpus)
```

and a write block modelled on the corpus-qa one, placed before the `if args.suite == "extraction":` block:

```python
    if args.suite == "breadcrumb-qa":
        from evals.retrieval import breadcrumb_qa

        meta = {"engine": args.engine, "name": name, "date": date}
        md = breadcrumb_qa.render_md(meta, result)
        print("\n" + md)
        if not args.no_write:
            BASELINE_DIR.mkdir(exist_ok=True)
            (BASELINE_DIR / f"{stem}.json").write_text(
                json.dumps({"meta": meta, **result}, indent=2), encoding="utf-8")
            (BASELINE_DIR / f"{stem}.md").write_text(md, encoding="utf-8")
            print(f"wrote evals/baselines/{stem}.{{json,md}}")
        return 0
```

- [ ] **Step 7: Point `library_probe.py` at the shared detector**

In `sidecar/evals/library_probe.py`, replace the `INLINE_TAGS`, `LONE_LETTER`, `heading_flaws` and `strip_markup` definitions with:

```python
# The detector is shared with the graded harness so the real-library probe
# and the corpus baseline report the same flaws (evals/retrieval/breadcrumb_qa.py).
sys.path.insert(0, str(SIDECAR_DIR.parent))
from evals.retrieval.breadcrumb_qa import flaws as _flaws, strip_markup  # noqa: E402


def heading_flaws(heading: str) -> list[str]:
    return sorted(_flaws(heading))
```

(`sys` is already imported there; `SIDECAR_DIR` is defined above the constants.)

- [ ] **Step 8: Run the suite on the corpus (sidecar env, no Ollama, ~3 min)**

```bash
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa
```

Expected: a by-doc table; `osric_2e` top root is the running footer (`fOR fRee UpdateS…`) with a large count; `srd_5_1` shows `S eed` among top roots; `all` `markup_rate` well above 0.5. Then check the probe still runs (app closed, real library indexed):

```bash
cd sidecar && uv run python evals/library_probe.py | tail -25
```

Expected: the "breadcrumb damage" section lists `markup`, `split_letter`, … percentages.

- [ ] **Step 9: Document and commit**

Add to `evals/README.md` under "Run it":

```bash
# Breadcrumb QA — every chunk's section_heading graded for markup, split
# letters, small-caps damage, furniture roots (no Ollama, ~3 min). The gate
# Phase 1's heading work must clear. Writes evals/baselines/<date>-v2-breadcrumb-qa.*
uv run --project sidecar python -m evals.run_eval --engine v2 --suite breadcrumb-qa
```

and a row in "What gates what": `| breadcrumb flaws per doc | breadcrumb-qa baseline (Phase 1 gate: markup 0, split 0, furniture roots 0) | a heading change that helps the mean and hurts a book |`.

```bash
git add evals/retrieval/breadcrumb_qa.py evals/engines/v2.py evals/engines/base.py \
        evals/run_eval.py sidecar/evals/library_probe.py evals/README.md \
        evals/tests/test_breadcrumb_qa.py evals/baselines/*-v2-breadcrumb-qa.json \
        evals/baselines/*-v2-breadcrumb-qa.md
git commit -m "feat(evals): breadcrumb-qa — grade the heading that feeds embed + rerank

Per-chunk flaws (markup, split letter, small-caps mixed case, furniture
root, no heading) over every chunk the v2 chunker emits, with top roots
per book. No embedding, seconds. Baseline committed; library_probe shares
the detector. Roadmap 2026-09-02 §4 Phase 0.2."
```

---

### Task 6: Local-only library tier — graded queries in the confusable regime

The committed corpus cannot create hundreds of topically adjacent candidates. This tier grades queries against Jerome's real index: `library.yaml` pins each book by the SHA-256 the sidecar already stores in its manifest (`content_hash`), so no path and no PDF is committed; the harness resolves docs through the manifest of a v2 data dir, skips queries whose book is absent, and never indexes. It reads the app's own index read-only, which is exactly the representative regime.

**Files:**
- Create: `evals/retrieval/library.yaml`
- Create: `evals/library.py`
- Modify: `evals/run_eval.py` (`--suite library`, guards, meta)
- Modify: `evals/engines/v2.py` (`pipeline_identity()`)
- Modify: `evals/retrieval/verify_anchors.py` (`--library DATA_DIR`)
- Modify: `evals/README.md`
- Create: `evals/tests/test_library.py`

**Interfaces:**
- Produces: `library.LIBRARY_PATH`, `library.load_library(path=LIBRARY_PATH) -> dict` (`{"docs": [...], "queries": [...]}`), `library.LibraryDoc(id, pdf_path: Path, pdf_sha256: str, system: str, ref_digest=None)`, `library.resolve(library: dict, manifest_files: dict[str, dict]) -> tuple[LibraryCorpus, list[str]]` (corpus with `.documents`, plus missing doc ids), `library.select_queries(queries, present: set[str]) -> tuple[list[dict], list[str]]`.
- Produces: `V2Engine.pipeline_identity() -> str` = `"<CHUNKER_VERSION>/<EMBEDDING_MODEL>"`.
- Consumes: `run_eval.run(...)` with `do_index=False`; `run_eval.query_docs`; `verify_anchors.verify_query`.

- [ ] **Step 1: Write the failing tests**

Create `evals/tests/test_library.py`:

```python
"""Library tier: docs pinned by SHA-256, resolved through a v2 index manifest,
never indexed by the harness (roadmap 2026-09-02 Phase 0.4)."""
import hashlib
import json

import pytest

from evals import library


def _manifest(tmp_path, files: dict[str, bytes]) -> dict:
    """Write PDFs (any bytes) + a v2-shaped index_manifest.json; return its files dict."""
    entries = {}
    for name, data in files.items():
        p = tmp_path / name
        p.write_bytes(data)
        entries[str(p)] = {"filename": name, "mtime": 0.0, "chunk_count": 1,
                           "indexed_at": "2026-09-02", "game_system": "unknown",
                           "game_systems": [], "content_hash": hashlib.sha256(data).hexdigest(),
                           "file_size": len(data)}
    (tmp_path / "index_manifest.json").write_text(json.dumps({"version": 1, "files": entries}))
    return entries


def test_resolve_maps_docs_by_sha256_and_reports_missing(tmp_path):
    files = _manifest(tmp_path, {"MM.pdf": b"monster manual", "PHB.pdf": b"players handbook"})
    lib = {"docs": [
        {"id": "mm", "sha256": hashlib.sha256(b"monster manual").hexdigest(), "title": "MM"},
        {"id": "dmg", "sha256": "0" * 64, "title": "DMG (not indexed)"},
    ], "queries": []}
    corpus, missing = library.resolve(lib, files)
    assert [d.id for d in corpus.documents] == ["mm"]
    assert corpus.documents[0].pdf_path == tmp_path / "MM.pdf"
    assert corpus.documents[0].pdf_sha256 == hashlib.sha256(b"monster manual").hexdigest()
    assert missing == ["dmg"]


def test_select_queries_skips_any_query_whose_doc_is_missing():
    queries = [
        {"id": "L001", "doc": "mm"},
        {"id": "L002", "doc": "dmg"},
        {"id": "L003", "doc": ["mm", "dmg"]},
        {"id": "L004", "doc": "any"},
    ]
    kept, skipped = library.select_queries(queries, present={"mm"})
    assert [q["id"] for q in kept] == ["L001", "L004"]
    assert skipped == ["L002", "L003"]


def test_load_library_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "library.yaml"
    p.write_text("docs:\n  - {id: mm, sha256: '%s', title: MM}\n  - {id: mm, sha256: '%s', title: MM2}\nqueries: []\n"
                 % ("a" * 64, "b" * 64))
    with pytest.raises(ValueError, match="duplicate doc id"):
        library.load_library(p)


def test_manifest_files_reads_the_v2_manifest(tmp_path):
    _manifest(tmp_path, {"MM.pdf": b"x"})
    files = library.manifest_files(tmp_path)
    assert list(files.values())[0]["filename"] == "MM.pdf"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_library.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.library'`.

- [ ] **Step 3: Create `evals/library.py`**

```python
"""The local-only library tier (roadmap 2026-09-02 §4 Phase 0.4).

The committed corpus (7 CC/OGL books) cannot create the regime a real
library does — hundreds of topically adjacent candidates — and real books
cannot be committed. So the tier pins each book by the SHA-256 the v2
sidecar already stores in ``index_manifest.json`` (``content_hash``) and
resolves it against a v2 data dir at run time. Nothing is indexed by the
harness; the app's own index is read. A query whose book is not in that
index is skipped and reported, so the same YAML runs on any machine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

LIBRARY_PATH = Path(__file__).resolve().parent / "retrieval" / "library.yaml"
MANIFEST_FILENAME = "index_manifest.json"   # sidecar/server.py MANIFEST_FILENAME


@dataclass(frozen=True)
class LibraryDoc:
    id: str
    pdf_path: Path
    pdf_sha256: str
    system: str
    ref_digest: str | None = None   # no digital-native reference for a real book


@dataclass(frozen=True)
class LibraryCorpus:
    documents: list[LibraryDoc]


def load_library(path: Path = LIBRARY_PATH) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = raw.get("docs") or []
    queries = raw.get("queries") or []
    seen: set[str] = set()
    for d in docs:
        if d["id"] in seen:
            raise ValueError(f"duplicate doc id {d['id']!r} in {path.name}")
        seen.add(d["id"])
        if len(d["sha256"]) != 64:
            raise ValueError(f"doc {d['id']!r}: sha256 must be 64 hex chars")
    return {"docs": docs, "queries": queries}


def manifest_files(data_dir: Path) -> dict[str, dict]:
    """``{absolute pdf path: manifest entry}`` from a v2 data dir."""
    p = Path(data_dir) / MANIFEST_FILENAME
    if not p.exists():
        raise FileNotFoundError(f"no {MANIFEST_FILENAME} in {data_dir} — is this a v2 data dir?")
    return json.loads(p.read_text(encoding="utf-8")).get("files", {})


def resolve(library: dict, files: dict[str, dict]) -> tuple[LibraryCorpus, list[str]]:
    """Map library docs onto indexed files by content hash."""
    by_hash = {e.get("content_hash"): (path, e) for path, e in files.items() if e.get("content_hash")}
    docs: list[LibraryDoc] = []
    missing: list[str] = []
    for d in library["docs"]:
        hit = by_hash.get(d["sha256"])
        if hit is None:
            missing.append(d["id"])
            continue
        path, entry = hit
        docs.append(LibraryDoc(id=d["id"], pdf_path=Path(path), pdf_sha256=d["sha256"],
                               system=d.get("title", d["id"])))
    return LibraryCorpus(documents=docs), missing


def select_queries(queries: list[dict], present: set[str]) -> tuple[list[dict], list[str]]:
    """Queries whose every doc is present (``any`` needs nothing)."""
    kept: list[dict] = []
    skipped: list[str] = []
    for q in queries:
        doc = q["doc"]
        needed = [] if doc == "any" else (list(doc) if isinstance(doc, list) else [doc])
        if all(d in present for d in needed):
            kept.append(q)
        else:
            skipped.append(q["id"])
    return kept, skipped
```

- [ ] **Step 4: Run the library tests to verify they pass**

Run: `uv run --project sidecar-v3 pytest evals/tests/test_library.py -v`
Expected: all PASS.

- [ ] **Step 5: Create `evals/retrieval/library.yaml` (schema + empty tier)**

```yaml
# Local-only library tier — roadmap 2026-09-02 §4 Phase 0.4.
#
# Books are pinned by the SHA-256 the sidecar stores as `content_hash` in the
# v2 data dir's index_manifest.json. No path, no PDF in git. A query whose
# book is not in the index being read is skipped and reported.
#
# Get a book's sha256 from your indexed library:
#   python3 -c "import json,sys;m=json.load(open(sys.argv[1]));[print(e['content_hash'],e['filename']) for e in m['files'].values()]" \
#     "$HOME/Library/Application Support/games.unseenservant.legendlore/chroma_db/index_manifest.json"
#
# Query fields are identical to queries.yaml (id, pair, style, scope, category,
# query, doc, anchors, pages). Use ids L001… so they never collide. Author in
# the confusable regime: things that exist in several books at once.
#
# Verify anchors against the PDFs before committing:
#   uv run --project sidecar python -m evals.retrieval.verify_anchors --library "<data dir>"
docs: []
queries: []
```

- [ ] **Step 6: Add `pipeline_identity()` to the v2 adapter**

In `evals/engines/v2.py`, add `CHUNKER_VERSION` and `EMBEDDING_MODEL` to the `from server import (...)` list and the returned dict, then:

```python
    def pipeline_identity(self) -> str:
        """What produced the chunks this engine searches — recorded in a
        library-tier baseline, since that index was not built by the run."""
        if self._mods is None:
            self._mods = _import_sidecar()
        return f"{self._mods['CHUNKER_VERSION']}/{self._mods['EMBEDDING_MODEL']}"
```

- [ ] **Step 7: Add `--suite library` to `run_eval.py`**

In `main()`:
- add `"library"` to `--suite` choices and to the default-name dict (`"library": "library"`);
- replace the retrieval-only guard block with:

```python
    if args.suite == "retrieval":
        ...  # existing four guards unchanged
    if args.suite == "library":
        if args.data_dir is None:
            raise SystemExit("--suite library reads an existing v2 index: pass --data-dir <app data dir>")
        if (args.data_dir / "sidecar.port").exists():
            raise SystemExit("a sidecar is running on that data dir — quit Legend Lore first "
                             "(two processes on one ChromaDB fight over SQLite)")
```

- make the corpus gate conditional: `corpus = require_corpus() if args.suite != "library" else None`;
- in the temporary-index block, keep `args.suite == "retrieval"` as the only case that creates a temp dir (library uses `args.data_dir` as is);
- in the `try:` dispatch add, before the generic retrieval `else`:

```python
        elif args.suite == "library":
            from evals import library as lib

            spec = lib.load_library()
            corpus, missing = lib.resolve(spec, lib.manifest_files(data_dir))
            present = {d.id for d in corpus.documents}
            queries, skipped = lib.select_queries(spec["queries"], present)
            if missing:
                print(f"library docs not in this index (skipped): {', '.join(missing)}")
            if skipped:
                print(f"queries skipped: {', '.join(skipped)}")
            if not queries:
                raise SystemExit("no runnable library queries — author some in evals/retrieval/library.yaml")
            if args.limit:
                queries = queries[: args.limit]
            opts = SearchOptions(n_results=args.n_results, hybrid=args.hybrid,
                                 extra={"system_map": {}})
            result = run(engine, queries, corpus, opts, do_index=False)
            result["skipped_queries"], result["missing_docs"] = skipped, missing
```

- in the retrieval `meta` block, make the index description honest:

```python
        "index": ({"mode": "library", "data_dir": str(data_dir),
                   "pipeline_identity": getattr(engine, "pipeline_identity", lambda: "unknown")()}
                  if args.suite == "library" else
                  {"mode": "fresh", "pipeline_identity": "engine-managed"}),
        "skipped_queries": result.get("skipped_queries", []),
        "missing_docs": result.get("missing_docs", []),
```

(`corpus_fingerprint(corpus)` works unchanged: `LibraryDoc` carries `id`, `pdf_sha256`, `ref_digest`.) The `--no-write` rule for reused indexes stays for `retrieval`; `library` writes `<date>-v2-library.*` normally because its index is the app's, and `meta.index` says so.

- [ ] **Step 8: Add `--library` to `verify_anchors.py`**

Add a PDF-only text source and a flag:

```python
class PdfText:
    """PDF-only oracle for a real-library book (no digital-native reference)."""

    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self._pages_norm: list[str] | None = None

    def _load(self):
        import fitz

        with fitz.open(self.pdf_path) as pdf:
            self._pages_norm = [norm(p.get_text()) for p in pdf]

    def ref_norm(self, _answer_ref):   # no reference: the PDF stands in for it
        return self.pdf_norm()

    def pdf_norm(self) -> str:
        if self._pages_norm is None:
            self._load()
        return "\n".join(self._pages_norm)

    def anchor_pages(self, anchor) -> list[int]:
        if self._pages_norm is None:
            self._load()
        return [i + 1 for i, pg in enumerate(self._pages_norm)
                if any(norm(alt) in pg for alt in anchor_alts(anchor))]
```

add `import argparse` to the module imports, and at the top of `main()`:

```python
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--library", type=Path, default=None,
                    help="verify evals/retrieval/library.yaml against the PDFs of this v2 data dir")
    args = ap.parse_args()
    if args.library:
        from evals import library as lib

        spec = lib.load_library()
        corpus, missing = lib.resolve(spec, lib.manifest_files(args.library))
        by_id = {d.id: PdfText(d.pdf_path) for d in corpus.documents}
        queries, skipped = lib.select_queries(spec["queries"], set(by_id))
        if missing or skipped:
            print(f"not in this index — docs: {missing}  queries: {skipped}")
    else:
        corpus = require_corpus()
        by_id = {d.id: DocText(d) for d in corpus.documents}
        queries = yaml.safe_load(QUERIES_PATH.read_text(encoding="utf-8"))
```

The rest of `main()` (the loop over `verify_query`) is unchanged. Note `verify_query` calls `by_id[docs[0]].ref_norm(...)`; `PdfText.ref_norm` returns the PDF text, so "ref ∧ pdf" degrades to "pdf" for library docs — which is the only oracle a real book has.

- [ ] **Step 9: Run the full eval test suite and an end-to-end dry run**

Run: `uv run --project sidecar-v3 pytest evals/tests -v`
Expected: all PASS.

Dry run with the empty tier (app closed):

```bash
uv run --project sidecar python -m evals.run_eval --engine v2 --suite library \
    --data-dir "$HOME/Library/Application Support/games.unseenservant.legendlore/chroma_db" --no-write
```

Expected: `no runnable library queries — author some in evals/retrieval/library.yaml` (exit 1). That proves the guards and manifest resolution run; the tier itself is empty until Step 10.

- [ ] **Step 10: Author the tier [Jerome runs]**

Author ≥ 20 queries in `library.yaml` against the real library, following the roadmap's brief (spells or rules that exist in 4+ books, "falling damage" across systems, exact stat codes), in both keyword and natural-language style, all three scopes. Then:

```bash
uv run --project sidecar python -m evals.retrieval.verify_anchors --library "<data dir>"
uv run --project sidecar python -m evals.run_eval --engine v2 --suite library --data-dir "<data dir>"
```

Expected: every query verified; `wrote evals/baselines/<date>-v2-library.{json,md,results.json,html}`. This baseline is the tier's first number; Phase 1–3 rungs gate against it with `--gate` the same way.

- [ ] **Step 11: Document and commit**

`evals/README.md`, under "Suites", add:

```
**Library tier** (`retrieval/library.yaml`, `evals/library.py`) — graded queries
against YOUR indexed library, the confusable regime the 7-book corpus cannot
create. Books are pinned by the sidecar's own `content_hash`; the harness reads
the app's index (quit the app first), never indexes, and skips queries whose
book is absent. Local-only by construction: the YAML commits hashes + anchors,
never a PDF. `--suite library --data-dir <app data dir>`; verify with
`verify_anchors --library <app data dir>`.
```

```bash
git add evals/library.py evals/retrieval/library.yaml evals/run_eval.py evals/engines/v2.py \
        evals/retrieval/verify_anchors.py evals/README.md evals/tests/test_library.py
git commit -m "feat(evals): local-only library tier — graded queries on the real index

Books pinned by the manifest's content_hash, resolved at run time, never
indexed by the harness; queries whose book is absent are skipped. Answers
the corpus-source question with two tiers: committed CC corpus + local
library. Roadmap 2026-09-02 §4 Phase 0.4."
```

The authored queries and the first `<date>-v2-library.*` baseline land in a second commit once Jerome has scored them:

```bash
git add evals/retrieval/library.yaml evals/baselines/*-v2-library.json evals/baselines/*-v2-library.md
git commit -m "eval(evals): first library-tier baseline (<N> queries, <M> books)"
```

---

### Task 7: v2 blind round with the readability tick **[Jerome runs]**

The 08-15 sheet predates the "garbled" tick, so v2 has no `readable@5`. Regenerate from `phase0b` (same chunks, cued order changed) and score all 68 queries once; this is the human bar Phase 4 clears.

**Files:**
- Create: `evals/baselines/<date>-v2-phase0b.blind.json`, `…phase0b.blind.md` (the `.blind.html` is gitignored)
- Modify: `evals/README.md` (one line)

- [ ] **Step 1: Generate and serve the sheet**

```bash
uv run --project sidecar python -m evals.blind.generate evals/baselines/<date>-v2-phase0b
cd evals/baselines && python3 -m http.server 8765
```

Open `http://localhost:8765/<date>-v2-phase0b.blind.html`. (Serve over http: a `file://` preview runs as a `data:` URL and localStorage is disabled, so the sheet would not keep ticks.)

- [ ] **Step 2: Score**

For each of the 68 queries: tick every chunk that answers the query; tick **garbled** on any chunk you cannot read as prose (interleaved columns, torn stat lines, whitespace litter); mark the query reviewed. Export → saves `<date>-v2-phase0b.blind.json` next to the sheet.

- [ ] **Step 3: Score the sheet against the anchor grade**

```bash
uv run --project sidecar python -m evals.blind.score evals/baselines/<date>-v2-phase0b
```

Expected: `Reviewed 68 queries (skipped 0)`; κ ≥ 0.70 overall (08-15 was 0.740); a `readable@5` number per scope (not `—`); the disagreements list. Record human single MRR@5 and readable@5 in the roadmap §5 table's "why" column for the two human rows (replace "(0.87)" with the new human single, and note readable@5).

- [ ] **Step 4: Commit**

```bash
git add evals/baselines/*-v2-phase0b.blind.json evals/baselines/*-v2-phase0b.blind.md \
        docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md
git commit -m "eval(evals): v2 phase0b blind round — κ <x>, human single <x>, readable@5 <x>

First readability number for v2; the human bar Phase 4 must clear."
```

---

### Task 8: Explain the three YZE misses (q023, q024, q050)

Both engines miss these; the roadmap does not know why. Classify each as ranking, chunk boundary, or anchor artefact, fix an anchor artefact if that is what it is, and log the verdict.

**Files:**
- Modify (maybe): `evals/retrieval/queries.yaml`
- Modify: `docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md` §8

- [ ] **Step 1: Where is the answer in the PDF, and in which v2 chunk?**

```bash
uv run --project sidecar python - <<'EOF'
import json, glob, yaml
from evals.corpus import require_corpus
from evals.retrieval.verify_anchors import DocText
from evals.retrieval.grade import matched_anchor_indexes
c = require_corpus(); yze = DocText(next(d for d in c.documents if d.id == "yze_srd"))
qs = {q["id"]: q for q in yaml.safe_load(open("evals/retrieval/queries.yaml"))}
res = json.load(open(sorted(glob.glob("evals/baselines/*-v2-phase0b.results.json"))[-1]))["results"]
for qid in ("q023", "q024", "q050"):
    q = qs[qid]
    print("\n==", qid, q["query"], "| anchors", q["anchors"])
    for a in q["anchors"]:
        print("   anchor", a, "on PDF pages", yze.anchor_pages(a))
    for h in res[qid][:10]:
        hit = matched_anchor_indexes(f"{h['section_heading']}\n{h['snippet']}", q["anchors"])
        print(f"   #{h['rank']:<2} {h['book'][:20]:<20} p{h['page_start']:<4} anchors {sorted(hit)}  {h['section_heading'][:50]}")
EOF
```

Read the output per query:
- if the anchors share **one** PDF page but no top-10 chunk from that page carries all of them → **chunk boundary** (the answer is split across chunks; Phase 2.1 section parents is the fix — note it there);
- if a top-10 chunk from the answer page carries all anchors but is graded a miss → it is not (the grader would have matched); if it carries all but one anchor whose wording differs from the PDF → **anchor artefact**: replace that anchor with an any-of list that appears in ref ∧ PDF and re-run `verify_anchors`;
- if the answer page never appears in the top 10 → **ranking**: note what outranked it (the `INTRODUCTION` chunks at 0.93–0.99 point at the saturated reranker; Phase 3.2).

- [ ] **Step 2: Apply an anchor fix if that is the verdict**

Edit the anchors in `queries.yaml`, then:

```bash
uv run --project sidecar python -m evals.retrieval.verify_anchors
```

Expected: `68/68 queries fully verified`. If anchors changed, re-run the `phase0b` retrieval baseline (Task 4 Step 1) so the committed number reflects the corrected queries — the index is unchanged, so the only lines that move in the Task 4 Step 2 diff are the three YZE queries.

- [ ] **Step 3: Log the verdict**

Append to the roadmap §8 table:

```
| YZE q023/q024/q050 explained | <per query: chunk boundary / ranking / anchor artefact, one clause each, with the page number> | — |
```

and, if any is a chunk-boundary case, add it to Phase 2.1's verify column ("q023/q024 flip").

- [ ] **Step 4: Commit**

```bash
git add evals/retrieval/queries.yaml docs/roadmap/2026-09-02-v2-retrieval-improvement-roadmap.md \
        evals/baselines/*-v2-phase0b.json evals/baselines/*-v2-phase0b.md
git commit -m "eval(evals): explain the three YZE misses (q023/q024/q050)

<one line per query with the verdict>. Roadmap 2026-09-02 §4 Phase 0.6."
```

---

## Self-review

**Spec coverage** (roadmap §4 Phase 0):
- 0.1 tag + re-baseline → Tasks 1, 4. 0.2 breadcrumb-qa + probe → Task 5. 0.3 cued-twin → Task 2. 0.4 library tier → Task 6. 0.5 blind round → Task 7. 0.6 YZE misses → Task 8. 0.7 payload@8k → Task 3 (named `top3_fit@8k`, the DoD's "top-3 intact inside 8 000 chars").

**Placeholder scan:** the `<date>`, `<x>` and `<data dir>` tokens are values produced by the runs themselves (file stems, measured numbers, Jerome's data dir); each step says where the value comes from. The empty `library.yaml` is a valid state, not a placeholder — the schema is in its header and Task 6 Step 10 is the authoring step.

**Type consistency:** `run(..., tags=)` (Task 1) and `query_docs` (Task 2) are the only runner signatures later tasks rely on; Task 6 calls `run(engine, queries, corpus, opts, do_index=False)` with a `LibraryCorpus` whose `documents` expose `id`, `pdf_path`, `pdf_sha256`, `ref_digest` — the four attributes `run()` and `corpus_fingerprint()` read. `grade_response`'s third argument is `str | set[str] | None` everywhere after Task 2. `verify_query(q, by_id)` (Task 2) is reused by Task 6 with `PdfText` objects that implement the same three methods as `DocText`.

**Ordering:** Tasks 1–3 change what a baseline measures and land before Task 4 writes `phase0b`; Task 7 and Task 8 read `phase0b`'s side files; Task 5 and Task 6 are independent of 4/7/8 and can run in parallel with them.
