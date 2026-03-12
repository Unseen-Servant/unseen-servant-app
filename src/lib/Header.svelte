<script lang="ts">
</script>

<header class="header">
  <div class="header-left">
    <span class="app-title">Legend Lore</span>
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    height: var(--header-height);
    padding: 0 1rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    gap: 1rem;
  }

  .header-left {
    flex-shrink: 0;
  }

  .app-title {
    font-family: var(--font-heading);
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-secondary);
    letter-spacing: 0.02em;
    -webkit-user-select: none;
    user-select: none;
  }
</style>
