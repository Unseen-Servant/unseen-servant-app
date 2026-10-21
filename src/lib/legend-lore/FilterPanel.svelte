<script lang="ts">
  // The filter panel: the mixer console for the unified S/M model,
  // docked in the left pane as the collections panel's sibling. Every
  // row is a channel — glyph, name, S/M buttons, LED count. The scope
  // bar stays the readout: engaging S/M here materializes a chip there,
  // and clearing a chip resets the row. Unlike the old dropdown console,
  // S/M are hover-revealed like the tree's folder rows — the panel is
  // furniture, not a popover.
  import { afterUpdate, tick, onDestroy } from 'svelte';
  import { computeFilterRows, sectionHeaderKey, stepFilterRow } from './filterRows';
  import { materializeKey } from '../shell/paneFocus';
  import { holdLatch } from '../ui/holdLatch';
  import { bindKeys, type KeyContext } from '../shell/keys';
  import { jumpEdge } from '../shell/keybindings';
  import { UNTAGGED_KEY } from './searchScope';
  import type { CurationKey } from './searchScope';
  import type { FilterSection } from './filterRows';
  import { CARET_RIGHT, GEM, GEM_OUTLINE, SHIELD } from '../ui/iconPaths';
  import { hoverLive } from '../ui/inputModality';

  // DAW-style filter state for game systems.
  //   - excludedSystems: muted rows (M lit). Empty = nothing muted.
  //   - soloedSystems:   solo'd rows. When non-empty, mute is overridden:
  //                      only solo'd systems pass, regardless of which
  //                      rows are muted. This matches Logic Pro / Ableton.
  //                      Untagged files don't pass under solos.
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let onToggleSystem: (system: string) => void = () => {};
  export let onToggleSolo: (system: string) => void = () => {};

  // Available systems (with counts) — typically gameSystemStats from +page.
  export let systems: { name: string; count: number }[] = [];

  // Count of indexed files with no game-system tag. Rendered as a
  // mute-only "Untagged" channel (key: UNTAGGED_KEY) so muting a real
  // system doesn't silently drop untagged files from search (issue #307).
  // No solo button — solo means "focus on these systems" and untagged
  // files never pass under solos; an 18px spacer keeps the column honest.
  export let untaggedCount: number = 0;

  // Whether the Game systems section is meaningful in the current context.
  // System tags are the organizing axis of the systems view, so we only
  // expose the filter there — in tree view it's a foreign content filter
  // over a filesystem-shaped structure.
  export let showSystemFilter: boolean = true;

  // Hidden items section. `hiddenCount` is the number of explicitly-hidden
  // paths (folders count as 1 each — descendants are implicit). The row
  // toggles `showHidden`; when count is 0 the row is disabled. This row
  // keeps its checkbox — it reveals, it doesn't narrow.
  export let showHidden: boolean = false;
  export let hiddenCount: number = 0;
  export let onToggleShowHidden: () => void = () => {};
  export let onClearHidden: () => void = () => {};

  // Focus lens (spec: scope doctrine) — hide out-of-scope rows on the
  // browsing surfaces (tree, systems view). Console surfaces — this
  // panel, the collections panel, the scope bar — never hide.
  export let hideOutOfScope: boolean = false;
  export let onToggleHideOutOfScope: () => void = () => {};

  // "Hide unindexed items" — the bulk gesture for material scope can't
  // speak about, sibling to per-item hide.
  export let hideUnindexed: boolean = false;
  export let onToggleHideUnindexed: () => void = () => {};
  // "Hide images": the pictures the tree lists beside the books (images
  // design §6), out of the way when token packs would bury them.
  export let hideImages: boolean = false;
  export let onToggleHideImages: () => void = () => {};

  // Where this pane's caret is. null means no cursor is drawn — which is
  // distinct from not holding the keyboard (the focus path, focus.ts).
  export let focusedRow: string | null = null;
  // A click anywhere in the panel activates the pane without ringing a row;
  // the first arrow then materializes the caret. Until this existed the panel
  // had no mouse entry point at all — Cmd+Alt+↓ was the only way in.
  export let onActivate: () => void = () => {};
  // Where that first arrow lands, remembered by the page.
  export let lastFocusedRow: string | null = null;
  export let onFocusRow: (key: string | null) => void = () => {};

  // Curation section: two channels over the collected/loose domain,
  // the third narrowing axis (same union/intersect/solo-overrides-mute
  // semantics as systems and collections). Soloing Collected is the old
  // "show only collection"; soloing Loose is the old "show only loose";
  // nothing engaged = show all. The parent gates the section via
  // `showCollectionFilter`.
  export let showCollectionFilter: boolean = false;
  export let collectedCount: number = 0;
  export let uncollectedCount: number = 0;
  export let curationSolos: Set<CurationKey> = new Set();
  export let curationMutes: Set<CurationKey> = new Set();
  export let onToggleCurationSolo: (key: CurationKey) => void = () => {};
  export let onToggleCurationMute: (key: CurationKey) => void = () => {};

  // Masthead [reset]: clears every solo/mute on all axes — the same action
  // as clearing each chip in the scope bar. `canReset` is the page's answer
  // to "is any of that engaged?", which this panel can't work out on its
  // own: half the axes it resets (file scope, collection plays and mutes)
  // never reach it as props. Unset means nothing to reset, so the control
  // sits dim rather than offering a no-op.
  export let onClearAll: () => void = () => {};
  export let canReset: boolean = false;

  let panelEl: HTMLElement;

  // Sections folded shut. Session state, like the systems view's collapsed
  // groups. Headers are rows, so folding only ever happens with the caret
  // on the header (a click parks it there) — never under a caret inside.
  let collapsed = new Set<FilterSection>();
  function toggleSection(section: FilterSection) {
    if (collapsed.has(section)) collapsed.delete(section);
    else collapsed.add(section);
    collapsed = collapsed;
  }
  function clickHeader(section: FilterSection) {
    toggleSection(section);
    clickRow(sectionHeaderKey(section));
  }

  // The navigable row set, derived not queried. Order is the j/k order.
  $: rows = computeFilterRows({
    hasHidden,
    showCollectionFilter,
    showSystemFilter,
    systems,
    untaggedCount,
    collapsed,
  });

  function rowElByKey(key: string): HTMLElement | null {
    return panelEl?.querySelector<HTMLElement>(`[data-fm-key="${CSS.escape(key)}"]`) ?? null;
  }

  // A mousedown on the panel's empty or non-selectable space — the masthead,
  // [reset], the gap below the rows — points at the pane and deselects. Rows are
  // skipped so their own click (below) owns the caret, and so that mousing
  // an S/M button doesn't drop a caret parked on some other row.
  function handlePanelMousedown(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-fm-key]')) return;
    onActivate();
  }

  // A click on the row body parks the caret there — the same gesture the
  // collections rows honor. The S/M buttons and checkboxes stop
  // propagation, so pressing one never re-aims a caret parked elsewhere.
  // Guarded on the row being navigable so the disabled Show-hidden row
  // can't take a caret j/k could never have reached.
  function clickRow(key: string) {
    if (rows.some((r) => r.key === key)) onFocusRow(key);
  }

  // Hover is latched on real pointerenter, not CSS :hover — closing a
  // menu or ending a drag re-hit-tests whatever lands under a pointer
  // that never moved, and :hover lights it with no leave ever queued.
  // Same fix the collections panel carries; see the note there.
  // Painted only while $hoverLive, so an arrow scrolling rows under a
  // resting pointer doesn't light a second row.
  let hoveredRow: string | null = null;
  function enterRow(key: string) {
    hoveredRow = key;
  }
  function leaveRow(key: string) {
    if (hoveredRow === key) hoveredRow = null;
  }

  // The panel body scrolls, and the cursor no longer moves DOM focus, so
  // nothing scrolls it into view for us any more.
  let lastScrolled: string | null = null;
  afterUpdate(() => {
    if (!focusedRow) { lastScrolled = null; return; }
    if (focusedRow === lastScrolled) return;
    lastScrolled = focusedRow;
    rowElByKey(focusedRow)?.scrollIntoView({ block: 'nearest' });
  });

  /** Claim the pane, restoring `preferred` when that row still exists. */
  export function claim(preferred: string | null) {
    if (rows.length === 0) return;
    const target = preferred && rows.some((r) => r.key === preferred) ? preferred : rows[0].key;
    onFocusRow(target);
  }

  // The pane's keys, dispatched while it is the region with the keyboard
  // (keys.ts), which also stands down for a dialog.
  function paneKeys(event: KeyboardEvent, ctx: KeyContext): boolean {
    if (event.isComposing || ctx.menu || ctx.typing) return false;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');
    // Unmodified only, as in the collections panel: ⌘⌥←/→ are the page's
    // pane-jump chords and must not also fold the header they land on.
    const isLeft  = bareLetter && (event.key === 'ArrowLeft'  || lk === 'h');
    const isRight = bareLetter && (event.key === 'ArrowRight' || lk === 'l');

    if (event.key === 'Escape') {
      // Release the pane. Not a close — the panel is docked furniture whose
      // open state is persisted, and the header toggle is its close
      // affordance. Matches CollectionsPanel's onFocusCollection(null).
      onFocusRow(null);
      return true;
    }
    const edge = jumpEdge(event);
    if (edge && rows.length > 0) {
      onFocusRow(rows[edge === 'first' ? 0 : rows.length - 1].key);
      return true;
    }
    // Active with no caret (the pane was claimed by a click on its chrome):
    // the first arrow places the caret rather than stepping, so it lands *on*
    // the restored row instead of one past it.
    if (focusedRow === null && (isDown || isUp)) {
      onFocusRow(materializeKey(rows.map((r) => r.key), lastFocusedRow, isDown ? 1 : -1));
      return true;
    }
    if (isDown) {
      onFocusRow(stepFilterRow(rows, focusedRow, 1));
      return true;
    }
    if (isUp) {
      onFocusRow(stepFilterRow(rows, focusedRow, -1));
      return true;
    }

    // Everything below acts on the caret's row, which the branches above are
    // the only way to create. Escape stays above so it can still release an
    // active pane that never grew one.
    if (focusedRow === null) return false;

    // ←/→ walk sections the way the tree walks folders: on a header, ← folds
    // it and → unfolds it and steps onto its first row; on a row, ← climbs
    // to the header.
    if (isLeft || isRight) {
      const row = rows.find((r) => r.key === focusedRow);
      if (!row) return true;
      if (row.kind !== 'header') {
        if (isLeft) onFocusRow(sectionHeaderKey(row.section));
        return true;
      }
      if (isLeft) {
        if (!collapsed.has(row.section)) toggleSection(row.section);
        return true;
      }
      const enter = () => {
        if (focusedRow !== row.key) return;
        const next = rows[rows.findIndex((r) => r.key === row.key) + 1];
        if (next && next.kind !== 'header' && next.section === row.section) onFocusRow(next.key);
      };
      if (collapsed.has(row.section)) {
        toggleSection(row.section);
        // rows re-derives on the next flush.
        tick().then(enter);
      } else {
        enter();
      }
      return true;
    }

    // X ticks the focused row's checkbox, the same key both file views
    // spend on theirs. Channel rows carry S/M instead of a checkbox and
    // are reached through those. Space and Enter are unbound here.
    if (bareLetter && lk === 'x') {
      rowElByKey(focusedRow)?.querySelector<HTMLElement>('[data-fm-action]')?.click();
      return true;
    }
    if (bareLetter && (lk === 's' || lk === 'm')) {
      if (event.repeat) return true;
      // Capture the button, not the row: focus may move before release.
      const btn = rowElByKey(focusedRow)
        ?.querySelector<HTMLElement>(lk === 's' ? '[data-sm-s]' : '[data-sm-m]');
      if (btn) holdLatch.press(lk, () => btn.click());
      return true;
    }
    return false;
  }
  const unbindKeys = bindKeys(paneKeys, { tool: 'legend-lore', region: 'filters' });
  onDestroy(unbindKeys);

  $: hasHidden = hiddenCount > 0;

  // A folded section still owns up to what's thrown inside it: a lamp on the
  // header, lit only while it's collapsed (open, the rows say it themselves).
  // Hidden items counts its view switches too — unlike the header's Filters
  // lamp, which tracks search narrowing only — since a forgotten lens behind
  // a fold is exactly what this guards against. Show-hidden with nothing
  // hidden is a disabled row, so it doesn't count.
  $: sectionEngaged = {
    curation: curationSolos.size > 0 || curationMutes.size > 0,
    system: soloedSystems.size > 0 || excludedSystems.size > 0,
    view: (showHidden && hasHidden) || hideUnindexed || hideOutOfScope || hideImages,
  } satisfies Record<FilterSection, boolean>;
  $: curationRows = [
    { key: 'collected' as CurationKey, name: 'In a collection', count: collectedCount },
    { key: 'loose' as CurationKey, name: 'Loose', count: uncollectedCount },
  ];
</script>


<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<aside
  class="filter-panel"
  bind:this={panelEl}
  on:mousedown={handlePanelMousedown}
  on:pointerleave={() => (hoveredRow = null)}
>
  <header class="panel-head nameplate">
    <span class="panel-name ledger-label">Filters</span>
    <button class="plate-btn" on:click={onClearAll} disabled={!canReset}>reset</button>
  </header>

  <div class="panel-body">
    {#if showCollectionFilter}
      <button
        type="button"
        class="sect sect-toggle ledger-label"
        class:kb-focused={focusedRow === 'sect:curation'}
        aria-expanded={!collapsed.has('curation')}
        data-fm-key="sect:curation"
        on:click={() => clickHeader('curation')}
      ><svg class="caret sect-arrow" class:open={!collapsed.has('curation')} viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>Curation{#if collapsed.has('curation') && sectionEngaged.curation}<span class="sect-lamp" role="img" aria-label="Filters active in this section" title="Filters active in this section"></span>{/if}</button>
      {#if !collapsed.has('curation')}
      {#each curationRows as ch (ch.key)}
        {@const soloed = curationSolos.has(ch.key)}
        {@const muted = curationMutes.has(ch.key)}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
        <div
          class="row channel-row"
          class:soloed
          class:dimmed={muted && !soloed}
          class:kb-focused={focusedRow === `curation:${ch.key}`}
          class:hovered={$hoverLive && hoveredRow === `curation:${ch.key}`}
          data-fm-key="curation:{ch.key}"
          on:click={() => clickRow(`curation:${ch.key}`)}
          on:pointerenter={() => enterRow(`curation:${ch.key}`)}
          on:pointerleave={() => leaveRow(`curation:${ch.key}`)}
        >
          <!-- Outline gem — same gem as the chip gems, unfilled:
               the channel is the curation bucket, not a specific collection.
               Loose dashes that same gem's outline rather than taking a shape
               of its own — the systems section walks the same ladder (a shield for
               a tagged system, that shield dashed for Untagged), so dashed
               means "in none" on both axes. A strike or
               slash would have been the obvious alternative and is wrong here:
               in this panel that reads as muted, which is a live state on this
               very row. -->
          <svg
            class="row-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linejoin="round"
            stroke-dasharray={ch.key === 'loose' ? '3.2 2.4' : undefined}
            aria-hidden="true"
          >
            <path d={ch.key === 'loose' ? GEM_OUTLINE : GEM}/>
          </svg>
          <span class="row-name">{ch.name}</span>
          <span class="sm" class:engaged={soloed || muted}>
            <button
              type="button"
              class="sm-btn"
              class:solo-on={soloed}
              data-sm-s
              on:click|stopPropagation={() => onToggleCurationSolo(ch.key)}
              aria-pressed={soloed}
              title={ch.key === 'collected'
                ? (soloed ? 'Stop soloing collected files' : 'Solo collected files (show only collection)')
                : (soloed ? 'Stop soloing loose files' : 'Solo loose files (show only loose)')}
            >S</button>
            <button
              type="button"
              class="sm-btn"
              class:mute-on={muted}
              data-sm-m
              on:click|stopPropagation={() => onToggleCurationMute(ch.key)}
              aria-pressed={muted}
              title={ch.key === 'collected'
                ? (muted ? 'Unmute collected files' : 'Mute collected files')
                : (muted ? 'Unmute loose files' : 'Mute loose files')}
            >M</button>
          </span>
          <span class="row-count">{ch.count}</span>
        </div>
      {/each}
      {/if}
    {/if}

    {#if showSystemFilter}
      <button
        type="button"
        class="sect sect-toggle ledger-label"
        class:kb-focused={focusedRow === 'sect:system'}
        aria-expanded={!collapsed.has('system')}
        data-fm-key="sect:system"
        on:click={() => clickHeader('system')}
      ><svg class="caret sect-arrow" class:open={!collapsed.has('system')} viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>Game systems{#if collapsed.has('system') && sectionEngaged.system}<span class="sect-lamp" role="img" aria-label="Filters active in this section" title="Filters active in this section"></span>{/if}</button>
      {#if collapsed.has('system')}
        <!-- Folded shut: nothing below renders. -->
      {:else if systems.length > 0}
        {#each systems as { name, count } (name)}
          {@const soloed = soloedSystems.has(name)}
          {@const muted = excludedSystems.has(name)}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div
            class="row channel-row"
            class:soloed
            class:dimmed={muted && !soloed}
            class:kb-focused={focusedRow === `system:${name}`}
            class:hovered={$hoverLive && hoveredRow === `system:${name}`}
            title={name}
            data-fm-key="system:{name}"
            on:click={() => clickRow(`system:${name}`)}
            on:pointerenter={() => enterRow(`system:${name}`)}
            on:pointerleave={() => leaveRow(`system:${name}`)}
          >
            <!-- Shield — monochrome; systems don't carry color. -->
            <svg class="row-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d={SHIELD}/>
            </svg>
            <span class="row-name">{name}</span>
            <span class="sm" class:engaged={soloed || muted}>
              <button
                type="button"
                class="sm-btn"
                class:solo-on={soloed}
                data-sm-s
                on:click|stopPropagation={() => onToggleSolo(name)}
                aria-pressed={soloed}
                aria-label={soloed ? `Stop soloing ${name}` : `Solo ${name}`}
                title={soloed ? `Stop soloing ${name} (S)` : `Solo ${name} (S)`}
              >S</button>
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                data-sm-m
                on:click|stopPropagation={() => onToggleSystem(name)}
                aria-pressed={muted}
                aria-label={muted ? `Unmute ${name}` : `Mute ${name}`}
                title={muted ? `Unmute ${name} (M)` : `Mute ${name} (M)`}
              >M</button>
            </span>
            <span class="row-count">{count}</span>
          </div>
        {/each}
        {#if untaggedCount > 0}
          {@const muted = excludedSystems.has(UNTAGGED_KEY)}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div
            class="row channel-row untagged-row"
            class:dimmed={muted}
            class:kb-focused={focusedRow === `system:${UNTAGGED_KEY}`}
            class:hovered={$hoverLive && hoveredRow === `system:${UNTAGGED_KEY}`}
            title="Files with no game-system tag"
            data-fm-key="system:{UNTAGGED_KEY}"
            on:click={() => clickRow(`system:${UNTAGGED_KEY}`)}
            on:pointerenter={() => enterRow(`system:${UNTAGGED_KEY}`)}
            on:pointerleave={() => leaveRow(`system:${UNTAGGED_KEY}`)}
          >
            <!-- Dashed shield: the untagged bucket is a placeholder, not an identity -->
            <svg class="row-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-dasharray="3.2 2.4" aria-hidden="true">
              <path d={SHIELD}/>
            </svg>
            <span class="row-name">Untagged</span>
            <span class="sm" class:engaged={muted}>
              <span class="sm-spacer" aria-hidden="true"></span>
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                data-sm-m
                on:click|stopPropagation={() => onToggleSystem(UNTAGGED_KEY)}
                aria-pressed={muted}
                aria-label={muted ? 'Unmute untagged files' : 'Mute untagged files'}
                title={muted ? 'Unmute untagged files (M)' : 'Mute untagged files (M)'}
              >M</button>
            </span>
            <span class="row-count">{untaggedCount}</span>
          </div>
        {/if}
      {:else}
        <div class="empty">No game systems detected yet. Index some files first.</div>
      {/if}
    {/if}

    <!-- View-visibility switches last: they say what the tree shows, not
         what search sees, so they sit below the narrowing axes. -->
    <div class="sect-split" class:kb-focused={focusedRow === 'sect:view'} data-fm-key="sect:view">
      <button
        type="button"
        class="sect sect-toggle ledger-label"
        aria-expanded={!collapsed.has('view')}
        on:click={() => clickHeader('view')}
      ><svg class="caret sect-arrow" class:open={!collapsed.has('view')} viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>Hidden items</button>
      {#if collapsed.has('view') && sectionEngaged.view}<span class="sect-lamp" role="img" aria-label="Filters active in this section" title="Filters active in this section"></span>{/if}
      {#if hasHidden}
        <button class="reset-link" on:click={onClearHidden}>Clear</button>
      {/if}
    </div>
    {#if !collapsed.has('view')}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="row"
      class:row-disabled={!hasHidden}
      class:kb-focused={focusedRow === 'view:showHidden'}
      class:hovered={$hoverLive && hoveredRow === 'view:showHidden'}
      title={hasHidden ? 'Reveal hidden files and folders in the tree' : 'Right-click any file or folder to hide it'}
      data-fm-key="view:showHidden"
      on:click={() => clickRow('view:showHidden')}
      on:pointerenter={() => enterRow('view:showHidden')}
      on:pointerleave={() => leaveRow('view:showHidden')}
    >
      <span class="row-name muted-name">Show hidden items</span>
      <span class="row-count">{hiddenCount}</span>
      <button
        type="button"
        class="app-checkbox"
        role="checkbox"
        aria-checked={showHidden}
        aria-label="Show hidden items"
        disabled={!hasHidden}
        data-fm-action
        on:click|stopPropagation={onToggleShowHidden}
      ></button>
    </div>

    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideUnindexed'}
      class:hovered={$hoverLive && hoveredRow === 'view:hideUnindexed'}
      title="Hide files and folders the library knows nothing about — not indexed, not selected for indexing"
      data-fm-key="view:hideUnindexed"
      on:click={() => clickRow('view:hideUnindexed')}
      on:pointerenter={() => enterRow('view:hideUnindexed')}
      on:pointerleave={() => leaveRow('view:hideUnindexed')}
    >
      <span class="row-name muted-name">Hide unindexed items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideUnindexed}
        aria-label="Hide unindexed items"
        data-fm-action
        on:click|stopPropagation={onToggleHideUnindexed}
      ></button>
    </div>

    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideOutOfScope'}
      class:hovered={$hoverLive && hoveredRow === 'view:hideOutOfScope'}
      title="Hide dimmed out-of-scope rows in the tree and systems view"
      data-fm-key="view:hideOutOfScope"
      on:click={() => clickRow('view:hideOutOfScope')}
      on:pointerenter={() => enterRow('view:hideOutOfScope')}
      on:pointerleave={() => leaveRow('view:hideOutOfScope')}
    >
      <span class="row-name muted-name">Hide out-of-scope items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideOutOfScope}
        aria-label="Hide out-of-scope items"
        data-fm-action
        on:click|stopPropagation={onToggleHideOutOfScope}
      ></button>
    </div>

    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideImages'}
      class:hovered={$hoverLive && hoveredRow === 'view:hideImages'}
      title="Hide the images the tree lists beside the books"
      data-fm-key="view:hideImages"
      on:click={() => clickRow('view:hideImages')}
      on:pointerenter={() => enterRow('view:hideImages')}
      on:pointerleave={() => leaveRow('view:hideImages')}
    >
      <span class="row-name muted-name">Hide images</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideImages}
        aria-label="Hide images"
        data-fm-action
        on:click|stopPropagation={onToggleHideImages}
      ></button>
    </div>
    {/if}
  </div>
</aside>

<style>
  .filter-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-app);
    font-family: var(--font-body);
    overflow: hidden;
  }
  .panel-head {
    display: flex;
    /* Centred, not baseline-aligned, and padded like the scope bar: the
       plate's min-height sets the box, and the title sits in its middle
       the same way SCOPE does, instead of riding the mono control's
       taller line box off-centre. */
    align-items: center;
    gap: 0.5rem;
    padding: 0.15rem 0.75rem;
    margin-bottom: 0.3rem;
    flex-shrink: 0;
  }
  /* The name takes the slack, so the control sits at the plate's end. */
  .panel-name {
    flex: 1;
  }
  .panel-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-bottom: 0.4rem;
  }

  /* Quiet small-caps section headers — ledger voice, like the tree.
     No rule under them. The fold arrow sits in the left gutter so the
     label lines up with the row icons (1.1rem padding + 3px solo rule).
     The gap above is margin, not padding, so the focus ring hugs the
     label evenly instead of hanging empty space over it. */
  .sect {
    margin-top: 0.35rem;
    padding: 0.2rem 0.25rem 0.2rem calc(0.3rem + 3px);
  }
  /* A list row's height (.row), centred in it, as the systems view's
     group heads: a section head is a row you click. */
  .sect-toggle {
    display: flex;
    align-items: center;
    min-height: 1.65rem;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    transition: color var(--transition-fast);
  }
  .sect-toggle:hover {
    color: var(--text-secondary);
  }
  .sect-toggle.kb-focused,
  .sect-split.kb-focused {
    box-shadow: var(--ring-focus);
  }
  /* The header keys' engagement lamp (Header.svelte), lit face only: it
     appears when there's something to report and is otherwise absent, so
     quiet headers stay quiet. Its right edge sits over the centre of the
     rows' 18px count box — 0.75rem row padding + 4px. */
  .sect-lamp {
    align-self: center;
    flex-shrink: 0;
    width: 10px;
    height: 2px;
    margin: 0 calc(0.5rem + 4px) 0 auto;
    border-radius: var(--radius-sm);
    background: var(--text-active);
    filter: var(--glow-active);
  }
  /* Outside the toggle here, between it and Clear, so the container's
     0.75rem padding already does most of the inset. */
  .sect-split .sect-lamp {
    margin: 0 4px 0 0.4rem;
  }
  .sect-split .reset-link {
    margin-left: 0.4rem;
  }
  /* Centred with the label, as the toggle centres everything; the margin
     restores the old text arrow's gap. */
  .sect-arrow {
    align-self: center;
    margin-right: 0.3rem;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    /* Vertical padding and type size match the collections panel's rows, so
       names read the same down the dock and the natural height stays under
       the shared min-height. */
    padding: 0.15rem 0.75rem 0.15rem 1.1rem;
    /* Matches the collections panel's rows — see the note there. */
    min-height: 1.65rem;
    font-size: 0.9rem;
    color: var(--text-primary);
    /* Reserved for the solo rule so engaging S doesn't shift layout. */
    border-left: 3px solid transparent;
    transition: background var(--transition-fast);
  }
  .row.hovered {
    background: var(--bg-container);
  }
  /* Keyboard focus rings rather than fills, so the caret stays visible
     on a soloed row instead of losing the background to it. */
  .row.kb-focused {
    box-shadow: var(--ring-focus);
  }
  .row-disabled {
    color: var(--text-tertiary);
    cursor: default;
  }
  .row-disabled.hovered {
    background: transparent;
  }
  .row-disabled .row-count {
    color: var(--text-tertiary);
  }
  /* Section head variant with a right-aligned reset link. */
  .sect-split {
    display: flex;
    align-items: baseline;
    margin-top: 0.35rem;
    padding-right: 0.75rem;
  }
  /* The container carries the gap here, since it carries the ring. */
  .sect-split .sect {
    margin-top: 0;
  }
  .sect-split .sect-toggle {
    flex: 1;
  }

  /* Soloed channel — the tree's own soloed-collection treatment:
     parchment wash + purple rule on the reserved border. */
  .row.soloed {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }
  /* The active shield comes up in parchment, the systems view's ink for a
     system; at rest it sits back in secondary with the other row icons. */
  .row.soloed .row-icon {
    color: var(--text-accent);
  }

  .row-icon {
    width: 0.8rem;
    height: 0.8rem;
    flex-shrink: 0;
    color: var(--text-secondary);
  }

  .row-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .muted-name {
    color: var(--text-secondary);
  }
  .row-disabled .muted-name {
    color: var(--text-tertiary);
  }

  .reset-link {
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.7rem;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .reset-link:hover {
    color: var(--text-secondary);
  }

  /* LED count readout — same inverted 18px box as the systems-view group
     count (filled, borderless, tabular digits). */
  .row-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    flex-shrink: 0;
  }

  /* S/M cluster — hidden at rest, revealed on row hover or keyboard
     focus, always visible while engaged. Same reveal grammar as the
     tree's folder rows; button anatomy is the shared .sm-btn in app.css.
     Hover is the latched .hovered class, not :hover — see enterRow. */
  .sm {
    display: inline-flex;
    gap: 0.25rem;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row.hovered .sm,
  .row:focus-within .sm,
  .row.kb-focused .sm,
  .sm.engaged {
    opacity: 1;
  }
  /* Untagged has no S — the spacer keeps the M column aligned. */
  .sm-spacer {
    width: 18px;
    flex-shrink: 0;
  }

  /* A muted channel dims in place — removed from results, still on the
     board. Solo overrides mute, so a soloed row never dims. */
  .row.dimmed .row-name,
  .row.dimmed .row-icon,
  .row.dimmed .row-count {
    opacity: var(--opacity-out-of-scope);
  }

  .untagged-row {
    color: var(--text-tertiary);
  }
  .untagged-row .row-icon {
    color: var(--text-tertiary);
  }

  .empty {
    padding: 0.3rem 0.75rem 0.5rem 1.1rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  /* The lens is a mode the user switched on — checked wears purple,
     not the parchment content accent. Matched on aria-checked, not
     :checked: these rows are role="checkbox" buttons, and a button never
     matches :checked, so the purple never landed. */
  .lens-checkbox[aria-checked="true"] {
    background-color: var(--text-active);
    border-color: var(--text-active);
  }
</style>
