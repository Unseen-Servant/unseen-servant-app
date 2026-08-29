"""Corpus integrity tests that do not require the private corpus fixture."""
from evals.corpus import _aggregate_digest


def test_reference_digest_binds_paths_as_well_as_content():
    original = {"rules/goblin.md": "same", "rules/armor.md": "other"}
    renamed = {"rules/hobgoblin.md": "same", "rules/armor.md": "other"}
    swapped = {"rules/goblin.md": "other", "rules/armor.md": "same"}
    assert _aggregate_digest(original) != _aggregate_digest(renamed)
    assert _aggregate_digest(original) != _aggregate_digest(swapped)
