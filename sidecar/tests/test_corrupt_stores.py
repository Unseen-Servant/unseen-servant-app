"""Unreadable store files are moved aside, not fatal and not overwritten.

The stores are written atomically, so a bad file means a hand edit or
disk damage. A corrupt custom_game_systems.json used to stop the sidecar
booting; a corrupt manifest or collections file 500'd its endpoints.
Falling back silently (as search settings do) would let the next save
overwrite the user's collections or systems, so the file is kept beside
the fresh store for them to repair.
"""

import pytest
from fastapi.testclient import TestClient

from server import create_app


@pytest.mark.parametrize("contents", ["{not json", "[1, 2]"])
@pytest.mark.parametrize("filename, endpoint", [
    ("index_manifest.json", "/api/sources"),
    ("collections.json", "/api/collections"),
    ("custom_game_systems.json", "/api/game-systems"),
])
def test_unreadable_store_is_moved_aside(
    filename, endpoint, contents, test_store, test_embed_fn, tmp_path
):
    (tmp_path / filename).write_text(contents)

    app = create_app(store=test_store, data_dir=tmp_path, embed_fn=test_embed_fn)
    assert TestClient(app).get(endpoint).status_code == 200

    assert not (tmp_path / filename).exists()
    aside = list(tmp_path.glob(f"{filename}.corrupt-*"))
    assert len(aside) == 1
    assert aside[0].read_text() == contents
