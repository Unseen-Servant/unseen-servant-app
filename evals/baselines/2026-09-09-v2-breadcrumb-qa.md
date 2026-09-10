# Breadcrumb QA — v2 — breadcrumb-qa

Date: 2026-09-09
Unit: every chunk the chunker emits; flaw = property of its section_heading

## By doc
```
doc               chunks         markup_rate   split_letter_rate     mixed_case_rate furniture_root_rate     no_heading_rate
----------------------------------------------------------------------------------------------------------------------------
bfrpg_4e            1195               0.000               0.000               0.000               0.003               0.001
black_hack_1e         94               0.000               0.000               0.000               0.000               0.011
cairn_1e             102               0.000               0.000               0.000               0.000               0.010
osric_2e            2706               0.000               0.025               0.000               0.984               0.000
srd_5_1             3244               0.000               0.003               0.000               0.000               0.000
srd_5_2_1           3455               0.000               0.002               0.000               0.000               0.000
yze_srd              369               0.000               0.000               0.000               0.005               0.003
all                11165               0.000               0.008               0.000               0.239               0.000
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
- **black_hack_1e**: no_heading: `` ×1
- **cairn_1e**: no_heading: `` ×1
- **srd_5_1**: split_letter: `Spellcasting > Range: 120 feet Components: V, S, M (a small block of granite) Duration: Concentration, up to 10 minutes` ×2; split_letter: `Ability Scores and Modifiers > S ecial T es of Movement p yp` ×1; split_letter: `Ability Scores and Modifiers > Dro in to 0 Hit Points pp g` ×1; split_letter: `Spellcasting > Verbal (V)` ×1; split_letter: `Spellcasting > Somatic (S)` ×1; split_letter: `Spellcasting > Material (M)` ×1; split_letter: `Spellcasting > Branding Smite > V` ×1; split_letter: `Spellcasting > Hunter’s Mark > V` ×1
- **srd_5_2_1**: split_letter: `The Six Abilities > Dro in to 0 Hit Points pp g` ×1; split_letter: `Casting Spells > Verbal (V)` ×1; split_letter: `Casting Spells > Somatic (S)` ×1; split_letter: `Casting Spells > Material (M)` ×1; split_letter: `Gameplay Toolbox > Sli er Ice pp y` ×1; split_letter: `Monsters A–Z > Copper Dragons > Co er Dra on W rmlin pp g y g` ×1
- **osric_2e**: split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > class d demon > (Nalfeshnee and others)` ×9; split_letter: `I > T > OSRIc Open license:` ×9; split_letter: `I > T > Open Game License Version 1.0a` ×7; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > class c demon > (Glabrezu)` ×4; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > class B demon > (Hezrou)` ×3; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > monster Summoning IV > (Monster Summoning V)` ×2; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Shocking Grasp > area of effect: See below components: V,S,M casting time: 1 segment Saving throw: None` ×2; split_letter: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Blindness > components: V,S,M casting time: 5 segments Saving throw: See below` ×2; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > MISCELLANEOUS MAGIC > Bag of Tricks Colour` ×126; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > CURSED ITEMS > Table of Common Item Curses` ×47; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > POTIONS > Potion Admixture Results Table` ×34; furniture_root: `For Free Updates, Errata and Other OSRIc Support, VISIt: > Standard Hirelings > EXPERT HIRELINGS` ×30
- **yze_srd**: furniture_root: `CONTENTS` ×2; no_heading: `` ×1