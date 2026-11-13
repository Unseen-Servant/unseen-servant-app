"""
Tests for the parent-death watchdog.

The app passes its PID with ``--parent-pid`` and the sidecar exits once
that process is gone, so a crashed or killed app doesn't leave an orphan
holding the library store open. POSIX probes the PID; Windows waits on a
process handle, and its tests stand in for the three kernel32 calls.
"""

import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from server import (
    _process_alive,
    _stop_self,
    _wait_for_exit_windows,
    _watch_parent,
    _watch_parent_windows,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="probes a PID with signal 0")


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()  # reaped, so the PID no longer names a process
    return proc.pid


@posix_only
def test_process_alive_tells_a_live_pid_from_a_dead_one():
    assert _process_alive(os.getpid())
    assert not _process_alive(_dead_pid())


@posix_only
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


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

ACCESS_DENIED = 5
NO_SUCH_PROCESS = 87
WAIT_FAILED = 0xFFFFFFFF


class FakeKernel32:
    """kernel32 as the watchdog uses it: ``opens`` is what OpenProcess
    answers, ``waits`` what WaitForSingleObject does."""

    def __init__(self, opens, waits=0):
        self.opens = opens
        self.waits = waits
        self.closed = []

    def open_process(self, pid):
        return self.opens

    def wait(self, handle):
        return self.waits

    def close(self, handle):
        self.closed.append(handle)


def test_the_windows_wait_ends_when_the_app_process_does():
    k32 = FakeKernel32(opens=(0x1F4, 0), waits=0)
    assert _wait_for_exit_windows(4242, kernel32=k32) is True
    assert k32.closed == [0x1F4]


def test_an_app_that_is_already_gone_counts_as_ended():
    k32 = FakeKernel32(opens=(None, NO_SUCH_PROCESS))
    assert _wait_for_exit_windows(4242, kernel32=k32) is True
    assert k32.closed == []


@pytest.mark.parametrize(
    "k32",
    [
        FakeKernel32(opens=(None, ACCESS_DENIED)),
        FakeKernel32(opens=(0x1F4, 0), waits=WAIT_FAILED),
    ],
    ids=["no handle", "wait failed"],
)
def test_a_process_that_cannot_be_watched_is_not_taken_for_dead(k32):
    assert _wait_for_exit_windows(4242, kernel32=k32) is False


def test_the_windows_watchdog_stops_the_sidecar_once_the_app_is_gone():
    stopped = []
    _watch_parent_windows(4242, wait=lambda pid: True, stop=lambda: stopped.append(True))
    assert stopped == [True]


def test_the_windows_watchdog_leaves_the_sidecar_running_when_it_cannot_watch():
    def broken(pid):
        raise OSError("no kernel32")

    stopped = []
    _watch_parent_windows(4242, wait=lambda pid: False, stop=lambda: stopped.append(True))
    _watch_parent_windows(4242, wait=broken, stop=lambda: stopped.append(True))
    assert stopped == []


def test_the_windows_stop_runs_the_sigterm_handler_in_the_main_thread():
    """Windows has no SIGTERM to send a process: ``os.kill`` ends it at
    once, with no clean-up. The stop raises the signal instead, from the
    watchdog's thread, and the handler ``__main__`` installed runs where
    it can unwind the server."""
    ran_in = []
    before = signal.signal(signal.SIGTERM, lambda *_: ran_in.append(threading.current_thread()))
    try:
        watchdog = threading.Thread(target=_stop_self, kwargs={"posix": False})
        watchdog.start()
        watchdog.join(timeout=2)
        deadline = time.monotonic() + 2
        while not ran_in and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        signal.signal(signal.SIGTERM, before)
    assert ran_in == [threading.main_thread()]
