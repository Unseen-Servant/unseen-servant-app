"""Spell-correction accuracy on typo'd eval queries (roadmap 3.5).

No Ollama, no ground truth beyond the query itself: every eligible word of
every query in ``evals/retrieval/queries.yaml`` is corrupted ``--samples``
times by the seeded error model (``typos.py``), the whole query goes
through the real ``SpellCorrector`` (context included), and the corrupted
word's fate is tallied:

  restored     corrected back to the original word
  miscorrected rewritten to a different word — worse than leaving it
  left         typo left as typed
  real-word    the typo is itself a valid word (library or English): an
               out-of-vocabulary corrector cannot see it, by design

Also counted: collateral (another word of the query changed) and clean
false positives (a clean query changed at all). Content words and
stopwords are reported apart — fixing one by breaking the other is not
an improvement.

    uv run --project sidecar python -m evals.retrieval.spell_bench \\
        --data-dir evals/.eval_data/v2-p3
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
QUERIES = ROOT / "evals/retrieval/queries.yaml"

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def load_corrector(data_dir: Path):
    """The production corrector, protecting the built-in system keywords
    the way ``/api/search`` does (custom systems aside)."""
    sys.path.insert(0, str(ROOT / "sidecar"))
    from legend_lore.embedder import EMBEDDING_DIM, EMBEDDING_MODEL
    from legend_lore.game_systems import KNOWN_SYSTEMS
    from legend_lore.library_store import LIBRARY_FILENAME, LibraryStore
    from legend_lore.spelling import SpellCorrector, keyword_tokens

    store = LibraryStore.open(
        data_dir / LIBRARY_FILENAME, EMBEDDING_MODEL, EMBEDDING_DIM
    )
    corrector = SpellCorrector.from_store(store)
    protected = keyword_tokens(KNOWN_SYSTEMS)
    plain = corrector.correct
    corrector.correct = lambda q: plain(q, protected=protected)
    return corrector


def bench(corrector, queries: list[str], samples: int, seed: int) -> dict:
    sys.path.insert(0, str(ROOT / "sidecar"))
    from legend_lore.lexical import _STOPWORDS
    from legend_lore.spelling import _english_words

    from evals.retrieval.typos import MIN_WORD_LEN, typo

    def valid(word: str) -> bool:
        w = word.lower()
        return corrector._in_vocab(w) or w in _english_words()

    tally = {"content": Counter(), "stopword": Counter()}
    collateral = clean_fp = 0
    examples: dict[str, list[str]] = {"miscorrected": [], "left": []}
    rng = random.Random(seed)
    for q in queries:
        if corrector.correct(q) is not None:
            clean_fp += 1
        matches = [m for m in _TOKEN_RE.finditer(q)
                   if m.group().isalpha() and len(m.group()) >= MIN_WORD_LEN]
        for m in matches:
            word = m.group()
            kind = "stopword" if word.lower() in _STOPWORDS else "content"
            for _ in range(samples):
                bad = typo(word, rng)
                typed = q[:m.start()] + bad + q[m.end():]
                out = corrector.correct(typed) or typed
                before, after = _TOKEN_RE.findall(typed), _TOKEN_RE.findall(out)
                idx = len(_TOKEN_RE.findall(q[:m.start()]))
                got = after[idx] if idx < len(after) and len(after) == len(before) else None
                if valid(bad):
                    outcome = "real-word"
                elif got is not None and got.lower() == word.lower():
                    outcome = "restored"
                elif got is not None and got.lower() == bad.lower():
                    outcome = "left"
                else:
                    outcome = "miscorrected"
                tally[kind][outcome] += 1
                if outcome in examples and len(examples[outcome]) < 12:
                    examples[outcome].append(f"{bad}→{got} ({word})")
                if len(after) == len(before) and any(
                    a.lower() != b.lower()
                    for j, (a, b) in enumerate(zip(before, after)) if j != idx
                ):
                    collateral += 1
    return {"tally": tally, "collateral": collateral, "clean_fp": clean_fp,
            "n_queries": len(queries), "examples": examples}


def format_report(r: dict) -> str:
    out = [f"{'words':<9}{'typos':>6}{'restored':>10}{'miscorr.':>10}{'left':>7}"
           f"{'real-word':>11}   restored of fixable"]
    for kind, t in r["tally"].items():
        n = sum(t.values())
        fixable = n - t["real-word"]
        out.append(
            f"{kind:<9}{n:>6}{t['restored'] / n:>10.1%}{t['miscorrected'] / n:>10.1%}"
            f"{t['left'] / n:>7.1%}{t['real-word'] / n:>11.1%}"
            f"   {t['restored'] / max(fixable, 1):.1%}")
    out.append(f"collateral (another word changed): {r['collateral']}")
    out.append(f"clean queries changed: {r['clean_fp']} / {r['n_queries']}")
    for k, ex in r["examples"].items():
        out.append(f"e.g. {k}: " + ", ".join(ex))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="an index directory (vocabulary comes from its unit_fts rows)")
    ap.add_argument("--samples", type=int, default=5, help="typos per eligible word")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    queries = [q["query"] for q in yaml.safe_load(QUERIES.read_text(encoding="utf-8"))]
    print(format_report(bench(load_corrector(args.data_dir), queries, args.samples, args.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
