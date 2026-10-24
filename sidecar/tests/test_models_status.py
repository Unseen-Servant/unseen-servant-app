"""``/api/models/status`` — model readiness for the desktop UI.

The process and the ``/health`` probe are stubbed, so no test needs a
live runtime; the three states the UI distinguishes (not running,
running while the model loads, ready) are each covered.
"""
import httpx

from legend_lore import embedder


class _Proc:
    def poll(self):
        return None


def _stub(monkeypatch, running, health=None):
    monkeypatch.setattr(embedder, "_proc", _Proc() if running else None)
    monkeypatch.setattr(embedder, "_base_url", "http://127.0.0.1:9")
    monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(health or 503))


def test_status_when_runtime_down(monkeypatch):
    _stub(monkeypatch, running=False)
    status = embedder.embedder_status()
    assert status["runtime_up"] is False
    assert status["ready"] is False


def test_status_while_the_model_loads(monkeypatch):
    _stub(monkeypatch, running=True, health=503)
    status = embedder.embedder_status()
    assert status["runtime_up"] is True
    assert status["ready"] is False


def test_status_when_ready(monkeypatch):
    _stub(monkeypatch, running=True, health=200)
    assert embedder.embedder_status() == {
        "role": "embed",
        "runtime": "llama-server",
        "model": embedder.EMBEDDING_MODEL,
        "runtime_up": True,
        "ready": True,
    }


def test_endpoint_lists_embed_role(client, monkeypatch):
    _stub(monkeypatch, running=False)
    response = client.get("/api/models/status")
    assert response.status_code == 200
    rows = response.json()["models"]
    assert [r["role"] for r in rows] == ["embed"]
    assert rows[0]["ready"] is False
