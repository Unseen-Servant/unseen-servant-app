"""
Game system definitions for TTRPG detection and tagging.

Each entry has three fields:
- tag:         Short label stored in ChromaDB metadata and shown in UI badges
- game_system: Broader family name (for grouping related editions)
- keywords:    Lowercase strings matched against folder paths and PDF content

To add a new system, append an entry to the GAME_SYSTEMS list below.
The KNOWN_SYSTEMS lookup dict is derived automatically.
"""

GAME_SYSTEMS: list[dict] = [
    # --- Dungeons & Dragons ---
    {
        "tag": "D&D 5E",
        "game_system": "Dungeons & Dragons",
        "keywords": ["d&d 5e", "dnd 5e", "dnd5e", "5th edition", "5e srd"],
    },
    {
        "tag": "D&D 3.5E",
        "game_system": "Dungeons & Dragons",
        "keywords": ["d&d 3.5", "dnd 3.5", "3.5 edition", "3.5e", "d&d 3.5e"],
    },
    {
        "tag": "D&D 4E",
        "game_system": "Dungeons & Dragons",
        "keywords": ["d&d 4e", "dnd 4e", "4th edition", "4e srd"],
    },
    {
        "tag": "AD&D 2E",
        "game_system": "Advanced Dungeons & Dragons",
        "keywords": ["d&d 2e", "dnd 2e", "2nd edition", "ad&d 2e", "adnd 2e"],
    },
    {
        "tag": "AD&D",
        "game_system": "Advanced Dungeons & Dragons",
        "keywords": ["d&d 1e", "dnd 1e", "1st edition", "ad&d 1e", "adnd 1e"],
    },
    # --- Pathfinder ---
    {
        "tag": "PF1E",
        "game_system": "Pathfinder",
        "keywords": ["pathfinder 1e", "pathfinder1e", "pf1e", "pfrpg"],
    },
    {
        "tag": "PF2E",
        "game_system": "Pathfinder",
        "keywords": ["pathfinder 2e", "pathfinder2e", "pf2e"],
    },
    # --- Free League ---
    {
        "tag": "Dragonbane",
        "game_system": "Dragonbane",
        "keywords": ["dragonbane", "drakar och demoner"],
    },
    {
        "tag": "MORK BORG",
        "game_system": "MORK BORG",
        "keywords": ["mork borg", "morkborg"],
    },
    {
        "tag": "Blades in the Dark",
        "game_system": "Blades in the Dark",
        "keywords": ["blades in the dark", "bitd"],
    },
    # --- Horror ---
    {
        "tag": "CoC 7E",
        "game_system": "Call of Cthulhu",
        "keywords": ["call of cthulhu", "coc 7e", "coc 7th"],
    },
    # --- Cyberpunk ---
    {
        "tag": "Shadowrun",
        "game_system": "Shadowrun",
        "keywords": ["shadowrun"],
    },
    {
        "tag": "CPRed",
        "game_system": "Cyberpunk",
        "keywords": ["cyberpunk red"],
    },
    # --- Fantasy ---
    {
        "tag": "WFRP",
        "game_system": "Warhammer Fantasy Roleplay",
        "keywords": ["warhammer fantasy roleplay", "wfrp"],
    },
    {
        "tag": "W40KRP",
        "game_system": "Warhammer 40K RPG",
        "keywords": ["dark heresy", "rogue trader", "deathwatch", "black crusade", "only war"],
    },
    {
        "tag": "SotDL",
        "game_system": "Shadow of the Demon Lord",
        "keywords": ["shadow of the demon lord", "sotdl"],
    },
    {
        "tag": "SotWW",
        "game_system": "Shadow of the Weird Wizard",
        "keywords": ["shadow of the weird wizard", "sotww"],
    },
    # --- Generic / universal ---
    {
        "tag": "Savage Worlds",
        "game_system": "Savage Worlds",
        "keywords": ["savage worlds"],
    },
    {
        "tag": "GURPS",
        "game_system": "GURPS",
        "keywords": ["gurps"],
    },
    {
        "tag": "Fate",
        "game_system": "Fate",
        "keywords": ["fate core", "fate accelerated", "fate condensed"],
    },
    # --- Old-school renaissance ---
    {
        "tag": "OSR",
        "game_system": "OSR",
        "keywords": ["osr", "old school essentials", "ose", "basic fantasy", "b/x", "labyrinth lord", "swords & wizardry", "sw", "osric"],
    },
    {
        "tag": "SHDW",
        "game_system": "Shadowdark",
        "keywords": ["shadowdark"],
    },
    {
        "tag": "LotFP",
        "game_system": "Lamentations of the Flame Princess",
        "keywords": ["lamentations of the flame princess", "lotfp"],
    },
    {
        "tag": "DCC",
        "game_system": "Dungeon Crawl Classics",
        "keywords": ["dungeon crawl classics", "dcc"],
    }
]


# Derived lookup: tag → keywords (used by detect_game_system in server.py)
KNOWN_SYSTEMS: dict[str, list[str]] = {
    entry["tag"]: entry["keywords"] for entry in GAME_SYSTEMS
}
