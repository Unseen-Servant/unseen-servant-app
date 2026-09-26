"""``/api/models/status`` — model readiness for the desktop UI.

The Ollama probe is stubbed at ``httpx.get`` so no test needs a live
runtime; the three states the UI distinguishes (down, up without the
model, ready) are each covered.
"""
import httpx

from legend_lore import embedder


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _stub_get(monkeypatch, response=None, exc=None):
    def fake_get(url, timeout):
        if exc:
            raise exc
        return response
    monkeypatch.setattr(httpx, "get", fake_get)


def test_status_when_runtime_down(monkeypatch):
    _stub_get(monkeypatch, exc=httpx.ConnectError("refused"))
    status = embedder.embedder_status()
    assert status["runtime_up"] is False
    assert status["ready"] is False


def test_status_when_model_missing(monkeypatch):
    _stub_get(monkeypatch, _Resp(200, {"models": [{"name": "llama3:latest"}]}))
    status = embedder.embedder_status()
    assert status["runtime_up"] is True
    assert status["ready"] is False


def test_status_when_ready(monkeypatch):
    _stub_get(monkeypatch, _Resp(200, {"models": [{"name": "bge-m3:latest"}]}))
    status = embedder.embedder_status()
    assert status == {
        "role": "embed",
        "runtime": "ollama",
        "model": embedder.EMBEDDING_MODEL,
        "runtime_up": True,
        "ready": True,
    }


def test_endpoint_lists_embed_role(client, monkeypatch):
    _stub_get(monkeypatch, exc=httpx.ConnectError("refused"))
    response = client.get("/api/models/status")
    assert response.status_code == 200
    rows = response.json()["models"]
    assert [r["role"] for r in rows] == ["embed"]
    assert rows[0]["ready"] is False
