"""Self-contained HTML inspector for an eval baseline.

Reads ``<stem>.json`` (committed metrics) + ``<stem>.results.json``
(gitignored retrieved chunks) and writes a single standalone
``<stem>.html`` — open it in any browser, no server, no external assets.
Regenerate/restyle anytime without re-running the eval::

    uv run --project sidecar python -m evals.retrieval.report \
        evals/baselines/2026-08-15-v2-phase0 [--open]

run_eval calls write_html() automatically at the end of a run.
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path


def _stem(path) -> Path:
    """Normalize any of <stem>, <stem>.json, <stem>.results.json to <stem>."""
    s = str(path)
    for suffix in (".results.json", ".json", ".html", ".md"):
        if s.endswith(suffix):
            return Path(s[: -len(suffix)])
    return Path(s)


def load(path) -> tuple[dict, dict]:
    stem = _stem(path)
    baseline = json.loads(Path(f"{stem}.json").read_text(encoding="utf-8"))
    rp = Path(f"{stem}.results.json")
    results = json.loads(rp.read_text(encoding="utf-8")).get("results", {}) if rp.exists() else {}
    return baseline, results


def render_html(baseline: dict, results: dict) -> str:
    data = {**baseline, "results": results}
    # </ would prematurely close the inline <script>; neutralize it.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    m = baseline.get("meta", {})
    title = f"eval · {m.get('engine','?')} · {m.get('name','?')} · {m.get('date','')}"
    return _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", payload)


def write_html(path) -> Path:
    baseline, results = load(path)
    out = Path(f"{_stem(path)}.html")
    out.write_text(render_html(baseline, results), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("baseline", help="path to a baseline (<stem> or <stem>.json)")
    ap.add_argument("--open", action="store_true", help="open the report in a browser")
    args = ap.parse_args()
    out = write_html(args.baseline)
    print(f"wrote {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --bg-app:#191919; --bg-container:#232323; --bg-hover:#323232;
  --text-primary:#c9d1d9; --text-secondary:#8b949e; --text-tertiary:#7d8590;
  --text-accent:rgb(182,159,129); --text-active:#9076be; --text-connected:#b08850;
  --text-danger:#e15342; --border:rgb(50,50,50);
  --font-body:Georgia,'Times New Roman',serif; --font-mono:ui-monospace,'SF Mono',Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0 auto;max-width:1120px;padding:26px;background:var(--bg-app);color:var(--text-primary);
  font-family:var(--font-body);font-size:15px;line-height:1.5}
h1{font-size:20px;margin:0 0 3px;color:var(--text-accent);font-weight:600;letter-spacing:.02em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-secondary);
  margin:26px 0 8px;font-weight:600}
.sub{color:var(--text-secondary);font-size:12.5px}
.mono{font-family:var(--font-mono)} .num{font-variant-numeric:tabular-nums}
.headline{display:flex;gap:22px;flex-wrap:wrap;margin:12px 0;font-variant-numeric:tabular-nums}
.headline b{color:var(--text-accent);font-weight:600}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12.5px}
th{color:var(--text-secondary);text-align:right;font-weight:400;padding:3px 9px;border-bottom:1px solid var(--border)}
th:first-child,td:first-child{text-align:left}
td{padding:3px 9px;border-bottom:1px solid rgba(50,50,50,.5)}
tr.all td{color:var(--text-accent);border-top:1px solid var(--border);font-weight:600}
.tables>div{margin-bottom:18px}  /* stacked full-width; side-by-side collided once tables grew wide */
.filters{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:10px 0 6px;font-size:13px}
.filters .lbl{color:var(--text-tertiary);margin-right:2px}
.chip{cursor:pointer;color:var(--text-secondary);padding:2px 9px;border-radius:3px;user-select:none;
  border:1px solid transparent}
.chip:hover{background:var(--bg-hover);color:var(--text-primary)}
.chip.on{color:var(--text-active);border-color:var(--text-active)}
.q{border-bottom:1px solid var(--border)}
.qhead{display:grid;grid-template-columns:14px 52px 132px 44px 1fr auto;gap:11px;align-items:baseline;
  padding:6px 4px;cursor:pointer}
.qhead:hover{background:var(--bg-hover)}
.caret{color:var(--text-tertiary);font-size:11px}
.qid{font-family:var(--font-mono);color:var(--text-secondary);font-size:12.5px}
.cat{color:var(--text-secondary);font-size:12px}
.badge{font-family:var(--font-mono);font-variant-numeric:tabular-nums;font-size:12.5px}
.hit{color:var(--text-connected)} .miss{color:var(--text-danger)}
.pay{color:var(--text-tertiary);font-size:11.5px;font-variant-numeric:tabular-nums}
.results{padding:2px 0 12px 25px;display:none}
.q.open .results{display:block}
.res{display:grid;grid-template-columns:30px 15px 128px 62px 46px 56px 1fr;gap:9px;align-items:baseline;
  padding:3px 0;font-size:12px;border-top:1px solid rgba(50,50,50,.4)}
.res.matched{background:rgba(182,159,129,.07)}
.res .rank{font-family:var(--font-mono);color:var(--text-tertiary);text-align:right}
.res .ok{color:var(--text-accent)} .res .no{color:var(--text-tertiary)}
.res .book{color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res .n{font-family:var(--font-mono);font-variant-numeric:tabular-nums;color:var(--text-secondary);text-align:right}
.res .tier{color:var(--text-tertiary);font-size:11px}
.res .head{color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res .snip{color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;grid-column:3 / -1;
  font-style:italic;opacity:.85;padding-top:1px}
.empty{color:var(--text-tertiary);font-style:italic;padding:4px 0}
</style></head>
<body><div id="app"></div>
<script>
const DATA = __DATA__;
const R = DATA.results || {}, M = DATA.meta || {};
const METRICS = ["mrr@5","ndcg@10","recall@3","recall@5","recall@10","payload_chars","dup_sections@10","top3_fit@8k"];
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const fmt = (m,v) => m==="payload_chars" ? Math.round(v).toLocaleString() : Number(v).toFixed(3);

function aggTable(kind, summary){
  const cats = Object.keys(summary).filter(c=>c!=="all").sort().concat("all");
  let h = `<div><h2>by ${kind}</h2><table><thead><tr><th>${kind}</th><th>n</th>`
    + METRICS.map(m=>`<th>${m}</th>`).join("") + `</tr></thead><tbody>`;
  for(const c of cats){ const r=summary[c];
    h += `<tr class="${c==='all'?'all':''}"><td>${esc(c)}</td><td class="num">${r.queries}</td>`
      + METRICS.map(m=>`<td class="num">${fmt(m,r[m])}</td>`).join("") + `</tr>`;
  }
  return h + `</tbody></table></div>`;
}

function resultRow(r){
  const mk = r.matched ? `<span class="ok">✓</span>` : `<span class="no">·</span>`;
  const pages = r.page_start==null ? "" : (r.page_end && r.page_end!==r.page_start
    ? `p.${r.page_start}-${r.page_end}` : `p.${r.page_start}`);
  return `<div class="res ${r.matched?'matched':''}">`
    + `<span class="rank">#${r.rank}</span>${mk}`
    + `<span class="book" title="${esc(r.book)}">${esc(r.book)}</span>`
    + `<span class="n">${pages}</span><span class="n">${Number(r.relevance).toFixed(3)}</span>`
    + `<span class="tier">${esc(r.tier)}${r.reranked?'*':''}</span>`
    + `<span class="head" title="${esc(r.section_heading)}">${esc(r.section_heading)||'—'}</span>`
    + `<span class="snip">${esc(r.snippet)}</span></div>`;
}

function queryEl(q){
  const rank = q.hit_rank;
  const badge = rank ? `<span class="badge hit">#${rank}</span>` : `<span class="badge miss">MISS</span>`;
  const rows = (R[q.id]||[]);
  const body = rows.length ? rows.map(resultRow).join("")
    : `<div class="empty">no retrieved-results capture for this baseline — re-run run_eval to populate it.</div>`;
  const div = document.createElement("div");
  div.className = "q"; div.dataset.style = q.style; div.dataset.cat = q.category;
  div.dataset.scope = q.scope || "cued"; div.dataset.miss = rank ? "0" : "1";
  div.innerHTML =
    `<div class="qhead"><span class="caret">▸</span>`
    + `<span class="qid">${esc(q.id)}</span><span class="cat">${esc(q.scope||"")}·${esc(q.category)}</span>`
    + `${badge}<span class="qtext">${esc(q.query||q.pair)}</span>`
    + `<span class="pay">${Math.round(q.metrics.payload_chars).toLocaleString()}c</span></div>`
    + `<div class="results">${body}</div>`;
  div.querySelector(".qhead").addEventListener("click", ()=>{
    div.classList.toggle("open");
    div.querySelector(".caret").textContent = div.classList.contains("open") ? "▾" : "▸";
  });
  return div;
}

const state = {style:"all", scope:"all", cats:new Set(), missesOnly:false};
function applyFilters(){
  for(const div of document.querySelectorAll(".q")){
    const ok = (state.style==="all" || div.dataset.style===state.style)
      && (state.scope==="all" || div.dataset.scope===state.scope)
      && (state.cats.size===0 || state.cats.has(div.dataset.cat))
      && (!state.missesOnly || div.dataset.miss==="1");
    div.style.display = ok ? "" : "none";
  }
}

function render(){
  const app = document.getElementById("app");
  const agg = DATA.by_category.all, lat = DATA.latency||{};
  const opts = M.opts||{};
  const head = `<h1>${esc(M.engine)} · ${esc(M.name)} · ${esc(M.date)}</h1>`
    + `<div class="sub mono">rerank=${opts.rerank} hybrid=${opts.hybrid} spell=${opts.spell_correction}`
    + ` · ${M.n_queries} queries (${M.n_pairs} pairs) · n_results=${M.n_results} · ${esc((M.docs||[]).join(", "))}</div>`
    + `<div class="headline"><span>MRR@5 <b>${agg["mrr@5"].toFixed(3)}</b></span>`
    + `<span>nDCG@10 <b>${agg["ndcg@10"].toFixed(3)}</b></span>`
    + `<span>recall@3 <b>${agg["recall@3"].toFixed(3)}</b></span>`
    + `<span>recall@10 <b>${agg["recall@10"].toFixed(3)}</b></span>`
    + `<span>payload <b>${Math.round(agg["payload_chars"]).toLocaleString()}</b>c</span>`
    + `<span>p95 <b>${Math.round(lat.p95_ms||0)}</b>ms</span></div>`;
  const tables = `<div class="tables">${DATA.by_scope?aggTable("scope",DATA.by_scope):""}`
    + `${aggTable("category",DATA.by_category)}${aggTable("style",DATA.by_style)}</div>`;

  const cats = [...new Set(DATA.per_query.map(q=>q.category))].sort();
  const styleChip = s => `<span class="chip ${state.style===s?'on':''}" data-style="${s}">${s}</span>`;
  const scopeChip = s => `<span class="chip ${state.scope===s?'on':''}" data-scope="${s}">${s}</span>`;
  const filters = `<div class="filters"><span class="lbl">scope</span>`
    + ["all","single","cued","uncued"].map(scopeChip).join("")
    + `<span class="lbl" style="margin-left:12px">style</span>`
    + ["all","keyword","nl"].map(styleChip).join("")
    + `<span class="lbl" style="margin-left:12px">category</span>`
    + cats.map(c=>`<span class="chip" data-cat="${c}">${c}</span>`).join("")
    + `<span class="chip" id="misses" style="margin-left:12px">misses only</span></div>`;

  app.innerHTML = head + tables + `<h2>queries</h2>` + filters + `<div id="qlist"></div>`;
  const list = document.getElementById("qlist");
  DATA.per_query.slice().sort((a,b)=>a.id.localeCompare(b.id)).forEach(q=>list.appendChild(queryEl(q)));

  app.querySelectorAll(".chip[data-style]").forEach(c=>c.onclick=()=>{
    state.style=c.dataset.style;
    app.querySelectorAll(".chip[data-style]").forEach(x=>x.classList.toggle("on",x.dataset.style===state.style));
    applyFilters();
  });
  app.querySelectorAll(".chip[data-scope]").forEach(c=>c.onclick=()=>{
    state.scope=c.dataset.scope;
    app.querySelectorAll(".chip[data-scope]").forEach(x=>x.classList.toggle("on",x.dataset.scope===state.scope));
    applyFilters();
  });
  app.querySelectorAll(".chip[data-cat]").forEach(c=>c.onclick=()=>{
    c.classList.toggle("on"); c.classList.contains("on")?state.cats.add(c.dataset.cat):state.cats.delete(c.dataset.cat);
    applyFilters();
  });
  document.getElementById("misses").onclick=e=>{
    state.missesOnly=!state.missesOnly; e.target.classList.toggle("on",state.missesOnly); applyFilters();
  };
}
render();
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
