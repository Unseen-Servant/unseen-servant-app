"""
Game system definitions for TTRPG detection and tagging.

Each entry has three fields:
- tag:      Short label stored in ChromaDB metadata and shown in UI badges
- keywords: Lowercase strings matched against folder paths and PDF content
- color:    Default badge tint (hex). User can override per-system in Settings.

To add a new system, append an entry to the GAME_SYSTEMS list below.
The KNOWN_SYSTEMS lookup dict is derived automatically.
"""

# Palette mirrors the collection picker in CollectionEditDialog.svelte:
#   #c75450 red    #d49449 orange  #caa84b amber  #5fb068 green
#   #4fa896 teal   #5a8dc4 blue    #9b6cb6 purple #b69f81 tan
GAME_SYSTEMS: list[dict] = [
    # --- Dungeons & Dragons (red family) ---
    {
        "tag": "D&D 5E",
        "keywords": ["d&d 5e", "dnd 5e", "dnd5e", "5th edition", "5e srd"],
        "color": "#c75450",
    },
    {
        "tag": "D&D 3.5E",
        "keywords": ["d&d 3.5", "dnd 3.5", "3.5 edition", "3.5e", "d&d 3.5e"],
        "color": "#c75450",
    },
    {
        "tag": "D&D 4E",
        "keywords": ["d&d 4e", "dnd 4e", "4th edition", "4e srd"],
        "color": "#c75450",
    },
    {
        "tag": "AD&D 2E",
        "keywords": ["d&d 2e", "dnd 2e", "2nd edition", "ad&d 2e", "adnd 2e"],
        "color": "#c75450",
    },
    {
        "tag": "AD&D",
        "keywords": ["d&d 1e", "dnd 1e", "1st edition", "ad&d 1e", "adnd 1e"],
        "color": "#c75450",
    },
    # --- Pathfinder (green family) ---
    {
        "tag": "PF1E",
        "keywords": ["pathfinder 1e", "pathfinder1e", "pf1e", "pfrpg"],
        "color": "#5fb068",
    },
    {
        "tag": "PF2E",
        "keywords": ["pathfinder 2e", "pathfinder2e", "pf2e"],
        "color": "#5fb068",
    },
    # --- Free League (teal) ---
    {
        "tag": "Dragonbane",
        "keywords": ["dragonbane", "drakar och demoner"],
        "color": "#4fa896",
    },
    {
        "tag": "MORK BORG",
        "keywords": ["mork borg", "morkborg"],
        "color": "#4fa896",
    },
    # --- Horror (purple) ---
    {
        "tag": "CoC 7E",
        "keywords": ["call of cthulhu", "coc 7e", "coc 7th"],
        "color": "#9b6cb6",
    },
    # --- Cyberpunk (blue) ---
    {
        "tag": "CP RED",
        "keywords": ["cyberpunk red"],
        "color": "#5a8dc4",
    },
    # --- Warhammer (orange) ---
    {
        "tag": "WFRP 4E",
        "keywords": ["warhammer fantasy roleplay", "wfrp"],
        "color": "#d49449",
    },
    {
        "tag": "W40KRP",
        "keywords": ["dark heresy", "rogue trader", "deathwatch", "black crusade", "only war"],
        "color": "#d49449",
    },
    # --- Schwalb (purple — adjacent to horror in tone) ---
    {
        "tag": "SotDL",
        "keywords": ["shadow of the demon lord", "sotdl"],
        "color": "#9b6cb6",
    },
    {
        "tag": "SotWW",
        "keywords": ["shadow of the weird wizard", "sotww"],
        "color": "#9b6cb6",
    },
    # --- Generic / universal (tan) ---
    {
        "tag": "SaWo",
        "keywords": ["savage worlds"],
        "color": "#b69f81",
    },
    {
        "tag": "GURPS",
        "keywords": ["gurps"],
        "color": "#b69f81",
    },
    {
        "tag": "Fate",
        "keywords": ["fate core", "fate accelerated", "fate condensed"],
        "color": "#b69f81",
    },
    # --- Old-school renaissance (amber family) ---
    {
        "tag": "OSR",
        "keywords": ["osr", "old school essentials", "ose", "basic fantasy", "b/x", "labyrinth lord", "swords & wizardry", "sw", "osric"],
        "color": "#caa84b",
    },
    {
        "tag": "SD",
        "keywords": ["shadowdark"],
        "color": "#caa84b",
    },
    {
        "tag": "LotFP",
        "keywords": ["lamentations of the flame princess", "lotfp"],
        "color": "#caa84b",
    },
    {
        "tag": "DCC",
        "keywords": ["dungeon crawl classics", "dcc"],
        "color": "#caa84b",
    },
    {
        "tag": "C&C",
        "keywords": ["castles & crusades", "c&c"],
        "color": "#caa84b",
    }
]


# Derived lookup: tag → keywords (used by detect_game_system in server.py)
KNOWN_SYSTEMS: dict[str, list[str]] = {
    entry["tag"]: entry["keywords"] for entry in GAME_SYSTEMS
}
