<!--
  ConsequenceOverlay.svelte — V4.1
  Full-screen dramatic moment for TRIUMPH, DESPAIR, HP_CRITICAL, and TURNING_POINT.
  Auto-dismisses after a brief display (or on click/key press).
-->
<script lang="ts">
  import { onMount } from 'svelte';

  interface Props {
    consequenceType: string;
    narrativeSummary?: string;
    onDismiss: () => void;
  }

  let { consequenceType, narrativeSummary = '', onDismiss }: Props = $props();

  // Auto-dismiss timing (ms)
  const AUTO_DISMISS_MS = 2800;

  let visible = $state(true);
  let timer: ReturnType<typeof setTimeout> | null = null;

  onMount(() => {
    timer = setTimeout(() => {
      visible = false;
      setTimeout(onDismiss, 400); // wait for fade-out animation
    }, AUTO_DISMISS_MS);

    return () => {
      if (timer) clearTimeout(timer);
    };
  });

  function dismiss() {
    if (timer) clearTimeout(timer);
    visible = false;
    setTimeout(onDismiss, 400);
  }

  const CONFIG: Record<string, { title: string; subtitle: string; icon: string; cls: string }> = {
    TRIUMPH: {
      title: 'TRIUMPH',
      subtitle: 'You passed the test that mattered.',
      icon: '⬦',
      cls: 'triumph',
    },
    DESPAIR: {
      title: 'DESPAIR',
      subtitle: 'The world noticed what you lost.',
      icon: '✕',
      cls: 'despair',
    },
    HP_CRITICAL: {
      title: 'CRITICAL',
      subtitle: 'You are barely standing.',
      icon: '⚠',
      cls: 'critical',
    },
    TURNING_POINT: {
      title: 'TURNING POINT',
      subtitle: 'The story shifts.',
      icon: '◆',
      cls: 'turning',
    },
  };

  let cfg = $derived(CONFIG[consequenceType] ?? CONFIG['TURNING_POINT']);
</script>

{#if visible}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="consequence-overlay overlay-{cfg.cls} fade-in"
    onclick={dismiss}
    role="status"
    aria-live="assertive"
    aria-label="{cfg.title}: {cfg.subtitle}"
  >
    <div class="consequence-content slide-up">
      <div class="consequence-icon" aria-hidden="true">{cfg.icon}</div>
      <div class="consequence-title">{cfg.title}</div>
      {#if cfg.subtitle}
        <div class="consequence-subtitle">{cfg.subtitle}</div>
      {/if}
      {#if narrativeSummary}
        <div class="consequence-summary">{narrativeSummary}</div>
      {/if}
      <div class="dismiss-hint" aria-hidden="true">tap to continue</div>
    </div>
  </div>
{/if}

<style>
  .consequence-overlay {
    position: fixed;
    inset: 0;
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  /* ======================== VARIANT BACKGROUNDS ======================== */
  .overlay-triumph {
    background: radial-gradient(ellipse at center, rgba(180, 140, 40, 0.35) 0%, rgba(5, 10, 20, 0.92) 70%);
    border: none;
  }
  .overlay-triumph::before {
    content: '';
    position: absolute;
    inset: 0;
    border: 2px solid rgba(201, 168, 76, 0.5);
    pointer-events: none;
    animation: borderPulse 1.5s ease-out forwards;
  }

  .overlay-despair {
    background: radial-gradient(ellipse at center, rgba(180, 30, 30, 0.25) 0%, rgba(3, 5, 8, 0.95) 70%);
  }
  .overlay-despair::before {
    content: '';
    position: absolute;
    inset: 0;
    border: 2px solid rgba(200, 50, 50, 0.4);
    pointer-events: none;
    animation: borderPulse 1.5s ease-out forwards;
  }

  .overlay-critical {
    background: radial-gradient(ellipse at center, rgba(200, 80, 20, 0.25) 0%, rgba(4, 7, 12, 0.94) 70%);
  }
  .overlay-critical::before {
    content: '';
    position: absolute;
    inset: 0;
    border: 2px solid rgba(220, 100, 30, 0.4);
    pointer-events: none;
    animation: borderPulse 1.2s ease-out forwards;
  }

  .overlay-turning {
    background: radial-gradient(ellipse at center, rgba(80, 100, 180, 0.22) 0%, rgba(4, 8, 20, 0.93) 70%);
  }
  .overlay-turning::before {
    content: '';
    position: absolute;
    inset: 0;
    border: 2px solid rgba(100, 140, 220, 0.35);
    pointer-events: none;
    animation: borderPulse 1.5s ease-out forwards;
  }

  /* ======================== CONTENT ======================== */
  .consequence-content {
    text-align: center;
    padding: 48px 32px;
    max-width: 480px;
  }

  .consequence-icon {
    font-size: 2.4rem;
    margin-bottom: 16px;
    opacity: 0.9;
  }

  .consequence-title {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: 4px;
    text-transform: uppercase;
    margin-bottom: 12px;
    line-height: 1.1;
  }

  .consequence-subtitle {
    font-size: 1rem;
    font-style: italic;
    opacity: 0.75;
    margin-bottom: 16px;
    line-height: 1.4;
  }

  .consequence-summary {
    font-size: 0.82rem;
    opacity: 0.55;
    font-style: italic;
    max-width: 340px;
    margin: 0 auto 20px;
    line-height: 1.5;
  }

  .dismiss-hint {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    opacity: 0.3;
    margin-top: 24px;
    font-family: 'JetBrains Mono', monospace;
  }

  /* Variant text colors */
  .overlay-triumph .consequence-title { color: #e8c96a; }
  .overlay-triumph .consequence-icon { color: #c9a84c; }
  .overlay-despair .consequence-title { color: #e05555; }
  .overlay-despair .consequence-icon { color: #c04040; }
  .overlay-critical .consequence-title { color: #e07040; }
  .overlay-critical .consequence-icon { color: #c06030; }
  .overlay-turning .consequence-title { color: #7aabee; }
  .overlay-turning .consequence-icon { color: #6090d0; }

  /* ======================== ANIMATIONS ======================== */
  .fade-in {
    animation: overlayFadeIn 0.35s ease forwards;
  }

  @keyframes overlayFadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .slide-up {
    animation: slideUp 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }

  @keyframes slideUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes borderPulse {
    0% { opacity: 0; transform: scale(1.04); }
    40% { opacity: 1; }
    100% { opacity: 0.7; transform: scale(1); }
  }
</style>
