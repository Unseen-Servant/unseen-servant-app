<script lang="ts">
  export let tag: string;
  export let color: string | null = null;
</script>

<span class="game-system-badge" style={color ? `--badge-color: ${color}` : ''} title={tag}>
  <!-- Font Awesome "dice-d6" -->
  <svg class="badge-die" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
    <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
  </svg>
  {tag}
</span>

<style>
  .game-system-badge {
    --badge-color: var(--text-accent);
    display: inline-block;
    max-width: 9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-family: var(--font-body);
    background: color-mix(in srgb, var(--badge-color) 20%, transparent);
    color: var(--badge-color);
    white-space: nowrap;
    border: 1px solid transparent;
    transition: border-color var(--transition-fast);
  }
  .badge-die {
    width: 10px;
    height: 10px;
    vertical-align: -1px;
    margin-right: 0.25rem;
  }
</style>
