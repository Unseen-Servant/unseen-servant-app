# Breadcrumb QA — v2 — breadcrumb-qa

Date: 2026-09-11
Unit: every chunk the chunker emits; flaw = property of its section_heading

## By doc
```
doc               chunks         markup_rate   split_letter_rate     mixed_case_rate furniture_root_rate     no_heading_rate
----------------------------------------------------------------------------------------------------------------------------
bfrpg_4e            1194               0.000               0.000               0.000               0.003               0.001
black_hack_1e         87               0.000               0.000               0.000               0.000               0.011
cairn_1e              92               0.000               0.000               0.000               0.000               0.011
osric_2e            2674               0.000               0.010               0.000               0.009               0.000
srd_5_1             3237               0.000               0.004               0.000               0.000               0.000
srd_5_2_1           3445               0.000               0.002               0.000               0.000               0.000
yze_srd              370               0.000               0.000               0.000               0.005               0.003
all                11099               0.000               0.004               0.000               0.003               0.000
```

## Top roots per doc
- **bfrpg_4e** (1194 chunks): `PART 6: MONSTERS` ×563; `PART 3: SPELLS` ×169; `PART 8: GAME MASTER INFORMATION` ×130; `PART 7: TREASURE` ×115; `PART 2: PLAYER CHARACTERS` ×66
- **black_hack_1e** (87 chunks): `CONJURER` ×23; `EXAMPLE OF PLAY` ×10; `CONVERTING SAVES` ×6; `CLERIC` ×5; `ARMOR POINTS` ×3
- **cairn_1e** (92 chunks): `Rules` ×30; `100 Spells` ×10; `Rules Summary` ×10; `Character Traits (d10)` ×7; `Bestiary` ×6
- **srd_5_1** (3237 chunks): `Monsters` ×1001; `Spellcasting` ×650; `Paired Items` ×367; `Creatures` ×344; `Ability Scores and Modifiers` ×172
- **srd_5_2_1** (3445 chunks): `Monsters A–Z` ×894; `Casting Spells` ×526; `Classes` ×477; `Magic Item Categories` ×438; `Animals` ×294
- **osric_2e** (2674 chunks): `Monsters` ×822; `CHAPTER II: Spells` ×610; `CHAPTER VI: TREASURE` ×445; `CHAPTER III: How To Play THE FIRST TIME` ×261; `CHAPTER I: Creating a Character` ×201
- **yze_srd** (370 chunks): `COMBAT & DAMAGE` ×106; `LEARNING MAGIC` ×91; `OTHER SKILLS` ×75; `PLAYER CHARACTERS` ×34; `TRAVEL MAPS` ×33


## Residue (most frequent flawed headings per doc)
- **bfrpg_4e**: furniture_root: `TABLE OF CONTENTS` ×3; no_heading: `` ×1
- **black_hack_1e**: no_heading: `` ×1
- **cairn_1e**: no_heading: `` ×1
- **srd_5_1**: split_letter: `Spellcasting > Find Steed > V, S > Instantaneous` ×2; split_letter: `Ability Scores and Modifiers > S ecial T es of Movement p yp` ×1; split_letter: `Ability Scores and Modifiers > Dro in to 0 Hit Points pp g` ×1; split_letter: `Spellcasting > Verbal (V)` ×1; split_letter: `Spellcasting > Somatic (S)` ×1; split_letter: `Spellcasting > Material (M)` ×1; split_letter: `Spellcasting > Chill Touch > V, S` ×1; split_letter: `Spellcasting > Chill Touch > V, S > 1 round` ×1
- **srd_5_2_1**: split_letter: `The Six Abilities > Dro in to 0 Hit Points pp g` ×1; split_letter: `Casting Spells > Verbal (V)` ×1; split_letter: `Casting Spells > Somatic (S)` ×1; split_letter: `Casting Spells > Material (M)` ×1; split_letter: `Casting Spells > Remove Curse > V, S` ×1; split_letter: `Gameplay Toolbox > Sli er Ice pp y` ×1; split_letter: `Monsters A–Z > Copper Dragons > Co er Dra on W rmlin pp g y g` ×1
- **osric_2e**: split_letter: `Monsters > class d demon > (Nalfeshnee and others)` ×9; split_letter: `Monsters > class c demon > (Glabrezu)` ×4; split_letter: `Monsters > class B demon > (Hezrou)` ×3; split_letter: `CHAPTER II: Spells > monster Summoning IV > (Monster Summoning V)` ×2; split_letter: `CHAPTER II: Spells > Blindness > components: V,S,M casting time: 5 segments Saving throw: See below` ×2; split_letter: `CHAPTER II: Spells > Speak with plants > components: V,S,M casting time: 1 turn Saving throw: None` ×1; split_letter: `CHAPTER II: Spells > turn Wood > components: V,S,M casting time: 8 segments Saving throw: None` ×1; split_letter: `CHAPTER II: Spells > crushing hand > components: V,S,M casting time: 9 segments Saving throw: None` ×1; furniture_root: `CONTENTS` ×7; furniture_root: `CONTENTS > LIST OF SPELLS` ×7; furniture_root: `CONTENTS > LIST OF MAGIC ITEMS` ×5; furniture_root: `CONTENTS > LIST OF MONSTERS` ×4
- **yze_srd**: furniture_root: `CONTENTS` ×2; no_heading: `` ×1