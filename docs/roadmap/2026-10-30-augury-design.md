# Augury (2026-10-30)

**Status:** settled 2026-10-30 (§11). Steps 1–3 built 2026-10-30; step 4 to come.

## 0. TL;DR

Augury is the workstation's dice roller, a fourth tool in the rack beside Legend Lore and Command. It is small on purpose: a narrow column that fits beside both at 1280 px. It looks like a MIDI pad controller. A display names a dice set, ◀ ▶ browse the sets, and load (⏎) puts the set on a 4×4 pad matrix. Pressing a pad adds its die to a formula in `xdy` notation, which the GM can also type; right-clicking takes one away. A ±1 pad in the corner moves the formula's number, and advantage or disadvantage rolls the formula twice and keeps the higher or lower total. A big seven-segment readout shows the total, with a level meter and each die's value under it. Dice sets: Standard, Zocchi (the 14 dice of DCC's chain), Oracle (dice with words on their faces), Tracks (a note drawn at random from each of Command's tracks) and the GM's own.

---

## 1. Why

- **A GM rolls all session**, often for the table rather than a player, and a dice app on a phone or a website sits outside the workstation.
- **Games use odd dice:** DCC's d3–d30 chain, Daggerheart's two d12s of different colours, oracles that answer Yes/No or roll the weather. A roller that knows only the seven standard dice leaves those on paper.
- **Improvisation needs answers fast:** "is the guard awake?", "what's the weather?", "how does the merchant feel?". An Oracle die is one press.

## 2. Rules

1. **Small in both directions.** Augury's minimum is 270×356, and it opens at that size: mounted from the rack bar it takes a column of its minimum width, its box in the rack stops at its minimum height with bare rack below (a short unit in a tall bay; a tool carried onto that bare rack goes beneath it), and its own window opens at its minimum. At 1280 px, Legend Lore (560) and Command (420) leave about 280 px beside them.
2. **The app's instrument panel, not a casino.** Keys in wells, lamps, readouts and the pigment palette. No dice art, no 3D dice, no sound.
3. **Augury reads no game's rules.** It shows each die and the total. It does not say "with Hope" or call a critical; colours make the dice easy to tell apart, and the GM reads them.
4. **Everything the GM builds is theirs.** Dice sets are plain JSON in the settings store, per machine.

---

## 3. The panel

```
┌──────────────────────────────────────────┐
│ ◀ ▪ Zocchi        ▶ ⏎ ✎              ⧉   │  header bar: set strip (browse, load, edit), window key
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
- **A word result** (§7) prints in the well in IBM Plex Mono (`--font-readout`, the site's mono, bundled), parchment, and wraps to two lines at a smaller size past sixteen characters. The digits, meter and breakdown go dark.
- **The moment of the roll** is the app's detent: one bright frame on the new value. No glow at rest; glows mark states the user switched on. No colour for a high or low roll: red means removal here.

## 6. Dice sets

- **The set strip:** one well of keys, as a pad controller's program section, each with one job: ◀ and ▶ step through the sets and wrap at the ends; the display names the set; ⏎ (Font Awesome's arrow-right-to-bracket) loads it; ✎ edits it. A faint rule parts browsing from the keys that act on what's browsed. ◀ ▶ change only the display; the pads keep the loaded set until ⏎, which is dimmed while the display shows the loaded set. A lamp left of the name (the rack's 6 px square cell) is lit while the set on display is the one on the pads. ✎ is the loaded set's, dimmed unless it's one of the GM's. Nothing in the strip moves between play and edit mode. Load and edit carry lamps under their glyphs: load's lit parchment while the display shows a set waiting to load, edit's purple while editing; the arrows and the name, with none, sit centred. (Bracket keys came first: `[load]`, then `[edit]` turning into `[done]` with `[delete]` beside it, which took the width and read nothing like hardware.)
- **Loading keeps the formula**, so `1d20` from Standard and `1d7` from a custom set roll together.
- **Standard:** d4 d6 d8 d10 / d12 d20 d100, the seven-die set. Fixed.
- **Zocchi:** the 14 dice of DCC's chain in order, row by row: d3 d4 d5 d6 / d7 d8 d10 d12 / d14 d16 d20 d24 / d30 d100. Stepping up or down the chain is the next or previous pad. Fixed.
- **Oracle:** four word dice (§7). Fixed, as Standard and Zocchi are: its dice are particular, made-for-purpose keys, not a starting point (user, 2026-10-30). The GM's own word dice go in a custom set. Its corner pad is dark: words take no numbers.
- **Tracks:** a pad for each track of the campaign open in Command, in Command's order and pigment, the first fifteen. A track is a word die whose faces are its unspent notes and images: a press draws one, and its name prints on the readout in the track's pigment; roll again draws again. A spent note is used up, so a draw never lands on one, and a track with none left can't be pressed. With no campaign open the pads are dark and the display's tooltip says why. Fixed: the tracks are Command's to change. Augury reads them through Rust (`command_draw_tracks`), the way Legend Lore's Send to Command crosses between the tools, and again whenever the campaign or its folder changes (`command://vault`).
- **Custom sets:** *New set* is the entry past the last set, and ⏎ on it makes *Custom 1*, *Custom 2*… (the first number free), loads it and opens it for editing with its name's field open. In edit mode a custom set's name is clicked to rename it (no two sets share a name), and a ✕ at its end, red under the pointer, deletes it after a confirmation: the ✕ every pad shows in edit mode, so whatever edit mode can remove shows one. (A right-click menu on the display did this first and was dropped the same day: nobody finds a right-click, and `+ new set` → `[new]` → *Custom 1* read as three names for one thing.) A custom set holds up to 15 number dice of any size (a d25) and word dice side by side, with the ±1 pad in its corner. The ids are `custom-<time>`.
- **Edit mode.** In play a click adds a die and a right-click takes one away, and a double-click's first click would add one, so editing is a mode, as on a pad controller: ✎ turns the loaded set's pads into fields, lighting its lamp purple (a mode switched on), and ✎ again (or Esc) turns them back. Meanwhile ◀ ▶ and ⏎ dim and go inert, as Command dims its Prep keys in Play: browsing or loading would end editing. Empty pads show dashed with a `+` (the app's "not yet real" edge), and the ±1 pad rests.
- **Pads are placed, not sorted.** In edit mode a click opens the pad's field in place: `25` or `d25` makes a die of that size (2–1000), any other words name a word die, and a lone `d` (a die begun) and a formula are refused (a formula would roll as dice, never as that die). A word die renamed keeps its faces, and any pad its pigment. A filled pad shows a small ✕ in its corner, red under the pointer, which clears it; emptying its field does too. A right-click opens the pad's menu: *Pigment* (§8) and *Edit faces* for a word die. (*Clear pad* sat in that menu first; behind a right-click it went unfound.)
- **The last loaded set** is remembered.

## 7. Oracle and word dice

- **A word die** has faces that are words or short phrases. Each face is equally likely; writing a face twice doubles its chance, so there's no weighting control.
- **A word pad rolls at once.** Two Weather dice mean nothing, so there is nothing to stack: one press, one answer. The field shows the die's name, so roll (▶, Enter) asks again, and a word die's name typed alone rolls that die of the loaded set. While one is in the field the latches and the ±1 pad rest, and a die pad starts a new formula. A word die with no faces yet can't be pressed.
- **Oracle's dice** (messages in `en.json`, so they translate):
  - **Yes/No:** a d12 weighted toward yes, so the table hears yes more than no: Yes, and… ×1, Yes ×3, Yes, but… ×3, No, but… ×2, No ×2, No, and… ×1. *And* amplifies the answer; *but* adds a twist the other way.
  - **Weather:** Clear, Overcast, Wind, Rain, Fog, Storm
  - **Mood:** Calm, Curious, Joyful, Proud, Wary, Afraid, Angry, Sad
  - **Direction:** N, NE, E, SE, S, SW, W, NW
- **Editing faces:** in edit mode (§6), a custom set's word pad's faces open in the readout's well as an editable list, one face per line, from *Edit faces*, and at once for a word die just named. The pad is ringed while its faces are open. Esc, a click away or leaving edit mode keeps the edit. A word die closed with no faces goes back to an empty pad, so the matrix never holds a pad that does nothing.

## 8. Pigments: the same die twice

- **Several pads may hold the same die**, such as two d12s for Daggerheart's Hope and Fear. Pressing one then the other gives `1d12+1d12`, never `2d12`.
- **The palette** is the app's pigments (`src/lib/legend-lore/palette.ts`), which Legend Lore's collections and Command's tracks already use. It keeps clear of the interface's own colours (danger red, lamp amber, parchment, mode purple) and is checked for colour-blind pairs.
- **Choosing one:** the *Pigment* pick row Command's tracks use (`.menu-picks`), with *None*, in the pad's menu in edit mode (§6). Only sets the GM can edit take pigments.
- **A term carries its pad's pigment**, so two pads of the same die stay two terms, each counted on its own pad. The field's text doesn't show it; typing keeps each pigment on the term at the same place among the dice terms while it is the same die and sign, and a term typed new is plain.
- **The colour follows the die.** At rest, a pigmented pad shows its pigment on its edge. Loaded, its label and lamp take the pigment where a plain pad's take parchment, and a word die's face prints in it. Its windows in the breakdown take the pigment on their edge, as the pad does. Tinting its term in the field is not yet built: a text field can't colour part of its text without a drawn layer under it. The total stays parchment: it belongs to no one pad. Terms typed by hand stay plain.

## 9. Keys and storage

- **Enter** rolls and **Esc** clears, from anywhere in Augury while it has the keyboard. With an empty formula, Esc steps down the app's Esc ladder.
- **Right-click** on a pad takes a die away (§4).
- **Bare 1–8 stay the rack's.** The field doesn't take the caret when Augury takes the keyboard; click it to type.
- **The settings store** keeps `augurySet` (the loaded set) and `augurySets` (the custom sets), per machine.

## 10. Order of work

1. **The panel and number dice.** Augury in the rack and as a pop-out (`panels.ts`, `panels.rs`, `PanelView`), on the first launch's view 2 beside Command, opening at its minimum. Formula parsing and rolling, with tests. Readout, level meter and breakdown. Field, clear and roll keys, Enter and Esc. The matrix, Standard and Zocchi, the browser and its load key, the remembered set. Right-click, ±1, advantage and disadvantage.
2. **Oracle.** Word dice, the word readout, Oracle's four dice, editing a word die's faces.
3. **Custom sets and pigments.** `+ new set`, renaming and deleting, edit mode, placing and clearing pads, the pad menu, pigments in the pads and the breakdown. Then the Tracks set.
4. **Help and keys.** Help → Guides → Augury, the shortcut sheet, CHANGELOG.

## 11. Settled (2026-10-30)

- The name: Augury, after the divination spell, as the other tools are named after spells.
- Seven-segment lamps for the total, with a level meter and the breakdown kept.
- Calculator semantics: the formula stays after a roll; the first press after it starts a new one.
- Dice sets on a MIDI-style browser with a load key, not a row of bank keys, so the GM can keep any number of sets. Its keys are one strip of glyph keys with fixed jobs (user, 2026-10-30).
- A 4×4 matrix. Zocchi is the full 14-dice chain.
- Word pads roll at once.
- Pads of the same die told apart by pigment, shown as an edge on the pad.
- Oracle is fixed; only the GM's own sets are edited (user, 2026-10-30).
- A Tracks set draws a note from each of Command's tracks (user, 2026-10-30).
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
- Opening a drawn note in Command.
- A pigment tint on the field's terms (§8).
