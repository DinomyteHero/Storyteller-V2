<!--
  NpcIdentityStrip.svelte — V4.1
  Shows the active NPC(s) with their MemoryAgent-enriched emotional state and agenda.
  Renders above the narrative when present_npcs are in the scene.
  Clicking/tapping expands to full memory detail.
-->
<script lang="ts">
  import type { NpcContext } from '$lib/api/types';

  interface Props {
    npcs: NpcContext[];
  }

  let { npcs }: Props = $props();

  let expandedNpc: string | null = $state(null);

  function emotionClass(state: string): string {
    const s = (state || '').toLowerCase();
    if (s.includes('hostile') || s.includes('furious') || s.includes('angry') || s.includes('suspicious')) return 'hostile';
    if (s.includes('friendly') || s.includes('warm') || s.includes('trust') || s.includes('pleased')) return 'friendly';
    if (s.includes('fearful') || s.includes('afraid') || s.includes('nervous') || s.includes('wary')) return 'fearful';
    if (s.includes('curious') || s.includes('interested') || s.includes('intrigued')) return 'curious';
    return 'neutral';
  }

  function toggle(id: string) {
    expandedNpc = expandedNpc === id ? null : id;
  }
</script>

{#if npcs.length > 0}
  <div class="npc-strip" aria-label="Active NPCs in scene">
    {#each npcs.slice(0, 3) as npc}
      {@const ec = emotionClass(npc.emotional_state)}
      {@const isExpanded = expandedNpc === npc.id}
      <div
        class="npc-card emotion-{ec}"
        class:expanded={isExpanded}
        role="button"
        tabindex="0"
        aria-expanded={isExpanded}
        aria-label="{npc.name}: {npc.emotional_state}. {npc.agenda ? 'Agenda: ' + npc.agenda : ''}"
        onclick={() => toggle(npc.id)}
        onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && toggle(npc.id)}
      >
        <div class="npc-header">
          <span class="npc-sigil" aria-hidden="true">◈</span>
          <div class="npc-info">
            <span class="npc-name">{npc.name}</span>
            <span class="npc-role">{npc.role}</span>
          </div>
          {#if npc.emotional_state}
            <span class="emotion-badge emotion-{ec}" aria-label="Emotional state: {npc.emotional_state}">
              {npc.emotional_state}
            </span>
          {/if}
          {#if npc.agenda || npc.next_move}
            <span class="expand-hint" aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
          {/if}
        </div>

        {#if isExpanded && (npc.agenda || npc.next_move)}
          <div class="npc-detail fade-in" aria-label="NPC detail">
            {#if npc.agenda}
              <div class="detail-row">
                <span class="detail-label">wants</span>
                <span class="detail-value">{npc.agenda}</span>
              </div>
            {/if}
            {#if npc.next_move}
              <div class="detail-row">
                <span class="detail-label">will</span>
                <span class="detail-value">{npc.next_move}</span>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .npc-strip {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 10px;
  }

  .npc-card {
    border-radius: 6px;
    padding: 7px 10px;
    border: 1px solid;
    cursor: pointer;
    transition: all 0.2s ease;
    user-select: none;
  }

  /* Emotion color variants */
  .emotion-neutral {
    background: rgba(100, 120, 160, 0.07);
    border-color: rgba(100, 120, 160, 0.22);
  }
  .emotion-hostile {
    background: rgba(220, 60, 50, 0.06);
    border-color: rgba(220, 60, 50, 0.25);
  }
  .emotion-friendly {
    background: rgba(80, 180, 120, 0.06);
    border-color: rgba(80, 180, 120, 0.22);
  }
  .emotion-fearful {
    background: rgba(220, 160, 40, 0.06);
    border-color: rgba(220, 160, 40, 0.22);
  }
  .emotion-curious {
    background: rgba(90, 150, 220, 0.07);
    border-color: rgba(90, 150, 220, 0.22);
  }

  .npc-card:hover {
    filter: brightness(1.12);
  }
  .npc-card.expanded {
    padding-bottom: 10px;
  }

  /* ======================== HEADER ======================== */
  .npc-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .npc-sigil {
    font-size: 0.75rem;
    opacity: 0.5;
    flex-shrink: 0;
  }

  .npc-info {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
  }

  .npc-name {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-heading);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .npc-role {
    font-size: 0.65rem;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ======================== EMOTION BADGE ======================== */
  .emotion-badge {
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 1px 6px;
    border-radius: 3px;
    border: 1px solid;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .emotion-badge.emotion-neutral {
    color: var(--text-muted);
    border-color: rgba(100, 120, 160, 0.35);
    background: transparent;
  }
  .emotion-badge.emotion-hostile {
    color: #e05555;
    border-color: rgba(220, 60, 50, 0.4);
    background: transparent;
  }
  .emotion-badge.emotion-friendly {
    color: #5ab87a;
    border-color: rgba(80, 180, 120, 0.4);
    background: transparent;
  }
  .emotion-badge.emotion-fearful {
    color: #c8963a;
    border-color: rgba(220, 160, 40, 0.4);
    background: transparent;
  }
  .emotion-badge.emotion-curious {
    color: #5a9fdc;
    border-color: rgba(90, 150, 220, 0.4);
    background: transparent;
  }

  .expand-hint {
    font-size: 0.65rem;
    color: var(--text-muted);
    flex-shrink: 0;
    transition: transform 0.2s ease;
  }

  /* ======================== EXPANDED DETAIL ======================== */
  .npc-detail {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid rgba(120, 140, 180, 0.15);
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .detail-row {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }

  .detail-label {
    font-size: 0.6rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.4px;
    width: 28px;
    flex-shrink: 0;
    font-family: 'JetBrains Mono', monospace;
  }

  .detail-value {
    font-size: 0.7rem;
    color: var(--text-secondary);
    font-style: italic;
    line-height: 1.3;
  }

  /* ======================== ANIMATION ======================== */
  .fade-in {
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* ======================== RESPONSIVE ======================== */
  @media (max-width: 768px) {
    .npc-card {
      padding: 6px 8px;
    }
    .npc-name {
      font-size: 0.68rem;
    }
  }
</style>
