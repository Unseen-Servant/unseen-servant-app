# Unsloth as the AI backend — migration brainstorm

**Date:** 2026-10-22
**Status:** brainstorm, no code. Waits on a decision about which role Unsloth takes (§3).
**Driver:** move every AI model (embed, rerank, and the Servant's chat model to come) from Ollama and the first-use download to Unsloth.
**Builds on:** `2026-09-26-ml-runtime-consolidation.md` (one runtime for embed, rerank and chat) and GH #413 (bundle every model on a pinned `llama-server`).

---

## 0. TL;DR

- **Ollama, Unsloth Studio/Desktop and #413 all run llama.cpp.** The engine is not the choice. The choice is who manages it: the user's app (Ollama or Studio, each with its own flags, API, model policy and install), or our sidecar (a pinned `llama-server` with flags we set). Unsloth's GGUFs, and every hub GGUF, run unchanged on either.
- **Unsloth is three things, and only one of them is a runtime:**
  1. **Unsloth Studio**, a local web app with an OpenAI-compatible API server (`unsloth studio`, `unsloth run`). **Unsloth Desktop** is the same thing in a native Tauri shell. For GGUF it runs **`llama-server` underneath**, and MLX on Macs.
  2. **A model supplier**: the `unsloth/*` Hugging Face org, with "Dynamic" GGUF quants of current chat models.
  3. **A fine-tuning toolchain** (Apache-2.0 core). Since 2026 it can also train embedding and reranker models, `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3` among them.
- **Studio as the runtime that replaces Ollama is a step back.** It is a user-installed prerequisite again, and a heavier one than Ollama. Its catalogue lists reranker GGUFs, but **Studio refuses to serve them** (§1.1). Every request needs an API key that the user must create in Studio's UI and paste into our app. That undoes the goal of #413: no prerequisite and no network at first launch.
- **Recommendation: Unsloth as supplier and trainer, with `llama-server` as the runtime.** That is the same engine Studio drives, bundled and pinned by us as #413 already designs. Unsloth then provides:
  - the Servant's chat weights (Unsloth Dynamic GGUF);
  - the training pipeline to fine-tune bge-m3 and a multilingual reranker on TTRPG data.
  
  That is "Unsloth for everything AI-model related" with none of the runtime costs.
- **Chat is a slot, not a fixed model** (§4). Embed and rerank are part of the index, so they are pinned and identical on every machine. Chat depends on the hardware, so it comes from a local model sized to the machine's memory, from any OpenAI-compatible URL, or from nowhere (an external MCP client). The Servant is built for the smallest local tier.
- **What does not change:** embedding stays bge-m3 f16 on `llama-server`, because Unsloth publishes no bge-m3 GGUF. PDF layout stays on the bundled PyMuPDF Layout ONNX.

## 1. What Unsloth is today (checked 2026-10-22)

| | Fact | Source |
|---|---|---|
| Studio engine | "Powered by llama.cpp + Hugging Face"; GGUF models "are exposed as an authenticated API via `llama-server`"; MLX inference on Mac | unsloth.ai/docs/new/studio, /docs/basics/api |
| Studio API | OpenAI-compatible: `/v1/chat/completions`, `/v1/responses`, `/v1/messages`, `/v1/embeddings`, `/v1/models`, … **No `/v1/rerank`.** | /docs/basics/api |
| Auth | `Authorization: Bearer sk-unsloth-…` on every request. Keys are made in Settings → API, stored as a hash, shown once. | /docs/basics/api |
| Install | install script, desktop app, Homebrew, WinGet or Docker. Needs Python 3.11–3.13 in a `uv` venv under `~/.unsloth/studio`. Mac needs Homebrew, Git, cmake and openssl. **Windows lists "NVIDIA GPU with drivers installed"**, with a CPU-only path for GGUF chat only. Installs torch unless `--no-torch`. | /docs/get-started/…/unsloth-requirements, install.sh (521 KB) |
| Licence | core package Apache-2.0; the Studio UI and some optional parts AGPL-3.0 | /docs/new/studio |
| Maturity | Studio is labelled **beta** | /docs/new/studio |
| Embed / rerank training | `BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`, Qwen3-Embedding, EmbeddingGemma, … through SentenceTransformers; export runs on "transformers, LangChain, Ollama, vLLM, llama.cpp" | /docs/basics/embedding-finetuning |
| HF uploads relevant to us | `unsloth/bge-m3` (safetensors, **no GGUF**), `unsloth/Qwen3-Embedding-{0.6B,4B,8B}`, `unsloth/embeddinggemma-300m-GGUF`. No reranker under `author=unsloth`. | huggingface.co/api/models?author=unsloth |
| Desktop app | Tauri app wrapping Studio; Mac, Windows, Linux; "can run entirely offline", no telemetry. A hands-on review reports patchy docs, no download progress, a 4,096 default context, and console-only full updates. | unsloth.ai/docs/desktop, InfoWorld hands-on |
| Model hub | Lists Hugging Face models tagged for the Unsloth app (`huggingface.co/models?apps=unsloth`). That includes **~430 third-party reranker GGUFs**, e.g. `gpustack/bge-reranker-v2-m3-GGUF`, `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`, `gpustack/jina-reranker-v2-base-multilingual-GGUF`. | HF, 2026-10-22 |

### 1.1 Listed in the hub is not the same as served by Studio

Read in `unslothai/unsloth` at `3e35cbb49` (2026-10-23):

- **`/v1/rerank` and `/v1/reranking` are deliberately unserved.** `studio/backend/routes/llama_compat.py` puts them in `_UNSERVED_V1_PROBE_PATHS` and answers 404. `test_llama_compat_routes.py` fails CI if Studio ever starts serving them, so the change would have to be deliberate.
- **The `--rerank` / `--reranking` flags are denied in pass-through args.** `studio/backend/core/inference/llama_server_args.py` lists them as "server-mode flips" Studio sets itself, and also scrubs the `LLAMA_ARG_RERANKING` env var. Nothing in Studio sets the flag, so a user can't start `llama-server` in rerank mode through it.
- **A reranker GGUF can't go through `/v1/embeddings` either.** `test_embedding_gguf_launch.py::test_false_for_a_reranker` shows a RANK-pooling GGUF is not treated as an embedding model, because the RANK head's output can't be read as a vector.
- The agent model picker filters rerankers out on purpose (`isClassifierOrRerankerHubModel`).

So the hub is a **download source** for reranker GGUFs, and Studio itself has no rerank inference. The GGUFs it lists run fine on a plain `llama-server --reranking`, which is option C's runtime.

Note: a GitHub org named `unsloth-studio/unsloth-studio` ranks in search results with a "Download unsloth studio" README. The real project is `unslothai/unsloth`. Never fetch binaries from the other org.

## 2. Role by role

| Role | Today | With Studio as the runtime (A) | With Unsloth as supplier + trainer (C, recommended) |
|---|---|---|---|
| Embed | bge-m3 f16 on the user's Ollama | `/v1/embeddings` on a "loaded embedding GGUF". We would ship or point at a bge-m3 GGUF ourselves; Unsloth has none. Same `llama-server`, so the vectors should match. | #413 unchanged: BAAI bge-m3 converted at a pinned revision, bundled `llama-server --embeddings`. Later, an Unsloth fine-tune of bge-m3 (§5 step 5). |
| Rerank | MiniLM-L-6 int8 (fastembed, ONNX, 23 MB, English-only), downloaded on first use | **Downloadable from the hub, not servable** (§1.1). Keep fastembed beside it, so two runtimes again. | Keep fastembed, loaded from Resources (#413 step 2). Then a multilingual GGUF reranker on our `llama-server --reranking`: off-the-shelf `bge-reranker-v2-m3` or `Qwen3-Reranker-0.6B` first, an Unsloth fine-tune later (§5 step 5), if the evals pay for it. |
| Chat (Servant) | none | `/v1/chat/completions` with tool calling; Studio's own server-side tools must be off (`--disable-tools`) or they swallow ours | A slot, not a fixed model (§4): a machine-sized Unsloth Dynamic GGUF on a second bundled `llama-server`, any OpenAI-compatible URL, or none |
| PDF layout | PyMuPDF Layout ONNX, bundled | unchanged | unchanged |

## 3. The options

### A. Studio replaces Ollama as an external daemon

The smallest code change: `EMBED_BASE_URL` points at Studio's port, and `embedder.py` adds the bearer header. Costs:

- **Onboarding gets worse, not better.** Today it is "install Ollama, pull bge-m3, set one env var". With Studio it becomes:
  1. install Homebrew, cmake and a Python env (plus an NVIDIA GPU on Windows);
  2. start Studio;
  3. load an embedding GGUF;
  4. make an API key;
  5. paste the key into Unseen Servant.

  That breaks the first-run rule (a bare console, no setup pages).
- **No rerank endpoint**, so it is not the single provider either.
- **Beta** software we don't pin, with flags and endpoints that can change under every user.
- Model loading is Studio's policy, not ours (can embed and chat both stay warm on 16 GB?), and the 8k-context flags are not ours to set. That is the `OLLAMA_CONTEXT_LENGTH` foot-gun again.

### B. Bundle Studio inside the app

Not viable. It is a Python app with its own venv, an optional torch, and a cmake toolchain on Mac. That conflicts with the PyInstaller sidecar, the NSIS ~2 GB limit, and the rule "ONNX/llama.cpp, never a ~2.5 GB framework in the shipped app". Underneath, it is `llama-server`, and #413 bundles that alone.

### C. Unsloth as supplier and trainer, `llama-server` as runtime (recommended)

- **Runtime:** the #413 shape. A pinned `llama-server` with Metal, spawned by the sidecar, flags set by us, models in `Resources/models` with a `manifest.json`.
- **Unsloth's part** is everything around the weights:
  - Unsloth Dynamic GGUF quants for the Servant chat model;
  - the Unsloth training scripts (dev-side, spikes repo) for domain-tuned embed and rerank models, exported to GGUF;
  - Studio as an optional **dev tool**, for trying chat models and running fine-tunes on the Mac.
- **Users who already run Studio, LM Studio or Ollama** point the Servant at it with an OpenAI-compatible URL (§4).

## 4. Chat varies per machine

Embed and rerank run the same everywhere; chat can't. A 4B model on an 8 GB Mac and a mixture-of-experts model on a 64 GB Mac are different products. The two roles have different constraints, so they get different rules.

- **Embed and rerank are fixed.** The index stores bge-m3 vectors, so the model is part of the data (`EMBEDDING_MODEL` is its fingerprint). They are small (~1.2 GB) and run on every machine. Bundled and pinned, no user choice: #413 as written.
- **Chat is a slot.** Nothing stored depends on which model wrote an answer. The Servant settings offer one choice with three values:
  1. **Local:** a model from our manifest, sized to the machine, on the bundled runtime.
  2. **URL:** any OpenAI-compatible endpoint (Unsloth Desktop, LM Studio, Ollama, a GPU box on the network) plus an optional key.
  3. **None:** the Servant's tools are already MCP tools, so an external MCP client is the brain. The app works fully without local chat.

### 4.1 Local tier by memory

At setup, read total memory, subtract the resident embed and rerank models plus OS headroom, and offer the tier that fits as a download. It is the same fit check the Unsloth Desktop hub runs. Starting rows, to fix with measurements:

| Total memory | Default | Model class |
|---|---|---|
| 8 GB | None | a 1–4B model only on request |
| 16 GB | Local | a 4–8B dense model, 4-bit quant |
| 32 GB and up | Local | a mixture-of-experts model with few active parameters |

- The tier table is a manifest field (minimum memory per chat row), not code.
- On Windows we bundle the CPU and Vulkan backends only. CUDA users who want more take the URL choice.
- The chat model is never in the installer, so the NSIS limit and the download size do not apply to it.

### 4.2 Own process, loaded on demand

- Chat runs in a **second `llama-server` process**, apart from embed and rerank. If it runs out of memory or the machine starts to swap, search stays up.
- Spawned on the first Servant request, and stopped after an idle time and during bulk indexing.
- The sidecar owns both processes, like the embed server in #413.

### 4.3 Design for the floor

- The Servant is built and gated on the **smallest local tier**. A larger model gives better answers, never more features.
- A small tool set, short contexts, and retrieval doing the heavy lifting.
- Tool calls are constrained to each tool's JSON schema (a `llama-server` grammar), so small models can't send malformed calls. On the URL choice, use the endpoint's structured output where it has one, and otherwise validate the call and retry.
- Pass/fail is measured on the smallest local tier, through our own MCP tool registry: tool-call validity, refusals, latency.

## 5. Order of work (option C)

Each step ships on its own and is gated by the evals that exist today.

1. **#413 step 1 spike, unchanged** (spikes repo): pinned `llama-server` + bge-m3 f16, measured against the stored vectors and against Ollama on speed, the 8k tail and RSS. Add one check: is `unsloth/bge-m3` byte-identical to `BAAI/bge-m3` at our pinned revision? If yes, nothing changes. Convert from BAAI (upstream), either way.
2. **#413 step 2: the reranker from Resources.** Proves the manifest, the fetch script and the CI cache on 23 MB.
3. **#413 step 3: the `llama-server` embedder.** Ollama leaves the sidecar, the UI (~40 references in 8 Svelte files) and the site copy. Re-run both gate baselines.
4. **Servant chat slot (§4).** Starts when the Servant does, not before.
   - Pick one Unsloth Dynamic GGUF per tier, starting with the floor tier, which also gates the Servant.
   - Add the chat rows to the manifest with a minimum memory and "download on demand".
   - Add the second `llama-server` process and its load/unload policy.
   - Add the local / URL / none setting.
5. **Domain fine-tunes (research, spikes repo).**
   - Unsloth embedding training on (query, section) pairs: bge-m3 first, `bge-reranker-v2-m3` second.
   - Gate on the cued/single/uncued suites and `library_probe.py`, because a harness GO is not enough (see the eval-limits notes).
   - A new embed model bumps `EMBEDDING_MODEL`, so every user reindexes once. That happens at Metal speed after step 3.
   - A multilingual reranker also needs a refit of the score tiers.

## 6. Risks and open questions

- **Training data and copyright.** Fine-tuning on the dev library's commercial rulebooks, then shipping the weights, clashes with "respectful of authors' copyrights". Build the training pairs from openly licensed text only (SRDs under CC-BY or OGL, our own synthetic queries), and record the source in `manifest.json`.
- **Where the fine-tune runs.** Studio claims Mac training. Third-party reports from 2026 say Apple Silicon is inference-only. Test it on the M1 Pro before planning around it. The fallback is a rented NVIDIA GPU for a few hours per run.
- **Fine-tune gain is unproven.** Every retrieval change since July went through a GO/NO-GO, and several good-looking ones lost (rerank-off, BM25 default-on). Treat step 5 as a spike, not a migration step.
- **Unsloth GGUF chat models vs grammar-constrained tool calls.** `llama-server`'s native tool-call parser depends on the chat template. Unsloth often ships template fixes, which is a point in their favour. Check this per model.
- **Licences per model:** Apache/MIT for bge-m3 and bge-reranker-v2-m3; check each chat model (Gemma terms, Llama licence) before bundling or redistributing.

## 7. Not doing

- No Studio dependency in the shipped app, and no Unsloth Python package in the sidecar.
- No provider abstraction for embed or rerank. `embedder.py` stays the one file that knows the runtime. Only chat has a choice of source (§4).
- No fine-tune before the bundled runtime ships. A model change without Metal-speed reindexing costs users ~1.8 h on CPU.
