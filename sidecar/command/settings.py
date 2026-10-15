"""Command's settings, kept by the sidecar so the watcher and MCP know the
campaign folder with no window open (design §6.1). Same shape as Legend
Lore's ``search_settings.json``: a missing or corrupt file means defaults."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .vault import atomic_write

SETTINGS_FILENAME = "command_settings.json"
SETTINGS_VERSION = 1


def default_root() -> Path:
    """Where campaigns go until the GM picks a folder: Command opens on a
    campaign at launch, so it can't wait to be told."""
    return Path.home() / "Unseen Servant"


class CommandSettings(BaseModel):
    root: str | None = None
    # Launching a beat marks it spent (design §4); off, spending is by hand.
    spend_on_launch: bool = False
    # The campaign open when the app last quit, which launch reopens.
    last_campaign: str | None = None


def load_settings(data_dir: Path | None) -> CommandSettings:
    if data_dir is None:
        return CommandSettings()
    path = data_dir / SETTINGS_FILENAME
    if not path.exists():
        return CommandSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {k: raw[k] for k in CommandSettings.model_fields if k in raw}
        return CommandSettings(**known)
    except Exception as e:
        print(f"Unreadable {SETTINGS_FILENAME} ({e}); using default Command settings")
        return CommandSettings()


def save_settings(data_dir: Path | None, settings: CommandSettings) -> None:
    if data_dir is None:
        return
    payload = {**settings.model_dump(), "version": SETTINGS_VERSION}
    atomic_write(data_dir / SETTINGS_FILENAME, json.dumps(payload, indent=2).encode())
