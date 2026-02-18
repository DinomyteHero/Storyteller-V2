<script lang="ts">
  import type { EraSpecies } from '$lib/api/types';

  interface Props {
    species: EraSpecies;
    selected: boolean;
    onclick: () => void;
  }

  let { species, selected, onclick }: Props = $props();

  // Format stat bonuses as "+1 Charisma" style strings
  let statBonusLines = $derived(
    Object.entries(species.stat_bonus ?? {})
      .filter(([, v]) => v !== 0)
      .map(([k, v]) => `${v > 0 ? '+' : ''}${v} ${k}`)
  );
</script>

<button
  class="species-card"
  class:selected
  onclick={onclick}
  type="button"
  aria-pressed={selected}
>
  <div class="species-header">
    <span class="species-name">{species.name}</span>
    {#if statBonusLines.length > 0}
      <span class="stat-bonus">{statBonusLines.join(', ')}</span>
    {/if}
  </div>

  <p class="species-description">{species.description}</p>

  {#if species.typical_traits && species.typical_traits.length > 0}
    <div class="trait-tags">
      {#each species.typical_traits as trait}
        <span class="trait-tag">{trait}</span>
      {/each}
    </div>
  {/if}

  {#if species.narrative_hooks && species.narrative_hooks.length > 0}
    <p class="narrative-hook">{species.narrative_hooks[0]}</p>
  {/if}
</button>

<style>
  .species-card {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.03);
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s, background 0.15s;
    width: 100%;
  }

  .species-card:hover {
    border-color: rgba(255, 255, 255, 0.35);
    background: rgba(255, 255, 255, 0.07);
  }

  .species-card.selected {
    border-color: #e8c56a;
    background: rgba(232, 197, 106, 0.08);
  }

  .species-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .species-name {
    font-size: 1.05rem;
    font-weight: 600;
    color: #f0e6c8;
  }

  .stat-bonus {
    font-size: 0.8rem;
    color: #a0e080;
    font-family: monospace;
  }

  .species-description {
    font-size: 0.88rem;
    color: rgba(240, 230, 200, 0.75);
    line-height: 1.5;
    margin: 0;
  }

  .trait-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }

  .trait-tag {
    font-size: 0.75rem;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.07);
    color: rgba(240, 230, 200, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  .narrative-hook {
    font-size: 0.8rem;
    font-style: italic;
    color: rgba(240, 230, 200, 0.5);
    margin: 0;
    padding-top: 0.25rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }
</style>
