"""What's live at the table (design §6.2): per campaign, the beat launched
last and the notes now in play.

This is sidecar state, never written to notes (design §3.5). It's saved to
the data dir on every change so a crash mid-session brings it back, and
MCP can read it with no window open.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from .vault import atomic_write

LIVE_FILENAME = "command_live.json"
LIVE_VERSION = 1


def _clean(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    notes = raw.get("notes")
    seq = raw.get("seq")
    return {
        "seq": seq if isinstance(seq, int) and not isinstance(seq, bool) else 0,
        "beat": raw["beat"] if isinstance(raw.get("beat"), str) else None,
        "notes": [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else [],
    }


class LiveSets:
    """The live set of every campaign, kept in ``command_live.json``. A
    missing or corrupt file means nothing is live."""

    def __init__(self, data_dir: Path | None):
        self._path = data_dir / LIVE_FILENAME if data_dir is not None else None
        self._lock = threading.Lock()
        self._sets: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            campaigns = raw.get("campaigns", {})
            return {c: s for c, raw_set in campaigns.items() if (s := _clean(raw_set))}
        except Exception as e:
            print(f"Unreadable {LIVE_FILENAME} ({e}); nothing is live")
            return {}

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {"version": LIVE_VERSION, "campaigns": self._sets}
        atomic_write(self._path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"))

    def get(self, campaign: str) -> dict:
        current = self._sets.get(campaign) or {"seq": 0, "beat": None, "notes": []}
        return {"campaign": campaign, "seq": current["seq"], "beat": current["beat"], "notes": list(current["notes"])}

    def set(self, campaign: str, beat: str | None, notes: list[str]) -> dict:
        """Make ``notes`` the live set, launched from ``beat``. Each change
        takes the next ``seq``, so a reader can tell a newer snapshot."""
        with self._lock:
            seq = self._sets.get(campaign, {}).get("seq", 0) + 1
            self._sets[campaign] = {"seq": seq, "beat": beat, "notes": list(dict.fromkeys(notes))}
            self._save()
            return self.get(campaign)

    def remap(self, campaign: str, move: Callable[[str], str]) -> dict | None:
        """Follow renames and moves: ``move`` gives each path's new path.
        Returns the new snapshot, or None if nothing live moved."""
        current = self.get(campaign)
        beat = move(current["beat"]) if current["beat"] else None
        notes = [move(n) for n in current["notes"]]
        if beat == current["beat"] and notes == current["notes"]:
            return None
        return self.set(campaign, beat, notes)

    def rename_campaign(self, name: str, new_name: str) -> dict | None:
        with self._lock:
            moved = self._sets.pop(name, None)
            if moved is None:
                return None
            moved["seq"] += 1
            self._sets[new_name] = moved
            self._save()
        return self.get(new_name)
