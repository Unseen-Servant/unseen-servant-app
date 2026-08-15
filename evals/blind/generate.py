"""Blind scoresheet generator — the human half of Phase 0 (scaffold §2).

Renders a self-contained HTML scoresheet from a baseline's results: each
query with its top-N retrieved chunks in RANDOM order, stripped of every
pipeline hint (rank, tier, relevance) and of the auto ✓/· and the anchors.
The human marks which snippets actually answer the query, ticks Reviewed,
and Exports ``<stem>.blind.json``. blind/score.py then compares those labels
to the deterministic anchor grade → a trust number + the anchors to fix.

    uv run --project sidecar python -m evals.blind.generate \
        evals/baselines/2026-08-15-v2-phase0 [--top 5] [--open]

The scoresheet is gitignored (regenerable); the exported labels are the
human artifact worth committing.
"""
from __future__ import annotations

import argparse
import json
import random
import webbrowser
from pathlib import Path


def _stem(path) -> Path:
    s = str(path)
    for suffix in (".results.json", ".blind.json", ".blind.html", ".json", ".html", ".md"):
        if s.endswith(suffix):
            return Path(s[: -len(suffix)])
    return Path(s)


def build(stem, top: int) -> dict:
    """Per-query blind view: top-N chunks, shuffled (stable per query), with
    all pipeline hints removed."""
    stem = _stem(stem)
    baseline = json.loads(Path(f"{stem}.json").read_text(encoding="utf-8"))
    results = json.loads(Path(f"{stem}.results.json").read_text(encoding="utf-8"))["results"]
    queries = []
    for q in sorted(baseline["per_query"], key=lambda x: x["id"]):
        rows = results.get(q["id"], [])[:top]
        # Shuffle stably per query so reloads keep the same order; the true
        # rank rides along in `rank` for export, but is not shown.
        shuffled = list(rows)
        random.Random(q["id"]).shuffle(shuffled)
        queries.append({
            "id": q["id"],
            "query": q["query"],
            "chunks": [
                {"rank": c["rank"], "book": c["book"],
                 "heading": c["section_heading"], "page_start": c["page_start"],
                 "page_end": c["page_end"], "snippet": c["snippet"]}
                for c in shuffled
            ],
        })
    return {"baseline": _stem(stem).name, "top": top, "queries": queries}


def write_html(stem, top: int) -> Path:
    data = build(stem, top)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = Path(f"{_stem(stem)}.blind.html")
    out.write_text(_TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("baseline", help="baseline stem or <stem>.json")
    ap.add_argument("--top", type=int, default=5, help="chunks scored per query (default 5)")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    out = write_html(args.baseline, args.top)
    print(f"wrote {out}  ({args.top} chunks × queries to score)")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>blind scoresheet</title>
<style>
:root{
  --bg-app:#191919; --bg-container:#232323; --bg-hover:#323232;
  --text-primary:#c9d1d9; --text-secondary:#8b949e; --text-tertiary:#7d8590;
  --text-accent:rgb(182,159,129); --text-active:#9076be; --text-connected:#b08850;
  --border:rgb(50,50,50);
  --font-body:Georgia,'Times New Roman',serif; --font-mono:ui-monospace,'SF Mono',Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0 auto;max-width:900px;padding:26px 26px 120px;background:var(--bg-app);
  color:var(--text-primary);font-family:var(--font-body);font-size:15px;line-height:1.55}
h1{font-size:20px;margin:0 0 4px;color:var(--text-accent);font-weight:600}
.intro{color:var(--text-secondary);font-size:13.5px;margin:0 0 18px}
.q{border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin:14px 0;background:var(--bg-container)}
.q.reviewed{border-color:var(--text-connected)}
.qhead{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:10px}
.qtext{font-size:16px;color:var(--text-primary)}
.qid{font-family:var(--font-mono);color:var(--text-secondary);font-size:12px}
.reviewed-btn{cursor:pointer;user-select:none;font-size:12.5px;color:var(--text-tertiary);
  border:1px solid var(--border);border-radius:3px;padding:2px 10px;white-space:nowrap}
.reviewed-btn.on{color:var(--text-connected);border-color:var(--text-connected)}
.chunk{display:flex;gap:12px;padding:9px 0;border-top:1px solid rgba(50,50,50,.6)}
.mark{cursor:pointer;user-select:none;flex:0 0 84px;height:fit-content;text-align:center;
  border:1px solid var(--border);border-radius:3px;padding:4px 0;font-size:12px;color:var(--text-tertiary)}
.mark.on{color:var(--text-accent);border-color:var(--text-accent);background:rgba(182,159,129,.08)}
.body{flex:1;min-width:0}
.src{color:var(--text-secondary);font-size:12px;font-family:var(--font-mono)}
.heading{color:var(--text-accent);font-size:13px}
.snippet{color:var(--text-primary);font-size:13.5px;white-space:pre-wrap;word-break:break-word;margin-top:2px}
.bar{position:fixed;left:0;right:0;bottom:0;background:#111;border-top:1px solid var(--border);
  padding:10px 26px;display:flex;justify-content:space-between;align-items:center;
  max-width:900px;margin:0 auto}
.progress{color:var(--text-secondary);font-variant-numeric:tabular-nums;font-size:13px}
.export{cursor:pointer;color:var(--text-active);border:1px solid var(--text-active);
  border-radius:3px;padding:5px 16px;font-size:13px;background:none}
.export:hover{background:var(--bg-hover)}
</style></head>
<body>
<h1>blind scoresheet</h1>
<div class="intro">For each query, mark the snippets that <b>correctly answer it</b> — no pipeline
hints are shown, and the order is randomised. A query that <i>names a system</i> requires that
system's answer; an ambiguous query accepts any system's. Tick <b>reviewed</b> when done with a
query (even if nothing was relevant). Progress saves in this browser; <b>Export</b> when finished
and hand back the downloaded file.</div>
<div id="app"></div>
<div class="bar"><span class="progress" id="progress"></span>
  <button class="export" id="export">Export labels ↓</button></div>
<script>
const DATA = __DATA__;
const KEY = "blind:" + DATA.baseline;
const store = JSON.parse(localStorage.getItem(KEY) || "{}");   // {qid:{reviewed:bool, relevant:[rank]}}
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function save(){ localStorage.setItem(KEY, JSON.stringify(store)); progress(); }
function rec(qid){ return store[qid] || (store[qid]={reviewed:false, relevant:[]}); }
function progress(){
  const done = DATA.queries.filter(q => (store[q.id]||{}).reviewed).length;
  document.getElementById("progress").textContent =
    `reviewed ${done} / ${DATA.queries.length} queries`;
}

const app = document.getElementById("app");
for(const q of DATA.queries){
  const r = rec(q.id);
  const div = document.createElement("div");
  div.className = "q" + (r.reviewed ? " reviewed" : "");
  const pages = c => c.page_start==null ? "" : (c.page_end && c.page_end!==c.page_start
    ? `p.${c.page_start}-${c.page_end}` : `p.${c.page_start}`);
  div.innerHTML =
    `<div class="qhead"><span class="qtext">${esc(q.query)}</span>`
    + `<span class="qid">${esc(q.id)}</span></div>`
    + q.chunks.map(c =>
        `<div class="chunk"><span class="mark ${r.relevant.includes(c.rank)?'on':''}" data-rank="${c.rank}">`
        + `${r.relevant.includes(c.rank)?'✓ relevant':'relevant?'}</span>`
        + `<div class="body"><span class="src">${esc(c.book)} ${pages(c)}</span>`
        + ` <span class="heading">${esc(c.heading)||''}</span>`
        + `<div class="snippet">${esc(c.snippet)}</div></div></div>`).join("")
    + `<div style="margin-top:10px"><span class="reviewed-btn ${r.reviewed?'on':''}">`
    + `${r.reviewed?'✓ reviewed':'mark reviewed'}</span></div>`;

  div.querySelectorAll(".mark").forEach(m => m.onclick = () => {
    const rank = Number(m.dataset.rank), rr = rec(q.id);
    const i = rr.relevant.indexOf(rank);
    if(i>=0){ rr.relevant.splice(i,1); m.classList.remove("on"); m.textContent="relevant?"; }
    else { rr.relevant.push(rank); m.classList.add("on"); m.textContent="✓ relevant"; }
    save();
  });
  const rb = div.querySelector(".reviewed-btn");
  rb.onclick = () => {
    const rr = rec(q.id); rr.reviewed = !rr.reviewed;
    rb.classList.toggle("on", rr.reviewed);
    rb.textContent = rr.reviewed ? "✓ reviewed" : "mark reviewed";
    div.classList.toggle("reviewed", rr.reviewed);
    save();
  };
  app.appendChild(div);
}
progress();

document.getElementById("export").onclick = () => {
  const out = {baseline: DATA.baseline, top: DATA.top, labels: store};
  const blob = new Blob([JSON.stringify(out, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = DATA.baseline + ".blind.json";
  a.click();
};
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
