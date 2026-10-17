<script lang="ts">
  // The main window: one rack with eight views of it (PANELS.md). Each docked
  // tool is mounted once and laid over its slot in the current view, so a
  // view switch moves tools rather than remounting them; a tool with no slot
  // here stays mounted, hidden. A popped-out tool is unmounted, and keeps its
  // slot in every view that holds it as the way back to it.
  import { onDestroy, onMount } from 'svelte';
  import { listen } from '@tauri-apps/api/event';
  import { load } from '@tauri-apps/plugin-store';
  import ActionButton from '../ui/ActionButton.svelte';
  import ConfirmDialog from '../ui/ConfirmDialog.svelte';
  import DockToggle from './DockToggle.svelte';
  import PanelView from './PanelView.svelte';
  import RackBar from './RackBar.svelte';
  import { menuSlotHeld } from './menuSlot';
  import { isPanelId, panelTitle, type PanelId } from './panels';
  import {
    RACK_TOOLS,
    RAIL,
    VIEW_COUNT,
    defaultViews,
    landing,
    layout,
    mount,
    parseViews,
    resize,
    toolsIn,
    without,
    type Landing,
    type Rail,
    type RackView,
  } from './rack';
  import { dock, popOut, poppedPanels } from './shellState';

  /** The private type a tool's key carries into the rack. */
  const CARRY = 'application/x-unseen-rack-tool';

  let views: RackView[] = defaultViews();
  let current = 0;
  let loaded = false;
  let focused: PanelId | null = null;
  let rackEl: HTMLElement;
  let rackW = 0;
  let rackH = 0;

  $: view = views[current];
  $: present = toolsIn(view.root);
  $: popped = new Set($poppedPanels.popped);
  $: placed = layout(view.root, rackW, rackH, view.locked);
  // The keyboard belongs to the tool last clicked into. When that one isn't
  // in the view, or is in its own window, the view's first tool takes it.
  $: focusable = present.filter((id) => !popped.has(id));
  $: if (!focused || !focusable.includes(focused)) focused = focusable[0] ?? null;

  onMount(async () => {
    try {
      const store = await load('settings.json');
      views = parseViews(await store.get('rackViews')) ?? views;
      const at = await store.get('rackView');
      if (typeof at === 'number' && Number.isInteger(at) && at >= 0 && at < VIEW_COUNT) current = at;
    } catch (e) {
      console.error('Failed to load the rack:', e);
    }
    loaded = true;
  });

  async function save() {
    try {
      const store = await load('settings.json');
      await store.set('rackViews', views);
      await store.set('rackView', current);
    } catch (e) {
      console.error('Failed to save the rack:', e);
    }
  }

  function commit(next: RackView) {
    views[current] = next;
    void save();
  }

  function switchTo(i: number) {
    if (i === current) return;
    current = i;
    void save();
  }

  // A tool's key: mounts it in this view, or takes it out — unless it's
  // locked here.
  function toggle(id: PanelId) {
    if (!present.includes(id)) {
      commit({ ...view, root: mount(view.root, id) });
      focused = id;
    } else if (!view.locked.includes(id)) {
      commit({ ...view, root: without(view.root, id) });
    }
  }

  function lock(id: PanelId) {
    if (!present.includes(id)) return;
    const held = view.locked.includes(id);
    commit({ ...view, locked: held ? view.locked.filter((l) => l !== id) : [...view.locked, id] });
  }

  // Rust asks for a tool (panels.rs show_panel): the File menu brings
  // Command forward when it opens a campaign. In this view it takes the
  // keyboard; otherwise the first view holding it comes up, and failing
  // that it's mounted here.
  const unlistenShow = listen<string>('panels://show', (e) => {
    const id = e.payload;
    if (!isPanelId(id) || !RACK_TOOLS.some((t) => t.id === id)) return;
    if (!present.includes(id)) {
      const at = views.findIndex((v) => toolsIn(v.root).includes(id));
      if (at >= 0) switchTo(at);
      else commit({ ...view, root: mount(view.root, id) });
    }
    focused = id;
  });
  onDestroy(() => void unlistenShow.then((stop) => stop()));

  // A tool back from its own window takes the keyboard if it's in this view,
  // whether it came back through [dock back] or the window's close button.
  let lastPopped: PanelId[] = [];
  function focusDockedBack(now: PanelId[]) {
    const back = lastPopped.find((id) => !now.includes(id));
    if (back && present.includes(back)) focused = back;
    lastPopped = now;
  }
  $: focusDockedBack($poppedPanels.popped);

  // Bare 1–8 bring up a view, unless a field has the caret (the guard
  // Command's bare keys use), or a dialog or menu is open.
  function onKey(e: KeyboardEvent) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey || e.isComposing) return;
    const digit = /^Digit([1-8])$/.exec(e.code);
    if (!digit || menuSlotHeld() || document.querySelector('dialog[open]')) return;
    if (e.target instanceof Element && e.target.closest('input, textarea, select, [contenteditable], .cm-editor')) return;
    e.preventDefault();
    switchTo(Number(digit[1]) - 1);
  }

  // ---- resizing --------------------------------------------------------------

  let held: Rail | null = null;

  function sameRail(a: Rail | null, b: Rail): boolean {
    return !!a && a.index === b.index && a.path.join() === b.path.join();
  }

  function pressRail(e: PointerEvent, rail: Rail) {
    if (e.button !== 0) return;
    // Held still or not, the press is the rail's: no text selection sweeps
    // across the panels from it.
    e.preventDefault();
    if (rail.inert || !view.root) return;
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const from = view.root;
    const start = rail.dir === 'row' ? e.clientX : e.clientY;
    held = rail;
    const move = (m: PointerEvent) => {
      views[current] = { ...view, root: resize(from, rail, (rail.dir === 'row' ? m.clientX : m.clientY) - start) };
    };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      held = null;
      void save();
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }

  // ---- carrying a tool in by its key -----------------------------------------

  let carried: PanelId | null = null;
  let target: Landing | null = null;

  function carry(id: PanelId, data: DataTransfer) {
    carried = id;
    data.setData(CARRY, id);
  }

  function endCarry() {
    carried = null;
    target = null;
  }

  // A tool carried over the rack is the rack's alone: the drop targets inside
  // the panels never see it.
  function carrying(e: DragEvent): boolean {
    if (!carried || !e.dataTransfer?.types.includes(CARRY)) return false;
    e.stopPropagation();
    return true;
  }

  function carryOver(e: DragEvent) {
    if (!carrying(e)) return;
    const box = rackEl.getBoundingClientRect();
    target = landing(view, carried!, e.clientX - box.left, e.clientY - box.top, box.width, box.height);
    if (target?.ok) e.preventDefault();
  }

  function carryLeave(e: DragEvent) {
    if (!carrying(e)) return;
    if (!(e.relatedTarget instanceof Node && rackEl.contains(e.relatedTarget))) target = null;
  }

  function carryDrop(e: DragEvent) {
    if (!carrying(e)) return;
    e.preventDefault();
    if (target?.ok) {
      commit({ ...view, root: target.root });
      focused = carried;
    }
    endCarry();
  }

  function report(action: Promise<void>, what: string) {
    action.catch((err) => console.error(`Failed to ${what}:`, err));
  }
</script>

<svelte:window on:keydown={onKey} />

<div class="host" style={`--rail: ${RAIL}px`}>
  <RackBar
    {views}
    {current}
    {focused}
    {popped}
    onSwitch={switchTo}
    onToggle={toggle}
    onLock={lock}
    onCarry={carry}
    onCarryEnd={endCarry}
  />

  <div
    class="rack"
    class:resizing={!!held}
    bind:this={rackEl}
    bind:clientWidth={rackW}
    bind:clientHeight={rackH}
    on:dragenter|capture={carrying}
    on:dragover|capture={carryOver}
    on:dragleave|capture={carryLeave}
    on:drop|capture={carryDrop}
    role="presentation"
  >
    {#if loaded}
      {#each RACK_TOOLS as tool (tool.id)}
        {@const r = placed.rects.get(tool.id)}
        {@const locked = view.locked.includes(tool.id)}
        <div
          class="slot"
          class:shown={!!r}
          style={r ? `left: ${r.x}px; top: ${r.y}px; width: ${r.w}px; height: ${r.h}px` : undefined}
          on:pointerdown|capture={() => (focused = tool.id)}
          role="presentation"
        >
          {#if popped.has(tool.id)}
            <div class="away-note">
              <p><em>{tool.title}</em> is in its own window.</p>
              <div class="away-actions">
                <ActionButton label="focus" onClick={() => report(popOut(tool.id), `focus ${tool.title}`)} />
                <ActionButton label="dock back" onClick={() => report(dock(tool.id), `dock ${tool.title}`)} />
              </div>
            </div>
          {:else}
            <!-- Locked in this view, the pop-out key stays in place but out
                 of reach, as Command's Prep keys do in Play. -->
            <PanelView id={tool.id} active={!!r && focused === tool.id}>
              {#snippet windowKey()}
                <span class="window-key" class:locked inert={locked}><DockToggle id={tool.id} popped={false} /></span>
              {/snippet}
            </PanelView>
          {/if}
        </div>
      {/each}

      {#each placed.rails as rail (`${rail.path.join('.')}:${rail.index}`)}
        <div
          class="rail {rail.dir}"
          class:inert={rail.inert}
          class:held={sameRail(held, rail)}
          style={`left: ${rail.rect.x}px; top: ${rail.rect.y}px; width: ${rail.rect.w}px; height: ${rail.rect.h}px`}
          on:pointerdown={(e) => pressRail(e, rail)}
          role="separator"
          aria-orientation={rail.dir === 'row' ? 'vertical' : 'horizontal'}
        ></div>
      {/each}

      {#if !view.root}
        <div class="empty-rack">
          <p class="ledger-label">View {current + 1} is empty</p>
          <p class="lede">Press a tool's key to mount it, or carry the key here.</p>
        </div>
      {/if}

      {#if carried && target && !(!target.ok && target.reason === 'self')}
        <div
          class="drop"
          class:refused={!target.ok}
          style={`left: ${target.rect.x}px; top: ${target.rect.y}px; width: ${target.rect.w}px; height: ${target.rect.h}px`}
        >
          <span class="ledger-label">{target.ok ? panelTitle(carried) : target.reason === 'locked' ? 'locked' : 'no room'}</span>
        </div>
      {/if}
    {/if}
  </div>

  <!-- One prompt per window, for whichever panel asks (confirmStore). -->
  <ConfirmDialog />
</div>

<style>
  /* The rack's frame is the tools' own ground: it parts the plates, under
     the bar and as rails between tools, and runs into their bodies. */
  .host {
    height: 100vh;
    display: flex;
    flex-direction: column;
    gap: var(--rail);
    background: var(--bg-app);
  }

  .rack {
    position: relative;
    flex: 1;
    min-height: 0;
  }
  .rack.resizing {
    user-select: none;
  }

  /* Each tool sits boxed: its header plate runs down both sides as a thin
     edge, so neighbours read as separate units across the rail. */
  .slot {
    position: absolute;
    display: none;
    overflow: hidden;
    background: var(--bg-app);
    border-left: 2px solid var(--bg-header);
    border-right: 2px solid var(--bg-header);
  }
  .slot.shown {
    display: block;
  }

  .window-key {
    display: flex;
  }
  .window-key.locked {
    opacity: var(--opacity-out-of-scope);
  }

  /* A rail is the frame itself: hover brightens it a grey step. */
  .rail {
    position: absolute;
    z-index: 2;
    transition: background var(--transition-fast);
  }
  .rail.row {
    cursor: col-resize;
  }
  .rail.col {
    cursor: row-resize;
  }
  .rail:not(.inert):hover,
  .rail.held {
    background: var(--border-subtle);
  }
  .rail.inert {
    cursor: default;
  }

  .away-note {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--text-secondary);
  }
  .away-note p {
    margin: 0;
  }
  .away-note em {
    font-family: var(--font-heading);
    font-style: normal;
    color: var(--text-primary);
  }
  .away-actions {
    display: flex;
    gap: 1rem;
  }

  /* An empty view: the dashed "prospective" outline, inset from the frame. */
  .empty-rack {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    background: var(--bg-app);
    outline: 1px dashed var(--border-subtle);
    outline-offset: -0.75rem;
  }
  .empty-rack p {
    margin: 0;
  }
  .empty-rack .ledger-label {
    color: var(--text-secondary);
  }
  .empty-rack .lede {
    color: var(--text-tertiary);
    font-style: italic;
  }

  /* Where a carried tool would land: the drop-target outline over a
     parchment wash. A refusal greys the slot instead and says why. */
  .drop {
    position: absolute;
    z-index: 3;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    background: color-mix(in srgb, var(--text-accent) 12%, transparent);
    outline: var(--outline-drop);
    outline-offset: -1px;
  }
  .drop .ledger-label {
    color: var(--text-accent);
  }
  .drop.refused {
    background: color-mix(in srgb, var(--bg-app) 50%, transparent);
    outline: none;
  }
  .drop.refused .ledger-label {
    color: var(--text-tertiary);
  }
</style>
