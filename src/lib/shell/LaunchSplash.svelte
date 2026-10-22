<script lang="ts">
  import { statusLine, STEP_COPY, TOOL_GROUPS, type BootSnapshot, type BootStep } from './bootSteps';
  import { MARK, MARK_VIEWBOX } from '../ui/iconPaths';
  import { m } from '../paraglide/messages';

  export let snapshot: BootSnapshot | null = null;
  export let version: string = '';

  $: steps = new Map((snapshot?.steps ?? []).map((s) => [s.id, s]));
  $: line = statusLine(snapshot);

  function lampTitle(id: string, step: BootStep | undefined): string {
    const name = STEP_COPY[id].name();
    return step?.detail ? m.boot_lamp_title({ step: name, detail: step.detail }) : name;
  }
</script>

<div class="splash">
  <div class="card">
    <!-- The Unseen Servant mark (iconPaths MARK), cropped to its ink. -->
    <svg class="mark" viewBox={MARK_VIEWBOX} aria-hidden="true">
      <path d={MARK} />
    </svg>
    <h1 class="wordmark font-heading">Unseen Servant</h1>
    <!-- The cold start as a console self-test: one lamp per step, grouped
         under the tool it serves. The status bar's lamps take over after. -->
    <div class="rack">
      {#each TOOL_GROUPS as group (group.id)}
        <div class="group">
          <span class="ledger-label">{group.name()}</span>
          <div class="lamps">
            {#each group.steps as id (id)}
              {@const step = steps.get(id)}
              <span class="lamp {step?.state ?? 'pending'}" title={lampTitle(id, step)}>
                <span class="led"></span>
                <span class="code">{STEP_COPY[id].lamp}</span>
              </span>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  </div>
  <footer class="foot">
    <span class="line {line.tone}" role="status">{line.text}</span>
    {#if version}
      <span class="version">v{version}</span>
    {/if}
  </footer>
</div>

<style>
  /* The window is transparent, so the card is the window: its corners and
     edge are drawn here. */
  .splash {
    position: fixed;
    inset: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-window);
    cursor: default;
    user-select: none;
    -webkit-user-select: none;
  }

  .card {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
  }

  .mark {
    height: 112px;
    width: auto;
    fill: var(--text-primary);
  }

  .wordmark {
    margin: 0.25rem 0 0;
    font-size: 2rem;
    font-weight: 400;
    line-height: 1.1;
    letter-spacing: 0.01em;
    color: var(--text-primary);
  }

  .rack {
    display: flex;
    margin-top: 1rem;
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0 1.1rem;
  }

  .group + .group {
    border-left: 1px solid var(--border-subtle);
  }

  .lamps {
    display: flex;
    gap: 0.5rem;
  }

  .lamp {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    width: 26px;
  }

  /* The status bar's meter cell, widened into a pilot lamp: grey until its
     step runs, amber blinking while it does, amber once it's up. */
  .led {
    width: 16px;
    height: 6px;
    border-radius: var(--radius-cell);
    background: var(--bg-category);
  }

  .code {
    font-family: var(--font-mono);
    font-size: 0.55rem;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
  }

  .lamp.running .led {
    background: var(--text-connected);
    animation: lamp-blink 0.5s steps(1, end) infinite;
  }

  .lamp.done .led {
    background: var(--text-connected);
  }

  .lamp.done .code {
    color: var(--text-secondary);
  }

  .lamp.failed .led {
    background: var(--text-danger);
  }

  .lamp.failed .code {
    color: var(--text-danger);
  }

  /* Skipped: nothing ran, nothing's wrong. */
  .lamp.skipped {
    opacity: var(--opacity-out-of-scope);
  }

  @keyframes lamp-blink {
    50% {
      opacity: 0.3;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .lamp.running .led {
      animation: none;
      opacity: 0.55;
    }
  }

  /* The status bar's plate, so the line reads as the one the tool window
     picks up once it opens. */
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    height: var(--statusbar-height);
    padding: 0 0.75rem;
    flex-shrink: 0;
    background: var(--bg-header);
    border-top: 1px solid var(--border-subtle);
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .line {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .line.ready {
    color: var(--text-primary);
  }

  .line.warning {
    color: var(--text-danger);
  }

  .version {
    flex-shrink: 0;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-tertiary);
    font-variant-numeric: tabular-nums;
  }
</style>
