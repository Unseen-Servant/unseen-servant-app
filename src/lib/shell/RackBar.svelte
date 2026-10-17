<script lang="ts">
  // The main window's bar: the rack's eight views, then one well per tool
  // (PANELS.md). A tool's key mounts it in the current view or gives it the
  // keyboard, takes it out when pressed again, and carries it into the rack
  // by hand; its lamp is lit while the tool is in this view, and the raised
  // fill marks the one that has the keyboard. The lock beside it holds the
  // tool in this view: no pop-out, no resizing, no drops onto it. On macOS
  // the bar is the window's title bar too: the title bar is an overlay
  // (tauri.conf.json), the traffic lights sit at its left end, and its bare
  // plate drags the window.
  import { grab } from '../ui/grab';
  import { MARK, MARK_VIEWBOX } from '../ui/iconPaths';
  import { panelTitle, type PanelId } from './panels';
  import { RACK_TOOLS, toolsIn, type RackView } from './rack';

  export let views: RackView[];
  export let current: number;
  export let focused: PanelId | null;
  export let popped: ReadonlySet<PanelId>;
  export let onSwitch: (view: number) => void;
  export let onToggle: (id: PanelId) => void;
  export let onLock: (id: PanelId) => void;
  export let onCarry: (id: PanelId, data: DataTransfer) => void;
  export let onCarryEnd: () => void;

  // Only macOS overlays its title bar; elsewhere the native one stays above.
  const overlaid = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || '');

  $: present = toolsIn(views[current].root);
  $: locked = views[current].locked;

  function viewTitle(v: RackView, i: number): string {
    const tools = toolsIn(v.root).map(panelTitle);
    return `View ${i + 1} — ${tools.length ? tools.join(' · ') : 'empty'} (${i + 1})`;
  }

  function keyTitle(id: PanelId, title: string): string {
    if (!present.includes(id)) return `Mount ${title} in this view — or drag it where it should go`;
    if (focused !== id && !popped.has(id)) return `Give ${title} the keyboard`;
    if (locked.includes(id)) return `${title} is locked in this view`;
    if (popped.has(id)) return `${title} is in its own window — press to take it out of this view`;
    return `Take ${title} out of this view — or drag it to move it`;
  }

  function carry(e: DragEvent, id: PanelId) {
    if (e.dataTransfer) onCarry(id, e.dataTransfer);
  }
</script>

<nav class="rack-bar" class:overlaid aria-label="Rack" data-tauri-drag-region>
  <!-- A picker, like the view switch: one view is always showing, so the
       current key sits raised rather than lit. An empty view's numeral
       steps down to the out-of-scope dim. -->
  <div class="view-keys" role="group" aria-label="Rack views">
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

  <div class="tool-wells" role="group" aria-label="Tools" data-tauri-drag-region>
    {#each RACK_TOOLS as tool (tool.id)}
      {@const here = present.includes(tool.id)}
      {@const held = locked.includes(tool.id)}
      <div class="tool-well">
        <button
          class="key tool-key"
          class:open={focused === tool.id}
          class:away={popped.has(tool.id)}
          title={keyTitle(tool.id, tool.title)}
          aria-pressed={here}
          use:grab={!held}
          on:dragstart={(e) => carry(e, tool.id)}
          on:dragend={onCarryEnd}
          on:click={() => onToggle(tool.id)}
        >
          <span class="cell" class:lit={here} aria-hidden="true"></span>
          <span class="tool-name">{tool.title}</span>
        </button>
        <button
          class="key lock-key"
          title={held ? `Unlock ${tool.title}` : `Lock ${tool.title} in this view: no pop-out, no resizing`}
          aria-label={held ? `Unlock ${tool.title}` : `Lock ${tool.title}`}
          aria-pressed={held}
          disabled={!here}
          on:click={() => onLock(tool.id)}
        >
          {#if held}
            <!-- Font Awesome "lock" icon (src/lib/ui/icons/lock-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M256 160L256 224L384 224L384 160C384 124.7 355.3 96 320 96C284.7 96 256 124.7 256 160zM192 224L192 160C192 89.3 249.3 32 320 32C390.7 32 448 89.3 448 160L448 224C483.3 224 512 252.7 512 288L512 512C512 547.3 483.3 576 448 576L192 576C156.7 576 128 547.3 128 512L128 288C128 252.7 156.7 224 192 224z"/>
            </svg>
          {:else}
            <!-- Font Awesome "lock-open" icon (src/lib/ui/icons/lock-open-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M416 160C416 124.7 444.7 96 480 96C515.3 96 544 124.7 544 160L544 192C544 209.7 558.3 224 576 224C593.7 224 608 209.7 608 192L608 160C608 89.3 550.7 32 480 32C409.3 32 352 89.3 352 160L352 224L192 224C156.7 224 128 252.7 128 288L128 512C128 547.3 156.7 576 192 576L448 576C483.3 576 512 547.3 512 512L512 288C512 252.7 483.3 224 448 224L416 224L416 160z"/>
            </svg>
          {/if}
          <span class="lamp" class:lit={held} aria-hidden="true"></span>
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
    width: 17px;
    height: 24px;
    fill: currentColor;
  }
  .wordmark {
    font-family: var(--font-heading);
    font-size: 0.8rem;
    line-height: 1;
    letter-spacing: 0.01em;
    white-space: nowrap;
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
  .key.open {
    background: var(--bg-header);
    color: var(--text-primary);
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
  .key.open .cell {
    background: var(--bg-app);
  }
  .cell.lit,
  .key.open .cell.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }

  /* The lock is a latch, LatchKey rule for rule: the icon over its lamp. */
  .lock-key {
    flex-direction: column;
    gap: 3px;
    width: 26px;
  }
  .lock-key svg {
    width: 12px;
    height: 12px;
  }
  .lock-key:disabled {
    opacity: var(--opacity-out-of-scope);
    cursor: default;
    pointer-events: none;
  }
  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }
  .lamp.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }
</style>
