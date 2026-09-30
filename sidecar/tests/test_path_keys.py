"""One spelling of a tree path across the UI, the manifest and the store.

The Tauri shell hands the UI '/'-separated paths on every platform (see
ui_path in legend_lore.rs), and the UI's helpers split on '/'. On Windows
a concrete Path prints with '\\', so any path the sidecar rebuilds from a
Path (a store key, a parent id's source, a rename it detects on disk) has
to be re-spelled with '/' or it stops matching what the UI sent.
"""
from pathlib import PurePosixPath, PureWindowsPath

from legend_lore.service import path_key


def test_windows_paths_key_with_forward_slashes():
    assert path_key(PureWindowsPath("C:/lib/Core/a.pdf")) == "C:/lib/Core/a.pdf"
    assert path_key(PureWindowsPath(r"C:\lib\Core\a.pdf")) == "C:/lib/Core/a.pdf"


def test_posix_paths_key_unchanged():
    assert path_key(PurePosixPath("/lib/Core/a.pdf")) == "/lib/Core/a.pdf"
