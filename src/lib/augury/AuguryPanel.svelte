<script lang="ts">
  // Augury, the dice roller (docs/roadmap/2026-10-30-augury-design.md). The
  // loaded dice set's pads feed a formula in xdy notation, which the GM can
  // also type, and a roll lands on the readout. After a roll the formula
  // stays, so rolling again is the reroll; the first die pad pressed after
  // it starts a new formula, as a calculator's first key after = does. A
  // right-click takes from the formula there. A macro's pad adds its whole
  // formula, as its dice's pads would. The ±1 pad in the corner moves its
  // number, and after a roll the total without new dice: the one pad that
  // never starts a new formula, since no roll starts with a bonus. A word
  // die's pad rolls at once, and its name stands in the field. Tracks makes
  // each track of the campaign open in Command such a die, its faces the
  // track's unspent notes. A roll that leaves the readout goes onto the tape
  // under the pads, which rises over them, inside the panel's box.
  //
  // The GM's own sets are edited in place (§6): edit (✎) turns the pads into
  // fields, a click opens one's entry across its row (room for a macro's
  // formula) and a right-click opens its menu, since in
  // play those gestures add and take away dice. The header's strip keeps
  // its keys where they are: edit's lamp lights, the keys that would end
  // editing dim, the set's name is clicked to rename it, and a ✕ at its end
  // deletes it, as each pad's ✕ clears the pad.
  import { onMount, onDestroy, type Snippet } from 'svelte';
  import { load } from '@tauri-apps/plugin-store';
  import CommandMenu from '../command/CommandMenu.svelte';
  import { action, picks, type OpenMenu } from '../command/menu';
  import { PIGMENTS } from '../legend-lore/palette';
  import { m } from '../paraglide/messages';
  import { confirmPrompt } from '../shell/confirmStore';
  import { focusPath } from '../shell/focus';
  import { chordHint } from '../shell/keybindings';
  import { bindKeys } from '../shell/keys';
  import { appContext } from '../shell/shellState';
  import { parseString } from '../shell/storeParsers';
  import { CARET_RIGHT, PLAY } from '../ui/iconPaths';
  import RenameField from '../ui/RenameField.svelte';
  import FacesEditor from './FacesEditor.svelte';
  import Readout from './Readout.svelte';
  import Tape from './Tape.svelte';
  import { print, type TapeLine } from './tape';
  import { drawTracks, onVaultChange, type DrawTrack } from './tracks';
  import {
    addTerms,
    bump,
    diceOf,
    formatFormula,
    holds,
    numberOf,
    parseFormula,
    pickFace,
    reattach,
    refigure,
    rollOutcome,
    stepDie,
    type Edge,
    type Outcome,
    type Term,
  } from './dice';
  import {
    allSets,
    newSet,
    padEntry,
    padFromEntry,
    padLabel,
    parseSets,
    TRACKS,
    type MacroPad,
    type Pad,
    type StoredSets,
    type WordPad,
  } from './sets';

  export let windowKey: Snippet | undefined = undefined;

  // Font Awesome "arrow-right-to-bracket" (src/lib/ui/icons/arrow-right-to-bracket-solid-full.svg):
  // load, the set on the display going onto the pads.
  const LOAD =
    'M416 160L480 160C497.7 160 512 174.3 512 192L512 448C512 465.7 497.7 480 480 480L416 480C398.3 480 384 494.3 384 512C384 529.7 398.3 544 416 544L480 544C533 544 576 501 576 448L576 192C576 139 533 96 480 96L416 96C398.3 96 384 110.3 384 128C384 145.7 398.3 160 416 160zM406.6 342.6C419.1 330.1 419.1 309.8 406.6 297.3L278.6 169.3C266.1 156.8 245.8 156.8 233.3 169.3C220.8 181.8 220.8 202.1 233.3 214.6L306.7 288L96 288C78.3 288 64 302.3 64 320C64 337.7 78.3 352 96 352L306.7 352L233.3 425.4C220.8 437.9 220.8 458.2 233.3 470.7C245.8 483.2 266.1 483.2 278.6 470.7L406.6 342.7z';
  // Font Awesome "pen-to-square" (src/lib/ui/icons/pen-to-square-solid-full.svg)
  const PEN =
    'M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z';
  // Font Awesome "xmark" (src/lib/ui/icons/xmark-solid-full.svg)
  const XMARK =
    'M183.1 137.4C170.6 124.9 150.3 124.9 137.8 137.4C125.3 149.9 125.3 170.2 137.8 182.7L275.2 320L137.9 457.4C125.4 469.9 125.4 490.2 137.9 502.7C150.4 515.2 170.7 515.2 183.2 502.7L320.5 365.3L457.9 502.6C470.4 515.1 490.7 515.1 503.2 502.6C515.7 490.1 515.7 469.8 503.2 457.3L365.8 320L503.1 182.6C515.6 170.1 515.6 149.8 503.1 137.3C490.6 124.8 470.3 124.8 457.8 137.3L320.5 274.7L183.1 137.4z';
  // The browser's last entry, past the sets: loading it makes a new set of
  // the GM's, empty, and opens it for editing.
  const NEW = 'new';

  let text = '';
  // The field's terms, null while it doesn't read as dice.
  let terms: Term[] | null = [];
  // A word die in the field instead of dice.
  let word: WordPad | null = null;
  let refused = false;
  let outcome: Outcome | null = null;
  let answer: { face: string; pigment?: string } | null = null;
  // Advantage or disadvantage, part of the formula: it stays for a reroll
  // and goes with a new formula.
  let edge: Edge | null = null;
  let seq = 0;
  // The field holds the formula on the readout, so the next press starts anew.
  let rolled = false;
  // How the readout's roll was made, to print it as it was once the edge or
  // the field has moved on.
  let rolledAs: { edge: Edge | null; die: WordPad | null } = { edge: null, die: null };
  let tape: TapeLine[] = [];
  let printed = 0;
  let tapeOpen = false;

  let stored: StoredSets = { custom: [] };
  // The campaign open in Command and its tracks, for the Tracks set.
  let campaign: string | null = null;
  let open: DrawTrack[] = [];
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  let unlistenVault: Promise<() => void> | undefined;
  // The set on the pads, and the one on the display: ◀ ▶ move only the
  // display, and [load] brings its set onto the pads.
  let loadedId = 'standard';
  let browsedId = 'standard';
  let editing = false;
  // While editing: the pad whose field is open, and the word die whose faces
  // are in the readout's well.
  let entry: number | null = null;
  let facesOf: number | null = null;
  let renaming = false;
  let menu: OpenMenu | null = null;

  $: sets = allSets(stored, open);
  // Tracks follows Command: read again when the campaign changes or its
  // folder does.
  $: $appContext.campaign, refreshTracks();
  $: set = sets.find((s) => s.id === loadedId) ?? sets[0];
  $: browsed = sets.find((s) => s.id === browsedId) ?? null;
  $: browsedName = browsed ? browsed.name() : m.augury_new_set();
  $: displayTitle =
    browsedId === TRACKS && !campaign
      ? m.augury_tracks_none()
      : browsedId === set.id
        ? m.augury_set_on_pads({ set: browsedName })
        : browsed
          ? m.augury_set_off_pads({ set: browsedName })
          : m.augury_new_title();
  $: bonus = numberOf(terms ?? []);
  $: facesPad = facesOf === null ? null : set.pads[facesOf];
  // Load takes the set on the display onto the pads (New set makes one
  // first); edit is the loaded set's, when it's one of the GM's.
  $: canLoad = !editing && browsedId !== set.id;
  $: canEdit = editing || (browsedId === set.id && set.editable);

  // The readout's roll onto the tape, as it leaves the readout.
  function retire() {
    if (outcome) tape = print(tape, { id: ++printed, kind: 'dice', edge: rolledAs.edge, outcome });
    else if (answer && rolledAs.die) tape = print(tape, { id: ++printed, kind: 'word', die: rolledAs.die, face: answer.face });
  }

  // A changed formula has no result yet, so the readout goes dark.
  function unroll() {
    if (!rolled) return;
    retire();
    rolled = false;
    outcome = null;
    answer = null;
  }

  function setTerms(next: Term[]) {
    terms = next;
    word = null;
    text = formatFormula(next);
    refused = false;
    unroll();
  }

  // Typed, the dice keep their pigments where they stand for the same die,
  // and a word die's name alone is that die.
  function onInput(value: string) {
    text = value;
    refused = false;
    const typed = parseFormula(value);
    word = typed ? null : wordNamed(value);
    terms = typed && reattach(typed, terms ?? []);
    unroll();
  }

  // The die as its set has it now: a track's notes change in Command, and
  // a GM's word die's faces in edit mode, between rolls of the same die.
  function current(die: WordPad): WordPad {
    const now = set.pads.find((p) => p?.kind === 'word' && p.name === die.name && p.pigment === die.pigment);
    return now?.kind === 'word' ? now : die;
  }

  function wordNamed(value: string): WordPad | null {
    const name = value.trim().toLowerCase();
    const pad = set.pads.find((p) => p?.kind === 'word' && p.name.toLowerCase() === name);
    return pad?.kind === 'word' ? pad : null;
  }

  // A press after a roll, or over a word die, starts a new formula with no
  // edge; a right-click (by -1) takes from the dice there.
  function press(by: 1 | -1, add: (base: Term[]) => Term[] | null) {
    const fresh = (rolled && by > 0) || word !== null;
    const next = add(fresh ? [] : (terms ?? []));
    if (!next) return;
    if (fresh) edge = null;
    setTerms(next);
  }

  function pressDie(pad: Extract<Pad, { kind: 'die' }>, by: 1 | -1) {
    press(by, (base) => stepDie(base, pad.size, by, pad.pigment));
  }

  function pressMacro(pad: MacroPad, by: 1 | -1) {
    press(by, (base) => addTerms(base, parseFormula(pad.formula) ?? [], by, pad.pigment));
  }

  function pressWord(pad: WordPad) {
    if (pad.faces.length === 0) return;
    word = pad;
    terms = null;
    text = pad.name;
    edge = null;
    refused = false;
    rollNow();
  }

  function bumpBy(by: 1 | -1) {
    if (word) return;
    if (terms === null) {
      refused = true;
      return;
    }
    const next = bump(terms, by);
    if (!next) return;
    if (!rolled || !outcome) {
      setTerms(next);
      return;
    }
    // Only the number moved: the dice on the readout stay, and the total
    // moves with it.
    terms = next;
    text = formatFormula(next);
    outcome = { kept: refigure(outcome.kept, next), dropped: outcome.dropped && refigure(outcome.dropped, next) };
  }

  function toggleEdge(to: Edge) {
    edge = edge === to ? null : to;
    unroll();
  }

  function rollNow() {
    if (word) {
      word = current(word);
      if (word.faces.length === 0) return;
      retire();
      answer = { face: pickFace(word.faces), pigment: word.pigment };
      outcome = null;
    } else {
      if (terms === null) {
        refused = true;
        return;
      }
      if (terms.length === 0) return;
      retire();
      outcome = rollOutcome(terms, edge);
      answer = null;
    }
    rolledAs = { edge: word ? null : edge, die: word };
    seq += 1;
    rolled = true;
  }

  // A line of the tape back in the field as it was rolled, for ↵ to roll
  // again; the readout's roll goes onto the tape as it leaves.
  function recall(line: TapeLine) {
    if (line.kind === 'dice') {
      edge = line.edge;
      setTerms(line.outcome.kept.terms);
      return;
    }
    unroll();
    word = line.die;
    terms = null;
    text = line.die.name;
    edge = null;
    refused = false;
  }

  function clear() {
    retire();
    text = '';
    terms = [];
    word = null;
    refused = false;
    outcome = null;
    answer = null;
    edge = null;
    rolled = false;
  }

  // ---- the sets ---------------------------------------------------------

  function step(by: number) {
    const ids = [...sets.map((s) => s.id), NEW];
    browsedId = ids[(ids.indexOf(browsedId) + by + ids.length) % ids.length];
    renaming = false;
    stopEditing();
  }

  function stopEditing() {
    editing = false;
    renaming = false;
    entry = null;
    facesOf = null;
  }

  // A beat after the last change: the folder changes in bursts while Command
  // writes.
  function refreshTracks() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      try {
        const got = await drawTracks();
        campaign = got.campaign;
        open = got.tracks;
      } catch (e) {
        console.error('Failed to read the tracks to draw from:', e);
      }
    }, 300);
  }

  async function save(key: 'augurySet' | 'augurySets', value: unknown) {
    try {
      const store = await load('settings.json');
      await store.set(key, value);
    } catch (e) {
      console.error(`Failed to save ${key}:`, e);
    }
  }

  function loadSet() {
    if (browsedId === NEW) {
      createSet();
      return;
    }
    loadedId = browsedId;
    stopEditing();
    void save('augurySet', loadedId);
  }

  // Editing is the pads', so the tape goes back down off them.
  function toggleEditing() {
    if (editing) stopEditing();
    else {
      editing = true;
      tapeOpen = false;
    }
  }

  function createSet() {
    const made = newSet(stored.custom, `custom-${Date.now()}`);
    stored = { ...stored, custom: [...stored.custom, made] };
    loadedId = browsedId = made.id;
    editing = true;
    tapeOpen = false;
    // Named Custom N, with its name open to change at once.
    renaming = true;
    void save('augurySets', stored);
    void save('augurySet', loadedId);
  }

  // Each write names its set, so one that lands late (the faces editor
  // closing as another set loads) can't fall on the wrong one.
  function putPad(id: string, i: number, pad: Pad | null) {
    const pads = [...(allSets(stored).find((s) => s.id === id)?.pads ?? [])];
    if (i >= pads.length) return;
    pads[i] = pad;
    stored = { ...stored, custom: stored.custom.map((c) => (c.id === id ? { ...c, pads } : c)) };
    void save('augurySets', stored);
  }

  function commitEntry(i: number, typed: string): string | null {
    const made = padFromEntry(typed, set.pads[i]);
    if ('refused' in made) return made.refused;
    putPad(set.id, i, made.pad);
    entry = null;
    // A new word die opens on its faces.
    if (made.pad.kind === 'word' && made.pad.faces.length === 0) facesOf = i;
    return null;
  }

  // A word die needs a face to roll: closed with none, it goes back to an
  // empty pad rather than staying on the matrix doing nothing.
  function putFaces(id: string, i: number, faces: string[]) {
    const pad = allSets(stored).find((s) => s.id === id)?.pads[i];
    if (pad?.kind === 'word') putPad(id, i, faces.length ? { ...pad, faces } : null);
    if (facesOf === i) facesOf = null;
  }

  function plain(pad: Pad): Pad {
    if (pad.kind === 'die') return { kind: 'die', size: pad.size };
    if (pad.kind === 'macro') return { kind: 'macro', name: pad.name, formula: pad.formula };
    return { kind: 'word', name: pad.name, faces: pad.faces };
  }

  // Off the matrix: the pad's ✕ in edit mode, or its field emptied. A word
  // die's faces editor closes with it, and finds no pad to write to.
  function clearPad(i: number) {
    if (entry === i) entry = null;
    if (facesOf === i) facesOf = null;
    putPad(set.id, i, null);
  }

  // In edit mode a pad's right-click is its menu: Command's track pigment
  // row, and its faces for a word die.
  function padMenu(e: MouseEvent, i: number) {
    const pad = set.pads[i];
    if (!pad) return;
    const id = set.id;
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        picks(m.augury_pad_pigment(), [
          ...PIGMENTS.map((p) => ({
            label: p.name,
            swatch: p.hex,
            on: pad.pigment === p.hex,
            action: () => putPad(id, i, { ...plain(pad), pigment: p.hex }),
          })),
          { label: m.augury_pad_pigment_none(), swatch: null, on: !pad.pigment, action: () => putPad(id, i, plain(pad)) },
        ]),
        ...(pad.kind === 'word' ? [action(m.augury_pad_edit_faces(), () => (facesOf = i))] : []),
      ],
    };
  }

  function renameSet(name: string): string | null {
    if (sets.some((s) => s.id !== browsedId && s.name().toLowerCase() === name.toLowerCase())) {
      return m.augury_set_name_taken();
    }
    stored = { ...stored, custom: stored.custom.map((c) => (c.id === browsedId ? { ...c, name } : c)) };
    renaming = false;
    void save('augurySets', stored);
    return null;
  }

  async function deleteSet(id: string, name: string) {
    const confirmed = await confirmPrompt.request({
      title: m.augury_delete_set_title({ set: name }),
      message: m.augury_delete_set_message(),
      confirmLabel: m.augury_delete_set(),
      danger: true,
    });
    if (!confirmed) return;
    stored = { ...stored, custom: stored.custom.filter((c) => c.id !== id) };
    if (loadedId === id) {
      loadedId = 'standard';
      stopEditing();
      void save('augurySet', loadedId);
    }
    browsedId = loadedId;
    void save('augurySets', stored);
  }

  const unbindKeys = bindKeys(
    (event, ctx) => {
      // A field that took the key (a pad's or a set's name) keeps it.
      if (event.defaultPrevented || ctx.menu || event.metaKey || event.ctrlKey || event.altKey) return false;
      // A focused key's Enter is its own press.
      if (event.key === 'Enter' && !(event.target instanceof HTMLButtonElement)) {
        rollNow();
        return true;
      }
      if (event.key === 'Escape' && editing) {
        stopEditing();
        return true;
      }
      // With nothing to clear, Esc goes on down the app's ladder.
      if (event.key === 'Escape' && (text !== '' || outcome || answer || edge)) {
        clear();
        return true;
      }
      return false;
    },
    { tool: 'augury' },
  );

  onMount(async () => {
    unlistenVault = onVaultChange(refreshTracks);
    try {
      const store = await load('settings.json');
      stored = parseSets(await store.get('augurySets'));
      const id = parseString(await store.get('augurySet'));
      if (id && allSets(stored).some((s) => s.id === id)) loadedId = browsedId = id;
    } catch (e) {
      console.error('Failed to read the dice sets:', e);
    }
  });

  onDestroy(() => {
    unbindKeys();
    clearTimeout(refreshTimer);
    void unlistenVault?.then((stop) => stop());
  });
</script>

<section class="augury" class:dormant={$focusPath.tool !== 'augury'}>
  <header class="bar">
    <!-- A pad controller's program section: one strip of keys, each with one
         job. Edit mode lights edit's lamp and dims the keys that would end
         it, so nothing in the strip moves. Load and edit carry lamps: load's
         lit parchment while a set waits on the display, edit's purple while
         editing. -->
    <div class="well browser" role="group" aria-label={m.augury_sets_label()}>
      <button
        type="button"
        class="key"
        disabled={editing}
        title={m.augury_set_previous()}
        aria-label={m.augury_set_previous()}
        on:click={() => step(-1)}
      >
        <svg class="back" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <!-- The rack's tool lamp (RackBar .cell): lit while the set on the
           display is the one on the pads. -->
      <span class="display" class:new={browsedId === NEW} title={displayTitle}>
        <span class="cell" class:lit={browsedId === set.id} aria-hidden="true"></span>
        {#if renaming && browsed}
          <span class="name-field">
            <RenameField
              value={browsedName}
              label={m.augury_set_name_label()}
              onCommit={renameSet}
              onCancel={() => (renaming = false)}
            />
          </span>
        {:else if editing}
          <!-- A set of the GM's takes a new name as a pad takes a new die:
               a click opens its field. -->
          <button
            type="button"
            class="set-name readout-label renamable"
            title={m.augury_set_rename_title()}
            on:click={() => (renaming = true)}
          >
            {browsedName}
          </button>
          <!-- Edit mode's ✕, as every pad shows one: the set itself can go. -->
          <button
            type="button"
            class="clear"
            title={m.augury_delete_title()}
            aria-label={m.augury_delete_title()}
            on:click={() => void deleteSet(set.id, set.name())}
          >
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={XMARK} /></svg>
          </button>
        {:else}
          <span class="set-name readout-label">{browsedName}</span>
        {/if}
      </span>
      <button
        type="button"
        class="key"
        disabled={editing}
        title={m.augury_set_next()}
        aria-label={m.augury_set_next()}
        on:click={() => step(1)}
      >
        <svg viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <!-- Browsing, then acting on what's browsed. -->
      <span class="rule" aria-hidden="true"></span>
      <button
        type="button"
        class="key"
        disabled={!canLoad}
        title={browsedId === NEW ? m.augury_new_title() : m.augury_load_title({ set: browsedName })}
        aria-label={browsedId === NEW ? m.augury_new_title() : m.augury_load_title({ set: browsedName })}
        on:click={loadSet}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={LOAD} /></svg>
        <span class="lamp" class:lit={canLoad} aria-hidden="true"></span>
      </button>
      <!-- A mode switched on: its lamp lights purple, LatchKey's way. -->
      <button
        type="button"
        class="key"
        disabled={!canEdit}
        aria-pressed={editing}
        title={editing ? m.augury_done_title() + chordHint('augury.clear') : m.augury_edit_title()}
        aria-label={m.augury_edit_label()}
        on:click={toggleEditing}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PEN} /></svg>
        <span class="lamp mode" class:lit={editing} aria-hidden="true"></span>
      </button>
    </div>
    {@render windowKey?.()}
  </header>

  <div class="body">
    {#if facesOf !== null && facesPad?.kind === 'word'}
      {@const at = facesOf}
      {@const id = set.id}
      {#key `${id}:${at}`}
        <FacesEditor name={facesPad.name} faces={facesPad.faces} onDone={(faces) => putFaces(id, at, faces)} />
      {/key}
    {:else}
      <Readout result={outcome?.kept ?? null} dropped={outcome?.dropped ?? null} word={answer} {seq} />
    {/if}

    <div class="formula-row">
      <input
        class="formula"
        class:refused
        value={text}
        aria-label={m.augury_formula_label()}
        aria-invalid={refused}
        title={refused ? m.augury_formula_refused() : undefined}
        spellcheck="false"
        autocomplete="off"
        autocapitalize="off"
        on:input={(e) => onInput(e.currentTarget.value)}
      />
      <!-- Latches: a mode on the formula, so the lamp lights purple. A word
           die rolls once, so they wait while one is in the field. -->
      <div class="well" role="group" aria-label={m.augury_edge_label()}>
        <button
          type="button"
          class="key text-key"
          disabled={word !== null}
          aria-pressed={edge === 'advantage'}
          title={m.augury_advantage_title()}
          on:click={() => toggleEdge('advantage')}
        >
          <span>{m.augury_advantage()}</span>
          <span class="lamp mode" class:lit={edge === 'advantage'} aria-hidden="true"></span>
        </button>
        <button
          type="button"
          class="key text-key"
          disabled={word !== null}
          aria-pressed={edge === 'disadvantage'}
          title={m.augury_disadvantage_title()}
          on:click={() => toggleEdge('disadvantage')}
        >
          <span>{m.augury_disadvantage()}</span>
          <span class="lamp mode" class:lit={edge === 'disadvantage'} aria-hidden="true"></span>
        </button>
      </div>
      <!-- Transport keys: neither moves when the dice set changes. -->
      <div class="well">
        <button
          type="button"
          class="key"
          disabled={text === '' && !outcome && !answer && !edge}
          title={m.augury_clear() + chordHint('augury.clear')}
          aria-label={m.augury_clear()}
          on:click={clear}
        >
          <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={XMARK} /></svg>
        </button>
        <button
          type="button"
          class="key"
          disabled={text.trim() === ''}
          title={m.augury_roll() + chordHint('augury.roll')}
          aria-label={m.augury_roll()}
          on:click={rollNow}
        >
          <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
        </button>
      </div>
    </div>

    <!-- The tape, raised, stands where the pads are. -->
    {#if !tapeOpen}
      <div class="pads" class:editing role="group" aria-label={m.augury_pads_label()}>
        {#each set.pads as pad, i (i)}
          <!-- A pigment shows on the pad's edge at rest, and lights its label
               and lamp once loaded, where a plain pad's light parchment. -->
          <div
            class="pad-well"
            class:pigmented={!!pad?.pigment}
            class:blank={editing && !pad}
            class:open={facesOf === i}
            style:--pigment={pad?.pigment ?? null}
          >
            {#if editing}
              <button
                type="button"
                class="pad"
                class:word={pad?.kind === 'word' || (pad?.kind === 'macro' && pad.name !== pad.formula)}
                class:macro={pad?.kind === 'macro' && pad.name !== pad.formula}
                title={pad ? m.augury_pad_edit_title() : m.augury_pad_add_title()}
                on:click={() => (entry = i)}
                on:contextmenu|preventDefault={(e) => padMenu(e, i)}
              >
                <span class="pad-text">{pad ? padLabel(pad) : '+'}</span>
                {#if pad?.kind === 'macro' && pad.name !== pad.formula}
                  <span class="pad-formula">{pad.formula}</span>
                {/if}
                <span class="lamp" aria-hidden="true"></span>
              </button>
              {#if pad}
                <!-- Edit mode's way off a pad, in sight on every one: a small
                     ✕ in the corner, danger's hue under the pointer. -->
                <button
                  type="button"
                  class="clear"
                  title={m.augury_pad_clear()}
                  aria-label={m.augury_pad_clear()}
                  on:click={() => clearPad(i)}
                >
                  <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={XMARK} /></svg>
                </button>
              {/if}
            {:else if pad?.kind === 'die'}
              {@const count = diceOf(terms ?? [], pad.size, pad.pigment)}
              <button
                type="button"
                class="pad"
                class:loaded={count !== 0}
                title={m.augury_pad_title({ size: pad.size })}
                on:click={() => pressDie(pad, 1)}
                on:contextmenu|preventDefault={() => pressDie(pad, -1)}
              >
                <span>{count === 0 ? `d${pad.size}` : `${count}d${pad.size}`}</span>
                <span class="lamp" class:lit={count !== 0} aria-hidden="true"></span>
              </button>
            {:else if pad?.kind === 'macro'}
              <!-- A named macro shows its formula under the name; one named by
                   its formula shows it once, as notation. -->
              {@const named = pad.name !== pad.formula}
              {@const lit = holds(terms ?? [], parseFormula(pad.formula) ?? [], pad.pigment)}
              <button
                type="button"
                class="pad"
                class:word={named}
                class:macro={named}
                class:loaded={lit}
                title={m.augury_macro_pad_title({ formula: pad.formula })}
                on:click={() => pressMacro(pad, 1)}
                on:contextmenu|preventDefault={() => pressMacro(pad, -1)}
              >
                <span class="pad-text">{pad.name}</span>
                {#if named}<span class="pad-formula">{pad.formula}</span>{/if}
                <span class="lamp" class:lit aria-hidden="true"></span>
              </button>
            {:else if pad?.kind === 'word'}
              {@const lit = word !== null && word.name === pad.name && word.pigment === pad.pigment}
              <button
                type="button"
                class="pad word"
                class:loaded={lit}
                disabled={pad.faces.length === 0}
                title={set.id === TRACKS
                  ? pad.faces.length
                    ? m.augury_track_pad_title({ name: pad.name })
                    : m.augury_track_pad_empty({ name: pad.name })
                  : pad.faces.length
                    ? m.augury_word_pad_title({ name: pad.name })
                    : m.augury_word_pad_empty({ name: pad.name })}
                on:click={() => pressWord(pad)}
                on:contextmenu|preventDefault
              >
                <span class="pad-text">{pad.name}</span>
                <span class="lamp" class:lit aria-hidden="true"></span>
              </button>
            {/if}
          </div>
        {/each}
        <!-- The ±1 pad, in the same corner of every number set. -->
        <div class="pad-well">
          {#if set.bonus}
            <button
              type="button"
              class="pad"
              class:loaded={bonus !== 0}
              disabled={editing || word !== null}
              title={m.augury_bonus_title()}
              on:click={() => bumpBy(1)}
              on:contextmenu|preventDefault={() => bumpBy(-1)}
            >
              <span>{bonus === 0 ? '+1' : bonus > 0 ? `+${bonus}` : `${bonus}`}</span>
              <span class="lamp" class:lit={bonus !== 0} aria-hidden="true"></span>
            </button>
          {/if}
        </div>
        <!-- A pad's entry opens across its row, over its neighbours, so a
             macro's formula has room. -->
        {#if entry !== null}
          {@const at = entry}
          {@const pad = set.pads[at]}
          {#key at}
            <span class="pad-field" style:--row={Math.floor(at / 4)} title={m.augury_pad_entry_label()}>
              <RenameField
                value={pad ? padEntry(pad) : ''}
                label={m.augury_pad_entry_label()}
                onCommit={(typed) => commitEntry(at, typed)}
                onCancel={() => (entry = null)}
                onEmpty={() => clearPad(at)}
              />
            </span>
          {/key}
        {/if}
      </div>
    {/if}

    <Tape lines={tape} open={tapeOpen} onToggle={() => (tapeOpen = !tapeOpen)} onRecall={recall} />
  </div>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .augury.dormant {
    --ring-focus: var(--ring-dormant);
  }

  /* The faceplate: every part of the instrument is a well sunk into it. */
  .augury {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-faceplate);
    color: var(--text-primary);
  }

  /* Command's bar (CommandPanel .bar): the same height, inset and rule, so
     the keys centre where the neighbours' do. */
  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    justify-content: space-between;
    height: var(--header-height);
    padding: 1px 0.5rem 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  /* The board tools' wells and keys (BoardTools .well, .key). */
  .well {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .key {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: color var(--transition-fast), transform var(--transition-fast);
  }

  .key:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .key:active:not(:disabled) {
    transform: scale(0.97);
  }

  .key:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .key svg {
    width: 12px;
    height: 12px;
  }

  .back {
    transform: scaleX(-1);
  }

  /* A key with a word or a number on its face: the icon keys' height, as
     wide as its label needs. */
  .text-key {
    flex-direction: column;
    gap: 3px;
    width: auto;
    min-width: 26px;
    padding: 0 0.3rem;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    line-height: 1;
  }

  /* At the rack's narrowest the set's name gives way, not the keys. */
  .browser {
    min-width: 0;
  }

  .display {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    width: 6.5rem;
    min-width: 0;
    flex-shrink: 1;
    height: 22px;
    padding: 0 0.2rem;
  }

  .set-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* The entry past the sets is what a set would be: a step down the ramp. */
  .display.new .set-name {
    color: var(--text-tertiary);
  }

  .name-field {
    flex: 1;
    min-width: 0;
    display: flex;
    font-size: 0.8rem;
  }

  /* The name as a key in edit mode: the label as it was, a step up the
     ramp under the pointer. */
  .renamable {
    padding: 0;
    background: none;
    border: none;
    text-align: left;
    cursor: text;
    transition: color var(--transition-fast);
  }

  .renamable:hover {
    color: var(--text-primary);
  }

  /* The status bar's rule (StatusBar .rule), in the well's own edge grey:
     on the well's darker ground the bar's grey would stand out. */
  .rule {
    flex-shrink: 0;
    width: 1px;
    height: 12px;
    margin: 0 0.15rem;
    background: var(--border-subtle);
  }

  /* Load and edit stack a glyph over a lamp, as LatchKey's keys do; the
     arrows, with no lamp, centre theirs. */
  .browser .key {
    flex-direction: column;
    gap: 3px;
  }

  /* The pads' ✕ (.clear), in line at the end of the set's name. */
  .display .clear {
    position: static;
    flex-shrink: 0;
    width: 12px;
    margin-left: auto;
  }

  /* RackBar .cell, verbatim. */
  .cell {
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-cell);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .cell.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.5rem;
  }

  .formula-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  /* Mono: notation is a code-flavoured affordance. The edge is the focus
     ring, or the refused ring once a roll can't read it. */
  .formula {
    flex: 1;
    min-width: 0;
    height: 28px;
    padding: 0 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--text-primary);
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    outline: none;
  }

  .formula:focus {
    box-shadow: var(--ring-focus);
  }

  .formula.refused {
    box-shadow: var(--ring-refused);
  }

  /* Four equal columns whatever the pads say: a bare 1fr would grow to fit
     a long name, so each column's floor is zero and the name ellipsizes. */
  .pads {
    position: relative;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 4px;
  }

  /* Each pad is a key in its own well, so the matrix reads as sixteen pads;
     one with no die is the bare well. */
  .pad-well {
    position: relative;
    display: flex;
    min-width: 0;
    height: 2.4rem;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .pad {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0;
    transition:
      color var(--transition-fast),
      background var(--transition-fast),
      transform var(--transition-fast);
  }

  .pad:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .pad:active:not(:disabled) {
    transform: scale(0.97);
  }

  .pad:disabled {
    opacity: 0.35;
    cursor: default;
  }

  /* A word die's name is words, not notation. */
  .pad.word {
    font-family: var(--font-body);
    font-size: 0.8rem;
  }

  .pad-text {
    max-width: 100%;
    padding: 0 0.25rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* A named macro: its name, then its formula small in notation's mono. */
  .pad.macro {
    gap: 2px;
  }

  .pad.macro .pad-text {
    line-height: 1.1;
  }

  .pad-formula {
    max-width: 100%;
    padding: 0 0.25rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: 0.55rem;
    line-height: 1.1;
    color: var(--text-tertiary);
  }

  /* The entry: a pad's well stretched over its row (gap 4px), holding the
     rename field and its ring. */
  .pad-field {
    position: absolute;
    top: calc(var(--row) * (2.4rem + 4px));
    left: 0;
    right: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    height: 2.4rem;
    padding: 0 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .clear {
    position: absolute;
    top: 1px;
    right: 1px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    padding: 0;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .clear:hover {
    color: var(--text-danger);
  }

  .clear svg {
    width: 8px;
    height: 8px;
  }

  /* In edit mode an empty pad is dashed: the app's not-yet-real edge. */
  .pad-well.blank {
    border-style: dashed;
    border-color: var(--text-tertiary);
  }

  .pad-well.pigmented {
    border-color: var(--pigment);
  }

  /* The word die whose faces are in the readout's well. */
  .pad-well.open {
    box-shadow: var(--ring-focus);
  }

  /* Loaded dice are content: parchment, where a mode's key would light
     purple. A loaded pad is lit from behind, as a pad controller's are: a
     wash of its colour over its face, in its well. */
  .pad.loaded {
    color: var(--text-accent);
    background: color-mix(in srgb, var(--text-accent) 16%, transparent);
  }

  .pad.loaded:hover {
    filter: brightness(1.2);
  }

  .pad-well.pigmented .pad.loaded {
    color: var(--pigment);
    background: color-mix(in srgb, var(--pigment) 16%, transparent);
  }

  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .lamp.lit {
    background: var(--text-accent);
    filter: var(--glow-accent);
  }

  .pad-well.pigmented .lamp.lit {
    background: var(--pigment);
    filter: drop-shadow(0 0 3px color-mix(in srgb, var(--pigment) 50%, transparent));
  }

  /* LatchKey's lamp: a mode switched on lights the transport's purple. */
  .lamp.mode.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }
</style>
