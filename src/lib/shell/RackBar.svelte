<script lang="ts">
  // The main window's bar: the rack's eight views, then one well per tool
  // (PANELS.md). A tool's key mounts it in the current view or gives it the
  // keyboard, takes it out when pressed again, and carries it into the rack
  // by hand; its lamp is lit while the tool is in this view. Which tool has
  // the keyboard shows on its frame in the rack (PanelHost), not here: the
  // bar's keys are not a picker, both tools are open. The lock beside the
  // view picker holds the view that's showing: no mount or take-out, no
  // carry, no resize, no pop-out. On macOS
  // the bar is the window's title bar too: the title bar is an overlay
  // (tauri.conf.json), the traffic lights sit at its left end, and its bare
  // plate drags the window.
  import { grab } from '../ui/grab';
  import LatchKey from '../ui/LatchKey.svelte';
  import { MARK, MARK_VIEWBOX } from '../ui/iconPaths';
  import { m } from '../paraglide/messages';
  import { panelTitle, type PanelId } from './panels';
  import { RACK_TOOLS, toolsIn, type RackView } from './rack';

  export let views: RackView[];
  export let current: number;
  export let focused: PanelId | null;
  export let popped: ReadonlySet<PanelId>;
  export let onSwitch: (view: number) => void;
  export let onToggle: (id: PanelId) => void;
  export let onLockView: () => void;
  export let onCarry: (id: PanelId, data: DataTransfer) => void;
  export let onCarryEnd: () => void;

  // Only macOS overlays its title bar; elsewhere the native one stays above.
  const overlaid = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || '');

  $: present = toolsIn(views[current].root);
  $: locked = views[current].locked;

  function viewTitle(v: RackView, i: number): string {
    const tools = toolsIn(v.root).map(panelTitle);
    return m.rack_view_title({ n: i + 1, tools: tools.length ? tools.join(' · ') : m.rack_view_title_empty() });
  }

  function keyTitle(id: PanelId, title: string): string {
    if (!present.includes(id)) {
      return locked ? m.rack_key_mount_locked({ n: current + 1, tool: title }) : m.rack_key_mount({ tool: title });
    }
    if (focused !== id && !popped.has(id)) return m.rack_key_keyboard({ tool: title });
    if (locked) return m.rack_key_stays({ tool: title, n: current + 1 });
    if (popped.has(id)) return m.rack_key_popped({ tool: title });
    return m.rack_key_take_out({ tool: title });
  }

  function carry(e: DragEvent, id: PanelId) {
    if (e.dataTransfer) onCarry(id, e.dataTransfer);
  }
</script>

<nav class="rack-bar" class:overlaid aria-label={m.rack_label()} data-tauri-drag-region>
  <!-- A picker, like the view switch: one view is always showing, so the
       current key sits raised rather than lit. An empty view's numeral
       steps down to the out-of-scope dim. -->
  <div class="view-group">
    <div class="view-keys" role="group" aria-label={m.rack_views()}>
      {#each views as v, i}
        <button
          class="view-key"
          class:current={i === current}
          class:empty={!v.root}
          aria-pressed={i === current}
          title={viewTitle(v, i)}
          on:click={() => onSwitch(i)}
        >{i + 1}</button>
      {/each}
    </div>
    <!-- The view's lock, a latch beside the picker reporting the view that
         shows: locked, it comes up on the raised fill with its lamp lit,
         as the gem does with its panel open and engaged. -->
    <LatchKey
      open={locked}
      lit={locked}
      title={locked ? m.rack_unlock({ n: current + 1 }) : m.rack_lock_title({ n: current + 1 })}
      label={locked ? m.rack_unlock({ n: current + 1 }) : m.rack_lock_label({ n: current + 1 })}
      onClick={onLockView}
    >
      <!-- Font Awesome "lock" icon (src/lib/ui/icons/lock-solid-full.svg) -->
      <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M256 160L256 224L384 224L384 160C384 124.7 355.3 96 320 96C284.7 96 256 124.7 256 160zM192 224L192 160C192 89.3 249.3 32 320 32C390.7 32 448 89.3 448 160L448 224C483.3 224 512 252.7 512 288L512 512C512 547.3 483.3 576 448 576L192 576C156.7 576 128 547.3 128 512L128 288C128 252.7 156.7 224 192 224z"/>
      </svg>
    </LatchKey>
  </div>

  <div class="tool-wells" role="group" aria-label={m.rack_tools()} data-tauri-drag-region>
    {#each RACK_TOOLS as tool (tool.id)}
      {@const here = present.includes(tool.id)}
      <div class="tool-well">
        <button
          class="key tool-key"
          class:away={popped.has(tool.id)}
          title={keyTitle(tool.id, tool.title)}
          aria-pressed={here}
          use:grab={!locked}
          on:dragstart={(e) => carry(e, tool.id)}
          on:dragend={onCarryEnd}
          on:click={() => onToggle(tool.id)}
        >
          <span class="cell" class:lit={here} aria-hidden="true"></span>
          <span class="tool-name">{tool.title}</span>
        </button>
      </div>
    {/each}
  </div>

  <!-- The splash's name and mark, small, at the bar's far end. The pointer
       passes through, so a press here drags the window as the bare plate
       does. -->
  <span class="brand">
    <span class="wordmark">Unseen Servant</span>
    <svg class="mark" viewBox={MARK_VIEWBOX} aria-hidden="true"><path d={MARK} /></svg>
  </span>
</nav>

<style>
  /* The tools' header plate (Header .header, Command's .bar). */
  .rack-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    height: var(--header-height);
    padding: 0 0.5rem;
    background: var(--bg-header);
  }
  /* Room for the traffic lights, then 12px before the view keys. Placed at
     x 16 (tauri.conf.json), the buttons end near 76px: a 23.5px pitch and
     15px across, measured off a macOS 26 screenshot. */
  .rack-bar.overlaid {
    padding-left: 88px;
  }

  /* The splash's mark and wordmark, small and quiet: chrome, not content. */
  .brand {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin: 0 0.5rem 0 auto;
    color: var(--text-tertiary);
    pointer-events: none;
  }
  /* Sized by height, the width following the mark's 685 × 960 ink. */
  .mark {
    flex-shrink: 0;
    width: 14px;
    height: 20px;
    fill: currentColor;
  }
  .wordmark {
    font-family: var(--font-heading);
    font-size: 0.8rem;
    line-height: 1;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }

  /* The picker and its lock, closer than the bar's other groups. */
  .view-group {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  /* Wells cut like Header's view switch. */
  .view-keys,
  .tool-well {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .view-key,
  .key {
    height: 22px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .view-key:hover,
  .key:hover {
    color: var(--text-primary);
  }
  .view-key:active,
  .key:active {
    transform: scale(0.97);
  }

  /* Crimson, not Almendra: Almendra's figures are old-style only, so 3, 4,
     5 and 7 hang below the line. Crimson's sit level, one height. */
  .view-key {
    width: 22px;
    font-family: var(--font-body);
    font-size: 0.85rem;
    line-height: 1;
    font-variant-numeric: lining-nums tabular-nums;
  }
  .view-key.empty {
    opacity: var(--opacity-out-of-scope);
  }
  .view-key.empty:hover {
    opacity: var(--opacity-out-of-scope-hover);
  }
  .view-key.current {
    background: var(--bg-header);
    color: var(--text-primary);
    opacity: 1;
  }

  .tool-wells {
    display: flex;
    gap: 0.3rem;
  }

  .key {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .tool-key {
    gap: 0.4rem;
    padding: 0 0.6rem 0 0.5rem;
    touch-action: none;
  }
  .tool-name {
    font-family: var(--font-heading);
    font-size: 0.85rem;
    line-height: 12px;
  }
  .tool-key.away .tool-name {
    opacity: var(--opacity-out-of-scope);
  }

  /* LatchKey's lamp as a square cell ahead of the name: dark at rest, lit in
     the transport's purple while the tool is in this view. */
  .cell {
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

</style>
