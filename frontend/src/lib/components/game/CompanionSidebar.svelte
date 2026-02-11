<!--
  CompanionSidebar: Always-visible companion reactions panel.
  Shows 2-3 active companions with affinity, arc stage, and last reaction.
  V3.0: Surfaces companion_reactions data that was previously hidden in drawer.
-->
<script lang="ts">
  import { partyStatus } from '$lib/stores/game';
  import type { PartyStatusItem } from '$lib/api/types';

  // Arc stage thresholds (matches backend companion_reactions.py)
  function getArcStage(affinity: number): string {
    if (affinity >= 80) return 'LOYAL';
    if (affinity >= 60) return 'TRUSTED';
    if (affinity >= 30) return 'ALLY';
    return 'STRANGER';
  }

  function getArcColor(stage: string): string {
    switch (stage) {
      case 'LOYAL': return 'var(--color-paragon, #4a9eff)';
      case 'TRUSTED': return 'var(--color-investigate, #e6a817)';
      case 'ALLY': return 'var(--color-neutral, #9ca3af)';
      default: return 'var(--color-muted, #6b7280)';
    }
  }

  function getDeltaIcon(delta: number): string {
    if (delta > 0) return '\u2191'; // up arrow
    if (delta < 0) return '\u2193'; // down arrow
    return '';
  }

  function getDeltaColor(delta: number): string {
    if (delta > 0) return 'var(--color-paragon, #4a9eff)';
    if (delta < 0) return 'var(--color-renegade, #ef4444)';
    return 'var(--color-muted, #6b7280)';
  }

  function getMoodText(mood: string | null): string {
    if (!mood) return '';
    const moods: Record<string, string> = {
      'pleased': 'approves',
      'happy': 'is pleased',
      'neutral': '',
      'uneasy': 'is uneasy',
      'displeased': 'disapproves',
      'angry': 'is angry',
    };
    return moods[mood] || mood;
  }

  function getAffinityHearts(affinity: number): string {
    const filled = Math.round(affinity / 20);
    return '\u2665'.repeat(Math.min(filled, 5)) + '\u2661'.repeat(Math.max(0, 5 - filled));
  }

  $: companions = ($partyStatus ?? []).slice(0, 3) as PartyStatusItem[];
  $: hasCompanions = companions.length > 0;
</script>

{#if hasCompanions}
  <aside class="companion-sidebar" role="complementary" aria-label="Companion reactions">
    <h3 class="sidebar-title">Companions</h3>
    {#each companions as companion (companion.id)}
      {@const stage = getArcStage(companion.affinity)}
      {@const moodText = getMoodText(companion.mood_tag)}
      <div class="companion-card">
        <div class="companion-header">
          <span class="companion-name">{companion.name}</span>
          <span class="arc-badge" style="color: {getArcColor(stage)}">{stage}</span>
        </div>
        <div class="companion-hearts" aria-label="Affinity: {companion.affinity}">
          {getAffinityHearts(companion.affinity)}
          {#if companion.affinity_delta !== 0}
            <span class="delta" style="color: {getDeltaColor(companion.affinity_delta)}">
              {getDeltaIcon(companion.affinity_delta)}{Math.abs(companion.affinity_delta)}
            </span>
          {/if}
        </div>
        {#if moodText}
          <div class="companion-reaction">{companion.name} {moodText}</div>
        {/if}
      </div>
    {/each}
  </aside>
{/if}

<style>
  .companion-sidebar {
    width: 260px;
    padding: 0.75rem;
    border-left: 1px solid var(--color-border, #374151);
    background: var(--color-surface, #1f2937);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    overflow-y: auto;
    max-height: 100vh;
  }

  .sidebar-title {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--color-muted, #9ca3af);
    margin: 0 0 0.25rem 0;
  }

  .companion-card {
    padding: 0.5rem;
    border-radius: 0.375rem;
    background: var(--color-surface-alt, #111827);
    border: 1px solid var(--color-border, #374151);
  }

  .companion-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  .companion-name {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--color-text, #f3f4f6);
  }

  .arc-badge {
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .companion-hearts {
    font-size: 0.75rem;
    color: var(--color-renegade, #ef4444);
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .delta {
    font-size: 0.625rem;
    font-weight: 600;
  }

  .companion-reaction {
    font-size: 0.75rem;
    font-style: italic;
    color: var(--color-muted, #9ca3af);
    margin-top: 0.25rem;
  }

  /* Mobile: collapse to bottom strip */
  @media (max-width: 768px) {
    .companion-sidebar {
      width: 100%;
      max-height: none;
      flex-direction: row;
      overflow-x: auto;
      overflow-y: hidden;
      border-left: none;
      border-top: 1px solid var(--color-border, #374151);
      padding: 0.5rem;
    }

    .sidebar-title {
      display: none;
    }

    .companion-card {
      min-width: 160px;
      flex-shrink: 0;
    }
  }
</style>
