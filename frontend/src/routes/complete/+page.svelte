<!--
  Campaign Completion Summary Screen (V3.2)
  Displays campaign results after completion: factions, companions, next campaign pitch.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { resetGame } from '$lib/stores/game';
  import type { PartyStatusItem } from '$lib/api/types';

  interface CompletionData {
    status: string;
    legacy_id: string;
    campaign_id: string;
    recommended_next_scale: string;
    next_campaign_pitch: string;
  }

  let data = $state<CompletionData | null>(null);
  let turnsPlayed = $state(0);
  let factions = $state<Record<string, number>>({});
  let party = $state<PartyStatusItem[]>([]);

  onMount(() => {
    const raw = sessionStorage.getItem('completionData');
    if (!raw) {
      goto('/');
      return;
    }
    data = JSON.parse(raw) as CompletionData;
    turnsPlayed = Number(sessionStorage.getItem('completionTurns') || '0');
    try { factions = JSON.parse(sessionStorage.getItem('completionFactions') || '{}'); } catch { factions = {}; }
    try { party = JSON.parse(sessionStorage.getItem('completionParty') || '[]'); } catch { party = []; }

    // Clean up session storage
    sessionStorage.removeItem('completionData');
    sessionStorage.removeItem('completionTurns');
    sessionStorage.removeItem('completionFactions');
    sessionStorage.removeItem('completionParty');
  });

  function startNewCampaign() {
    resetGame();
    goto('/create');
  }

  function backToMenu() {
    resetGame();
    goto('/');
  }

  const factionEntries = $derived(Object.entries(factions).sort(([,a], [,b]) => b - a));
  const scaleLabel = $derived(
    data?.recommended_next_scale
      ? data.recommended_next_scale.charAt(0).toUpperCase() + data.recommended_next_scale.slice(1)
      : 'Medium'
  );
</script>

{#if data}
<div class="complete-container">
  <div class="complete-content">
    <h1 class="complete-title">Campaign Complete</h1>
    <p class="complete-subtitle">Your story has reached its conclusion</p>

    <!-- Stats Overview -->
    <div class="stats-row">
      <div class="stat-card card">
        <div class="stat-value">{turnsPlayed}</div>
        <div class="stat-label">Turns Played</div>
      </div>
      <div class="stat-card card">
        <div class="stat-value">{factionEntries.length}</div>
        <div class="stat-label">Factions Encountered</div>
      </div>
      <div class="stat-card card">
        <div class="stat-value">{party.length}</div>
        <div class="stat-label">Companions</div>
      </div>
    </div>

    <!-- Faction Standings -->
    {#if factionEntries.length > 0}
      <section class="section card">
        <h2 class="section-heading">Faction Standings</h2>
        <div class="faction-list">
          {#each factionEntries as [name, rep]}
            {@const pct = Math.max(0, Math.min(100, ((rep + 100) / 200) * 100))}
            {@const repLabel = rep > 0 ? `+${rep}` : String(rep)}
            <div class="faction-row">
              <span class="faction-name">{name}</span>
              <div class="faction-bar-track">
                <div class="faction-bar-fill" style="width: {pct}%; background: {rep >= 0 ? 'var(--color-paragon, #4a9eff)' : 'var(--color-renegade, #ef4444)'}"></div>
              </div>
              <span class="faction-rep">{repLabel}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Companion Arcs -->
    {#if party.length > 0}
      <section class="section card">
        <h2 class="section-heading">Companion Arcs</h2>
        <div class="companion-list">
          {#each party as comp}
            {@const affinityLabel = comp.affinity > 0 ? `+${comp.affinity}` : String(comp.affinity)}
            <div class="companion-row">
              <span class="companion-name">{comp.name}</span>
              <span class="companion-mood">{comp.mood_tag ?? 'Neutral'}</span>
              <span class="companion-affinity" class:positive={comp.affinity >= 0} class:negative={comp.affinity < 0}>
                {affinityLabel}
              </span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Next Campaign Pitch -->
    {#if data.next_campaign_pitch}
      <section class="section card pitch-card">
        <h2 class="section-heading">What Comes Next...</h2>
        <p class="pitch-text">{data.next_campaign_pitch}</p>
        <div class="pitch-meta">
          Recommended scale: <strong>{scaleLabel}</strong>
        </div>
      </section>
    {/if}

    <!-- Actions -->
    <div class="actions">
      <button class="btn" onclick={backToMenu}>Main Menu</button>
      <button class="btn btn-primary" onclick={startNewCampaign}>New Campaign</button>
    </div>
  </div>
</div>
{:else}
<div class="complete-container">
  <div class="complete-content">
    <p>Loading completion data...</p>
  </div>
</div>
{/if}

<style>
  .complete-container {
    min-height: 100vh;
    display: flex;
    justify-content: center;
    padding: 2rem 1rem;
    background: var(--bg-primary, #0a0f1c);
  }

  .complete-content {
    max-width: 640px;
    width: 100%;
    text-align: center;
  }

  .complete-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-primary, #f3f4f6);
    margin-bottom: 0.25rem;
  }

  .complete-subtitle {
    color: var(--text-muted, #6b7280);
    margin-bottom: 2rem;
  }

  /* Stats overview */
  .stats-row {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    flex: 1;
    padding: 1rem;
    text-align: center;
  }

  .stat-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--accent, #4a9eff);
  }

  .stat-label {
    font-size: 0.75rem;
    color: var(--text-muted, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 0.25rem;
  }

  /* Sections */
  .section {
    text-align: left;
    padding: 1.25rem;
    margin-bottom: 1rem;
  }

  .section-heading {
    font-size: 1rem;
    color: var(--text-secondary, #9ca3af);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 1rem;
    text-align: center;
  }

  /* Faction bars */
  .faction-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .faction-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .faction-name {
    flex: 0 0 120px;
    font-size: 0.875rem;
    color: var(--text-primary, #f3f4f6);
    text-align: right;
  }

  .faction-bar-track {
    flex: 1;
    height: 8px;
    background: var(--color-surface-alt, #111827);
    border-radius: 4px;
    overflow: hidden;
  }

  .faction-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
  }

  .faction-rep {
    flex: 0 0 40px;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary, #9ca3af);
    text-align: left;
  }

  /* Companions */
  .companion-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .companion-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color, rgba(255, 255, 255, 0.06));
  }

  .companion-row:last-child {
    border-bottom: none;
  }

  .companion-name {
    flex: 1;
    font-weight: 600;
    color: var(--text-primary, #f3f4f6);
  }

  .companion-mood {
    font-size: 0.8rem;
    color: var(--text-muted, #6b7280);
  }

  .companion-affinity {
    font-weight: 700;
    font-size: 0.875rem;
  }

  .companion-affinity.positive {
    color: var(--color-paragon, #4a9eff);
  }

  .companion-affinity.negative {
    color: var(--color-renegade, #ef4444);
  }

  /* Pitch card */
  .pitch-card {
    text-align: center;
    background: linear-gradient(135deg, rgba(74, 158, 255, 0.05), rgba(234, 179, 8, 0.05));
    border-color: rgba(74, 158, 255, 0.15);
  }

  .pitch-text {
    font-size: 1.05rem;
    color: var(--text-primary, #f3f4f6);
    line-height: 1.6;
    font-style: italic;
    margin-bottom: 0.75rem;
  }

  .pitch-meta {
    font-size: 0.8rem;
    color: var(--text-muted, #6b7280);
  }

  /* Actions */
  .actions {
    display: flex;
    justify-content: center;
    gap: 1rem;
    margin-top: 2rem;
  }
</style>
