"""
Game system definitions for TTRPG detection and tagging.

Each entry has three fields:
- tag:      Short label stored in ChromaDB metadata and shown in UI badges
- keywords: Strings matched against folder paths and PDF content. Matching
            normalizes both sides — case, whitespace, punctuation (``&``,
            ``-``, ``_``, ``.``), and accents are ignored — so spelling
            variants like ``d&d 5e``, ``DnD-5e``, ``dnd5e`` all collapse
            to one needle. Pick the most readable spelling for the catalog;
            duplicates that normalize to the same string add nothing.
- color:    Default badge tint (hex). User can override per-system in Settings.

To add a new system, append an entry to the GAME_SYSTEMS list below.
The KNOWN_SYSTEMS lookup dict is derived automatically.

Two pitfalls when adding keywords:
1. Avoid very short keywords (≤ 3 chars after normalization) unless they
   are unambiguous in TTRPG context — they false-positive on unrelated
   path/text fragments. Prefer the spelled-out name.
2. Prefer spellings the user is likely to put in a folder name. Generic
   English phrases ("5th edition") match content but rarely paths.
"""

# Palette mirrors the collection picker in CollectionEditDialog.svelte:
#   #c75450 red    #d49449 orange  #caa84b amber  #5fb068 green
#   #4fa896 teal   #5a8dc4 blue    #9b6cb6 purple #b69f81 tan
GAME_SYSTEMS: list[dict] = [
    # --- Dungeons & Dragons (red family) ---
    {
        "tag": "D&D 5E",
        # "5e srd" is the safest short form (won't collide with "5e" in 3.5E
        # or 4E folder names). "5th edition" catches content that names the
        # edition prose-style.
        "keywords": ["d&d 5e", "dnd 5e", "5e srd", "5th edition"],
        "color": "#c75450",
    },
    {
        "tag": "D&D 3.5E",
        "keywords": ["d&d 3.5", "dnd 3.5", "3.5 edition"],
        "color": "#c75450",
    },
    {
        "tag": "D&D 4E",
        "keywords": ["d&d 4e", "dnd 4e", "4e srd", "4th edition"],
        "color": "#c75450",
    },
    {
        "tag": "AD&D 2E",
        "keywords": ["ad&d 2e", "advanced d&d 2", "2nd edition"],
        "color": "#c75450",
    },
    {
        "tag": "AD&D",
        "keywords": ["ad&d 1e", "advanced d&d", "1st edition"],
        "color": "#c75450",
    },
    # --- Pathfinder (green family) ---
    {
        "tag": "PF1E",
        "keywords": ["pathfinder 1e", "pf1e", "pfrpg"],
        "color": "#5fb068",
    },
    {
        "tag": "PF2E",
        "keywords": ["pathfinder 2e", "pf2e"],
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
        # Normalization strips the umlaut, so "Mörk Borg" matches via
        # "mork borg" naturally.
        "keywords": ["mork borg"],
        "color": "#4fa896",
    },
    # --- Horror (purple) ---
    {
        "tag": "CoC 7E",
        # Plain "coc" alone risks colliding with "cocoa" / "cocoon"; keep
        # the qualified forms.
        "keywords": ["call of cthulhu", "coc 7e", "coc 7th"],
        "color": "#9b6cb6",
    },
    # --- Cyberpunk (blue) ---
    {
        "tag": "CP RED",
        "keywords": ["cyberpunk red", "cp red"],
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
        # Game-specific imprints; "wh40k" / "warhammer 40k" added for
        # users who file by setting rather than imprint.
        "keywords": [
            "warhammer 40k", "wh40k",
            "dark heresy", "rogue trader", "deathwatch",
            "black crusade", "only war", "wrath & glory",
        ],
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
        # "swade" is the common abbreviation for the current edition.
        "keywords": ["savage worlds", "swade"],
        "color": "#b69f81",
    },
    {
        "tag": "GURPS",
        "keywords": ["gurps"],
        "color": "#b69f81",
    },
    {
        "tag": "Fate",
        # Bare "fate" would match too much English prose; keep qualified.
        "keywords": ["fate core", "fate accelerated", "fate condensed", "fate rpg"],
        "color": "#b69f81",
    },
    # --- Old-school renaissance (amber family) ---
    {
        "tag": "OSR",
        # Dropped from the previous catalog because they false-positive
        # under substring matching: "ose" (matches "prose", "verbose"),
        # "sw" (matches anything with those two letters anywhere),
        # "b/x" (normalizes to "bx", too short). Spelled-out names win.
        "keywords": [
            "osr",
            "old school essentials",
            "basic fantasy",
            "labyrinth lord",
            "swords & wizardry",
            "osric",
        ],
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
        "keywords": ["dungeon crawl classics", "dcc rpg"],
        "color": "#caa84b",
    },
    {
        "tag": "C&C",
        # Normalization folds ``&`` to ``n``: ``c&c`` and ``cnc`` collapse
        # to the same needle.
        "keywords": ["castles & crusades", "c&c"],
        "color": "#caa84b",
    }
]


# Derived lookup: tag → keywords (used by detect_game_system in server.py)
KNOWN_SYSTEMS: dict[str, list[str]] = {
    entry["tag"]: entry["keywords"] for entry in GAME_SYSTEMS
}
