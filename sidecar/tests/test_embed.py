"""embed() — the sidecar's own call to the embedding runtime.

No llama-server needed: ``_ready`` answers a fixed URL and ``httpx.post``
is replaced by a recorder that answers the way llama-server's
``/v1/embeddings``, ``/tokenize`` and ``/detokenize`` do. The last test
runs a real server when one has been built and the model fetched.
"""

from pathlib import Path

import httpx
import pytest

from legend_lore import embedder

BASE = "http://127.0.0.1:9"


@pytest.fixture
def server(monkeypatch):
    """Record requests; answer embeds with ``state["response"]``."""
    state = {"requests": [], "response": None}

    def post(url, json, timeout):
        state["requests"].append({"url": url, "json": json, "timeout": timeout})
        if url.endswith("/tokenize"):
            words = json["content"].split()
            return httpx.Response(200, json={"tokens": [0] * json.get("add_special", False) * 2 + list(range(len(words)))})
        if url.endswith("/detokenize"):
            return httpx.Response(200, json={"content": f"<{len(json['tokens'])} tokens>"})
        if state["response"] is not None:
            return state["response"]
        # Out of order, as the API allows: embed() sorts by index.
        data = [{"index": i, "embedding": [float(i), 0.5]} for i in range(len(json["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data))})

    monkeypatch.setattr(embedder, "_ready", lambda: BASE)
    monkeypatch.setattr(httpx, "post", post)
    return state


def test_embed_sends_one_openai_request(server):
    vectors = embedder.embed(["fire drake", "ice troll"])

    (req,) = server["requests"]
    assert req["url"] == f"{BASE}/v1/embeddings"
    assert req["json"] == {"model": "bge-m3", "input": ["fire drake", "ice troll"]}
    assert vectors == [[0.0, 0.5], [1.0, 0.5]]


def test_embed_timeout_defaults_to_120s(server, monkeypatch):
    """Long enough for a slow batch, short enough that a wedged server
    can't hold the sync lock forever."""
    monkeypatch.delenv("EMBED_TIMEOUT_SECONDS", raising=False)
    embedder.embed(["x"])
    assert server["requests"][0]["timeout"] == 120


def test_embed_timeout_env_override(server, monkeypatch):
    monkeypatch.setenv("EMBED_TIMEOUT_SECONDS", "30")
    embedder.embed(["x"])
    assert server["requests"][0]["timeout"] == 30


def test_embed_cuts_an_input_over_the_batch_and_retries(server, monkeypatch):
    """llama-server rejects an input longer than its batch where Ollama cut
    it; embed() cuts that input to fit and sends the batch again."""
    monkeypatch.setattr(embedder, "MAX_INPUT_TOKENS", 5)
    calls = {"n": 0}
    real = httpx.post

    def reject_once(url, json, timeout):
        if url.endswith("/v1/embeddings") and calls["n"] == 0:
            calls["n"] += 1
            return httpx.Response(500, json={"error": {
                "code": 500, "message": "input (9 tokens) is too large to process. "
                "increase the physical batch size (current batch size: 5)"}})
        return real(url, json=json, timeout=timeout)

    monkeypatch.setattr(httpx, "post", reject_once)
    embedder.embed(["short one", "one two three four five six seven"])
    final = server["requests"][-1]["json"]["input"]
    # 5 tokens with 2 specials leaves 3 for the text.
    assert final == ["short one", "<3 tokens>"]


def test_embed_surfaces_the_servers_error_message(server):
    server["response"] = httpx.Response(400, json={"error": {"code": 400, "message": "bad input"}})
    with pytest.raises(RuntimeError, match=r"400.*bad input"):
        embedder.embed(["x"])


def test_embed_error_without_json_body(server):
    server["response"] = httpx.Response(500, text="upstream exploded")
    with pytest.raises(RuntimeError, match="500.*upstream exploded"):
        embedder.embed(["x"])


def test_embed_explains_an_embedder_that_is_not_running(server, monkeypatch):
    def refused(url, json, timeout):
        raise httpx.ConnectError("[Errno 61] Connection refused")

    monkeypatch.setattr(httpx, "post", refused)
    with pytest.raises(RuntimeError) as err:
        embedder.embed(["fire drake"])
    assert str(err.value) == (
        f"Embedder not running — nothing answered at {BASE}. Try again in a moment."
    )


def test_embed_explains_an_embedder_that_does_not_answer(server, monkeypatch):
    def slow(url, json, timeout):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "post", slow)
    with pytest.raises(RuntimeError) as err:
        embedder.embed(["fire drake"])
    assert str(err.value) == (
        "Embedder not answering — no reply after 120s. "
        "It may be busy or stuck; try again in a moment."
    )


def test_embed_explains_a_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(embedder, "_binary", lambda: None)
    monkeypatch.setattr(embedder, "_proc", None)
    with pytest.raises(RuntimeError) as err:
        embedder.embed(["x"])
    assert str(err.value) == (
        "Embedder not available — llama-server is missing from the app. "
        "Reinstall Unseen Servant."
    )


def test_model_comes_from_the_bundled_models(monkeypatch, tmp_path):
    gguf = tmp_path / "embed" / "m" / "bge-m3-FP16.gguf"
    gguf.parent.mkdir(parents=True)
    gguf.write_text("x")
    (tmp_path / "manifest.json").write_text(
        '{"models": [{"role": "embed", "name": "bge-m3", "dir": "embed/m",'
        ' "files": [{"path": "bge-m3-FP16.gguf"}]}]}'
    )
    monkeypatch.setenv("BUNDLED_MODELS_DIR", str(tmp_path))
    assert embedder._model() == gguf


REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    embedder._binary() is None or not (REPO / "models" / "embed").is_dir(),
    reason="no llama-server built (scripts/build-llama-server.sh) or models/ not fetched",
)
def test_real_server_embeds_and_fits_a_long_input(monkeypatch):
    """The real binary and GGUF: 1024-d unit vectors, related texts closer
    than unrelated ones, and a ~9k-token input embedded after the cut."""
    monkeypatch.delenv("BUNDLED_MODELS_DIR", raising=False)
    try:
        a, b, c, long = embedder.embed([
            "The fire drake breathes flame.",
            "A dragon exhales fire at its foes.",
            "Coins come in copper, silver and gold.",
            "word " * 9000,
        ])
    finally:
        embedder.stop_embedder()
    dot = lambda x, y: sum(p * q for p, q in zip(x, y))
    assert len(a) == embedder.EMBEDDING_DIM
    assert abs(dot(a, a) - 1) < 1e-3 and abs(dot(long, long) - 1) < 1e-3
    assert dot(a, b) > dot(a, c)
