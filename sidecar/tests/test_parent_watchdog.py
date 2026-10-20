"""
Tests for the parent-death watchdog.

The app passes its PID with ``--parent-pid`` and the sidecar exits once
that process is gone, so a crashed or killed app doesn't leave an orphan
holding the library store open.
"""

import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from server import _process_alive, _watch_parent

pytestmark = pytest.mark.skipif(os.name != "posix", reason="the watchdog is POSIX-only")


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()  # reaped, so the PID no longer names a process
    return proc.pid


def test_process_alive_tells_a_live_pid_from_a_dead_one():
    assert _process_alive(os.getpid())
    assert not _process_alive(_dead_pid())


def test_watchdog_follows_the_app_not_our_direct_parent(monkeypatch):
    """The bundled case: our parent is PyInstaller's bootloader, the app is
    another process. The watchdog holds while the app lives and stops the
    sidecar once it's gone."""
    real_kill = os.kill
    sent = []

    def kill(pid, sig):
        if sig == signal.SIGTERM:
            sent.append(pid)
        else:
            real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", kill)
    app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    watchdog = threading.Thread(target=_watch_parent, args=(app.pid, 0.01), daemon=True)
    watchdog.start()

    time.sleep(0.1)
    assert sent == []

    app.kill()
    app.wait()
    watchdog.join(timeout=2)
    assert sent == [os.getpid()]
