<script lang="ts">
  // The spend key: Legend Lore's transport well with the box shut on a note
  // or beat. Spent or not it's the transport's grey: the spent row or card
  // says so, dimmed, and a row keeps the key showing while it's spent. A
  // card shows it always; a row while spent, hovered or focused.
  import { chordHint } from '../shell/keybindings';

  /** The date it was spent, or null. */
  export let spent: string | null;
  export let name: string;
  export let onToggle: () => void;
</script>

<!-- A double-click's first click only, and none of it reaches the row or
     card, whose double-click opens the note. nodrag: a card's board leaves
     the key to it. -->
<button
  type="button"
  class="spend-key nodrag"
  aria-pressed={!!spent}
  aria-label={`${name} spent`}
  title={(spent ? `${name} — spent ${spent}: mark unspent` : `Mark ${name} spent`) + chordHint('command.spend')}
  on:click|stopPropagation={(e) => e.detail <= 1 && onToggle()}
  on:dblclick|stopPropagation
>
  <!-- Font Awesome "box-archive" icon (src/lib/ui/icons/box-archive-solid-full.svg),
       its viewBox cropped to the glyph. -->
  <svg viewBox="64 96 512 448" fill="currentColor" aria-hidden="true">
    <path d="M64 128C64 110.3 78.3 96 96 96L544 96C561.7 96 576 110.3 576 128L576 160C576 177.7 561.7 192 544 192L96 192C78.3 192 64 177.7 64 160L64 128zM96 240L544 240L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 240zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z" />
  </svg>
</button>

<style>
  /* Legend Lore's transport well (CollectionsPanel .tr-btn). */
  .spend-key {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .spend-key:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .spend-key:active {
    transform: scale(0.97);
  }

  svg {
    display: block;
    width: 10px;
    height: 10px;
  }
</style>
