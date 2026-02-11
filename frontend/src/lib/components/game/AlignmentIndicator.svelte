<!--
  AlignmentIndicator: Paragon/Renegade alignment meter.
  Visual horizontal bar showing the player's accumulated moral alignment.
  V3.0: Tracks cumulative tone choices (PARAGON vs RENEGADE).
-->
<script lang="ts">
  import { lastTurnResponse } from '$lib/stores/game';

  // Extract alignment from world_state or compute from tone history
  // Range: -100 (full Renegade) to +100 (full Paragon), 0 = neutral
  $: alignment = (() => {
    const resp = $lastTurnResponse;
    if (!resp) return 0;
    // Check if alignment is directly available in the response
    const debug = resp.debug as Record<string, unknown> | undefined;
    if (debug?.alignment_score !== undefined) {
      return Number(debug.alignment_score) || 0;
    }
    // Fallback: compute from party_status or return 0
    return 0;
  })();

  $: percentage = Math.round(((alignment + 100) / 200) * 100);
  $: label = alignment > 20 ? 'Paragon' : alignment < -20 ? 'Renegade' : 'Neutral';
  $: barColor = alignment > 20
    ? 'var(--color-paragon, #4a9eff)'
    : alignment < -20
      ? 'var(--color-renegade, #ef4444)'
      : 'var(--color-neutral, #9ca3af)';
</script>

<div class="alignment-indicator" role="meter" aria-label="Alignment: {label}" aria-valuenow={alignment} aria-valuemin={-100} aria-valuemax={100}>
  <div class="alignment-labels">
    <span class="label-renegade">Renegade</span>
    <span class="label-current" style="color: {barColor}">{label}</span>
    <span class="label-paragon">Paragon</span>
  </div>
  <div class="alignment-track">
    <div class="alignment-fill" style="width: {percentage}%; background: {barColor}"></div>
    <div class="alignment-pip" style="left: {percentage}%"></div>
    <div class="alignment-center"></div>
  </div>
</div>

<style>
  .alignment-indicator {
    padding: 0.25rem 0.75rem;
    user-select: none;
  }

  .alignment-labels {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.625rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.125rem;
  }

  .label-renegade {
    color: var(--color-renegade, #ef4444);
  }

  .label-paragon {
    color: var(--color-paragon, #4a9eff);
  }

  .label-current {
    font-weight: 700;
    font-size: 0.6875rem;
  }

  .alignment-track {
    position: relative;
    height: 6px;
    background: var(--color-surface-alt, #111827);
    border-radius: 3px;
    overflow: visible;
  }

  .alignment-fill {
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease, background 0.5s ease;
    opacity: 0.6;
  }

  .alignment-pip {
    position: absolute;
    top: -2px;
    width: 10px;
    height: 10px;
    background: var(--color-text, #f3f4f6);
    border-radius: 50%;
    transform: translateX(-50%);
    transition: left 0.5s ease;
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
  }

  .alignment-center {
    position: absolute;
    left: 50%;
    top: -1px;
    width: 2px;
    height: 8px;
    background: var(--color-muted, #6b7280);
    transform: translateX(-50%);
    opacity: 0.5;
  }
</style>
