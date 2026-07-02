<script lang="ts">
  export let skipLaunchSplash: boolean = false;
  export let onSkipLaunchSplashChange: (value: boolean) => void = () => {};

  function handleChange(e: Event & { currentTarget: HTMLSelectElement }) {
    onSkipLaunchSplashChange(e.currentTarget.value === 'skip');
  }
</script>

<div class="general-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Startup</h3>
      <p class="field-desc">How the app behaves when it launches.</p>
    </div>

    <div class="setting-row">
      <div class="setting-row-head">
        <div class="setting-row-title">Launch splash</div>
        <div class="setting-row-desc">
          Show the branded splash screen while the app starts up.
        </div>
      </div>
      <select
        class="setting-select"
        value={skipLaunchSplash ? 'skip' : 'show'}
        on:change={handleChange}
      >
        <option value="show">Show</option>
        <option value="skip">Skip</option>
      </select>
    </div>
  </section>
</div>

<style>
  .general-settings {
    padding: 1rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .field-title {
    font-size: 0.95rem;
    color: var(--text-primary);
    margin: 0 0 0.35rem;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }

  .setting-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 0.1rem;
  }

  .setting-row-head {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .setting-row-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.8rem;
    color: var(--text-primary);
  }

  .setting-row-desc {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }

  .setting-select {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    cursor: pointer;
    min-width: 11rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
</style>
