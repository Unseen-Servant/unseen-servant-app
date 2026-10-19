"""Change notifications for the campaign folder (design §6.1), and for the
live set, which no file holds, and an agent's ask to open a session
(``publish``).

One watcher runs while anyone is listening — in the app that is Rust's
relay, connected for the app's lifetime — and fans each batch of changes
out to every listener. Command's own writes reach listeners the same way an
edit made in Obsidian or Finder does: through the file system, so there is
one way a change becomes visible.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path

from watchfiles import awatch

from .vault import PRESENTATION_DIR, PRESENTATION_FILE

# Everything may have changed: a campaign was added, removed or renamed, the
# campaign folder setting changed, or the listener has just connected.
REFRESH = {"type": "vault", "campaign": None, "paths": []}

PRESENTATION = f"{PRESENTATION_DIR}/{PRESENTATION_FILE}"

# How often to look again for a campaign folder that isn't there.
MISSING_ROOT_RETRY_SECONDS = 5.0


def _hidden(part: str) -> bool:
    return part.startswith(".")


def batch_events(root: Path, changes: Iterable[tuple[object, str]]) -> list[dict]:
    """The ``vault`` events for one batch of file changes under ``root``: one
    per campaign touched, naming the campaign-relative paths, or a single
    REFRESH when the batch changed the campaign list itself. Hidden files —
    Command's temp files, ``.obsidian/`` — are dropped, except the track
    order file."""
    touched: dict[str, set[str]] = {}
    for _change, raw in changes:
        try:
            parts = Path(raw).relative_to(root).parts
        except ValueError:
            continue
        if not parts or _hidden(parts[0]):
            continue
        if len(parts) == 1:
            return [REFRESH]
        rel = "/".join(parts[1:])
        if any(_hidden(p) for p in parts[1:]) and rel != PRESENTATION:
            continue
        touched.setdefault(parts[0], set()).add(rel)
    return [
        {"type": "vault", "campaign": campaign, "paths": sorted(paths)}
        for campaign, paths in sorted(touched.items())
    ]


class VaultWatcher:
    """Watches the configured campaign folder while at least one listener is
    connected, and follows the setting when it changes."""

    def __init__(self, root: Callable[[], Path | None]):
        self._root = root
        self._listeners: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._restart: asyncio.Event | None = None

    def root_changed(self) -> None:
        """Start over on the newly configured folder. Safe from any thread
        (the settings route runs in the threadpool)."""
        loop, restart = self._loop, self._restart
        if loop is not None and restart is not None:
            loop.call_soon_threadsafe(restart.set)

    async def listen(self) -> AsyncIterator[dict]:
        """Every event from now on, starting with a REFRESH: a listener that
        just connected may have missed anything."""
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._listeners.add(queue)
        if self._task is None or self._task.done():
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.create_task(self._run())
        try:
            yield REFRESH
            while True:
                yield await queue.get()
        finally:
            self._listeners.discard(queue)
            if not self._listeners and self._task is not None:
                self._task.cancel()
                self._task = None

    def publish(self, event: dict) -> bool:
        """Send ``event`` to every listener — the live set changing, which
        no file records. Safe from any thread. Whether anyone was
        listening."""
        loop = self._loop
        if loop is not None and self._listeners and not loop.is_closed():
            loop.call_soon_threadsafe(self._fanout, event)
            return True
        return False

    def _fanout(self, event: dict) -> None:
        for queue in self._listeners:
            queue.put_nowait(event)

    async def _run(self) -> None:
        while True:
            self._restart = asyncio.Event()
            root = self._root()
            if root is None or not root.is_dir():
                # Nothing to watch until a folder is set. A missing one is
                # looked for again, in case its drive comes back.
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._restart.wait(), MISSING_ROOT_RETRY_SECONDS)
                continue
            # The OS reports resolved paths (/private/var for /var on macOS).
            root = root.resolve()
            try:
                async for changes in awatch(root, watch_filter=None, stop_event=self._restart):
                    for event in batch_events(root, changes):
                        self._fanout(event)
            except FileNotFoundError:
                continue
            # The folder setting changed: everything listeners hold is stale.
            self._fanout(REFRESH)
