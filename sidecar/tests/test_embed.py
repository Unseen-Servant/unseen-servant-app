"""embed() — the sidecar's own call to the embedding runtime.

No Ollama needed: ``httpx.post`` is replaced by a recorder that answers
the way Ollama's ``/api/embed`` does.
"""

import httpx
import pytest

from legend_lore import embedder


@pytest.fixture
def ollama(monkeypatch):
    """Record requests; answer with ``state["response"]``."""
    state = {"requests": [], "response": None}

    def post(url, json, timeout):
        state["requests"].append({"url": url, "json": json, "timeout": timeout})
        return state["response"] or httpx.Response(
            200, json={"embeddings": [[float(i), 0.5] for i in range(len(json["input"]))]}
        )

    monkeypatch.setattr(httpx, "post", post)
    return state


def test_embed_sends_the_ollama_client_request(ollama):
    """Same body the ollama client sends, so vectors match existing indexes."""
    vectors = embedder.embed(["fire drake", "ice troll"])

    (req,) = ollama["requests"]
    assert req["url"] == "http://localhost:11434/api/embed"
    assert req["json"] == {"model": "bge-m3", "input": ["fire drake", "ice troll"]}
    assert vectors == [[0.0, 0.5], [1.0, 0.5]]


def test_embed_timeout_defaults_to_120s(ollama, monkeypatch):
    """Long enough for a slow batch, short enough that a wedged Ollama
    can't hold the sync lock forever."""
    monkeypatch.delenv("OLLAMA_EMBED_TIMEOUT_SECONDS", raising=False)
    embedder.embed(["x"])
    assert ollama["requests"][0]["timeout"] == 120


def test_embed_timeout_env_override(ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "30")
    embedder.embed(["x"])
    assert ollama["requests"][0]["timeout"] == 30


def test_embed_surfaces_ollamas_error_message(ollama):
    ollama["response"] = httpx.Response(
        404, json={"error": 'model "bge-m3" not found, try pulling it first'}
    )
    with pytest.raises(RuntimeError, match=r"404.*not found, try pulling"):
        embedder.embed(["x"])


def test_embed_error_without_json_body(ollama):
    ollama["response"] = httpx.Response(500, text="upstream exploded")
    with pytest.raises(RuntimeError, match="500.*upstream exploded"):
        embedder.embed(["x"])


def test_embed_explains_an_embedder_that_is_not_running(monkeypatch):
    def refused(url, json, timeout):
        raise httpx.ConnectError("[Errno 61] Connection refused")

    monkeypatch.setattr(httpx, "post", refused)
    with pytest.raises(RuntimeError) as err:
        embedder.embed(["fire drake"])
    assert str(err.value) == (
        "Embedder not running — nothing answered at http://localhost:11434. "
        "Start it and try again."
    )


def test_embed_explains_an_embedder_that_does_not_answer(monkeypatch):
    def slow(url, json, timeout):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "post", slow)
    with pytest.raises(RuntimeError) as err:
        embedder.embed(["fire drake"])
    assert str(err.value) == (
        "Embedder not answering — no reply after 120s. "
        "It may be busy or stuck; try again in a moment."
    )


def test_background_helpers_default_to_embed(ollama, monkeypatch):
    """The truncation probe and keep-warm ticker use embed() when no
    embedder is injected (they used to build Chroma's function)."""
    import threading

    embedder.probe_embed_truncation()
    assert ollama["requests"], "probe did not call embed()"

    ollama["requests"].clear()
    stop = threading.Event()
    real_post = httpx.post

    def post_then_stop(*args, **kwargs):
        stop.set()
        return real_post(*args, **kwargs)

    monkeypatch.setattr(httpx, "post", post_then_stop)
    embedder.keep_embedder_warm(interval=0.01, stop=stop)
    assert ollama["requests"][0]["json"]["input"] == ["ping"]
