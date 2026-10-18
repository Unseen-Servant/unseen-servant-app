<!-- Help → Guides for Command: the loop from a campaign to the table, one
     step per section, in the Legend Lore guide's shape
     (GettingStartedSteps.svelte). -->
<div class="manual">
  <section class="field">
    <h3 class="field-title section-title">Campaigns folder</h3>
    <p class="field-desc">
      Each campaign is a folder in it: <em>Unseen Servant</em> in your home
      folder until you choose another in <em>Settings &rarr; Command</em>.
      Command reopens the campaign you used last; its key in the bar switches
      campaigns or starts a new one.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Tracks and notes</h3>
    <p class="field-desc">
      A campaign's folders are its tracks (PCs, Secrets, Locations, NPCs&hellip;),
      shown as columns, and each note is a Markdown file in one, so Obsidian
      reads the same folder. <em>[[Name]]</em> links one note to another. The
      shelf (<strong>&#8984;B</strong>) holds what isn't filed yet, such as a
      Legend Lore result sent with right-click &rsaquo; <em>Send to
      Command</em>.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Beats and sessions</h3>
    <p class="field-desc">
      A beat is a scene: the notes it needs. Name one in the empty row of the
      session planner, on the right; it starts armed (&#9679;), so clicking
      notes puts them in it, and <strong>Esc</strong> disarms it.
      <em>New session</em> in the bar starts a session; drag beats into its
      plan.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Play</h3>
    <p class="field-desc">
      <strong>Tab</strong> switches to Play, where the board holds the plan's
      notes as cards. In the session player, <strong>P</strong> or &#9654;
      launches the focused beat and lights its cards; a card's &#9654; puts
      one more note in play. The card tray under the board holds what's in
      play: point at a card to read all of it, or click cards, then
      <em>select</em>, to read them side by side. <strong>A</strong> marks the note or beat under
      the pointer spent (a secret told, an NPC dead), and it stays dimmed in
      later sessions.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Session notes</h3>
    <p class="field-desc">
      The bar in the board's corner writes a line into the session note, and
      <strong>&#8984;O</strong> opens the note. Command logs each launch and
      spend there too, under <em>## Log</em>.
    </p>
  </section>
</div>

<style>
  /* GettingStartedSteps' vocabulary: stacked .field sections, Almendra
     titles, body text at 0.85rem. */
  .manual {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    width: 100%;
    font-family: var(--font-body);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .field-title {
    margin: 0;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }
  .field-desc strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .field-desc em {
    font-style: italic;
  }
</style>
