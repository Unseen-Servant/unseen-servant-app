"""Does the first search after an idle spell still run warm? (#341)

Ollama unloads an idle model after ~5 minutes and the sidecar's
keep-warm ticker re-embeds inside that window, so a search taken after
a long lull should cost about what a warm one costs. This probe
measures that against a sidecar that is already running::

    uv run --project sidecar python sidecar/server.py --data-dir evals/.eval_data/v2 --port 8420
    uv run --project sidecar python -m evals.retrieval.idle_probe --idle 600

Not part of any suite — it spends its idle window in wall-clock time by
design, so it is run by hand when the warm-up path changes. One untimed
search primes the process first: the comparison that matters is warm
versus post-idle, and a cold first search (model loads, vocabulary
build) would flatter the ratio.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

BAR = 1.5  # post-idle search within 1.5x of a warm one


def timed_search(url: str, query: str, timeout: float) -> tuple[float, int]:
    """(latency_ms, result_count) for one /api/search round trip."""
    body = json.dumps({"query": query, "n_results": 10}).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/search",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    return (time.perf_counter() - start) * 1000, len(payload.get("results", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default="http://localhost:8420",
                    help="running sidecar (default: %(default)s)")
    ap.add_argument("--query", default="how does armor reduce damage")
    ap.add_argument("--idle", type=float, default=600,
                    help="seconds between the two timed searches")
    ap.add_argument("--timeout", type=float, default=300,
                    help="per-request timeout; a cold model load is slow")
    args = ap.parse_args()

    prime_ms, _ = timed_search(args.url, args.query, args.timeout)
    print(f"prime (untimed baseline): {prime_ms:.0f} ms", flush=True)

    warm_ms, warm_n = timed_search(args.url, args.query, args.timeout)
    print(f"warm search:  {warm_ms:8.0f} ms  ({warm_n} results)", flush=True)

    print(f"idling {args.idle:.0f}s ...", flush=True)
    time.sleep(args.idle)

    idle_ms, idle_n = timed_search(args.url, args.query, args.timeout)
    print(f"after idle:   {idle_ms:8.0f} ms  ({idle_n} results)")

    ratio = idle_ms / warm_ms if warm_ms else float("inf")
    verdict = "PASS" if ratio <= BAR else "FAIL"
    print(f"ratio: {ratio:.2f}x  (bar <= {BAR}x)  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
