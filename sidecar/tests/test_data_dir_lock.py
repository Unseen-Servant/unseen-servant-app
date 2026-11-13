"""One sidecar per data dir.

Two sidecars on one data dir write one library store, and the second takes
the first one's port and token files. The sidecar locks ``sidecar.lock``
for as long as it runs; these tests pin who gets the data dir, that a dead
holder never keeps it, and that a second sidecar leaves before it has
touched anything of the first.
"""

import errno
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from server import (
    DATA_DIR_IN_USE,
    LOCK_FILENAME,
    PORT_FILENAME,
    TOKEN_FILENAME,
    DataDirInUse,
    hold_data_dir,
)

SERVER = Path(__file__).resolve().parents[1] / "server.py"


def test_the_first_sidecar_gets_the_data_dir_and_the_second_is_refused(tmp_path):
    first = hold_data_dir(tmp_path)
    assert first is not None

    with pytest.raises(DataDirInUse) as refused:
        hold_data_dir(tmp_path, patience=0)

    assert str(refused.value) == DATA_DIR_IN_USE
    first.close()


def test_the_data_dir_is_free_again_once_its_sidecar_is_gone(tmp_path):
    hold_data_dir(tmp_path).close()
    again = hold_data_dir(tmp_path, patience=0)
    assert again is not None
    again.close()


def test_a_lock_held_for_an_instant_is_waited_out(tmp_path):
    """The app asks the same lock before it starts a sidecar, and holds it
    for the length of the question."""
    asking = hold_data_dir(tmp_path)
    threading.Timer(0.2, asking.close).start()

    got = hold_data_dir(tmp_path, patience=5)

    assert got is not None
    got.close()


@pytest.mark.skipif(os.name != "posix", reason="holds the lock with flock")
def test_a_killed_sidecar_does_not_keep_the_data_dir(tmp_path):
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, sys, time\n"
            "f = open(sys.argv[1], 'a')\n"
            "fcntl.flock(f, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "time.sleep(60)\n",
            str(tmp_path / LOCK_FILENAME),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(DataDirInUse):
            hold_data_dir(tmp_path, patience=0)

        holder.kill()
        holder.wait()

        got = hold_data_dir(tmp_path, patience=0)
        assert got is not None
        got.close()
    finally:
        holder.kill()
        holder.wait()


def test_a_file_system_without_locks_runs_the_sidecar_unlocked(tmp_path, capsys):
    def no_locks(handle):
        raise OSError(errno.ENOLCK, "No locks available")

    assert hold_data_dir(tmp_path, try_lock=no_locks) is None
    assert "no lock on the data dir" in capsys.readouterr().out


def test_a_lock_file_that_cannot_be_opened_runs_the_sidecar_unlocked(tmp_path):
    assert hold_data_dir(tmp_path / "missing") is None


def test_a_second_sidecar_leaves_before_it_touches_the_first_ones_files(tmp_path):
    """``__main__`` end to end: the refusal comes before the port and token
    files are written, so the running sidecar's stay as they are."""
    (tmp_path / PORT_FILENAME).write_text("4242")
    (tmp_path / TOKEN_FILENAME).write_text("first-launch-token")
    first = hold_data_dir(tmp_path)
    try:
        second = subprocess.run(
            [sys.executable, str(SERVER), "--port", "0", "--data-dir", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        first.close()

    assert second.returncode == 1
    assert DATA_DIR_IN_USE in second.stdout
    assert (tmp_path / PORT_FILENAME).read_text() == "4242"
    assert (tmp_path / TOKEN_FILENAME).read_text() == "first-launch-token"
