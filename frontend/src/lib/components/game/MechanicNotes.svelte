<!--
  MechanicNotes.svelte — V7.0
  Collapsible panel showing mechanic resolution details (dice result, difficulty,
  success/failure, outcome summary). Gives players transparency into the Game
  Master's rulings without cluttering the narrative.
-->
<script lang="ts">
  import type { MechanicNotes } from '$lib/api/types';

  interface Props {
    notes: MechanicNotes;
  }

  let { notes }: Props = $props();

  let expanded = $state(false);

  function toggle() {
    expanded = !expanded;
  }

  // Dice result display mapping
  const DICE_LABELS: Record<string, { label: string; cls: string }> = {
    'Triumph': { label: 'Triumph', cls: 'result-triumph' },
    'Success+Advantage': { label: 'Success + Advantage', cls: 'result-success' },
    'Success': { label: 'Success', cls: 'result-success' },
    'Success+Threat': { label: 'Success + Threat', cls: 'result-mixed' },
    'Failure+Advantage': { label: 'Failure + Advantage', cls: 'result-mixed' },
    'Failure': { label: 'Failure', cls: 'result-failure' },
    'Failure+Threat': { label: 'Failure + Threat', cls: 'result-failure' },
    'Despair': { label: 'Despair', cls: 'result-despair' },
  };

  let diceInfo = $derived(
    notes.dice_result ? (DICE_LABELS[notes.dice_result] ?? { label: notes.dice_result, cls: '' }) : null
  );

  let successLabel = $derived(
    notes.success === true ? 'Succeeded' : notes.success === false ? 'Failed' : null
  );
</script>

<div class="mechanic-notes" role="region" aria-label="Mechanic resolution details">
  <button
    class="mechanic-toggle"
    onclick={toggle}
    aria-expanded={expanded}
    aria-controls="mechanic-details"
  >
    <span class="mechanic-icon" aria-hidden="true">&#x2B22;</span>
    <span class="mechanic-label">Mechanic's Notes</span>
    {#if diceInfo}
      <span class="mechanic-badge {diceInfo.cls}">{diceInfo.label}</span>
    {/if}
    <span class="mechanic-chevron" class:open={expanded} aria-hidden="true">&#x25B8;</span>
  </button>

  {#if expanded}
    <div id="mechanic-details" class="mechanic-details slide-down">
      <div class="detail-grid">
        {#if notes.action_type}
          <div class="detail-item">
            <span class="detail-key">Action</span>
            <span class="detail-value">{notes.action_type}</span>
          </div>
        {/if}
        {#if notes.difficulty}
          <div class="detail-item">
            <span class="detail-key">Difficulty</span>
            <span class="detail-value difficulty-{notes.difficulty.toLowerCase()}">{notes.difficulty}</span>
          </div>
        {/if}
        {#if diceInfo}
          <div class="detail-item">
            <span class="detail-key">Dice</span>
            <span class="detail-value {diceInfo.cls}">{diceInfo.label}</span>
          </div>
        {/if}
        {#if successLabel}
          <div class="detail-item">
            <span class="detail-key">Result</span>
            <span class="detail-value" class:success-true={notes.success} class:success-false={!notes.success}>{successLabel}</span>
          </div>
        {/if}
        {#if notes.critical_outcome}
          <div class="detail-item detail-span">
            <span class="detail-key">Critical</span>
            <span class="detail-value critical-{notes.critical_outcome === 'CRITICAL_SUCCESS' ? 'success' : 'failure'}">
              {notes.critical_outcome === 'CRITICAL_SUCCESS' ? 'Critical Success!' : 'Critical Failure!'}
            </span>
          </div>
        {/if}
        {#if notes.outcome_summary}
          <div class="detail-item detail-span">
            <span class="detail-key">Summary</span>
            <span class="detail-value detail-summary">{notes.outcome_summary}</span>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .mechanic-notes {
    margin-top: 0.5rem;
    border-top: 1px solid var(--color-border, rgba(255, 255, 255, 0.08));
  }

  .mechanic-toggle {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.4rem 0;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--color-muted, #6b7280);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-family: inherit;
    transition: color 0.15s ease;
  }

  .mechanic-toggle:hover {
    color: var(--color-text-secondary, #9ca3af);
  }

  .mechanic-icon {
    font-size: 0.6rem;
    opacity: 0.6;
  }

  .mechanic-label {
    flex-shrink: 0;
  }

  .mechanic-badge {
    font-size: 0.6rem;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: none;
  }

  .mechanic-chevron {
    margin-left: auto;
    font-size: 0.6rem;
    transition: transform 0.2s ease;
  }

  .mechanic-chevron.open {
    transform: rotate(90deg);
  }

  /* Dice result badge colors */
  .result-triumph { background: rgba(200, 160, 50, 0.2); color: #e8c96a; }
  .result-success { background: rgba(40, 160, 80, 0.15); color: #4ade80; }
  .result-mixed { background: rgba(200, 160, 50, 0.12); color: #d4a64a; }
  .result-failure { background: rgba(200, 60, 60, 0.15); color: #f87171; }
  .result-despair { background: rgba(160, 30, 30, 0.2); color: #ef4444; }

  /* Details panel */
  .mechanic-details {
    padding: 0.35rem 0 0.5rem;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.3rem 0.75rem;
  }

  .detail-span {
    grid-column: 1 / -1;
  }

  .detail-item {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .detail-key {
    font-size: 0.55rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--color-muted, #6b7280);
    font-weight: 600;
  }

  .detail-value {
    font-size: 0.75rem;
    color: var(--color-text-secondary, #9ca3af);
  }

  .detail-summary {
    font-style: italic;
    line-height: 1.4;
  }

  /* Success/failure colors */
  .success-true { color: #4ade80; }
  .success-false { color: #f87171; }

  /* Critical outcome colors */
  .critical-success { color: #e8c96a; font-weight: 700; }
  .critical-failure { color: #ef4444; font-weight: 700; }

  /* Difficulty colors */
  .difficulty-trivial { color: #9ca3af; }
  .difficulty-easy { color: #4ade80; }
  .difficulty-moderate { color: #d4a64a; }
  .difficulty-hard { color: #f59e0b; }
  .difficulty-formidable { color: #f87171; }
  .difficulty-extreme { color: #ef4444; font-weight: 700; }

  /* Slide-down animation */
  .slide-down {
    animation: mechSlideDown 0.2s ease forwards;
  }

  @keyframes mechSlideDown {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>
