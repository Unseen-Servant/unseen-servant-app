<script lang="ts">
  // The main window: one rack with eight views of it (PANELS.md). Each docked
  // tool is mounted once and laid over its slot in the current view, so a
  // view switch moves tools rather than remounting them; a tool with no slot
  // here stays mounted, hidden. A popped-out tool is unmounted, and keeps its
  // slot in every view that holds it as the way back to it. The status bar
  // under the rack carries the lamps and every docked tool's section.
  import { onDestroy, onMount } from 'svelte';
  import { listen } from '@tauri-apps/api/event';
  import { load } from '@tauri-apps/plugin-store';
  import ActionButton from '../ui/ActionButton.svelte';
  import ConfirmDialog from '../ui/ConfirmDialog.svelte';
  import DockToggle from './DockToggle.svelte';
  import KeyboardHelpOverlay from './KeyboardHelpOverlay.svelte';
  import PanelView from './PanelView.svelte';
  import RackBar from './RackBar.svelte';
  import StatusBar from './StatusBar.svelte';
  import { setFocusedTool } from './focus';
  import { bindKeys, dispatchKey, hostKeys, type KeyContext } from './keys';
  import { isPanelId, panelTitle, type PanelId } from './panels';
  import {
    RACK_TOOLS,
    RAIL,
    VIEW_COUNT,
    defaultViews,
    landing,
    layout,
    mount,
    neighbour,
    parseViews,
    resize,
    toolsIn,
    without,
    type Landing,
    type Rail,
    type RackView,
    type Side,
  } from './rack';
  import { dock, onShowPanel, openSettings, popOut, poppedPanels } from './shellState';

  /** The private type a tool's key carries into the rack. */
  const CARRY = 'application/x-unseen-rack-tool';

  let views: RackView[] = defaultViews();
  let current = 0;
  let loaded = false;
  let focused: PanelId | null = null;
  let rackEl: HTMLElement;
  let rackW = 0;
  let rackH = 0;
  // Each tool's slot in the status bar, which it hoists its section into.
  let statusSlots: Partial<Record<PanelId, HTMLElement>> = {};
  let showHelp = false;

  // A tool that asked for the whole rack (Command's expanded board) covers
  // it in every view that holds it; the rest stay mounted, hidden. Any change
  // to the layout lets go of it.
  let filling: PanelId | null = null;

  $: view = views[current];
  $: present = toolsIn(view.root);
  $: popped = new Set($poppedPanels.popped);
  $: filled = filling && present.includes(filling) && !popped.has(filling) ? filling : null;
  $: placed = layout(filled ? { kind: 'tool', id: filled } : view.root, rackW, rackH, view.locked);
  // The keyboard belongs to the tool last clicked into. When that one isn't
  // in the view, or is in its own window, the view's first tool takes it.
  $: focusable = filled ? [filled] : present.filter((id) => !popped.has(id));
  $: if (!focused || !focusable.includes(focused)) focused = focusable[0] ?? null;
  // The tool on the focus path (focus.ts), which keys.ts runs tools' and
  // regions' handlers by.
  $: setFocusedTool(focused);

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
    if (next.root !== view.root) filling = null;
    views[current] = next;
    void save();
  }

  function switchTo(i: number) {
    if (i === current) return;
    current = i;
    void save();
  }

  // A tool's key: mounts it in this view, or gives it the keyboard as a
  // click into it does; pressed again it takes the tool out — unless it's
  // locked here. Under a filled tool, the press lets go of the fill. One in
  // its own window can't take the keyboard here, so its press takes it out.
  function toggle(id: PanelId) {
    if (!present.includes(id)) {
      commit({ ...view, root: mount(view.root, id) });
      focused = id;
    } else if (focused !== id && !popped.has(id)) {
      if (filling !== id) filling = null;
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
  // Command forward when it opens a campaign. A panel in this window asks
  // the same way (shellState showPanel) ahead of a chord that changes what
  // it shows. In this view it takes the keyboard; otherwise the first view
  // holding it comes up, and failing that it's mounted here.
  function show(id: PanelId) {
    if (!RACK_TOOLS.some((t) => t.id === id)) return;
    if (filling !== id) filling = null;
    if (!present.includes(id)) {
      const at = views.findIndex((v) => toolsIn(v.root).includes(id));
      if (at >= 0) switchTo(at);
      else commit({ ...view, root: mount(view.root, id) });
    }
    focused = id;
  }
  const unlistenShow = listen<string>('panels://show', (e) => {
    if (isPanelId(e.payload)) show(e.payload);
  });
  const stopShow = onShowPanel(show);
  onDestroy(() => {
    void unlistenShow.then((stop) => stop());
    stopShow();
    for (const unbind of unbindKeys) unbind();
  });

  // A tool back from its own window takes the keyboard if it's in this view,
  // whether it came back through [dock back] or the window's close button.
  let lastPopped: PanelId[] = [];
  function focusDockedBack(now: PanelId[]) {
    const back = lastPopped.find((id) => !now.includes(id));
    if (back && present.includes(back)) focused = back;
    lastPopped = now;
  }
  $: focusDockedBack($poppedPanels.popped);

  const SIDES: Record<string, Side> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };

  // The rack's keys, after the tools' (keys.ts, which already stands down
  // for a dialog). Bare 1–8 bring up a view, unless a field has the caret
  // or a menu is open. ⌘⌥ arrows cross the rail: a tool takes the chord
  // first while it has somewhere to go inside (Legend Lore's dock and file
  // pane), and leaves it here at its edge, where the keyboard goes to the
  // tool beside it in the view's layout.
  function rackKeys(e: KeyboardEvent, ctx: KeyContext): boolean {
    if (e.isComposing) return false;
    const meta = e.metaKey || e.ctrlKey;
    if (meta && e.altKey && !e.shiftKey && SIDES[e.key] && focused) {
      const to = neighbour(placed.rects, focusable, focused, SIDES[e.key]);
      if (!to) return false;
      focused = to;
      return true;
    }
    if (meta || e.altKey || e.shiftKey) return false;
    const digit = /^Digit([1-8])$/.exec(e.code);
    if (!digit || ctx.menu || ctx.typing) return false;
    switchTo(Number(digit[1]) - 1);
    return true;
  }
  const unbindKeys = [
    bindKeys(hostKeys({ settings: () => showSettings('general'), shortcuts: () => (showHelp = true) })),
    bindKeys(rackKeys),
  ];

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

  // The whole rack comes back into sight, to be landed on.
  function carry(id: PanelId, data: DataTransfer) {
    filling = null;
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

  // Settings lives with Legend Lore for now; out in its own window, that
  // window comes forward to show it.
  function showSettings(tab: 'general' | 'help') {
    if (popped.has('legend-lore')) report(popOut('legend-lore'), 'bring Legend Lore forward');
    report(openSettings(tab), 'open settings');
  }
</script>

<svelte:window on:keydown={dispatchKey} />

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
          class:keyed={focused === tool.id}
          class:filled={filled === tool.id}
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
            <PanelView
              id={tool.id}
              active={!!r && focused === tool.id}
              statusSlot={statusSlots[tool.id] ?? null}
              filled={filled === tool.id}
              onFill={(on) => (filling = on ? tool.id : null)}
            >
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

  <StatusBar
    onOpenSettings={() => showSettings('general')}
    onOpenHelp={() => showSettings('help')}
    onShowShortcuts={() => (showHelp = true)}
  >
    {#each RACK_TOOLS as tool (tool.id)}
      <div class="status-section" bind:this={statusSlots[tool.id]}></div>
    {/each}
  </StatusBar>

  <KeyboardHelpOverlay visible={showHelp} onClose={() => (showHelp = false)} />
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

  /* Inset by a rail at either side, so the frame runs as evenly round the
     outer edges as between tools. A margin, not padding: the slots are
     placed from the rack's own box, which bind:clientWidth measures. */
  .rack {
    position: relative;
    flex: 1;
    min-height: 0;
    margin: 0 var(--rail);
  }
  .rack.resizing {
    user-select: none;
  }

  /* Each tool sits boxed: its header plate runs down both sides and across
     the foot as a thin edge, so neighbours read as separate units across
     the rail. */
  .slot {
    position: absolute;
    display: none;
    overflow: hidden;
    background: var(--bg-app);
    border: 3px solid var(--bg-header);
    border-top: none;
    border-radius: var(--radius-md);
  }
  .slot.shown {
    display: block;
  }
  /* Covering the rack, the tool has set its header aside: the edge closes
     over the top too. */
  .slot.filled {
    border-top: 3px solid var(--bg-header);
  }
  /* The tool with the keyboard: its frame one grey step up, the DAW's
     focused panel, where the eye is. Not a raised key in the bar — both
     tools are open, and the keyboard isn't a pick. */
  .slot.keyed {
    border-color: var(--border-frame-keyed);
  }
  /* The box has no top edge of its own — the tool's header plate closes it
     in the frame's grey — so the keyed frame paints its top as a strip
     over the plate, no layout shift. The filled slot draws a real top edge
     (above), coloured by the rule before, so it needs none. */
  .slot.keyed:not(.filled)::before {
    content: '';
    position: absolute;
    inset: 0 0 auto 0;
    height: 3px;
    background: var(--border-frame-keyed);
    z-index: 1;
    pointer-events: none;
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
