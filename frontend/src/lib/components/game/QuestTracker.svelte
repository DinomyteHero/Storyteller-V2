<!--
  QuestTracker: Floating quest objective indicator.
  Shows the active quest name, current objective, and progress dots.
  V3.0: Surfaces quest_log data as a persistent UI element.
-->
<script lang="ts">
  import { questLog } from '$lib/stores/game';

  interface QuestEntry {
    status: string;
    current_stage?: string;
    stages_completed?: number;
    total_stages?: number;
    title?: string;
    description?: string;
  }

  $: activeQuests = (() => {
    const log = $questLog as Record<string, QuestEntry> | null;
    if (!log || typeof log !== 'object') return [];
    return Object.entries(log)
      .filter(([_, q]) => q && q.status === 'active')
      .map(([id, q]) => ({
        id,
        title: q.title || id.replace(/-/g, ' ').replace(/^gen quest /, ''),
        stage: q.current_stage || q.description || 'Investigate...',
        completed: q.stages_completed || 0,
        total: q.total_stages || 3,
        status: q.status,
      }))
      .slice(0, 2); // Show max 2 active quests
  })();

  $: hasQuests = activeQuests.length > 0;
  $: primaryQuest = activeQuests[0] || null;

  let expanded = false;
  let pulseAnimation = false;

  // Pulse on quest change
  $: if (primaryQuest) {
    pulseAnimation = true;
    setTimeout(() => { pulseAnimation = false; }, 1500);
  }

  function toggleExpand() {
    expanded = !expanded;
  }
</script>

{#if hasQuests && primaryQuest}
  <div
    class="quest-tracker"
    class:pulse={pulseAnimation}
    class:expanded
    role="status"
    aria-label="Active quest: {primaryQuest.title}"
  >
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="quest-header" on:click={toggleExpand}>
      <span class="quest-icon">&#x2726;</span>
      <span class="quest-title">{primaryQuest.title}</span>
      <span class="quest-toggle">{expanded ? '\u25B2' : '\u25BC'}</span>
    </div>

    {#if expanded}
      <div class="quest-details">
        <p class="quest-stage">{primaryQuest.stage}</p>
        <div class="quest-progress" aria-label="Progress: {primaryQuest.completed} of {primaryQuest.total}">
          {#each Array(primaryQuest.total) as _, i}
            <span
              class="progress-dot"
              class:filled={i < primaryQuest.completed}
              class:current={i === primaryQuest.completed}
            ></span>
          {/each}
        </div>

        {#if activeQuests.length > 1}
          <div class="secondary-quest">
            <span class="quest-icon-small">&#x2726;</span>
            <span class="secondary-title">{activeQuests[1].title}</span>
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .quest-tracker {
    position: fixed;
    top: 4rem;
    right: 1rem;
    width: 240px;
    background: var(--color-surface, #1f2937);
    border: 1px solid var(--color-border, #374151);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 40;
    transition: all 0.3s ease;
  }

  .quest-tracker.pulse {
    animation: questPulse 1.5s ease;
  }

  @keyframes questPulse {
    0% { border-color: var(--color-investigate, #e6a817); box-shadow: 0 0 12px rgba(230, 168, 23, 0.4); }
    100% { border-color: var(--color-border, #374151); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3); }
  }

  .quest-header {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    cursor: pointer;
    user-select: none;
  }

  .quest-icon {
    color: var(--color-investigate, #e6a817);
    font-size: 0.875rem;
  }

  .quest-title {
    flex: 1;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--color-text, #f3f4f6);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .quest-toggle {
    font-size: 0.625rem;
    color: var(--color-muted, #6b7280);
  }

  .quest-details {
    margin-top: 0.5rem;
    padding-top: 0.375rem;
    border-top: 1px solid var(--color-border, #374151);
  }

  .quest-stage {
    font-size: 0.75rem;
    color: var(--color-muted, #9ca3af);
    margin: 0 0 0.5rem 0;
    font-style: italic;
  }

  .quest-progress {
    display: flex;
    gap: 0.375rem;
    align-items: center;
  }

  .progress-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-surface-alt, #111827);
    border: 1px solid var(--color-muted, #6b7280);
    transition: all 0.3s ease;
  }

  .progress-dot.filled {
    background: var(--color-investigate, #e6a817);
    border-color: var(--color-investigate, #e6a817);
  }

  .progress-dot.current {
    border-color: var(--color-investigate, #e6a817);
    box-shadow: 0 0 4px rgba(230, 168, 23, 0.5);
  }

  .secondary-quest {
    margin-top: 0.5rem;
    padding-top: 0.375rem;
    border-top: 1px solid var(--color-border, #374151);
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .quest-icon-small {
    color: var(--color-muted, #6b7280);
    font-size: 0.625rem;
  }

  .secondary-title {
    font-size: 0.6875rem;
    color: var(--color-muted, #9ca3af);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Mobile: bottom-right, smaller */
  @media (max-width: 768px) {
    .quest-tracker {
      top: auto;
      bottom: 1rem;
      right: 0.5rem;
      width: 200px;
    }
  }
</style>
