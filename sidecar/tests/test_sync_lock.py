"""The sync lock refuses concurrent index mutations with 409.

One lock guards every route that writes the index. A real
``/api/reindex-file`` is parked inside it — its indexer waits on an
Event — while the other guarded routes are called.
"""

import threading

import pytest

from legend_lore import router as router_mod


@pytest.fixture
def held_sync_lock(client, sample_pdf_path, monkeypatch):
    """Hold the sync lock the way production does, until the test ends."""
    entered, release = threading.Event(), threading.Event()

    def parked_index(*args, **kwargs):
        entered.set()
        release.wait(timeout=10)
        return 0, "parked", "unknown", []

    monkeypatch.setattr(router_mod, "index_single_pdf", parked_index)
    holder = threading.Thread(
        target=client.post,
        args=("/api/reindex-file",),
        kwargs={"json": {"path": str(sample_pdf_path)}},
    )
    holder.start()
    assert entered.wait(timeout=10), "reindex-file never took the lock"
    yield
    release.set()
    holder.join(timeout=10)


GUARDED_ROUTES = [
    ("/api/reindex-file", lambda p: {"path": str(p)}),
    ("/api/sync-index-stream", lambda p: {"selected_paths": [str(p)]}),
    ("/api/reindex-all-stream", lambda p: None),
    ("/api/delete-index", lambda p: None),
    ("/api/file-rename", lambda p: {"old_path": str(p), "new_path": str(p) + ".new"}),
    ("/api/file-delete", lambda p: {"path": str(p)}),
    ("/api/folder-rename", lambda p: {"old_prefix": str(p.parent), "new_prefix": str(p.parent) + "_new"}),
    ("/api/folder-delete", lambda p: {"folder_prefix": str(p.parent)}),
]


@pytest.mark.parametrize("route, body", GUARDED_ROUTES, ids=[r for r, _ in GUARDED_ROUTES])
def test_guarded_route_returns_409_while_a_sync_holds_the_lock(
    client, sample_pdf_path, held_sync_lock, route, body
):
    response = client.post(route, json=body(sample_pdf_path))
    assert response.status_code == 409, response.text


def test_lock_is_released_when_the_holder_finishes(client, sample_pdf_path, monkeypatch):
    monkeypatch.setattr(
        router_mod, "index_single_pdf", lambda *a, **k: (0, "stub", "unknown", [])
    )
    client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})

    response = client.post("/api/folder-delete", json={"folder_prefix": str(sample_pdf_path.parent)})
    assert response.status_code == 200, response.text
