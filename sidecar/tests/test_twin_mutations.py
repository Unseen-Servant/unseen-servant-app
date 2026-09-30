"""Mutations on same-named files in different folders (issue #330).

``/api/set-game-systems`` resolved its target by bare filename, so with
``/5e/Monster Manual.pdf`` and ``/pf2e/Monster Manual.pdf`` indexed, a
retag meant for one twin landed on whichever the manifest listed first,
and wrote the tags into *both* manifest entries. Tagging is now
path-addressed; a filename that names more than one file is refused
rather than guessed.
"""

from legend_lore.service import load_manifest


def _index_twins(client, twin_pdfs):
    a, b = twin_pdfs
    resp = client.post("/api/index-files", json={"paths": [str(a), str(b)]})
    assert resp.status_code == 200, resp.text
    return a, b


def _chunk_systems(store, path) -> set[str]:
    """The primary tag every unit of ``path`` reports (units read it from
    their book's documents row)."""
    docs = [d for d in store.documents() if d.path == str(path)]
    assert docs and docs[0].units, f"no chunks for {path}"
    return {docs[0].game_system}


def test_set_game_systems_by_path_leaves_twin_untouched(
    client, twin_pdfs, test_store, tmp_path
):
    a, b = _index_twins(client, twin_pdfs)

    resp = client.post("/api/set-game-systems", json={
        "path": str(b), "game_systems": ["Pathfinder 2E", "D&D 5E"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == b.name

    assert _chunk_systems(test_store, b) == {"Pathfinder 2E"}
    assert _chunk_systems(test_store, a) != {"Pathfinder 2E"}

    files = load_manifest(tmp_path).files
    assert files[str(b)].game_systems == ["Pathfinder 2E", "D&D 5E"]
    assert files[str(a)].game_systems != ["Pathfinder 2E", "D&D 5E"]
    assert files[str(a)].game_system != "Pathfinder 2E"


def test_set_game_systems_unknown_path_is_404(client, twin_pdfs, tmp_path):
    _index_twins(client, twin_pdfs)
    resp = client.post("/api/set-game-systems", json={
        "path": str(tmp_path / "nowhere" / "monsters.pdf"),
        "game_systems": ["OSRIC"],
    })
    assert resp.status_code == 404


def test_set_game_systems_ambiguous_filename_is_refused(
    client, twin_pdfs, test_store, tmp_path
):
    a, b = _index_twins(client, twin_pdfs)
    resp = client.post("/api/set-game-systems", json={
        "filename": a.name, "game_systems": ["OSRIC"],
    })
    assert resp.status_code == 409, resp.text

    for p in (a, b):
        assert "OSRIC" not in _chunk_systems(test_store, p)
        assert load_manifest(tmp_path).files[str(p)].game_systems != ["OSRIC"]

