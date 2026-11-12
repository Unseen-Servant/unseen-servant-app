"""The launch token: who the sidecar answers.

The API listens on loopback, where any local process and any web page can
reach it. ``__main__`` makes a token per launch, publishes it beside the
port file, and builds the app with it; these tests pin what a request
without it gets, and that the app's own callers (Rust reads the file, the
MCP server too) are let through.
"""

import argparse
import asyncio
import os
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

import mcp_server
from server import (
    TOKEN_FILENAME,
    create_app,
    remove_token_file,
    write_port_file,
    write_token_file,
)

TOKEN = "s3cret-launch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def guarded(test_store, tmp_path):
    """The app as ``__main__`` builds it, reached on a loopback Host."""
    app = create_app(store=test_store, data_dir=tmp_path, token=TOKEN)
    return TestClient(app, base_url="http://127.0.0.1:8420")


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_a_request_with_the_token_is_answered(guarded):
    response = guarded.get("/health", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong"},
    {"Authorization": TOKEN},
    {"Authorization": f"Basic {TOKEN}"},
])
def test_a_request_without_the_token_is_refused(guarded, headers):
    response = guarded.get("/health", headers=headers)
    assert response.status_code == 401
    # A sentence in ``detail``: Rust and the MCP server show it as it is.
    assert response.json() == {"detail": "The sidecar takes requests from Unseen Servant only"}


def test_a_web_pages_bodyless_post_no_longer_lands(guarded, tmp_path):
    """What a page on any site could send with no preflight: it used to
    delete the index."""
    response = guarded.post("/api/delete-index", headers={"Origin": "https://evil.example"})
    assert response.status_code == 401

    response = guarded.post(
        "/api/command/images",
        params={"campaign": "Untitled", "name": "x.svg"},
        content=b"<svg/>",
        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
    )
    assert response.status_code == 401


def test_command_routes_are_behind_the_token_too(guarded, tmp_path):
    body = {"root": str(tmp_path)}
    assert guarded.put("/api/command/settings", json=body).status_code == 401
    assert guarded.put("/api/command/settings", json=body, headers=AUTH).status_code == 200


def test_a_host_that_is_not_loopback_is_refused_even_with_the_token(guarded):
    """DNS rebinding: the page's own name resolves to 127.0.0.1, so the
    request arrives here carrying that name."""
    response = guarded.get("/health", headers={**AUTH, "Host": "evil.example:8420"})
    assert response.status_code == 400

    response = guarded.get("/health", headers={**AUTH, "Host": "localhost:8420"})
    assert response.status_code == 200


def test_a_preflight_is_still_answered(guarded):
    """A preflight carries no Authorization header: CORS answers it before
    the guard, for the origins it allows."""
    response = guarded.options("/api/search", headers={
        "Origin": "tauri://localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "tauri://localhost"


def test_the_event_stream_is_behind_the_token(guarded):
    assert guarded.get("/api/command/events").status_code == 401


def test_without_a_token_the_app_is_open_for_in_process_tests(client):
    """``create_app`` with no token is what every other test drives."""
    assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# The token file
# ---------------------------------------------------------------------------


def test_write_token_file_publishes_the_token_atomically(tmp_path):
    write_token_file(tmp_path, TOKEN)
    assert (tmp_path / TOKEN_FILENAME).read_text() == TOKEN
    assert not (tmp_path / "sidecar.token.tmp").exists()

    write_token_file(tmp_path, "the-next-launch")
    assert (tmp_path / TOKEN_FILENAME).read_text() == "the-next-launch"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_the_token_file_is_the_users_alone(tmp_path):
    # A tmp file a crashed launch left behind, readable by everyone.
    leftover = tmp_path / "sidecar.token.tmp"
    leftover.write_text("old")
    leftover.chmod(0o644)

    write_token_file(tmp_path, TOKEN)

    mode = stat.S_IMODE((tmp_path / TOKEN_FILENAME).stat().st_mode)
    assert mode == 0o600


def test_remove_token_file_is_idempotent(tmp_path):
    remove_token_file(tmp_path)
    write_token_file(tmp_path, TOKEN)
    remove_token_file(tmp_path)
    assert not (tmp_path / TOKEN_FILENAME).exists()
    remove_token_file(tmp_path)


# ---------------------------------------------------------------------------
# The MCP server sends it
# ---------------------------------------------------------------------------


def _args(data_dir):
    return argparse.Namespace(sidecar_url=None, data_dir=str(data_dir) if data_dir else None)


def test_mcp_headers_carry_the_token_of_the_current_launch(tmp_path):
    assert mcp_server.sidecar_headers(_args(tmp_path)) == {"X-Source": "mcp"}

    write_token_file(tmp_path, TOKEN)
    assert mcp_server.sidecar_headers(_args(tmp_path)) == {"X-Source": "mcp", **AUTH}

    # The app was relaunched: the next request carries the new token.
    write_token_file(tmp_path, "the-next-launch")
    assert mcp_server.sidecar_headers(_args(tmp_path))["Authorization"] == "Bearer the-next-launch"


def test_mcp_headers_without_a_data_dir_have_no_token():
    assert mcp_server.sidecar_headers(_args(None)) == {"X-Source": "mcp"}


@pytest.fixture
def mcp_against(test_store, tmp_path, monkeypatch):
    """The MCP server's own client, wired to a guarded app in-process."""
    app = create_app(store=test_store, data_dir=tmp_path, token=TOKEN)
    write_port_file(tmp_path, 8420)
    seen = {}
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        seen.update(kwargs)
        return real_client(transport=httpx.ASGITransport(app=app), **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client_factory)
    return mcp_server.SidecarClient(_args(tmp_path)), seen


def test_the_mcp_client_is_let_in_with_the_token_file(mcp_against, tmp_path):
    client, seen = mcp_against
    write_token_file(tmp_path, TOKEN)

    assert asyncio.run(client.get("/health")) == {"status": "ok"}
    # And it never goes through the machine's proxy to get there.
    assert seen["trust_env"] is False


def test_the_mcp_client_reports_the_refusal_when_its_token_is_stale(mcp_against, tmp_path):
    client, _ = mcp_against
    write_token_file(tmp_path, "from-an-earlier-launch")

    assert asyncio.run(client.get("/health")) == "The sidecar takes requests from Unseen Servant only"
    assert asyncio.run(client.post("/api/search", {"query": "x"})) == (
        "The sidecar takes requests from Unseen Servant only"
    )
