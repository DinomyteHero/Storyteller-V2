<!--
  SceneContext.svelte — KOTOR-soul scene awareness bar.
  Shows topic_primary, pressure indicators, and scene type.
  Only renders when SceneFrame data is available.
-->
<script lang="ts">
  import type { SceneFrame } from '$lib/api/types';

  interface Props {
    sceneFrame: SceneFrame | null;
  }

  let { sceneFrame }: Props = $props();

  const SCENE_TYPE_ICONS: Record<string, string> = {
    dialogue: '💬',
    combat: '⚔',
    exploration: '🔍',
    travel: '🚀',
    stealth: '👁',
  };

  const ALERT_COLORS: Record<string, string> = {
    Quiet: 'alert-quiet',
    Watchful: 'alert-watchful',
    Lockdown: 'alert-lockdown',
  };

  const HEAT_COLORS: Record<string, string> = {
    Low: 'heat-low',
    Noticed: 'heat-noticed',
    Wanted: 'heat-wanted',
  };
</script>

{#if sceneFrame && (sceneFrame.topic_primary || sceneFrame.pressure?.alert || sceneFrame.pressure?.heat)}
  <div class="scene-context-bar" role="status" aria-label="Scene context">
    {#if sceneFrame.topic_primary}
      <span class="topic-tag" aria-label="Scene topic: {sceneFrame.topic_primary}">
        {sceneFrame.topic_primary.toUpperCase()}
      </span>
    {/if}

    <span class="scene-type" aria-label="Scene type: {sceneFrame.allowed_scene_type}">
      <span class="scene-type-icon" aria-hidden="true">{SCENE_TYPE_ICONS[sceneFrame.allowed_scene_type] ?? '💬'}</span>
      {sceneFrame.allowed_scene_type}
    </span>

    {#if sceneFrame.pressure?.alert && sceneFrame.pressure.alert !== 'Quiet'}
      <span class="pressure-pill {ALERT_COLORS[sceneFrame.pressure.alert] ?? ''}" aria-label="Alert level: {sceneFrame.pressure.alert}">
        {sceneFrame.pressure.alert.toUpperCase()}
      </span>
    {/if}

    {#if sceneFrame.pressure?.heat && sceneFrame.pressure.heat !== 'Low'}
      <span class="pressure-pill {HEAT_COLORS[sceneFrame.pressure.heat] ?? ''}" aria-label="Heat level: {sceneFrame.pressure.heat}">
        🔥 {sceneFrame.pressure.heat.toUpperCase()}
      </span>
    {/if}
  </div>
{/if}

<style>
  .scene-context-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 6px 0;
    font-size: var(--font-small);
  }

  .topic-tag {
    color: var(--accent-primary);
    font-weight: 700;
    letter-spacing: 1.5px;
    font-size: 0.7rem;
    padding: 2px 8px;
    border: 1px solid var(--accent-glow);
    border-radius: 3px;
    background: var(--accent-glow);
  }

  .scene-type {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-muted);
    font-size: 0.7rem;
    text-transform: capitalize;
  }

  .scene-type-icon {
    font-size: 0.8rem;
  }

  .pressure-pill {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid;
  }

  .alert-quiet {
    color: var(--tone-paragon);
    border-color: var(--tone-paragon);
  }
  .alert-watchful {
    color: var(--tone-investigate);
    border-color: var(--tone-investigate);
    background: rgba(255, 210, 70, 0.08);
  }
  .alert-lockdown {
    color: var(--tone-renegade);
    border-color: var(--tone-renegade);
    background: rgba(255, 85, 65, 0.08);
    animation: pulse-alert 2s ease-in-out infinite;
  }

  .heat-low {
    color: var(--text-muted);
    border-color: var(--border-subtle);
  }
  .heat-noticed {
    color: var(--tone-investigate);
    border-color: var(--tone-investigate);
    background: rgba(255, 210, 70, 0.08);
  }
  .heat-wanted {
    color: var(--tone-renegade);
    border-color: var(--tone-renegade);
    background: rgba(255, 85, 65, 0.08);
  }

  @keyframes pulse-alert {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }
</style>
