"""
Tests for game system detection.

The detect_game_system() function identifies TTRPG game systems from
folder paths and PDF content, using a three-tier approach:
1. Folder name keywords (highest priority)
2. Content keyword scan (first 2000 chars)
3. Fallback to "unknown"
"""

from pathlib import Path

from game_systems import GAME_SYSTEMS, KNOWN_SYSTEMS
from server import detect_game_system


def test_game_systems_structure():
    """Each entry in GAME_SYSTEMS should have tag and keywords."""
    assert len(GAME_SYSTEMS) > 0
    for entry in GAME_SYSTEMS:
        assert "tag" in entry, f"Missing 'tag' in {entry}"
        assert "keywords" in entry, f"Missing 'keywords' in {entry}"
        assert isinstance(entry["keywords"], list)
        assert len(entry["keywords"]) > 0, f"Empty keywords for {entry['tag']}"
    # KNOWN_SYSTEMS should have same number of entries
    assert len(KNOWN_SYSTEMS) == len(GAME_SYSTEMS)


def test_detect_from_folder_dnd5e():
    """Path containing 'D&D 5E' folder should detect D&D 5E."""
    path = Path("/RPGs/D&D 5E/Player's Handbook.pdf")
    assert detect_game_system(path) == "D&D 5E"


def test_detect_from_folder_dragonbane():
    """Path containing 'Dragonbane' folder should detect Dragonbane."""
    path = Path("/Library/Dragonbane/Core Rules.pdf")
    assert detect_game_system(path) == "Dragonbane"


def test_detect_from_folder_pathfinder_2e():
    """Path containing 'Pathfinder 2E' should detect PF2E."""
    path = Path("/Games/Pathfinder 2E/Bestiary.pdf")
    assert detect_game_system(path) == "PF2E"


def test_detect_from_folder_case_insensitive():
    """Detection should be case-insensitive."""
    path = Path("/rpgs/d&d 5e/phb.pdf")
    assert detect_game_system(path) == "D&D 5E"


def test_detect_from_folder_mork_borg():
    """Path with 'MORK BORG' should match."""
    path = Path("/RPGs/MORK BORG/Feretory.pdf")
    assert detect_game_system(path) == "MORK BORG"


def test_detect_from_content():
    """When path has no hint, fall back to content keyword scan."""
    path = Path("/unsorted/rulebook.pdf")
    text = "Welcome to the Dragonbane roleplaying game. This book contains..."
    assert detect_game_system(path, text) == "Dragonbane"


def test_detect_from_content_dnd():
    """Content mentioning '5th edition' should detect D&D 5E."""
    path = Path("/misc/rules.pdf")
    text = "Player's Handbook for the 5th edition of the world's greatest RPG."
    assert detect_game_system(path, text) == "D&D 5E"


def test_detect_path_takes_priority_over_content():
    """If path says D&D 5E but text says Pathfinder, path wins."""
    path = Path("/RPGs/D&D 5E/conversion_guide.pdf")
    text = "How to convert Pathfinder 2E monsters to other systems."
    assert detect_game_system(path) == "D&D 5E"


def test_detect_unknown_when_no_match():
    """Generic path and no text should return 'unknown'."""
    path = Path("/documents/random_book.pdf")
    assert detect_game_system(path) == "unknown"


def test_detect_unknown_with_no_matching_text():
    """Text that doesn't match any system should return 'unknown'."""
    path = Path("/docs/stuff.pdf")
    text = "This is a book about cooking recipes and kitchen tips."
    assert detect_game_system(path, text) == "unknown"


def test_detect_with_none_text():
    """When text is None, only path detection should run."""
    path = Path("/unsorted/mystery.pdf")
    assert detect_game_system(path, None) == "unknown"


def test_detect_content_scans_first_2000_chars():
    """Keywords appearing after 2000 chars should NOT be detected."""
    path = Path("/unsorted/book.pdf")
    filler = "x" * 2100
    text = filler + "This is a Dragonbane adventure."
    assert detect_game_system(path, text) == "unknown"


def test_detect_savage_worlds():
    """Path with 'Savage Worlds' should match."""
    path = Path("/RPGs/Savage Worlds/SWADE.pdf")
    assert detect_game_system(path) == "SaWo"


def test_detect_call_of_cthulhu():
    """Path with 'Call of Cthulhu' should match."""
    path = Path("/RPGs/Call of Cthulhu/Keeper Rulebook.pdf")
    assert detect_game_system(path) == "CoC 7E"


def test_detect_osr_from_content():
    """Content mentioning 'Old School Essentials' should detect OSR."""
    path = Path("/unsorted/retro_game.pdf")
    text = "Old School Essentials is a retro-clone of the classic D&D rules."
    assert detect_game_system(path, text) == "OSR"


# ---------------------------------------------------------------------------
# Custom known_systems parameter
# ---------------------------------------------------------------------------

def test_detect_with_custom_known_systems():
    """Passing a custom known_systems dict should use those keywords."""
    custom = {
        "Mothership": ["mothership", "mothership rpg"],
        "Cairn": ["cairn"],
    }
    path = Path("/RPGs/Mothership/Dead Planet.pdf")
    assert detect_game_system(path, known_systems=custom) == "Mothership"


def test_detect_custom_overrides_builtin():
    """Custom known_systems replaces built-in — built-in keywords won't match."""
    # A dict with only one custom system — D&D keywords should NOT match
    custom = {
        "Cairn": ["cairn"],
    }
    path = Path("/RPGs/D&D 5E/Player's Handbook.pdf")
    assert detect_game_system(path, known_systems=custom) == "unknown"


def test_detect_custom_from_content():
    """Custom systems should also match via content scan."""
    custom = {
        "Cairn": ["cairn"],
    }
    path = Path("/unsorted/adventure.pdf")
    text = "This is a Cairn adventure set in the dark forest."
    assert detect_game_system(path, text, known_systems=custom) == "Cairn"
