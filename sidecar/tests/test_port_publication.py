"""
Tests for the ephemeral-port discovery contract.

The sidecar binds with ``--port 0`` in production so two app instances can
coexist and so a held port doesn't kill startup. Tauri's readiness gate and
the MCP server discover the actual port via ``data_dir/sidecar.port``.
These tests pin the file format and lifecycle.
"""

import socket
import time

import pytest

from server import write_port_file, remove_port_file, PORT_FILENAME


def test_write_port_file_creates_atomic(tmp_path):
    write_port_file(tmp_path, 12345)
    target = tmp_path / PORT_FILENAME
    assert target.read_text() == "12345"
    # No tmp file should be left behind after the os.replace
    assert not (tmp_path / "sidecar.port.tmp").exists()


def test_write_port_file_overwrites(tmp_path):
    write_port_file(tmp_path, 11111)
    write_port_file(tmp_path, 22222)
    assert (tmp_path / PORT_FILENAME).read_text() == "22222"


def test_remove_port_file_is_idempotent(tmp_path):
    # No-op when the file doesn't exist
    remove_port_file(tmp_path)
    write_port_file(tmp_path, 8420)
    remove_port_file(tmp_path)
    assert not (tmp_path / PORT_FILENAME).exists()
    # Calling again is still a no-op (covers shutdown after a partial cleanup)
    remove_port_file(tmp_path)


def test_pre_bind_socket_yields_real_port_for_port_zero():
    """The pattern the sidecar's __main__ uses: bind 0, getsockname, publish.

    This guards the production assumption that ``socket.bind(('127.0.0.1', 0))``
    plus ``getsockname()[1]`` returns a real, reachable port — which we then
    publish so callers can connect.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        assert 1024 <= port <= 65535
        # The socket is bound but not listening; that's fine — what matters is
        # that the port is allocated and reproducible across the call.
        assert sock.getsockname()[1] == port
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# MCP-side discovery
# ---------------------------------------------------------------------------


def test_discover_sidecar_url_prefers_explicit_url(tmp_path):
    from mcp_server import discover_sidecar_url

    class Args:
        sidecar_url = "http://example.com:9999"
        data_dir = str(tmp_path)

    # data_dir is set but no port file exists; explicit URL still wins
    assert discover_sidecar_url(Args()) == "http://example.com:9999"


def test_discover_sidecar_url_reads_port_file(tmp_path):
    from mcp_server import discover_sidecar_url

    write_port_file(tmp_path, 54321)

    class Args:
        sidecar_url = None
        data_dir = str(tmp_path)

    assert discover_sidecar_url(Args()) == "http://127.0.0.1:54321"


def test_discover_sidecar_url_picks_up_late_port_file(tmp_path, monkeypatch):
    """If MCP launches before the sidecar finishes booting, it should retry."""
    from mcp_server import discover_sidecar_url
    import mcp_server

    # Shrink the timeout so the test runs quickly even on a slow machine
    monkeypatch.setattr(mcp_server, "SIDECAR_URL_DISCOVERY_TIMEOUT", 2.0)

    class Args:
        sidecar_url = None
        data_dir = str(tmp_path)

    # Drop the port file mid-poll from another thread
    import threading
    def write_after_delay():
        time.sleep(0.6)
        write_port_file(tmp_path, 33333)

    t = threading.Thread(target=write_after_delay)
    t.start()
    try:
        assert discover_sidecar_url(Args()) == "http://127.0.0.1:33333"
    finally:
        t.join()


def test_discover_sidecar_url_falls_back_on_timeout(tmp_path, monkeypatch):
    from mcp_server import discover_sidecar_url
    import mcp_server

    monkeypatch.setattr(mcp_server, "SIDECAR_URL_DISCOVERY_TIMEOUT", 0.5)

    class Args:
        sidecar_url = None
        data_dir = str(tmp_path)

    # No port file ever appears; we should fall back to the legacy default
    assert discover_sidecar_url(Args()) == "http://localhost:8420"
