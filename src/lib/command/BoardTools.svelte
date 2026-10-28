<script lang="ts">
  // The board's toolbar (board toolbar design §3): Miro's tools in a column
  // of keys on the board's right edge, under the expand key, then undo, redo
  // and fit in a well below, and Arrange by beat at the foot (§6). The current tool's key is raised, as a well's
  // pick is; any tool but Select lights its lamp purple, since it changes
  // what a click on the board does. A tool that makes something hands back
  // to Select once it has (one shot, as Miro's do).
  import { chordHint } from '../shell/keybindings';
  import type { Tool } from './board';
  import { m } from '../paraglide/messages';

  export let tool: Tool;
  export let onTool: (tool: Tool) => void;
  export let canUndo: boolean;
  export let canRedo: boolean;
  export let onUndo: () => void;
  export let onRedo: () => void;
  /** The whole board in view, as the beat rows' frame key frames a beat. */
  export let onFit: () => void;
  /** Whether the session plans a beat to arrange by. */
  export let canArrange: boolean;
  export let onArrange: () => void;

  // Font Awesome Free 7.3.1 glyphs, viewBox 0 0 640 640; each from the
  // file named beside it in src/lib/ui/icons/.
  const TOOLS: { tool: Tool; name: () => string; chord: string; path: string }[] = [
    {
      tool: 'select',
      name: m.command_tools_select,
      chord: 'command.boardSelect',
      // arrow-pointer-solid-full.svg
      path: 'M173.3 66.5C181.4 62.4 191.2 63.3 198.4 68.8L518.4 308.7C526.7 314.9 530 325.7 526.8 335.5C523.6 345.3 514.4 351.9 504 351.9L351.7 351.9L440.6 529.6C448.5 545.4 442.1 564.6 426.3 572.5C410.5 580.4 391.3 574 383.4 558.2L294.5 380.5L203.2 502.3C197 510.6 186.2 513.9 176.4 510.7C166.6 507.5 160 498.3 160 488L160 88C160 78.9 165.1 70.6 173.3 66.5z',
    },
    {
      tool: 'hand',
      name: m.command_tools_hand,
      chord: 'command.boardHand',
      // hand-solid-full.svg
      path: 'M352 96C352 78.3 337.7 64 320 64C302.3 64 288 78.3 288 96L288 304C288 312.8 280.8 320 272 320C263.2 320 256 312.8 256 304L256 128C256 110.3 241.7 96 224 96C206.3 96 192 110.3 192 128L192 400C192 401.5 192 403.1 192.1 404.6L131.6 347C115.6 331.8 90.3 332.4 75 348.4C59.7 364.4 60.4 389.7 76.4 405L188.8 512C231.9 553.1 289.2 576 348.8 576L368 576C465.2 576 544 497.2 544 400L544 192C544 174.3 529.7 160 512 160C494.3 160 480 174.3 480 192L480 304C480 312.8 472.8 320 464 320C455.2 320 448 312.8 448 304L448 128C448 110.3 433.7 96 416 96C398.3 96 384 110.3 384 128L384 304C384 312.8 376.8 320 368 320C359.2 320 352 312.8 352 304L352 96z',
    },
    {
      tool: 'note',
      name: m.command_tools_note,
      chord: 'command.boardNote',
      // file-lines-solid-full.svg
      path: 'M128 128C128 92.7 156.7 64 192 64L341.5 64C358.5 64 374.8 70.7 386.8 82.7L493.3 189.3C505.3 201.3 512 217.6 512 234.6L512 512C512 547.3 483.3 576 448 576L192 576C156.7 576 128 547.3 128 512L128 128zM336 122.5L336 216C336 229.3 346.7 240 360 240L453.5 240L336 122.5zM248 320C234.7 320 224 330.7 224 344C224 357.3 234.7 368 248 368L392 368C405.3 368 416 357.3 416 344C416 330.7 405.3 320 392 320L248 320zM248 416C234.7 416 224 426.7 224 440C224 453.3 234.7 464 248 464L392 464C405.3 464 416 453.3 416 440C416 426.7 405.3 416 392 416L248 416z',
    },
    {
      tool: 'text',
      name: m.command_tools_text,
      chord: 'command.boardText',
      // font-solid-full.svg
      path: 'M349.1 114.7C343.9 103.3 332.5 96 320 96C307.5 96 296.1 103.3 290.9 114.7L123.5 480L112 480C94.3 480 80 494.3 80 512C80 529.7 94.3 544 112 544L200 544C217.7 544 232 529.7 232 512C232 494.3 217.7 480 200 480L193.9 480L215.9 432L424.2 432L446.2 480L440.1 480C422.4 480 408.1 494.3 408.1 512C408.1 529.7 422.4 544 440.1 544L528.1 544C545.8 544 560.1 529.7 560.1 512C560.1 494.3 545.8 480 528.1 480L516.6 480L349.2 114.7zM394.8 368L245.2 368L320 204.8L394.8 368z',
    },
    {
      tool: 'sticky',
      name: m.command_tools_sticky,
      chord: 'command.boardSticky',
      // note-sticky-solid-full.svg
      path: 'M160 544C124.7 544 96 515.3 96 480L96 160C96 124.7 124.7 96 160 96L480 96C515.3 96 544 124.7 544 160L544 373.5C544 390.5 537.3 406.8 525.3 418.8L418.7 525.3C406.7 537.3 390.4 544 373.4 544L160 544zM485.5 368L392 368C378.7 368 368 378.7 368 392L368 485.5L485.5 368z',
    },
    {
      tool: 'line',
      name: m.command_tools_line,
      chord: 'command.boardLine',
      // diagram-project-solid-full.svg
      path: 'M64 144C64 117.5 85.5 96 112 96L208 96C234.5 96 256 117.5 256 144L256 160L384 160L384 144C384 117.5 405.5 96 432 96L528 96C554.5 96 576 117.5 576 144L576 240C576 266.5 554.5 288 528 288L432 288C405.5 288 384 266.5 384 240L384 224L256 224L256 240C256 247.3 254.3 254.3 251.4 260.5L320 352L400 352C426.5 352 448 373.5 448 400L448 496C448 522.5 426.5 544 400 544L304 544C277.5 544 256 522.5 256 496L256 400C256 392.7 257.7 385.7 260.6 379.5L192 288L112 288C85.5 288 64 266.5 64 240L64 144z',
    },
    {
      tool: 'frame',
      name: m.command_tools_frame,
      chord: 'command.boardFrame',
      // object-group-solid-full.svg
      path: 'M64 183.4C44.9 172.4 32 151.7 32 128C32 92.7 60.7 64 96 64C119.7 64 140.4 76.9 151.4 96L488.5 96C499.6 76.9 520.2 64 543.9 64C579.2 64 607.9 92.7 607.9 128C607.9 151.7 595 172.4 575.9 183.4L575.9 456.5C595 467.6 607.9 488.2 607.9 511.9C607.9 547.2 579.2 575.9 543.9 575.9C520.2 575.9 499.5 563 488.5 543.9L151.4 543.9C140.3 563 119.7 575.9 96 575.9C60.7 575.9 32 547.2 32 511.9C32 488.2 44.9 467.5 64 456.5L64 183.4zM512 183.4C502.3 177.8 494.2 169.7 488.6 160L151.4 160C145.8 169.7 137.7 177.8 128 183.4L128 456.5C137.7 462.1 145.8 470.2 151.4 479.9L488.5 479.9C494.1 470.2 502.2 462.1 511.9 456.5L511.9 183.4zM176 240C176 222.3 190.3 208 208 208L320 208C337.7 208 352 222.3 352 240L352 304C352 321.7 337.7 336 320 336L208 336C190.3 336 176 321.7 176 304L176 240zM288 384L320 384C364.2 384 400 348.2 400 304L432 304C449.7 304 464 318.3 464 336L464 400C464 417.7 449.7 432 432 432L320 432C302.3 432 288 417.7 288 400L288 384z',
    },
  ];

  // rotate-left-solid-full.svg
  const UNDO =
    'M88 256L232 256C241.7 256 250.5 250.2 254.2 241.2C257.9 232.2 255.9 221.9 249 215L202.3 168.3C277.6 109.7 386.6 115 455.8 184.2C530.8 259.2 530.8 380.7 455.8 455.7C380.8 530.7 259.3 530.7 184.3 455.7C174.1 445.5 165.3 434.4 157.9 422.7C148.4 407.8 128.6 403.4 113.7 412.9C98.8 422.4 94.4 442.2 103.9 457.1C113.7 472.7 125.4 487.5 139 501C239 601 401 601 501 501C601 401 601 239 501 139C406.8 44.7 257.3 39.3 156.7 122.8L105 71C98.1 64.2 87.8 62.1 78.8 65.8C69.8 69.5 64 78.3 64 88L64 232C64 245.3 74.7 256 88 256z';
  // expand-solid-full.svg, the beat rows' frame key
  const FIT =
    'M128 96C110.3 96 96 110.3 96 128L96 224C96 241.7 110.3 256 128 256C145.7 256 160 241.7 160 224L160 160L224 160C241.7 160 256 145.7 256 128C256 110.3 241.7 96 224 96L128 96zM160 416C160 398.3 145.7 384 128 384C110.3 384 96 398.3 96 416L96 512C96 529.7 110.3 544 128 544L224 544C241.7 544 256 529.7 256 512C256 494.3 241.7 480 224 480L160 480L160 416zM416 96C398.3 96 384 110.3 384 128C384 145.7 398.3 160 416 160L480 160L480 224C480 241.7 494.3 256 512 256C529.7 256 544 241.7 544 224L544 128C544 110.3 529.7 96 512 96L416 96zM544 416C544 398.3 529.7 384 512 384C494.3 384 480 398.3 480 416L480 480L416 480C398.3 480 384 494.3 384 512C384 529.7 398.3 544 416 544L512 544C529.7 544 544 529.7 544 512L544 416z';
  // table-cells-large-solid-full.svg
  const ARRANGE =
    'M480 160L352 160L352 288L480 288L480 160zM544 288L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 160C96 124.7 124.7 96 160 96L480 96C515.3 96 544 124.7 544 160L544 288zM160 352L160 480L288 480L288 352L160 352zM288 288L288 160L160 160L160 288L288 288zM352 352L352 480L480 480L480 352L352 352z';
  // rotate-right-solid-full.svg
  const REDO =
    'M552 256L408 256C398.3 256 389.5 250.2 385.8 241.2C382.1 232.2 384.1 221.9 391 215L437.7 168.3C362.4 109.7 253.4 115 184.2 184.2C109.2 259.2 109.2 380.7 184.2 455.7C259.2 530.7 380.7 530.7 455.7 455.7C463.9 447.5 471.2 438.8 477.6 429.6C487.7 415.1 507.7 411.6 522.2 421.7C536.7 431.8 540.2 451.8 530.1 466.3C521.6 478.5 511.9 490.1 501 501C401 601 238.9 601 139 501C39.1 401 39 239 139 139C233.3 44.7 382.7 39.4 483.3 122.8L535 71C541.9 64.1 552.2 62.1 561.2 65.8C570.2 69.5 576 78.3 576 88L576 232C576 245.3 565.3 256 552 256z';
</script>

<div class="tools" role="toolbar" aria-label={m.command_tools_label()} aria-orientation="vertical">
  <div class="well">
    {#each TOOLS as t (t.tool)}
      <button
        type="button"
        class="key"
        class:open={tool === t.tool}
        aria-pressed={tool === t.tool}
        title={t.name() + chordHint(t.chord)}
        aria-label={t.name()}
        on:click={() => onTool(t.tool)}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={t.path} /></svg>
        <!-- Select is the board at rest: its lamp stays dark, as the bank's
             do while no mode is on. -->
        <span class="lamp" class:lit={tool === t.tool && t.tool !== 'select'} aria-hidden="true"></span>
      </button>
    {/each}
  </div>
  <div class="well">
    <button
      type="button"
      class="key"
      disabled={!canUndo}
      title={m.command_tools_undo() + chordHint('command.boardUndo')}
      aria-label={m.command_tools_undo()}
      on:click={onUndo}
    >
      <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={UNDO} /></svg>
    </button>
    <button
      type="button"
      class="key"
      disabled={!canRedo}
      title={m.command_tools_redo() + chordHint('command.boardRedo')}
      aria-label={m.command_tools_redo()}
      on:click={onRedo}
    >
      <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={REDO} /></svg>
    </button>
    <button
      type="button"
      class="key"
      title={m.command_tools_fit() + chordHint('command.boardFitAll')}
      aria-label={m.command_tools_fit()}
      on:click={onFit}
    >
      <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={FIT} /></svg>
    </button>
  </div>
  <div class="well">
    <button
      type="button"
      class="key"
      disabled={!canArrange}
      title={canArrange ? m.command_tools_arrange_title() : m.command_tools_arrange_none()}
      aria-label={m.command_tools_arrange()}
      on:click={onArrange}
    >
      <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={ARRANGE} /></svg>
    </button>
  </div>
</div>

<style>
  .tools {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  /* LatchKey's well and keys, stacked: one well for the tools, one for
     undo, redo and fit, one for Arrange. */
  .well {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .key {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 26px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
  }

  .key:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .key:active:not(:disabled) {
    transform: scale(0.97);
  }

  .key.open {
    background: var(--bg-header);
    color: var(--text-primary);
  }

  /* As the S/M switches: present but inert. */
  .key:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .key svg {
    width: 12px;
    height: 12px;
  }

  /* LatchKey's LED: a dark slot at rest, purple and glowing when lit, an
     empty socket where there's nothing to report. */
  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .key.open .lamp {
    background: var(--bg-app);
  }

  .lamp.lit,
  .key.open .lamp.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }
</style>
