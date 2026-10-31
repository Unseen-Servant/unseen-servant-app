# Augury (2026-10-30)

**Status:** settled 2026-10-30 (§11). Step 1 built 2026-10-30; steps 2–4 to come.

## 0. TL;DR

Augury is the workstation's dice roller, a fourth tool in the rack beside Legend Lore and Command. It is small on purpose: a narrow column that fits beside both at 1280 px. It looks like a MIDI pad controller. A display names a dice set, ◀ ▶ browse the sets, and `[load]` puts the set on a 4×4 pad matrix. Pressing a pad adds its die to a formula in `xdy` notation, which the GM can also type; right-clicking takes one away. A ±1 pad in the corner moves the formula's number, and advantage or disadvantage rolls the formula twice and keeps the higher or lower total. A big seven-segment readout shows the total, with a level meter and each die's value under it. Dice sets: Standard, Zocchi (the 14 dice of DCC's chain), Oracle (dice with words on their faces) and the GM's own.

---

## 1. Why

- **A GM rolls all session**, often for the table rather than a player, and a dice app on a phone or a website sits outside the workstation.
- **Games use odd dice:** DCC's d3–d30 chain, Daggerheart's two d12s of different colours, oracles that answer Yes/No or roll the weather. A roller that knows only the seven standard dice leaves those on paper.
- **Improvisation needs answers fast:** "is the guard awake?", "what's the weather?", "how does the merchant feel?". An Oracle die is one press.

## 2. Rules

1. **Small in both directions.** Augury's minimum is 270×360, and it opens at that size: mounted from the rack bar it takes a column of its minimum width, and its own window opens at its minimum. At 1280 px, Legend Lore (560) and Command (420) leave about 280 px beside them.
2. **The app's instrument panel, not a casino.** Keys in wells, lamps, readouts and the pigment palette. No dice art, no 3D dice, no sound.
3. **Augury reads no game's rules.** It shows each die and the total. It does not say "with Hope" or call a critical; colours make the dice easy to tell apart, and the GM reads them.
4. **Everything the GM builds is theirs.** Dice sets are plain JSON in the settings store, per machine.

---

## 3. The panel

```
┌──────────────────────────────────────────┐
│ ◀ ▪ Zocchi        ▶  [load]          ⧉   │  header bar: set browser, window key
├──────────────────────────────────────────┤
│ ┌──────────────────────────────────────┐ │
│ │    _   _                         ▯   │ │  readout: seven-segment total
│ │    _| | |                        ▮   │ │  level meter, filling upward
│ │   |_  |_|                        ▮   │ │
│ │   ▕7▏ ▕11▏  +2                       │ │  each die in a window, then numbers
│ └──────────────────────────────────────┘ │
│ ┌──────────────────┐ ┌───┬───┐ ┌──┬──┐  │
│ │ 1d12+1d12+2      │ │adv│dis│ │✕ │▶ │  │  formula field; latches; clear, roll
│ └──────────────────┘ └───┴───┘ └──┴──┘  │
│ ┌────────┬────────┬────────┬────────┐    │
│ │   d3   │   d4   │   d5   │   d6   │    │  4×4 pad matrix
│ ├────────┼────────┼────────┼────────┤    │
│ │   d7   │   d8   │  d10   │  d12   │    │
│ ├────────┼────────┼────────┼────────┤    │
│ │  d14   │  d16   │  d20   │  d24   │    │
│ ├────────┼────────┼────────┼────────┤    │
│ │  d30   │  d100  │        │   +2   │    │  the ±1 pad, in every number set
│ └────────┴────────┴────────┴────────┘    │
└──────────────────────────────────────────┘
```

- **The head** is the tool's header bar, as Legend Lore's and Command's are: 40 px on `--bg-header`, with the window key at the right end. The rack bar names the tool, so the panel doesn't. The set browser sits in it, where a pad controller has its program display.
- **The formula row** has the field, the advantage and disadvantage latches, then clear (✕) and roll (▶). None of them moves when the dice set changes. The field shows about 13 characters and scrolls past them.
- **The matrix** is 4×4 and always all there. A pad with no die is dark. The bottom-right pad of every number set is the ±1 pad, so a set holds up to 15 dice.

## 4. The formula

- **Notation:** terms joined by `+` or `-`. A term is `NdY` (N dice of size Y), `dY` (one die) or a whole number. Spaces don't matter, and `D` reads as `d`. `3d6+1d20-2`, `d8 + d8`.
- **Limits:** at most 100 dice in all, sizes 2–1000, numbers up to 999. The field refuses anything else with the refused ring (`--ring-refused`) and keeps the last roll on the readout.
- **A word die** (§7) is its own formula: the die's name, alone, such as `Weather`. Words and numbers don't mix.
- **The field and the pads agree.** A pad press rewrites the field; text typed in the field lights the pads it names. A pad's label reads its term once loaded: `d6` at rest, `3d6` after three presses.
- **A press adds to its pad's term.** Pressing d6 three times gives `3d6`, never `1d6+1d6+1d6`. Two pads with the same die are two terms (§8).
- **A right-click takes one away.** `3d6` becomes `2d6`, and past zero the die is subtracted: `1d12+1d12-1d6`, Daggerheart's disadvantage. A press and a right-click undo each other, and the pad reads its count with its sign: `-1d6`.
- **The ±1 pad** follows the pad rule: a press adds 1 to the formula's last number (`1d20` → `1d20+1`), a right-click takes 1 away, and the number drops at zero. It reads the formula's numbers summed (`+3`, `-2`), and `+1` at rest. After a roll it keeps the dice on the readout and moves its total, so a forgotten bonus needs no reroll: the one pad that never starts a new formula, since no roll starts with a bonus. It sits in the same corner of every number set, so the hand finds it without looking; a set the GM builds can't move it.
- **Advantage and disadvantage** are latches on the formula: the roll is made twice, and the higher total (advantage) or the lower (disadvantage) is kept. For `1d20+5` that is D&D's rule; for any other formula it is the same rule on the whole total. Not written in the field: the latch's purple lamp shows it.
- **After a roll** the formula stays, so roll again is the reroll. The first die pad pressed after a roll starts a new formula, as a calculator's first key after `=` does, and releases the latch. A right-click, the ±1 pad and the latches change the formula there. Clear empties the field and the readout and releases the latch.
- **Rolling** uses `crypto.getRandomValues` with rejection sampling, so no face is more likely than another.

## 5. The readout

- **The total** is drawn in seven-segment digits as SVG: each segment is a lamp, parchment (`--text-accent`) when lit and a dark slot when off. Not a font: the app has no display fonts. Three digit cells at rest, showing `888` unlit; a longer total adds cells, and a negative one lights the minus segment of the cell before it.
- **The level meter** is a column of ten LED cells at the readout's right edge, as tall as the digits so the breakdown runs the full width under both, filling from the bottom: where the total fell between the formula's least and greatest possible results. 15 on `3d6+3` lights six. A formula with one possible result lights all ten.
- **The breakdown** under the digits shows each die's face in its own small window, like the windows of a mechanical counter, in roll order; a gap sets the terms apart, and numbers stay bare: `▕3▏▕5▏▕4▏  ▕6▏  +2`. The windows need no separator glyph (a middle dot was tried and dropped). In Crimson tabular figures at a readable size, not a micro label, because Hope against Fear is read there. Under advantage or disadvantage the dropped roll's dice follow, at the app's out-of-scope dim. One line, so the pads never move: a long one ends in an ellipsis, and its tooltip holds the rest.
- **A word result** (§7) prints in the well in Crimson at the readout's height, parchment, and wraps to two lines at a smaller size if it must. The digits, meter and breakdown go dark.
- **The moment of the roll** is the app's detent: one bright frame on the new value. No glow at rest; glows mark states the user switched on. No colour for a high or low roll: red means removal here.

## 6. Dice sets

- **The browser:** ◀ and ▶ step through the sets and wrap at the ends. They change only the display; the pads keep the loaded set until `[load]`. A lamp left of the name (the rack's 6 px square cell) is lit while the set on display is the one on the pads. Browse away and it goes dark and `[load]` comes alive.
- **Loading keeps the formula**, so `1d20` from Standard and `1d7` from a custom set roll together.
- **Standard:** d4 d6 d8 d10 / d12 d20 d100, the seven-die set. Fixed.
- **Zocchi:** the 14 dice of DCC's chain in order, row by row: d3 d4 d5 d6 / d7 d8 d10 d12 / d14 d16 d20 d24 / d30 d100. Stepping up or down the chain is the next or previous pad. Fixed.
- **Oracle:** word dice (§7). Ships with four; the GM edits them. Its corner pad is dark: words take no numbers.
- **Custom sets:** `+ new set`, the last entry in the browser, makes *Custom 1*, *Custom 2*… Double-click the name in the display to rename it. A custom set holds up to 15 number dice of any size (a d25) and word dice side by side, with the ±1 pad in its corner.
- **Pads are placed, not sorted.** In a set the GM can edit, hovering an empty pad shows a dashed `+` (the app's "not yet real" idiom); clicking it opens a field there for a size (`25`) or a word die's name. Changing or clearing a pad, and its pigment (§8), can't hang off a right-click (it subtracts) or a double-click (its first click adds a die), so they come from an edit latch, as a pad controller's edit mode; settled with step 3.
- **The last loaded set** is remembered.

## 7. Oracle and word dice

- **A word die** has faces that are words or short phrases. Each face is equally likely; writing a face twice doubles its chance, so there's no weighting control.
- **A word pad rolls at once.** Two Weather dice mean nothing, so there is nothing to stack: one press, one answer. The field shows the die's name, so roll (▶, Enter) asks again.
- **Starters** (messages in `en.json`, so they translate until the GM edits them):
  - **Yes/No:** Yes, and… / Yes / Yes, but… / No, but… / No / No, and…
  - **Weather:** Clear, Overcast, Wind, Rain, Fog, Storm
  - **Mood:** Calm, Curious, Joyful, Proud, Wary, Afraid, Angry, Sad
  - **Direction:** N, NE, E, SE, S, SW, W, NW
- **Editing faces:** under the edit latch (§6), a word pad's faces open in the readout well as an editable list, one face per line. Esc or a click outside keeps the edit.

## 8. Pigments: the same die twice

- **Several pads may hold the same die**, such as two d12s for Daggerheart's Hope and Fear. Pressing one then the other gives `1d12+1d12`, never `2d12`.
- **The palette** is the app's pigments (`src/lib/legend-lore/palette.ts`), which Legend Lore's collections and Command's tracks already use. It keeps clear of the interface's own colours (danger red, lamp amber, parchment, mode purple) and is checked for colour-blind pairs.
- **Choosing one:** the *Pigment* pick row Command's tracks use (`.menu-picks`), with *None*, in the pad's menu under the edit latch (§6). Only sets the GM can edit take pigments.
- **The colour follows the die.** At rest, a pigmented pad shows its pigment on its edge. Loaded, its label and lamp take the pigment where a plain pad's take parchment. Its term in the field is tinted, and its windows in the breakdown take the pigment on their edge, as the pad does. The total stays parchment: it belongs to no one pad. Terms typed by hand stay plain.

## 9. Keys and storage

- **Enter** rolls and **Esc** clears, from anywhere in Augury while it has the keyboard. With an empty formula, Esc steps down the app's Esc ladder.
- **Right-click** on a pad takes a die away (§4).
- **Bare 1–8 stay the rack's.** The field doesn't take the caret when Augury takes the keyboard; click it to type.
- **The settings store** keeps `augurySet` (the loaded set) and `augurySets` (the Oracle's edits and the custom sets), per machine.

## 10. Order of work

1. **The panel and number dice.** Augury in the rack and as a pop-out (`panels.ts`, `panels.rs`, `PanelView`), on the first launch's view 2 beside Command, opening at its minimum. Formula parsing and rolling, with tests. Readout, level meter and breakdown. Field, clear and roll keys, Enter and Esc. The matrix, Standard and Zocchi, the browser and `[load]`, the remembered set. Right-click, ±1, advantage and disadvantage.
2. **Oracle.** Word dice, the word readout, the starters, editing faces.
3. **Custom sets and pigments.** `+ new set`, renaming, the edit latch, placing and clearing pads, the pad menu, pigments in the pads, field and breakdown.
4. **Help and keys.** Help → Guides → Augury, the shortcut sheet, CHANGELOG.

## 11. Settled (2026-10-30)

- The name: Augury, after the divination spell, as the other tools are named after spells.
- Seven-segment lamps for the total, with a level meter and the breakdown kept.
- Calculator semantics: the formula stays after a roll; the first press after it starts a new one.
- Dice sets on a MIDI-style browser with `[load]`, not a row of bank keys, so the GM can keep any number of sets.
- A 4×4 matrix. Zocchi is the full 14-dice chain.
- Word pads roll at once.
- Pads of the same die told apart by pigment, shown as an edge on the pad.
- Augury opens at its minimum size (user, 2026-10-30).
- A right-click on a pad subtracts that die; ±1; advantage and disadvantage (user, 2026-10-30).
- ±1 is a pad, fixed in the corner of every number set, and the latches share the formula row, so the panel has no control row (2026-10-30).

## 12. Not doing, or not yet

- A roll history.
- Keep-highest on part of a formula (`4d6kh3`) and exploding dice.
- Game rules: Hope against Fear, criticals, success counting.
- Colours for high or low rolls.
- Sending a roll to Command's session log.
- Dice sets per campaign.
- Odds for Yes/No (likely, unlikely).
- An MCP tool for rolling.
