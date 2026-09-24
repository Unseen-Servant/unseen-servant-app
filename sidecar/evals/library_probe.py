"""Retrieval quality probe against the *real* library.

The eval harness (``run_eval.py``) grades a locked 3-book corpus with
pre-registered ground truth, which is the right tool for comparing pipeline
changes. It cannot see the regime a real library creates: hundreds of
topically adjacent candidates, and chunk metadata degraded by extraction.

This probe has no ground truth and computes no nDCG. It reports the shape of
what search returns — tier distribution and breadcrumb health — which is what
surfaced the defects in
docs/roadmap/2026-08-14-agent-harness-retrieval-findings.md.

Why it exists: an agent consumes the whole result set as flat context, with
no ability to skip the junk a GM skips visually. That makes "how much of this
result set is usable?" a real quality question, and it is not one the graded
harness asks.

    python evals/library_probe.py                       # your indexed library
    python evals/library_probe.py --data-dir /path      # somewhere else
    python evals/library_probe.py --n-results 25

Requires the app to be closed: two sidecars on one ChromaDB will fight over
SQLite.
"""

import argparse
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

SIDECAR_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = (
    Path.home()
    / "Library/Application Support/games.unseenservant.legendlore/chroma_db"
)

# Ordinary mid-session lookups, not retrieval-shaped keyword queries. The
# graded corpus deliberately uses locked phrasings; these are deliberately
# the way a GM types.
# #366 / roadmap 3.4: above this share "strong" stops discriminating.
STRONG_SHARE_MAX = 0.35

DEFAULT_QUERIES = [
    "falling damage",
    "how does grappling work",
    "rules for surprise in combat",
    "what happens at zero hit points",
    "how do I roll initiative",
    "encumbrance and carrying capacity",
    "rules for underwater combat",
    "how does darkvision work",
    "sneak attack damage",
    "what does a critical hit do",
]

# The detector is shared with the graded harness so the real-library probe
# and the corpus baseline report the same flaws (evals/retrieval/breadcrumb_qa.py).
sys.path.insert(0, str(SIDECAR_DIR.parent))
from evals.retrieval.breadcrumb_qa import flaws as _flaws, strip_markup  # noqa: E402


def heading_flaws(heading: str) -> list[str]:
    return sorted(_flaws(heading))


def start_sidecar(data_dir: Path, log_path: Path):
    running = subprocess.run(
        ["pgrep", "-f", "legend-lore-sidecar"], capture_output=True, text=True
    ).stdout.strip()
    if running:
        sys.exit("A Legend Lore sidecar is already running — quit the app first.")

    port_file = data_dir / "sidecar.port"
    if port_file.exists():
        port_file.unlink()

    proc = subprocess.Popen(
        [sys.executable, str(SIDECAR_DIR / "server.py"),
         "--port", "0", "--data-dir", str(data_dir)],
        cwd=str(SIDECAR_DIR), stdout=log_path.open("w"),
        stderr=subprocess.STDOUT, text=True,
    )
    for _ in range(600):
        if port_file.exists():
            try:
                return proc, f"http://127.0.0.1:{int(port_file.read_text().strip())}"
            except ValueError:
                pass
        if proc.poll() is not None:
            sys.exit(f"sidecar died on startup — see {log_path}")
        time.sleep(0.2)
    proc.kill()
    sys.exit("sidecar never published a port")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--n-results", type=int, default=15)
    ap.add_argument("--log", type=Path, default=Path("/tmp/library-probe.log"))
    args = ap.parse_args()

    if not args.data_dir.exists():
        sys.exit(f"no indexed data at {args.data_dir}")

    proc, base = start_sidecar(args.data_dir, args.log)
    try:
        stats = httpx.get(f"{base}/api/stats", timeout=60).json()
        print(f"library: {stats['total_documents']} books, "
              f"{stats['total_chunks']:,} chunks, n_results={args.n_results}\n")

        tiers_total, damage_total = Counter(), Counter()
        headings_seen = 0
        top_hits = []

        for query in DEFAULT_QUERIES:
            body = {"query": query, "n_results": args.n_results}
            results = httpx.post(f"{base}/api/search", json=body,
                                 timeout=300).json().get("results", [])
            tiers = Counter(r["tier"] for r in results)
            tiers_total.update(tiers)
            for r in results:
                headings_seen += 1
                for flaw in heading_flaws(r.get("section_heading", "")):
                    damage_total[flaw] += 1
            if results:
                top_hits.append((query, results[0]))
            print(f"{query[:34]:<34} strong {tiers['strong']:>3}  "
                  f"good {tiers['good']:>3}  weak {tiers['weak']:>3}")

        total = sum(tiers_total.values()) or 1
        print(f"\n=== tiers over {len(DEFAULT_QUERIES)} queries, {total} results ===")
        for tier in ("strong", "good", "weak"):
            print(f"  {tier:<7} {tiers_total[tier]:>4}  {tiers_total[tier] / total:>5.0%}")
        strong_share = tiers_total["strong"] / total
        print(f"  target: strong ≤ {STRONG_SHARE_MAX:.0%} (#366) — "
              + ("OK" if strong_share <= STRONG_SHARE_MAX else "OVER"))
        print("  A tier that covers most results carries no signal — and for an "
              "agent it is the only\n  per-result quality hint in the tool output.")

        print(f"\n=== breadcrumb damage over {headings_seen} chunks ===")
        for flaw, count in damage_total.most_common():
            print(f"  {flaw:<12} {count:>4}  {count / max(headings_seen, 1):>5.0%}")
        if not damage_total:
            print("  none detected")
        print("  section_heading feeds both the embedding and the reranker, so "
              "damage here is\n  a retrieval defect, not a display one.")

        print("\n=== top hit per query ===")
        for query, hit in top_hits:
            print(f"  {query[:30]:<30} [{hit['tier']:<6}] "
                  f"{hit['filename'][:24]:<24} {strip_markup(hit['section_heading'])[:46]}")
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
