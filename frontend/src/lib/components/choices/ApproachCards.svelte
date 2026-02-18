<!--
  ApproachCards.svelte — V4.1
  Horizontal-scroll approach cards that POPULATE the free text input (not submit directly).
  The cards suggest tone/approach; the player refines the input text before submitting.

  Primary source: PlayerResponse[] from DialogueTurn.
  Fallback: ActionSuggestion[] (legacy flat format).
-->
<script lang="ts">
  import type { PlayerResponse, ActionSuggestion } from '$lib/api/types';
  import { TONE_ICONS } from '$lib/utils/constants';

  interface Props {
    playerResponses: PlayerResponse[];
    suggestedActions: ActionSuggestion[];
    animKey: number;
    onPopulate: (text: string) => void; // populate the text input (not submit)
    activeObligations?: string[] | null; // V5.0: narrative obligations from ContinuityAgent
  }

  let { playerResponses, suggestedActions, animKey, onPopulate, activeObligations = null }: Props = $props();

  const TONE_ORDER: Record<string, number> = {
    PARAGON: 0,
    INVESTIGATE: 1,
    RENEGADE: 2,
    NEUTRAL: 3,
  };

  interface UnifiedApproach {
    id: string;
    displayText: string;
    toneTag: string;
    riskLevel: string;
    consequenceHint: string;
    populateText: string;
    meaningTag: string;
  }

  let approaches = $derived.by(() => {
    let items: UnifiedApproach[];

    if (playerResponses.length > 0) {
      items = playerResponses.map((r, i) => ({
        id: r.id || `resp_${i + 1}`,
        displayText: r.display_text,
        toneTag: r.tone_tag?.toUpperCase() || 'NEUTRAL',
        riskLevel: r.risk_level || 'SAFE',
        consequenceHint: r.consequence_hint || '',
        populateText: r.display_text,
        meaningTag: r.meaning_tag || '',
      }));
    } else {
      items = suggestedActions.map((a, i) => ({
        id: `action_${i + 1}`,
        displayText: a.label,
        toneTag: a.tone_tag?.toUpperCase() || 'NEUTRAL',
        riskLevel: a.risk_level || 'SAFE',
        consequenceHint: a.consequence_hint || '',
        populateText: a.intent_text || a.label,
        meaningTag: '',
      }));
    }

    return items.sort((a, b) =>
      (TONE_ORDER[a.toneTag] ?? 3) - (TONE_ORDER[b.toneTag] ?? 3)
    );
  });

  function riskClass(level: string): string {
    const l = level?.toUpperCase() ?? 'SAFE';
    if (l === 'DANGEROUS') return 'risk-dangerous';
    if (l === 'RISKY') return 'risk-risky';
    return '';
  }
</script>

<div class="approach-section" role="group" aria-label="Suggested approaches">
  {#if activeObligations && activeObligations.length > 0}
    <div class="obligations-row" aria-label="Active narrative obligations">
      {#each activeObligations as obligation}
        <span class="obligation-badge" title={obligation}>
          {obligation.length > 40 ? obligation.slice(0, 37) + '…' : obligation}
        </span>
      {/each}
    </div>
  {/if}
  <div class="approach-label">approaches</div>
  {#key animKey}
    <div class="approach-scroll">
      {#each approaches as approach, i}
        <button
          class="approach-card tone-{approach.toneTag.toLowerCase()} stagger-enter"
          style="animation-delay: {i * 55}ms"
          onclick={() => onPopulate(approach.populateText)}
          aria-label="Approach {i + 1}: {approach.displayText}. Tap to use as starting point. {approach.consequenceHint ? approach.consequenceHint : ''}{approach.riskLevel && approach.riskLevel !== 'SAFE' ? '. Risk: ' + approach.riskLevel : ''}"
          title="Click to populate input"
        >
          <div class="card-tone-row">
            <span class="tone-icon" aria-hidden="true">{TONE_ICONS[approach.toneTag] ?? '◯'}</span>
            <span class="tone-label">{approach.toneTag}</span>
            {#if approach.riskLevel && approach.riskLevel !== 'SAFE'}
              <span class="risk-pill {riskClass(approach.riskLevel)}">{approach.riskLevel}</span>
            {/if}
          </div>
          <div class="card-text">{approach.displayText}</div>
          {#if approach.consequenceHint}
            <div class="card-hint">{approach.consequenceHint}</div>
          {/if}
        </button>
      {/each}
    </div>
  {/key}
</div>

<style>
  .approach-section {
    width: 100%;
  }

  .obligations-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 6px;
  }

  .obligation-badge {
    font-size: 0.58rem;
    font-weight: 600;
    color: var(--tone-investigate, #ffd246);
    background: rgba(255, 210, 70, 0.08);
    border: 1px solid rgba(255, 210, 70, 0.2);
    border-radius: 2px;
    padding: 2px 6px;
    letter-spacing: 0.3px;
    line-height: 1.3;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .approach-label {
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-muted);
    margin-bottom: 7px;
    font-family: 'JetBrains Mono', monospace;
    opacity: 0.7;
  }

  /* ======================== SCROLL CONTAINER ======================== */
  .approach-scroll {
    display: flex;
    flex-direction: row;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 6px;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
    scrollbar-color: var(--border-subtle) transparent;
  }
  .approach-scroll::-webkit-scrollbar {
    height: 3px;
  }
  .approach-scroll::-webkit-scrollbar-thumb {
    background: var(--border-subtle);
    border-radius: 2px;
  }

  /* ======================== APPROACH CARD ======================== */
  .approach-card {
    cursor: pointer;
    text-align: left;
    position: relative;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 10px 12px;
    transition: all 0.18s cubic-bezier(0.22, 1, 0.36, 1);
    flex-shrink: 0;
    width: 170px;
    min-height: 76px;
    display: flex;
    flex-direction: column;
    gap: 5px;

    background: var(--tone-bg);
    border-color: var(--tone-border);
  }

  /* Tone backgrounds (same as DialogueWheel) */
  .tone-paragon {
    --tone-color: var(--tone-paragon);
    --tone-bg: rgba(100, 170, 255, 0.07);
    --tone-border: rgba(100, 170, 255, 0.18);
    --tone-hover-bg: rgba(100, 170, 255, 0.15);
    --tone-hover-border: rgba(100, 170, 255, 0.38);
    --tone-glow: 0 0 14px rgba(100, 170, 255, 0.12);
  }
  .tone-investigate {
    --tone-color: var(--tone-investigate);
    --tone-bg: rgba(255, 210, 70, 0.05);
    --tone-border: rgba(255, 210, 70, 0.16);
    --tone-hover-bg: rgba(255, 210, 70, 0.12);
    --tone-hover-border: rgba(255, 210, 70, 0.35);
    --tone-glow: 0 0 14px rgba(255, 210, 70, 0.10);
  }
  .tone-renegade {
    --tone-color: var(--tone-renegade);
    --tone-bg: rgba(255, 85, 65, 0.05);
    --tone-border: rgba(255, 85, 65, 0.16);
    --tone-hover-bg: rgba(255, 85, 65, 0.12);
    --tone-hover-border: rgba(255, 85, 65, 0.35);
    --tone-glow: 0 0 14px rgba(255, 85, 65, 0.10);
  }
  .tone-neutral {
    --tone-color: var(--tone-neutral);
    --tone-bg: rgba(170, 170, 185, 0.05);
    --tone-border: rgba(170, 170, 185, 0.13);
    --tone-hover-bg: rgba(170, 170, 185, 0.10);
    --tone-hover-border: rgba(170, 170, 185, 0.30);
    --tone-glow: 0 0 10px rgba(170, 170, 185, 0.07);
  }

  .approach-card:hover {
    background: var(--tone-hover-bg);
    border-color: var(--tone-hover-border);
    box-shadow: var(--tone-glow);
    transform: translateY(-1px);
  }
  .approach-card:active {
    transform: translateY(0) scale(0.98);
  }

  /* ======================== CARD CONTENT ======================== */
  .card-tone-row {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .tone-icon {
    font-size: 0.85rem;
    color: var(--tone-color);
    flex-shrink: 0;
  }

  .tone-label {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--tone-color);
    opacity: 0.85;
    flex: 1;
  }

  .risk-pill {
    font-size: 0.55rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 1px 5px;
    border-radius: 2px;
    border: 1px solid;
    flex-shrink: 0;
  }
  .risk-risky {
    color: var(--tone-investigate);
    border-color: var(--tone-investigate);
  }
  .risk-dangerous {
    color: var(--tone-renegade);
    border-color: var(--tone-renegade);
  }

  .card-text {
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--text-primary);
    line-height: 1.3;
    flex: 1;
  }

  .card-hint {
    font-size: 0.65rem;
    font-style: italic;
    color: var(--text-muted);
    line-height: 1.2;
  }

  /* ======================== ANIMATION ======================== */
  .stagger-enter {
    animation: cardSlideIn 0.3s ease both;
  }

  @keyframes cardSlideIn {
    from {
      opacity: 0;
      transform: translateX(10px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  /* ======================== RESPONSIVE ======================== */
  @media (max-width: 480px) {
    .approach-card {
      width: 148px;
      min-height: 68px;
      padding: 8px 10px;
    }
    .card-text {
      font-size: 0.72rem;
    }
  }
</style>
