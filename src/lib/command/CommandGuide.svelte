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
      A beat is a scene: the notes it needs. Double-click the empty row of
      the session planner, on the right, to name one; it starts armed (&#9679;), so clicking
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
    <h3 class="field-title section-title">The board's tools</h3>
    <p class="field-desc">
      The toolbar on the board's right edge arranges it before the session.
      <strong>D</strong> places any note of the campaign where you click, by
      name. <strong>T</strong> adds a text card and <strong>N</strong> a sticky
      where you click. <strong>F</strong> draws a frame, which carries the cards
      inside it when you move it; <strong>&#8984;G</strong> frames the selected
      cards. <strong>L</strong> draws a line from one card to another. Double-click a text card, a
      frame's name or a line to write in it. <strong>H</strong> pans over the
      cards, <strong>V</strong> or <strong>Esc</strong> goes back to selecting,
      and <strong>&#8984;Z</strong> undoes.
    </p>
    <p class="field-desc">
      Select a sticky, a text card, a frame or a line to colour it from the bar
      over it; a line's bar also sets its arrowheads. <strong>&#8984;D</strong>
      duplicates text cards, stickies and frames. <strong>&#8997;1</strong>
      shows the whole board and <strong>&#8997;2</strong> the selection.
    </p>
    <p class="field-desc">
      The key at the toolbar's foot arranges the board by beat: a frame for
      each planned beat in plan order, with the notes several beats share in
      a frame of their own, Throughout. Once a beat has its frame, launching
      it shows that frame.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Images</h3>
    <p class="field-desc">
      A note shows the images it embeds, <em>![[map.png]]</em> as Obsidian
      writes them (<em>![[map.png|300]]</em> sets the width), on its card and
      when you read it. Drop an image from Finder on the board to put it
      there; it's copied into the campaign's <em>Shelf</em> folder, so the
      campaign keeps everything it uses.
    </p>
    <p class="field-desc">
      An image in a track or on the shelf works as a note does: put it in a
      beat, play it, and its card shows it. Double-click it to see it in
      the inspector. An image isn't spent: spend the beat that shows it.
    </p>
    <p class="field-desc">
      A track holds notes or images, chosen when you insert it:
      <em>+ track</em>, or a track's right-click, offers <em>Insert note
      track</em> (<strong>&#8984;T</strong>) and <em>Insert image track</em>
      (<strong>&#8679;&#8984;T</strong>). Double-clicking an image track's
      empty row copies pictures from your Mac into it, as does dropping
      them on it from Finder; dropped on the shelf, they land
      there. An image goes only in an image track, and a note only in a note
      track; the shelf holds both. A folder of images you fill in Finder is
      an image track already. In Legend Lore's tree, right-click an image
      and <em>Send to Command</em> to copy it in.
    </p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">Session notes</h3>
    <p class="field-desc">
      The bar in the board's corner writes a line into the session note, and
      <strong>&#8984;O</strong> opens the note.
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
