# Breadcrumb QA — v2 — breadcrumb-qa

Date: 2026-09-09
Unit: every chunk the chunker emits; flaw = property of its section_heading

## By doc
```
doc               chunks         markup_rate   split_letter_rate     mixed_case_rate furniture_root_rate     no_heading_rate
----------------------------------------------------------------------------------------------------------------------------
bfrpg_4e            1195               0.000               0.000               0.000               0.003               0.001
black_hack_1e         94               0.000               0.011               0.000               0.000               0.011
cairn_1e             102               0.000               0.000               0.000               0.000               0.010
osric_2e            2706               0.000               0.042               0.000               0.984               0.000
srd_5_1             3244               0.000               0.041               0.000               0.000               0.000
srd_5_2_1           3455               0.000               0.276               0.000               0.000               0.000
yze_srd              369               0.000               0.014               0.000               0.005               0.003
all                11165               0.000               0.108               0.000               0.239               0.000
```

## Top roots per doc
- **bfrpg_4e** (1195 chunks): `PART 6: MONSTERS` ×563; `PART 3: SPELLS` ×169; `PART 8: GAME MASTER INFORMATION` ×142; `PART 7: TREASURE` ×115; `PART 2: PLAYER CHARACTERS` ×66
- **black_hack_1e** (94 chunks): `CONJURER` ×28; `EXAMPLE OF PLAY` ×11; `CONVERTING SAVES` ×6; `CLERIC` ×5; `ARMOR POINTS` ×3
- **cairn_1e** (102 chunks): `Rules` ×30; `100 Spells` ×10; `Rules Summary` ×10; `Character Traits (d10)` ×7; `Bestiary` ×6
- **srd_5_1** (3244 chunks): `Monsters` ×1002; `Spellcasting` ×651; `Paired Items` ×372; `Creatures` ×344; `Ability Scores and Modifiers` ×172
- **srd_5_2_1** (3455 chunks): `Monsters A–Z` ×894; `Casting Spells` ×525; `Classes` ×477; `Magic Item Categories` ×444; `Animals` ×294
- **osric_2e** (2706 chunks): `For Free Updates, Errata and Other OSRIc Support, VISIt:` ×2664; `I` ×29; `A` ×9; `final author and editor in chief: Stuart Marshall` ×2; `Old School Reference and Index Compilation` ×1
- **yze_srd** (369 chunks): `COMBAT & DAMAGE` ×105; `LEARNING MAGIC` ×91; `OTHER SKILLS` ×75; `PLAYER CHARACTERS` ×34; `TRAVEL MAPS` ×33


## Residue (most frequent flawed headings per doc)
- **bfrpg_4e**: furniture_root: `TABLE OF CONTENTS` ×3; no_heading: `` ×1
- **black_hack_1e**: split_letter: `WHAT’S THIS?` ×1; no_heading: `` ×1
- **cairn_1e**: no_heading: `` ×1
- **srd_5_1**: split_letter: `Appendix MM-B: Nonplayer Characters > Priest` ×5; split_letter: `Monsters > Will-­‐o’-­‐Wisp` ×4; split_letter: `Appendix MM-B: Nonplayer Characters > Archmage` ×4; split_letter: `Appendix MM-B: Nonplayer Characters > Acolyte` ×3; split_letter: `Appendix MM-B: Nonplayer Characters > Archmage > Actions` ×3; split_letter: `Appendix MM-B: Nonplayer Characters > Bandit Captain` ×3; split_letter: `Appendix MM-B: Nonplayer Characters > Berserker` ×3; split_letter: `Appendix MM-B: Nonplayer Characters > Commoner` ×3
- **srd_5_2_1**: split_letter: `Monsters A–Z > Young Gold Dragon > Actions` ×4; split_letter: `Monsters A–Z > Axe Beak` ×3; split_letter: `Monsters A–Z > Azer Sentinel` ×3; split_letter: `Monsters A–Z > Basilisk` ×3; split_letter: `Monsters A–Z > Behir` ×3; split_letter: `Monsters A–Z > Berserker` ×3; split_letter: `Monsters A–Z > Black Pudding` ×3; split_letter: `Monsters A–Z > Bugbear Stalker` ×3
- **osric_2e**: split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Adventure and Exploration > Don’t forget, monsters can hear the party in the same way as the party can hear them!` ×24; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > class d demon > (Nalfeshnee and others)` ×9; split_letter: `I > T > OSRIc Open license:` ×9; split_letter: `I > T > Open Game License Version 1.0a` ×7; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Jewellery Table > roll d% and d10` ×5; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Dungeons > features table (d%)` ×4; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > class c demon > (Glabrezu)` ×4; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Dungeons > attributes (d%)` ×3; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > MISCELLANEOUS MAGIC > Bag of Tricks Colour` ×126; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > CURSED ITEMS > Table of Common Item Curses` ×47; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > POTIONS > Potion Admixture Results Table` ×34; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Standard Hirelings > EXPERT HIRELINGS` ×30
- **yze_srd**: split_letter: `LEARNING MAGIC > NATURE’S CURE` ×1; split_letter: `LEARNING MAGIC > CAT’S PAW` ×1; split_letter: `LEARNING MAGIC > HAWK’S EYE` ×1; split_letter: `LEARNING MAGIC > BEAR’S CLAW` ×1; split_letter: `LEARNING MAGIC > DEER’S DASH` ×1; furniture_root: `CONTENTS` ×2; no_heading: `` ×1