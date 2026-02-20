<script lang="ts">
  import type { ContentCatalogEntry } from '$lib/api/content';

  interface Props {
    world: ContentCatalogEntry;
    onclick?: () => void;
  }
  let { world, onclick }: Props = $props();

  let sourceBadge = $derived(
    world.source === 'generated' ? 'Generated' : 'Static'
  );
</script>

<button class="world-card press-scale" type="button" onclick={onclick}>
  <div class="world-header">
    <span class="world-name">{world.period_display_name || world.period_id}</span>
    <span class="source-badge" class:generated={world.source === 'generated'}>
      {sourceBadge}
    </span>
  </div>
  <p class="world-setting">{world.setting_display_name || world.setting_id}</p>
  {#if world.summary}
    <p class="world-summary">{world.summary}</p>
  {/if}
  <div class="world-stats">
    {#if world.backgrounds_count > 0}
      <span class="stat-pill">{world.backgrounds_count} backgrounds</span>
    {/if}
    {#if world.companions_count > 0}
      <span class="stat-pill">{world.companions_count} companions</span>
    {/if}
    {#if world.locations_count > 0}
      <span class="stat-pill">{world.locations_count} locations</span>
    {/if}
    {#if world.quests_count > 0}
      <span class="stat-pill">{world.quests_count} quests</span>
    {/if}
  </div>
  {#if !world.playable}
    <div class="not-playable">Not playable</div>
  {/if}
</button>

<style>
  .world-card {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 1rem;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.12));
    border-radius: var(--panel-radius, 8px);
    background: var(--bg-panel, rgba(255, 255, 255, 0.03));
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    width: 100%;
    text-align: left;
  }
  .world-card:hover {
    border-color: var(--border-accent, rgba(255, 255, 255, 0.35));
    background: rgba(255, 255, 255, 0.06);
  }
  .world-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }
  .world-name {
    font-family: var(--font-heading, 'Rajdhani', sans-serif);
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-heading, #e8c56a);
  }
  .source-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-muted, #888);
  }
  .source-badge.generated {
    background: rgba(100, 200, 255, 0.12);
    color: #7ec8e3;
  }
  .world-setting {
    font-size: 0.8rem;
    color: var(--text-secondary, #aaa);
    margin: 0;
  }
  .world-summary {
    font-size: 0.78rem;
    color: var(--text-muted, #888);
    margin: 0;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .world-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.25rem;
  }
  .stat-pill {
    font-size: 0.65rem;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-muted, #888);
  }
  .not-playable {
    font-size: 0.7rem;
    color: var(--accent-danger, #ff5040);
    margin-top: 0.2rem;
  }
</style>
