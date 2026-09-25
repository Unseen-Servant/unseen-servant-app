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

# Colors come from the manuscript-pigment palette; src/lib/legend-lore/palette.ts is
# the source of truth (keep hexes in sync by hand — no shared codegen):
#   #c2736d Madder  #bb7b4e Ember      #9f8b3e Gilt  #6b9b60 Moss
#   #2fa094 Verdigris  #5b90c7 Woad    #b5739f Plum
GAME_SYSTEMS: list[dict] = [
    # --- Dungeons & Dragons (Madder) ---
    {
        "tag": "D&D 5E",
        # "5e srd" is the safest short form (won't collide with "5e" in 3.5E
        # or 4E folder names). "5th edition" catches content that names the
        # edition prose-style.
        #
        # "black flag" (Kobold Press's 5E-compatible Black Flag Roleplaying /
        # ToV SRD) and the WotC CC SRD filename forms ("SRD_CC_v5.1" →
        # "srd cc", "SRD5.1" → "srd 5.1") don't name the edition anywhere
        # in their filenames and previously fell through to "unknown".
        "keywords": [
            "d&d 5e", "dnd 5e", "5e srd", "5th edition",
            "black flag", "srd cc", "srd 5.1",
        ],
        "color": "#c2736d",
    },
    {
        "tag": "D&D 3.5E",
        "keywords": ["d&d 3.5", "dnd 3.5", "3.5 edition"],
        "color": "#c2736d",
    },
    {
        "tag": "D&D 4E",
        "keywords": ["d&d 4e", "dnd 4e", "4e srd", "4th edition"],
        "color": "#c2736d",
    },
    {
        "tag": "AD&D 2E",
        "keywords": ["ad&d 2e", "advanced d&d 2", "2nd edition"],
        "color": "#c2736d",
    },
    {
        "tag": "AD&D",
        "keywords": ["ad&d 1e", "advanced d&d", "1st edition"],
        "color": "#c2736d",
    },
    # --- Pathfinder (Moss) ---
    {
        "tag": "PF1E",
        "keywords": ["pathfinder 1e", "pf1e", "pfrpg"],
        "color": "#6b9b60",
    },
    {
        "tag": "PF2E",
        "keywords": ["pathfinder 2e", "pf2e"],
        "color": "#6b9b60",
    },
    # --- Free League (Verdigris) ---
    {
        "tag": "Dragonbane",
        "keywords": ["dragonbane", "drakar och demoner"],
        "color": "#2fa094",
    },
    {
        "tag": "MORK BORG",
        # Normalization strips the umlaut, so "Mörk Borg" matches via
        # "mork borg" naturally.
        "keywords": ["mork borg"],
        "color": "#2fa094",
    },
    {
        "tag": "YZE",
        # "yze" alone is ≤3 chars (rule 1); the spelled-out name only.
        "keywords": ["year zero"],
        "color": "#2fa094",
    },
    # --- Horror (Plum) ---
    {
        "tag": "CoC 7E",
        # Plain "coc" alone risks colliding with "cocoa" / "cocoon"; keep
        # the qualified forms.
        "keywords": ["call of cthulhu", "coc 7e", "coc 7th"],
        "color": "#b5739f",
    },
    # --- Cyberpunk (Woad) ---
    {
        "tag": "CP RED",
        "keywords": ["cyberpunk red", "cp red"],
        "color": "#5b90c7",
    },
    # --- Warhammer (Ember) ---
    {
        "tag": "WFRP 4E",
        "keywords": ["warhammer fantasy roleplay", "wfrp"],
        "color": "#bb7b4e",
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
        "color": "#bb7b4e",
    },
    # --- Schwalb (Plum — adjacent to horror in tone) ---
    {
        "tag": "SotDL",
        "keywords": ["shadow of the demon lord", "sotdl"],
        "color": "#b5739f",
    },
    {
        "tag": "SotWW",
        "keywords": ["shadow of the weird wizard", "sotww"],
        "color": "#b5739f",
    },
    # --- Generic / universal (Ember — the palette has no tan; Ember is the
    #     nearest hue and keeps already-crowded Gilt to the OSR family) ---
    {
        "tag": "SWADE",
        # "swade" is the common abbreviation for the current edition.
        "keywords": ["savage worlds", "swade"],
        "color": "#bb7b4e",
    },
    {
        "tag": "GURPS",
        "keywords": ["gurps"],
        "color": "#bb7b4e",
    },
    {
        "tag": "Fate",
        # Bare "fate" would match too much English prose; keep qualified.
        "keywords": ["fate core", "fate accelerated", "fate condensed", "fate rpg"],
        "color": "#bb7b4e",
    },
    # --- Old-school renaissance (Gilt) ---
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
        "color": "#9f8b3e",
    },
    {
        "tag": "SD",
        "keywords": ["shadowdark"],
        "color": "#9f8b3e",
    },
    {
        "tag": "LotFP",
        "keywords": ["lamentations of the flame princess", "lotfp"],
        "color": "#9f8b3e",
    },
    {
        "tag": "DCC",
        "keywords": ["dungeon crawl classics", "dcc rpg"],
        "color": "#9f8b3e",
    },
    {
        "tag": "C&C",
        # Normalization folds ``&`` to ``n``: ``c&c`` and ``cnc`` collapse
        # to the same needle.
        "keywords": ["castles & crusades", "c&c"],
        "color": "#9f8b3e",
    },
    {
        "tag": "Black Hack",
        "keywords": ["black hack"],
        "color": "#9f8b3e",
    },
    {
        "tag": "Cairn",
        "keywords": ["cairn"],
        "color": "#9f8b3e",
    },
]


# Derived lookup: tag → keywords (used by detect_game_system in server.py)
KNOWN_SYSTEMS: dict[str, list[str]] = {
    entry["tag"]: entry["keywords"] for entry in GAME_SYSTEMS
}
