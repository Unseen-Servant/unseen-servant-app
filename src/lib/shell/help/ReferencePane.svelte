<script lang="ts">
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import { m } from '../../paraglide/messages';

  type Copy = () => string;

  // The words the app uses that a newcomer meets without a definition.
  const GLOSSARY: { group: Copy; terms: [term: Copy, meaning: Copy, key?: string][] }[] = [
    {
      group: () => 'Legend Lore',
      terms: [
        [m.glossary_collection, m.glossary_collection_desc],
        [m.glossary_play, m.glossary_play_desc, 'P'],
        [m.glossary_mix, m.glossary_mix_desc],
        [m.glossary_arm, m.glossary_arm_desc],
        [m.glossary_solo, m.glossary_solo_desc, 'S'],
        [m.glossary_mute, m.glossary_mute_desc, 'M'],
        [m.glossary_bypass, m.glossary_bypass_desc, 'B'],
        [m.glossary_strength, m.glossary_strength_desc],
        [m.glossary_sync, m.glossary_sync_desc, '⌘S'],
      ],
    },
    {
      group: () => 'Command',
      terms: [
        [m.glossary_campaign, m.glossary_campaign_desc],
        [m.glossary_track, m.glossary_track_desc],
        [m.glossary_note, m.glossary_note_desc],
        [m.glossary_shelf, m.glossary_shelf_desc],
        [m.glossary_beat, m.glossary_beat_desc],
        [m.glossary_session, m.glossary_session_desc],
        [m.glossary_prep_play, m.glossary_prep_play_desc],
        [m.glossary_launch, m.glossary_launch_desc, 'P'],
        [m.glossary_live_set, m.glossary_live_set_desc],
        [m.glossary_spent, m.glossary_spent_desc, 'A'],
        [m.glossary_board, m.glossary_board_desc],
        [m.glossary_card_tray, m.glossary_card_tray_desc],
      ],
    },
    {
      group: m.reference_machinery,
      terms: [
        [m.glossary_sidecar, m.glossary_sidecar_desc],
        [m.glossary_embedder, m.glossary_embedder_desc],
        [m.glossary_mcp, m.glossary_mcp_desc],
        [m.glossary_rack, m.glossary_rack_desc],
      ],
    },
  ];

  // The tools sidecar/mcp_server.py registers. Keep in step with it.
  const MCP_TOOLS: { group: Copy; tools: [name: string, what: Copy][] }[] = [
    {
      group: m.reference_mcp_library,
      tools: [
        ['search_library', m.mcp_search_library],
        ['get_section', m.mcp_get_section],
        ['get_pages', m.mcp_get_pages],
        ['list_sources', m.mcp_list_sources],
        ['list_collections', m.mcp_list_collections],
        ['list_game_systems', m.mcp_list_game_systems],
      ],
    },
    {
      group: m.reference_mcp_reads,
      tools: [
        ['campaign_overview', m.mcp_campaign_overview],
        ['current_session', m.mcp_current_session],
        ['live_set', m.mcp_live_set],
        ['read_note', m.mcp_read_note],
        ['find_notes', m.mcp_find_notes],
      ],
    },
    {
      group: m.reference_mcp_writes,
      tools: [
        ['create_note', m.mcp_create_note],
        ['edit_note', m.mcp_edit_note],
        ['create_track', m.mcp_create_track],
        ['move_note', m.mcp_move_note],
        ['create_beat', m.mcp_create_beat],
        ['add_to_beat', m.mcp_add_to_beat],
        ['create_session', m.mcp_create_session],
        ['set_active_session', m.mcp_set_active_session],
        ['plan_beat', m.mcp_plan_beat],
        ['add_to_live_set', m.mcp_add_to_live_set],
        ['spend', m.mcp_spend],
      ],
    },
    {
      group: m.reference_mcp_board,
      tools: [
        ['arrange_board', m.mcp_arrange_board],
        ['frame_cards', m.mcp_frame_cards],
        ['connect_cards', m.mcp_connect_cards],
        ['add_text', m.mcp_add_text],
      ],
    },
  ];
</script>

<div class="pane">
  <section class="block">
    <h3 class="block-title section-title">{m.sheet_title()}</h3>
    <p class="block-desc">
      <ParaglideMessage message={m.reference_shortcuts}>
        {#snippet kbd({ children })}<code class="kbd">{@render children?.()}</code>{/snippet}
      </ParaglideMessage>
    </p>
  </section>

  <section class="block">
    <h3 class="block-title section-title">{m.reference_glossary()}</h3>
    {#each GLOSSARY as group (group.group)}
      <section class="tool-group">
        <h4 class="tool-group-title ledger-label">{group.group()}</h4>
        <dl class="terms">
          {#each group.terms as [term, meaning, key] (term)}
            <dt class="term">{term()}</dt>
            <dd class="what">{meaning()}{key ? ` (${key})` : ''}</dd>
          {/each}
        </dl>
      </section>
    {/each}
  </section>

  <section class="block">
    <h3 class="block-title section-title">{m.reference_keywords()}</h3>
    <p class="block-desc">
      <ParaglideMessage message={m.reference_keywords_desc}>
        {#snippet em({ children })}<em>{@render children?.()}</em>{/snippet}
      </ParaglideMessage>
    </p>
    <p class="block-desc">{m.reference_keywords_search()}</p>
  </section>

  <section class="block">
    <h3 class="block-title section-title">{m.reference_mcp()}</h3>
    <p class="block-desc">{m.reference_mcp_desc()}</p>
    {#each MCP_TOOLS as group (group.group)}
      <section class="tool-group">
        <h4 class="tool-group-title ledger-label">{group.group()}</h4>
        <dl class="tools">
          {#each group.tools as [name, what] (name)}
            <dt class="tool">{name}</dt>
            <dd class="what">{what()}</dd>
          {/each}
        </dl>
      </section>
    {/each}
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

  .kbd {
    font-family: var(--font-mono);
    font-size: 0.85em;
    padding: 0.05em 0.3em;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
  }

  .tool-group {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .tool-group-title {
    margin: 0;
  }

  .tools,
  .terms {
    margin: 0;
    display: grid;
    grid-template-columns: 9rem 1fr;
    column-gap: 1.25rem;
    row-gap: 0.25rem;
    align-items: baseline;
    font-size: 0.8rem;
  }

  .tool {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .term {
    margin: 0;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .what {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.35;
  }
</style>
