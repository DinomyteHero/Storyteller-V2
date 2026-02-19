<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { onDestroy, onMount } from 'svelte';
  import { getHealthDetail } from '$lib/api/client';
  import { ui, ollamaStatus } from '$lib/stores/ui';
  import { THEMES, themeToCssVars } from '$lib/themes/tokens';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();

  // Reactive theme CSS variables
  let themeStyle = $derived.by(() => {
    const themeName = $ui.theme;
    const theme = THEMES[themeName] ?? THEMES['Clean Dark'];
    return themeToCssVars(theme);
  });

  // Phase 5.1: Font scale CSS variable
  let fontScaleStyle = $derived(`font-size: ${($ui.fontScale ?? 1.0) * 100}%;`);

  // Track route for page transitions - key changes re-trigger entrance animation
  let routeKey = $derived($page.url.pathname);
  let healthPoll: ReturnType<typeof setInterval> | null = null;

  async function checkOllamaHealth(): Promise<void> {
    try {
      const detail = await getHealthDetail();
      const ollama = detail.checks?.ollama;
      if (ollama?.ok) {
        ollamaStatus.set({ status: 'up', message: '', checkedAt: Date.now() });
      } else {
        ollamaStatus.set({
          status: 'down',
          message: (ollama?.message as string) || 'Story engine unavailable - Ollama is not running. Start it with: ollama serve',
          checkedAt: Date.now(),
        });
      }
    } catch {
      ollamaStatus.set({
        status: 'down',
        message: 'Story engine unavailable - Ollama is not running. Start it with: ollama serve',
        checkedAt: Date.now(),
      });
    }
  }

  function stopPolling() {
    if (healthPoll) {
      clearInterval(healthPoll);
      healthPoll = null;
    }
  }

  function ensurePolling() {
    if (!healthPoll) {
      healthPoll = setInterval(() => {
        void checkOllamaHealth();
      }, 10_000);
    }
  }

  onMount(() => {
    void checkOllamaHealth();
    const unsub = ollamaStatus.subscribe((value) => {
      if (value.status === 'down') {
        ensurePolling();
      } else {
        stopPolling();
      }
    });
    return () => {
      unsub();
      stopPolling();
    };
  });

  onDestroy(() => {
    stopPolling();
  });
</script>

<svelte:head>
  <title>Storyteller AI</title>
</svelte:head>

<!-- Inject theme CSS variables and font scale on body via a global style tag -->
{@html `<style>body { ${themeStyle} } html { ${fontScaleStyle} }</style>`}

<div class="app-shell">
  {#if $ollamaStatus.status === 'down'}
    <div class="ollama-banner" role="alert" aria-live="assertive">
      <strong>Story engine unavailable</strong> - Ollama is not running. Start it with: <code>ollama serve</code>
    </div>
  {/if}

  <!-- Live region for screen reader announcements -->
  <div id="sr-announcements" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>

  {#key routeKey}
    <div class="page-enter">
      {@render children()}
    </div>
  {/key}
</div>

<style>
  .app-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .ollama-banner {
    position: sticky;
    top: 0;
    z-index: 2000;
    background: #fef3c7;
    color: #7c2d12;
    border-bottom: 1px solid #f59e0b;
    padding: 10px 16px;
    font-size: 0.95rem;
    text-align: center;
  }

  .ollama-banner code {
    background: rgba(0, 0, 0, 0.08);
    padding: 1px 6px;
    border-radius: 4px;
  }
</style>
