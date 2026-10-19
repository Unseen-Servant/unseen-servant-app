"""Change events for the campaign folder (command/events.py): how a batch of
file changes becomes ``vault`` events, and the watcher's lifecycle against a
real temp folder."""

import asyncio
from pathlib import Path

import pytest

from command.events import REFRESH, VaultWatcher, batch_events

ROOT = Path("/vault")


def changes(*rels):
    return {(2, str(ROOT / rel)) for rel in rels}


def test_batch_groups_paths_by_campaign():
    events = batch_events(ROOT, changes("Strahd/NPCs/Ismark.md", "Strahd/NPCs/Ireena.md", "Odd/PCs/Bo.md"))
    assert events == [
        {"type": "vault", "campaign": "Odd", "paths": ["PCs/Bo.md"]},
        {"type": "vault", "campaign": "Strahd", "paths": ["NPCs/Ireena.md", "NPCs/Ismark.md"]},
    ]


def test_batch_drops_hidden_files_but_keeps_track_order():
    events = batch_events(ROOT, changes(
        "Strahd/NPCs/.Ismark.md.x1.tmp",
        "Strahd/.obsidian/workspace.json",
        ".DS_Store",
        "Strahd/.unseen/command.json",
    ))
    assert events == [{"type": "vault", "campaign": "Strahd", "paths": [".unseen/command.json"]}]


def test_batch_with_a_root_level_change_refreshes_everything():
    assert batch_events(ROOT, changes("Strahd/NPCs/Ismark.md", "New Campaign")) == [REFRESH]


def test_batch_ignores_paths_outside_the_root():
    assert batch_events(ROOT, {(1, "/elsewhere/Strahd/x.md")}) == []


# ---------------------------------------------------------------------------
# The watcher, on a real folder
# ---------------------------------------------------------------------------

async def next_event(events, timeout=10.0):
    return await asyncio.wait_for(anext(events), timeout)


async def until(events, predicate, timeout=10.0):
    """The first event matching ``predicate``; the OS may report other
    changes (a parent folder's mtime) along the way."""
    async def scan():
        while True:
            event = await anext(events)
            if predicate(event):
                return event
    return await asyncio.wait_for(scan(), timeout)


@pytest.fixture
def campaign(tmp_path):
    camp = tmp_path / "root" / "Strahd"
    (camp / "NPCs").mkdir(parents=True)
    return camp


async def test_a_new_listener_starts_with_a_refresh_then_hears_changes(campaign):
    watcher = VaultWatcher(lambda: campaign.parent)
    events = watcher.listen()
    assert await next_event(events) == REFRESH
    await asyncio.sleep(0.5)  # let the OS watch start

    (campaign / "NPCs" / "Ismark.md").write_text("hello")
    event = await until(events, lambda e: "NPCs/Ismark.md" in e["paths"])
    assert event["campaign"] == "Strahd"
    await events.aclose()


async def test_changing_the_folder_refreshes_and_follows_it(campaign, tmp_path):
    other = tmp_path / "other"
    (other / "Odd" / "PCs").mkdir(parents=True)
    current = {"root": campaign.parent}
    watcher = VaultWatcher(lambda: current["root"])
    events = watcher.listen()
    assert await next_event(events) == REFRESH
    await asyncio.sleep(0.5)

    current["root"] = other
    watcher.root_changed()
    assert await next_event(events) == REFRESH
    await asyncio.sleep(0.5)

    (other / "Odd" / "PCs" / "Bo.md").write_text("hi")
    event = await until(events, lambda e: "PCs/Bo.md" in e["paths"])
    assert event["campaign"] == "Odd"
    await events.aclose()


async def test_the_watch_stops_with_the_last_listener(campaign):
    watcher = VaultWatcher(lambda: campaign.parent)
    first, second = watcher.listen(), watcher.listen()
    await next_event(first)
    await next_event(second)
    task = watcher._task

    await first.aclose()
    assert not task.done()
    await second.aclose()
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()
    assert watcher._task is None


async def test_no_folder_set_waits_quietly_until_one_is(campaign):
    current = {"root": None}
    watcher = VaultWatcher(lambda: current["root"])
    events = watcher.listen()
    assert await next_event(events) == REFRESH

    current["root"] = campaign.parent
    watcher.root_changed()
    await asyncio.sleep(0.5)
    (campaign / "NPCs" / "Ireena.md").write_text("x")
    event = await until(events, lambda e: "NPCs/Ireena.md" in e["paths"])
    assert event["campaign"] == "Strahd"
    await events.aclose()


async def test_a_published_event_reaches_every_listener_from_any_thread(campaign):
    watcher = VaultWatcher(lambda: campaign.parent)
    first, second = watcher.listen(), watcher.listen()
    await next_event(first)
    await next_event(second)
    event = {"type": "live", "campaign": "Strahd", "seq": 1, "beat": None, "notes": []}
    assert await asyncio.to_thread(watcher.publish, event) is True
    assert await until(first, lambda e: e["type"] == "live") == event
    assert await until(second, lambda e: e["type"] == "live") == event
    await first.aclose()
    await second.aclose()


def test_publishing_with_nobody_listening_does_nothing():
    assert VaultWatcher(lambda: None).publish({"type": "live"}) is False
