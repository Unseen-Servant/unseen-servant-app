# ML runtime consolidation — one provider for embed, rerank and chat

**Date:** 2026-09-26
**Status:** analysis + prep landed; the Phase 5 runtime *target* is reopened (was in-process ONNX, see `2026-09-02-v2-retrieval-improvement-roadmap.md` §8). Decision waits on the parity/speed numbers in §5.
**Driver:** the Servant (workstation step 5) needs a local chat model with tool calling. That is a third model role beside embed and rerank, and the roadmap goal is one runtime for all of them with no user-installed prerequisite.
**Branch:** `claude/ollama-sidecar-runtime-tradeoffs-mxltod` (422a771..ff84dc8), sidecar-only prep that is correct under any runtime choice.

---

## 0. TL;DR

- **Ollama cannot be the single provider.** It has no rerank endpoint (community uploads of `bge-reranker-v2-m3` answer only `/api/embed`, which returns a vector, not a query–document score), and it stays a user-installed daemon with the `OLLAMA_CONTEXT_LENGTH` foot-gun.
- **In-process ONNX (the Phase 5 plan) covers embed + rerank but has no chat story**, and on Apple Silicon it runs bge-m3 on the CPU: Ollama uses Metal, so bulk indexing gets several times slower. It is still the smallest change if the Servant ends up on a different runtime anyway.
- **llama.cpp (`llama-server`, bundled as a second Tauri sidecar binary) is the only candidate that serves all three roles**: `/v1/embeddings`, `/v1/rerank` (`--reranking`, GGUF cross-encoders), `/v1/chat/completions` with tool calling and JSON-schema/GBNF constrained output; Metal on macOS, same GGUF bge-m3 weights Ollama runs, OpenAI dialect throughout. Cost: we become the packager (per-platform builds, signing, model downloads) and the memory budget on a 16 GB Mac needs an explicit load/unload policy.
- **Prep landed (this branch):** the sidecar now has one file that knows the runtime — `sidecar/legend_lore/embedder.py` — and the desktop reads model readiness by *role* from the sidecar, not by probing Ollama from Rust. A runtime swap is that file plus a boot-time collection recreate (§3, finding 2).
- **Next:** embedder-parity mode in the eval (Jerome, on the Mac, live Ollama), then a one-day benchmark of llama-server vs Ollama vs ONNX on the eval set — speed and MRR. Decide the Phase 5 runtime target on those numbers.

---

## 1. The three options

| | Ollama (today) | in-process ONNX (Phase 5 plan) | llama.cpp sidecar binary |
|---|---|---|---|
| user installs anything | yes: app + `bge-m3` + context env var | no | no |
| embed | ✓ GPU (Metal) | ✓ CPU only in a PyInstaller bundle (CoreML EP is partial and fiddly) | ✓ GPU (Metal) |
| rerank | ✗ no endpoint | ✓ already shipped (fastembed, int8 L-6) | ✓ `/v1/rerank`, GGUF `bge-reranker-v2-m3` (bigger, multilingual, different score scale → tiers refit) |
| chat + tool calling | ✓ | ✗ | ✓ OpenAI dialect, native tool-call parsing, grammar-constrained JSON |
| vectors vs today's index | — | parity measured in `embed_parity_spike` (spikes repo) | same GGUF weights → likely near-identical; **verify** (§5) |
| model download | user pulls | fp32 2.2 GB or int8 ~570 MB, first launch | bge-m3 GGUF ~1.1 GB f16 / ~600 MB q8, first launch |
| packaging | none | none (Python deps) | per-platform `llama-server` build, codesign/notarize on the 10× macOS runner; pin a build, flags rename between releases |
| process model | external daemon we don't control | none | child process we spawn/health-check like the Python sidecar (`lib.rs` already does this) |
| Ollama-only code deleted | — | probe, keep-warm, runner-reset retry, `OLLAMA_*` env | probe and keep-warm; the retry stays (any HTTP embedder drops connections under load) |

**Memory budget (llama.cpp, 16 GB Apple Silicon):** bge-m3 q8 ~0.6 GB, bge-reranker-v2-m3 q8 ~0.6 GB, 8B chat q4_K_M ~5 GB + KV cache. Fits only if the chat model is unloaded during bulk indexing — an argument for llama-server's multi-model router mode (verify stability in the pinned build) or three single-model processes with an explicit policy: index → chat cold; play → embed + chat warm, reranker on demand.

**bge-m3 on llama.cpp:** not a causal model, so the whole input must fit one physical batch — `--ubatch-size ≥ 8192` or long sections fail instead of truncating.

## 2. Target architecture if llama.cpp is chosen

```text
Tauri (Rust)
  ├─ spawns + health-checks: Python sidecar (:8420)
  └─ spawns + health-checks: llama-server (:8421)  ← bundled, pinned build
                                  │
Python sidecar ───── HTTP ────────┘
  ├─ legend_lore/   embed (/v1/embeddings), rerank (/v1/rerank), Chroma/sqlite-vec, PDF
  ├─ (servant)      agent loop, tool dispatch, /v1/chat/completions
  ├─ (models)       GGUF download, checksum, cache dir, readiness per role
  └─ mcp_server.py  same tool registry, exposed to Claude Desktop
```

Rust owns processes; Python owns ML behind HTTP, so tests point at a stub or a CPU-only llama-server in CI. The Servant's tools are the same functions the MCP server exposes — MCP becomes an adapter over one registry, not a second implementation. Constrained output (JSON schema / GBNF) for tool calls and typed agent output; local 8B-class models drift far less under a grammar. The Claude/MCP path stays as the big-brain option.

## 3. Findings while preparing the sidecar

1. **Re-index detection already existed.** Each manifest entry stores `pipeline_version` (`structure_aware-v3/bge-m3`) and preflight flags files as `outdated` when it differs. The fingerprint just lived in `chunker.py`, far from the code that builds the embedder. Now `EMBEDDING_MODEL` lives in `embedder.py` beside the builder; its value stays `bge-m3` so no user is flagged today, and a runtime whose vectors are not comparable changes it there.
2. **Chroma persists the embedding function's `name()` ("ollama") in the collection config and refuses to open the collection under a differently named function** (`validate_embedding_function_conflict_on_get`). So the runtime swap cannot be "change the embed URL": it needs a boot-time drop-and-recreate of the collection when the persisted name differs. Noted in `embedder.py`. This is moot if the store swap (Chroma → sqlite-vec) lands first or together.
3. **Ollama's OpenAI-dialect endpoints are the same code path as `/api/embed`** (chromadb's `OllamaEmbeddingFunction` uses the `ollama` client's `embed`, normalised vectors). Moving to `/v1/embeddings` should be vector-identical; §5 confirms.
4. **`ollama` (pip) is a dependency only because chromadb's `OllamaEmbeddingFunction` imports it.** A custom `/v1/embeddings` function drops it — but see finding 2 for when.
5. **The Ollama surface in the sidecar is now one file.** `grep -i ollama` outside `embedder.py` hits only comments, `OLLAMA_*` env-var names and the UI copy (`OllamaStatus.svelte`, the Getting Started pill, guides). The UI props are still named `ollamaRunning`/`ollamaModelReady`; the status row already carries `runtime`, so renaming is a cosmetic commit for the day the runtime name changes.

## 4. Prep landed on the branch

| commit | change | why it is runtime-agnostic |
|---|---|---|
| 422a771 | `legend_lore/embedder.py`: `EMBEDDING_MODEL` + `build_embedding_function()`; three call sites, eval and tests use the neutral name | one seam to swap; fingerprint unchanged |
| 8889c15 | sidecar `GET /api/models/status` → `{models: [{role, runtime, model, runtime_up, ready}]}`; Tauri `check_models_status` is a proxy like `check_mcp_status`; `check_ollama_health`, `OLLAMA_URL` and tag parsing leave Rust; `+page.svelte` reads the `embed` row | the UI renders roles; reranker/chat rows slot in without a frontend change; also does the "lift Ollama status to Rust" half of workstation step 3 for free, since Rust no longer knows the runtime |
| f3ef717 | truncation probe + keep-warm ticker move into `embedder.py`; `server.py` calls one `start_background_tasks()` | a bundled runtime's `embedder.py` starts nothing; server.py stops knowing which threads a runtime needs |
| ff84dc8 | readiness probe uses `/v1/models` (answered identically by Ollama, llama-server, LM Studio, vLLM); `EMBED_BASE_URL` constant | a swap changes one constant, not the probe |

Verified: pytest 764 passed; `cargo fmt` + `clippy -D warnings` clean; `svelte-check` 0 errors. No behaviour change for users.

## 5. Next steps

1. **Embedder-parity mode in `evals/run_eval.py`** (Jerome, Mac, live Ollama): embed N fixed chunks, save the vectors as the baseline, then a compare mode that reports cosine similarity against a candidate embedder (`EMBED_BASE_URL` pointed at llama-server, or the ONNX path). Answers "do existing indexes survive?" in minutes.
2. **One-day benchmark on the eval set, Apple Silicon:** index time and warm search p50 for Ollama vs llama-server (Metal) vs ONNX fp32/int8 (CPU); MRR@5 on `2026-09-24-v2-rerank` for each; cosine drift from step 1. Router-mode stability and memory on the pinned llama.cpp build. Tool-calling quality of the candidate chat model through llama-server's native parser (varies by template).
3. **Decide the Phase 5 runtime target** on those numbers and add the row to the v2 roadmap §8. Rule of thumb from §1: if the Servant will run on llama.cpp anyway, ONNX for embeddings is a second runtime we would later remove; if llama.cpp indexing is not within ~1.5× of Ollama or router mode is unstable, ONNX + a separate chat runtime is the fallback.
4. **Then the migration itself** (whichever target): boot-time collection recreate on persisted-EF-name mismatch (or land the store swap first), delete the Ollama-only helpers, drop the `ollama` pip dep, rename the UI props and copy, model download manager with checksums, per-platform binary in `build-sidecar.sh` and `release.yml` (estimate the 10× macOS minutes first).

## 6. Not doing now

- No backend flag or provider abstraction with one implementation. Co-location in `embedder.py` is the abstraction until a second backend exists.
- No model download manager, no bundled binary, no `ollama` dep removal — all worth nothing until the target is decided, and finding 2 blocks the last one anyway.
- No rerank move to llama.cpp before the evals show multilingual reranking is worth the slower, larger model.
