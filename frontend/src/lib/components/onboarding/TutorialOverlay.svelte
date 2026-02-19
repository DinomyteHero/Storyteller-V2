<!--
  TutorialOverlay.svelte — Guided walkthrough for first-time players.

  Shows a spotlight on the target element with a tooltip explaining its purpose.
  Steps through 5 key UI regions: narrative, approaches, free text, HUD, drawer.
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import {
    onboarding,
    showTutorial,
    TUTORIAL_STEPS,
    type TutorialStep,
  } from '$lib/stores/onboarding';

  let spotlightRect = $state<DOMRect | null>(null);
  let tooltipEl = $state<HTMLElement | null>(null);

  let currentStep = $derived(
    $onboarding.currentStep < TUTORIAL_STEPS.length
      ? TUTORIAL_STEPS[$onboarding.currentStep]
      : null
  );

  let stepIndex = $derived($onboarding.currentStep);
  let totalSteps = TUTORIAL_STEPS.length;

  async function updateSpotlight() {
    if (!currentStep) return;
    await tick();
    const el = document.querySelector(currentStep.targetSelector);
    if (el) {
      spotlightRect = el.getBoundingClientRect();
    } else {
      spotlightRect = null;
    }
  }

  function handleNext() {
    onboarding.nextStep();
    requestAnimationFrame(() => void updateSpotlight());
  }

  function handlePrev() {
    onboarding.prevStep();
    requestAnimationFrame(() => void updateSpotlight());
  }

  function handleSkip() {
    onboarding.dismiss();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!$showTutorial) return;
    if (e.key === 'Escape') {
      handleSkip();
    } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
      handleNext();
    } else if (e.key === 'ArrowLeft') {
      handlePrev();
    }
  }

  onMount(() => {
    void updateSpotlight();
    window.addEventListener('resize', () => void updateSpotlight());
    return () => {
      window.removeEventListener('resize', () => void updateSpotlight());
    };
  });

  // Tooltip positioning
  let tooltipStyle = $derived.by(() => {
    if (!spotlightRect || !currentStep) return 'display: none;';
    const pad = 16;
    const pos = currentStep.position;

    if (pos === 'bottom') {
      return `top: ${spotlightRect.bottom + pad}px; left: ${spotlightRect.left + spotlightRect.width / 2}px; transform: translateX(-50%);`;
    }
    if (pos === 'top') {
      return `bottom: ${window.innerHeight - spotlightRect.top + pad}px; left: ${spotlightRect.left + spotlightRect.width / 2}px; transform: translateX(-50%);`;
    }
    if (pos === 'right') {
      return `top: ${spotlightRect.top + spotlightRect.height / 2}px; left: ${spotlightRect.right + pad}px; transform: translateY(-50%);`;
    }
    // left
    return `top: ${spotlightRect.top + spotlightRect.height / 2}px; right: ${window.innerWidth - spotlightRect.left + pad}px; transform: translateY(-50%);`;
  });

  // Spotlight cutout style
  let cutoutStyle = $derived.by(() => {
    if (!spotlightRect) return '';
    const m = 6; // margin around element
    return `top: ${spotlightRect.top - m}px; left: ${spotlightRect.left - m}px; width: ${spotlightRect.width + m * 2}px; height: ${spotlightRect.height + m * 2}px;`;
  });
</script>

<svelte:window onkeydown={handleKeydown} />

{#if $showTutorial && currentStep}
  <div class="tutorial-overlay" role="dialog" aria-modal="true" aria-label="Tutorial walkthrough">
    <!-- Dark backdrop with spotlight cutout -->
    <div class="tutorial-backdrop" onclick={handleSkip}></div>

    <!-- Spotlight ring -->
    {#if spotlightRect}
      <div class="spotlight-ring" style={cutoutStyle}></div>
    {/if}

    <!-- Tooltip -->
    <div class="tutorial-tooltip" style={tooltipStyle} bind:this={tooltipEl}>
      <div class="tooltip-header">
        <span class="tooltip-step">{stepIndex + 1} / {totalSteps}</span>
        <button class="tooltip-skip" onclick={handleSkip}>Skip</button>
      </div>
      <h3 class="tooltip-title">{currentStep.title}</h3>
      <p class="tooltip-desc">{currentStep.description}</p>
      <div class="tooltip-nav">
        {#if stepIndex > 0}
          <button class="tooltip-btn tooltip-btn-back" onclick={handlePrev}>Back</button>
        {/if}
        <button class="tooltip-btn tooltip-btn-next" onclick={handleNext}>
          {stepIndex === totalSteps - 1 ? 'Got it!' : 'Next'}
        </button>
      </div>
      <!-- Progress dots -->
      <div class="tooltip-dots" aria-hidden="true">
        {#each TUTORIAL_STEPS as _, i}
          <span class="dot" class:active={i === stepIndex} class:done={i < stepIndex}></span>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  .tutorial-overlay {
    position: fixed;
    inset: 0;
    z-index: 9999;
    pointer-events: none;
  }

  .tutorial-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    pointer-events: auto;
    cursor: pointer;
  }

  .spotlight-ring {
    position: fixed;
    border: 2px solid var(--accent-primary, #4fc3f7);
    border-radius: 8px;
    box-shadow:
      0 0 0 9999px rgba(0, 0, 0, 0.65),
      0 0 20px rgba(79, 195, 247, 0.3);
    pointer-events: none;
    z-index: 10000;
    transition: all 0.35s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .tutorial-tooltip {
    position: fixed;
    z-index: 10001;
    background: var(--bg-panel, #1a1a2e);
    border: 1px solid var(--accent-primary, #4fc3f7);
    border-radius: 12px;
    padding: 18px 20px 14px;
    max-width: 360px;
    min-width: 260px;
    pointer-events: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  .tooltip-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .tooltip-step {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--accent-primary, #4fc3f7);
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  .tooltip-skip {
    font-size: 0.72rem;
    color: var(--text-muted, #888);
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;
    transition: color 0.15s;
  }
  .tooltip-skip:hover {
    color: var(--text-primary, #fff);
  }

  .tooltip-title {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-heading, #e0e0e0);
    margin: 0 0 6px;
    line-height: 1.3;
  }

  .tooltip-desc {
    font-size: 0.85rem;
    color: var(--text-secondary, #b0b0b0);
    margin: 0 0 14px;
    line-height: 1.5;
  }

  .tooltip-nav {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .tooltip-btn {
    font-size: 0.8rem;
    font-weight: 600;
    padding: 6px 16px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    border: 1px solid transparent;
  }

  .tooltip-btn-back {
    background: transparent;
    color: var(--text-secondary, #b0b0b0);
    border-color: var(--border-subtle, #333);
  }
  .tooltip-btn-back:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary, #fff);
  }

  .tooltip-btn-next {
    background: var(--accent-primary, #4fc3f7);
    color: #000;
    border-color: var(--accent-primary, #4fc3f7);
  }
  .tooltip-btn-next:hover {
    filter: brightness(1.1);
  }

  .tooltip-dots {
    display: flex;
    gap: 6px;
    justify-content: center;
    margin-top: 12px;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--border-subtle, #333);
    transition: all 0.2s;
  }
  .dot.active {
    background: var(--accent-primary, #4fc3f7);
    transform: scale(1.3);
  }
  .dot.done {
    background: var(--accent-secondary, #66bb6a);
  }

  @media (max-width: 480px) {
    .tutorial-tooltip {
      max-width: calc(100vw - 32px);
      min-width: 200px;
    }
  }
</style>
