<!--
  DialogueWheel.svelte — Enhanced KOTOR-style dialogue choices.

  Vertical stack with tone color as the DOMINANT visual (filled backgrounds).
  Primary source: PlayerResponse[] from DialogueTurn.
  Fallback: ActionSuggestion[] (legacy flat format).
  Sorted by tone: PARAGON → INVESTIGATE → RENEGADE → NEUTRAL.
-->
<script lang="ts">
  import type { PlayerResponse, ActionSuggestion } from '$lib/api/types';
  import { TONE_ICONS } from '$lib/utils/constants';

  interface Props {
    playerResponses: PlayerResponse[];
    suggestedActions: ActionSuggestion[];
    choiceAnimKey: number;
    onChoice: (userInput: string, label: string) => void;
  }

  let { playerResponses, suggestedActions, choiceAnimKey, onChoice }: Props = $props();

  // Tone sort order: fixed KOTOR positions
  const TONE_ORDER: Record<string, number> = {
    PARAGON: 0,
    INVESTIGATE: 1,
    RENEGADE: 2,
    NEUTRAL: 3,
  };

  // Unified choice interface for rendering
  interface UnifiedChoice {
    id: string;
    displayText: string;
    toneTag: string;
    riskLevel: string;
    consequenceHint: string;
    userInput: string;       // what to send to the backend
    meaningTag: string;
    companionReactions?: Record<string, number>;
  }

  // Convert PlayerResponse[] or ActionSuggestion[] into unified choices
  let choices = $derived.by(() => {
    let items: UnifiedChoice[];

    if (playerResponses.length > 0) {
      // Primary source: DialogueTurn player responses (KOTOR-style)
      items = playerResponses.map((r, i) => ({
        id: r.id || `resp_${i + 1}`,
        displayText: r.display_text,
        toneTag: r.tone_tag?.toUpperCase() || 'NEUTRAL',
        riskLevel: r.risk_level || 'SAFE',
        consequenceHint: r.consequence_hint || '',
        userInput: r.display_text,
        meaningTag: r.meaning_tag || '',
      }));
    } else {
      // Fallback: legacy ActionSuggestion format
      items = suggestedActions.map((a, i) => ({
        id: `action_${i + 1}`,
        displayText: a.label,
        toneTag: a.tone_tag?.toUpperCase() || 'NEUTRAL',
        riskLevel: a.risk_level || 'SAFE',
        consequenceHint: a.consequence_hint || '',
        userInput: a.intent_text || a.label,
        meaningTag: '',
        companionReactions: a.companion_reactions,
      }));
    }

    // Sort by tone order (PARAGON first, NEUTRAL last)
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

<div class="choice-panel" role="group" aria-label="Available choices">
  <div class="choice-prompt">What do you do?</div>
  {#key choiceAnimKey}
    <div class="choice-grid">
      {#each choices as choice, i}
        <button
          class="choice-card tone-{choice.toneTag.toLowerCase()} stagger-enter"
          style="animation-delay: {i * 80}ms"
          onclick={() => onChoice(choice.userInput, choice.displayText)}
          aria-label="Choice {i + 1}: {choice.displayText}. {choice.consequenceHint ? choice.consequenceHint : ''}{choice.riskLevel && choice.riskLevel !== 'SAFE' ? '. Risk: ' + choice.riskLevel : ''}"
        >
          <div class="choice-inner">
            <span class="choice-tone-badge" aria-hidden="true">
              {TONE_ICONS[choice.toneTag] ?? '◯'}
            </span>
            <div class="choice-content">
              <span class="choice-text">{choice.displayText}</span>
              <kbd class="choice-shortcut" aria-label="Press {i + 1}">{i + 1}</kbd>
            </div>
          </div>

          <!-- Hover-only details -->
          <div class="choice-details">
            {#if choice.riskLevel && choice.riskLevel !== 'SAFE'}
              <span class="risk-badge {riskClass(choice.riskLevel)}">
                {choice.riskLevel}
              </span>
            {/if}
            {#if choice.consequenceHint}
              <span class="consequence-hint">{choice.consequenceHint}</span>
            {/if}
            {#if choice.companionReactions}
              {#each Object.entries(choice.companionReactions) as [name, delta]}
                {#if delta !== 0}
                  <span
                    class="companion-delta"
                    class:positive={Number(delta) > 0}
                    class:negative={Number(delta) < 0}
                  >
                    {name} {Number(delta) > 0 ? '+' : ''}{delta}
                  </span>
                {/if}
              {/each}
            {/if}
          </div>
        </button>
      {/each}
    </div>
  {/key}
</div>

<style>
  .choice-panel {
    padding-top: 8px;
  }

  .choice-prompt {
    font-size: var(--font-body);
    color: var(--text-secondary);
    margin-bottom: 12px;
    font-style: italic;
  }

  .choice-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  /* ======================== CHOICE CARD ======================== */
  .choice-card {
    cursor: pointer;
    text-align: left;
    position: relative;
    overflow: hidden;
    border: 1px solid transparent;
    border-radius: var(--panel-radius);
    padding: 12px 16px;
    transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);

    /* Tone-filled background — THE key KOTOR visual change */
    background: var(--tone-bg);
    border-color: var(--tone-border);
  }

  /* Tone background fills */
  .tone-paragon {
    --tone-color: var(--tone-paragon);
    --tone-bg: rgba(100, 170, 255, 0.08);
    --tone-border: rgba(100, 170, 255, 0.20);
    --tone-hover-bg: rgba(100, 170, 255, 0.18);
    --tone-hover-border: rgba(100, 170, 255, 0.45);
    --tone-glow: 0 0 16px rgba(100, 170, 255, 0.15);
  }
  .tone-investigate {
    --tone-color: var(--tone-investigate);
    --tone-bg: rgba(255, 210, 70, 0.06);
    --tone-border: rgba(255, 210, 70, 0.18);
    --tone-hover-bg: rgba(255, 210, 70, 0.14);
    --tone-hover-border: rgba(255, 210, 70, 0.40);
    --tone-glow: 0 0 16px rgba(255, 210, 70, 0.12);
  }
  .tone-renegade {
    --tone-color: var(--tone-renegade);
    --tone-bg: rgba(255, 85, 65, 0.06);
    --tone-border: rgba(255, 85, 65, 0.18);
    --tone-hover-bg: rgba(255, 85, 65, 0.14);
    --tone-hover-border: rgba(255, 85, 65, 0.40);
    --tone-glow: 0 0 16px rgba(255, 85, 65, 0.12);
  }
  .tone-neutral {
    --tone-color: var(--tone-neutral);
    --tone-bg: rgba(180, 180, 190, 0.05);
    --tone-border: rgba(180, 180, 190, 0.15);
    --tone-hover-bg: rgba(180, 180, 190, 0.12);
    --tone-hover-border: rgba(180, 180, 190, 0.35);
    --tone-glow: 0 0 12px rgba(180, 180, 190, 0.08);
  }

  .choice-card:hover {
    background: var(--tone-hover-bg);
    border-color: var(--tone-hover-border);
    box-shadow: var(--tone-glow);
    transform: scale(1.01);
  }

  .choice-card:active {
    transform: scale(0.99);
  }

  /* ======================== CHOICE INNER LAYOUT ======================== */
  .choice-inner {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .choice-tone-badge {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    font-size: 1.2rem;
    color: var(--tone-color);
    border: 1px solid var(--tone-color);
    border-radius: 50%;
    flex-shrink: 0;
    opacity: 0.9;
  }

  .choice-content {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .choice-text {
    font-size: var(--font-body);
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
    flex: 1;
  }

  .choice-shortcut {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    opacity: 0.4;
    border: none;
    background: none;
    padding: 0;
    flex-shrink: 0;
  }

  /* ======================== HOVER-ONLY DETAILS ======================== */
  .choice-details {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    font-size: var(--font-small);
    margin-top: 0;
    max-height: 0;
    overflow: hidden;
    opacity: 0;
    transition: all 0.2s ease;
    padding-left: 44px; /* align with text after badge */
  }

  .choice-card:hover .choice-details,
  .choice-card:focus .choice-details {
    max-height: 40px;
    opacity: 1;
    margin-top: 6px;
  }

  .consequence-hint {
    font-style: italic;
    color: var(--text-muted);
  }

  .risk-badge {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .risk-risky {
    color: var(--tone-investigate);
    border: 1px solid var(--tone-investigate);
  }
  .risk-dangerous {
    color: var(--tone-renegade);
    border: 1px solid var(--tone-renegade);
  }

  .companion-delta {
    color: var(--text-secondary);
    font-size: var(--font-small);
  }
  .positive { color: var(--tone-paragon); }
  .negative { color: var(--tone-renegade); }

  /* ======================== ANIMATION ======================== */
  .stagger-enter {
    animation: slideUp 0.3s ease both;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ======================== RESPONSIVE ======================== */
  @media (max-width: 768px) {
    .choice-shortcut {
      display: none;
    }
    .choice-card {
      padding: 10px 12px;
    }
    .choice-tone-badge {
      width: 28px;
      height: 28px;
      font-size: 1rem;
    }
    .choice-details {
      padding-left: 40px;
    }
  }

  @media (max-width: 480px) {
    .choice-card {
      padding: 8px 10px;
    }
  }
</style>
