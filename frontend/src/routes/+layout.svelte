<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { ui } from '$lib/stores/ui';
  import { THEMES, themeToCssVars } from '$lib/themes/tokens';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();

  // Reactive theme CSS variables
  let themeStyle = $derived.by(() => {
    const themeName = $ui.theme;
    const theme = THEMES[themeName] ?? THEMES['Clean Dark'];
    return themeToCssVars(theme);
  });

  // Track route for page transitions — key changes re-trigger entrance animation
  let routeKey = $derived($page.url.pathname);
</script>

<svelte:head>
  <title>Storyteller AI</title>
</svelte:head>

<!-- Inject theme CSS variables on body via a global style tag -->
{@html `<style>body { ${themeStyle} }</style>`}

<div class="app-shell">
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
</style>
