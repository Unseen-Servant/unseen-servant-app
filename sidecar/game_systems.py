"""
Game system definitions for TTRPG detection and tagging.

Each entry has two fields:
- tag:      Short label stored in ChromaDB metadata and shown in UI badges
- keywords: Lowercase strings matched against folder paths and PDF content

To add a new system, append an entry to the GAME_SYSTEMS list below.
The KNOWN_SYSTEMS lookup dict is derived automatically.
"""

GAME_SYSTEMS: list[dict] = [
    # --- Dungeons & Dragons ---
    {
        "tag": "D&D 5E",
        "keywords": ["d&d 5e", "dnd 5e", "dnd5e", "5th edition", "5e srd"],
    },
    {
        "tag": "D&D 3.5E",
        "keywords": ["d&d 3.5", "dnd 3.5", "3.5 edition", "3.5e", "d&d 3.5e"],
    },
    {
        "tag": "D&D 4E",
        "keywords": ["d&d 4e", "dnd 4e", "4th edition", "4e srd"],
    },
    {
        "tag": "AD&D 2E",
        "keywords": ["d&d 2e", "dnd 2e", "2nd edition", "ad&d 2e", "adnd 2e"],
    },
    {
        "tag": "AD&D",
        "keywords": ["d&d 1e", "dnd 1e", "1st edition", "ad&d 1e", "adnd 1e"],
    },
    # --- Pathfinder ---
    {
        "tag": "PF1E",
        "keywords": ["pathfinder 1e", "pathfinder1e", "pf1e", "pfrpg"],
    },
    {
        "tag": "PF2E",
        "keywords": ["pathfinder 2e", "pathfinder2e", "pf2e"],
    },
    # --- Free League ---
    {
        "tag": "Dragonbane",
        "keywords": ["dragonbane", "drakar och demoner"],
    },
    {
        "tag": "MORK BORG",
        "keywords": ["mork borg", "morkborg"],
    },
    # --- Horror ---
    {
        "tag": "CoC 7E",
        "keywords": ["call of cthulhu", "coc 7e", "coc 7th"],
    },
    # --- Cyberpunk ---
    {
        "tag": "CP RED",
        "keywords": ["cyberpunk red"],
    },
    # --- Fantasy ---
    {
        "tag": "WFRP 4E",
        "keywords": ["warhammer fantasy roleplay", "wfrp"],
    },
    {
        "tag": "W40KRP",
        "keywords": ["dark heresy", "rogue trader", "deathwatch", "black crusade", "only war"],
    },
    {
        "tag": "SotDL",
        "keywords": ["shadow of the demon lord", "sotdl"],
    },
    {
        "tag": "SotWW",
        "keywords": ["shadow of the weird wizard", "sotww"],
    },
    # --- Generic / universal ---
    {
        "tag": "SaWo",
        "keywords": ["savage worlds"],
    },
    {
        "tag": "GURPS",
        "keywords": ["gurps"],
    },
    {
        "tag": "Fate",
        "keywords": ["fate core", "fate accelerated", "fate condensed"],
    },
    # --- Old-school renaissance ---
    {
        "tag": "OSR",
        "keywords": ["osr", "old school essentials", "ose", "basic fantasy", "b/x", "labyrinth lord", "swords & wizardry", "sw", "osric"],
    },
    {
        "tag": "SD",
        "keywords": ["shadowdark"],
    },
    {
        "tag": "LotFP",
        "keywords": ["lamentations of the flame princess", "lotfp"],
    },
    {
        "tag": "DCC",
        "keywords": ["dungeon crawl classics", "dcc"],
    },
    {
        "tag": "C&C",
        "keywords": ["castles & crusades", "c&c"],
    }
]


# Derived lookup: tag → keywords (used by detect_game_system in server.py)
KNOWN_SYSTEMS: dict[str, list[str]] = {
    entry["tag"]: entry["keywords"] for entry in GAME_SYSTEMS
}
