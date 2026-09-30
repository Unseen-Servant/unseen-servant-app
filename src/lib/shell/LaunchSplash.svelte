<script lang="ts">
  import { statusLine, STEP_COPY, TOOL_GROUPS, type BootSnapshot, type BootStep } from './bootSteps';

  export let snapshot: BootSnapshot | null = null;
  export let version: string = '';

  $: steps = new Map((snapshot?.steps ?? []).map((s) => [s.id, s]));
  $: line = statusLine(snapshot);

  function lampTitle(id: string, step: BootStep | undefined): string {
    const name = STEP_COPY[id].name;
    return step?.detail ? `${name}: ${step.detail}` : name;
  }
</script>

<div class="splash">
  <div class="card">
    <!-- The Unseen Servant mark: the visible path of static/logo.svg, inline
         so it takes the text colour, with the viewBox cropped to its ink. -->
    <svg class="mark" viewBox="165 38 685 960" aria-hidden="true">
      <path d="m 531.48251,996.79425 c 0,-5.71119 80.68699,-261.64303 109.0722,-345.96722 6.0315,-17.91785 12.17387,-33.7718 13.64974,-35.23102 1.4759,-1.45926 8.97158,-6.53133 16.65711,-11.27128 32.9359,-20.31284 54.16842,-37.98849 67.47142,-56.16879 16.04415,-21.92635 28.9418,-50.48234 35.45033,-78.48854 3.95674,-17.02593 3.36988,-18.27563 -6.92975,-14.75602 -11.52545,3.93853 -212.0373,91.42258 -217.37196,94.84017 -1.13116,0.72468 -2.94191,10.75759 -4.81899,26.70112 -1.65383,14.04712 -8.58032,71.92537 -15.39224,128.61831 -6.81191,56.69293 -14.42215,120.78987 -16.91162,142.4377 -2.48951,21.64777 -4.70877,39.52283 -4.93167,39.72232 -0.22295,0.19947 -1.15122,-5.69449 -2.06281,-13.09769 -30.5443,-248.05411 -40.2297,-324.80923 -41.08136,-325.56271 -1.36618,-1.20865 -154.72578,-68.41341 -189.5819,-83.07797 -30.37703,-12.78012 -34.69824,-14.03535 -36.20704,-10.51716 -3.09314,7.21257 10.41027,48.08159 23.70664,71.74983 18.71388,33.31172 37.76764,51.8621 77.04069,75.00532 9.28187,5.46971 18.28293,10.84278 20.00236,11.94014 3.59039,2.29145 8.91304,16.51555 26.8314,71.70376 35.70962,109.98493 93.67927,298.83806 92.15018,300.20629 -0.30587,0.27368 -12.97652,-26.53685 -28.15704,-59.57898 C 385.07627,784.53947 335.42532,679.18856 327.37515,665.66813 322.54283,657.55205 309.49676,644.31795 271.208,608.69137 l -26.2098,-24.38745 -9.37455,-31.20495 c -5.15599,-17.16271 -11.19157,-36.21454 -13.41243,-42.33738 -2.22083,-6.12284 -15.54974,-32.12212 -29.61972,-57.77625 l -25.58188,-46.6438 -1.1357,-24.29229 c -1.19044,-25.46293 -0.0944,-214.20475 1.48685,-256.05378 l 0.91793,-24.29228 4.16039,32.17087 c 12.21459,94.45047 20.71392,143.5027 27.49954,158.70776 13.76142,30.83628 66.24832,100.75582 91.8508,122.35744 12.70314,10.71809 18.87525,13.58383 101.01526,46.90224 70.35893,28.5397 77.39133,31.17317 80.44448,30.12485 1.40533,-0.48255 2.84378,-2.05367 1.91605,-0.95397 -3.6e-4,4.6e-4 -7.7e-4,8.9e-4 -10e-4,10e-4 -0.9803,1.08152 10.08704,-114.16487 16.7676,-218.7572 10.64568,-166.67129 13.80341,-232.56732 15.48269,-234.129037 0.32356,-0.300936 0.58887,0.880843 0.58956,2.62618 6.9e-4,1.7453 0.64325,9.377691 1.42795,16.960815 2.96013,28.604907 7.61561,93.807712 19.82917,277.719902 7.16743,107.92778 10.68995,154.05248 11.89859,155.80231 0.42269,0.61196 1.47822,1.11268 2.34561,1.11268 4.09913,0 129.08371,-49.77779 157.4724,-62.71677 16.73558,-7.62774 33.09298,-21.95393 55.32485,-48.45472 35.51423,-42.33367 60.90874,-81.69484 66.36391,-102.86321 3.35524,-13.01979 24.3265,-159.5797 24.3265,-170.00844 0,-1.18918 0.66039,-1.79697 1.46749,-1.35064 0.96427,0.53324 1.46752,51.44909 1.46752,148.4749 V 403.0935 l -10.09319,18.03756 c -17.4755,31.23056 -43.69,80.75201 -46.9872,88.76279 -1.74231,4.2331 -7.44344,21.58217 -12.66919,38.55351 -5.22577,16.97131 -10.76407,33.30276 -12.30742,36.29214 -1.75944,3.40796 -16.50401,18.16902 -39.53159,39.57571 l -36.72552,34.14051 -13.52533,28.23157 c -37.75333,78.80308 -87.71024,185.22668 -126.31136,269.08198 -10.49826,22.80593 -19.35928,41.7115 -19.69118,42.01244 -0.33187,0.30092 -0.60342,-0.14358 -0.60342,-0.98779 z"/>
    </svg>
    <h1 class="wordmark font-heading">Unseen Servant</h1>
    <!-- The cold start as a console self-test: one lamp per step, grouped
         under the tool it serves. The status bar's lamps take over after. -->
    <div class="rack">
      {#each TOOL_GROUPS as group (group.name)}
        <div class="group">
          <span class="ledger-label">{group.name}</span>
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
  .splash {
    position: fixed;
    inset: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
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
