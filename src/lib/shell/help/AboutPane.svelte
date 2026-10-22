<script lang="ts">
  import { onMount } from 'svelte';
  import { getVersion } from '@tauri-apps/api/app';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { m } from '../../paraglide/messages';

  export let dataDir: string = '';
  export let onOpenDataDir: () => void = () => {};

  const HOMEPAGE_URL = 'https://unseenservant.games';
  const LICENSE_URL = 'https://unseenservant.games/license';
  const FONTAWESOME_LICENSE_URL = 'https://fontawesome.com/license/free';

  let appVersion = '';

  onMount(async () => {
    try {
      appVersion = await getVersion();
    } catch {
      appVersion = '';
    }
  });

  function open(url: string) {
    openUrl(url).catch(() => {});
  }
</script>

<div class="pane">
  <section class="block">
    <header class="block-head">
      <h3 class="block-title section-title">{m.about_title()}</h3>
      <p class="block-desc">{m.about_desc()}</p>
    </header>

    <dl class="meta">
      <dt class="meta-label readout-label">{m.about_version()}</dt>
      <dd class="meta-value">{appVersion ? `v${appVersion}` : '—'}</dd>

      <dt class="meta-label readout-label">{m.about_data_dir()}</dt>
      <dd class="meta-value path-cell">
        <span class="path" title={dataDir}>{dataDir || m.about_resolving()}</span>
        <button
          type="button"
          class="btn-link"
          on:click={onOpenDataDir}
          disabled={!dataDir}
        >{m.about_reveal()}</button>
      </dd>
    </dl>
  </section>

  <section class="block">
    <header class="block-head">
      <h3 class="block-title section-title">{m.about_links()}</h3>
    </header>
    <ul class="link-list">
      <li>
        <button class="btn-link" on:click={() => open(HOMEPAGE_URL)}>Unseen Servant</button>
        <span class="link-desc">{m.about_homepage()}</span>
      </li>
      <li>
        <button class="btn-link" on:click={() => open(LICENSE_URL)}>{m.about_license()}</button>
        <span class="link-desc">Unseen Servant Games Software License</span>
      </li>
    </ul>
  </section>

  <section class="block">
    <header class="block-head">
      <h3 class="block-title section-title">{m.about_credits()}</h3>
    </header>
    <ul class="link-list">
      <li>
        <button class="btn-link" on:click={() => open(FONTAWESOME_LICENSE_URL)}>Font Awesome Free 7.2.0</button>
        <span class="link-desc">{m.about_icons()}</span>
      </li>
    </ul>
  </section>

</div>

<style>
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .block-head {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .block-title {
    margin: 0;
  }

  .block-desc {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .meta {
    margin: 0;
    display: grid;
    grid-template-columns: 8rem 1fr;
    column-gap: 1rem;
    row-gap: 0.4rem;
    font-size: 0.8rem;
    align-items: baseline;
  }

  .meta-label {
    margin: 0;
  }

  .meta-value {
    margin: 0;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    min-width: 0;
  }

  .path-cell {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    min-width: 0;
  }

  .path {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 1;
  }

  .link-list {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .link-list li {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    font-family: var(--font-body);
    font-size: 0.8rem;
  }

  .link-desc {
    color: var(--text-secondary);
    font-size: 0.75rem;
  }

  .btn-link {
    flex-shrink: 0;
  }

</style>
