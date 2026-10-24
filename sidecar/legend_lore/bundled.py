"""The models shipped with the app, as ``models/manifest.json`` lists them.

``scripts/fetch-models.mjs`` places and checks the files; tauri build
bundles the folder into the app's Resources, and server.py learns where
from ``--models-dir``. This module only finds a model's folder in it.
"""
from __future__ import annotations

import json
from pathlib import Path


def model_dir(root: str | Path | None, role: str, name: str) -> Path | None:
    """The folder of the ``role``/``name`` model under ``root``, or None.

    A folder missing any file its manifest entry lists doesn't count, nor
    does a root without a readable manifest.
    """
    if not root:
        return None
    try:
        manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for model in manifest.get("models", []):
        if model.get("role") == role and model.get("name") == name:
            path = Path(root) / model["dir"]
            if all((path / f["path"]).is_file() for f in model["files"]):
                return path
    return None
