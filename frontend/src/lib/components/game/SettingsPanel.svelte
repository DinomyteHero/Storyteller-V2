<!--
  SettingsPanel: Campaign settings for narrator mode and cloud quality.
  V9.0: Novel-Length Story feature — controls scene length, prose quality, and LLM routing.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { campaignId } from '$lib/stores/game';
  import { getCampaignSettings, patchCampaignSettings } from '$lib/api/campaigns';
  import type { CampaignSettings } from '$lib/api/campaigns';

  let narratorMode: CampaignSettings['narrator_mode'] = 'concise';
  let cloudPreset: CampaignSettings['cloud_preset'] = 'local';
  let loaded = false;
  let saving = false;
  let error: string | null = null;

  const NARRATOR_MODES = [
    {
      value: 'concise' as const,
      label: 'Concise',
      desc: 'Quick, punchy scenes (230\u2013430 words). Best for fast-paced gameplay.',
      words: '230\u2013430',
    },
    {
      value: 'novel' as const,
      label: 'Novel',
      desc: 'Rich, layered prose with internal monologue and sensory detail.',
      words: '500\u2013750',
    },
    {
      value: 'epic' as const,
      label: 'Epic',
      desc: 'Full cinematic treatment. Deep POV, literary devices, slow-motion beats.',
      words: '700\u2013900',
    },
  ] as const;

  import { presets, type Preset } from '$lib/stores/presets';
  import { goto } from '$app/navigation';

  let presetList = $state<Preset[]>([]);
  presets.subscribe((val) => { presetList = val; });

  // Load presets on mount
  $effect(() => {
    presets.load();
  });

  const CLOUD_PRESETS = [
    {
      value: 'local' as const,
      label: 'Local Only',
      desc: 'All Ollama. Free, private, offline.',
      cost: 'Free',
    },
    {
      value: 'budget' as const,
      label: 'Budget',
      desc: 'Narrator on cloud. Best prose quality boost for minimal cost.',
      cost: '~$0.01/turn',
    },
    {
      value: 'balanced' as const,
      label: 'Balanced',
      desc: 'Director + Narrator + Choices + Mechanic on cloud.',
      cost: '~$0.02/turn',
    },
    {
      value: 'quality' as const,
      label: 'Quality',
      desc: 'All narrative roles on cloud. Maximum prose quality.',
      cost: '~$0.05/turn',
    },
  ] as const;

  $: userPresets = presetList.filter((p) => !p.is_system);

  onMount(async () => {
    const cid = $campaignId;
    if (!cid) return;
    try {
      const settings = await getCampaignSettings(cid);
      narratorMode = settings.narrator_mode;
      cloudPreset = settings.cloud_preset;
    } catch {
      // Settings load failed — use defaults silently
    }
    loaded = true;
  });

  async function saveSettings(
    mode: CampaignSettings['narrator_mode'],
    preset: CampaignSettings['cloud_preset']
  ) {
    const cid = $campaignId;
    if (!cid) return;
    saving = true;
    error = null;
    try {
      await patchCampaignSettings(cid, {
        narrator_mode: mode,
        cloud_preset: preset,
      });
    } catch {
      error = 'Failed to save settings.';
    }
    saving = false;
  }

  function setNarratorMode(mode: CampaignSettings['narrator_mode']) {
    if (mode === narratorMode) return;
    narratorMode = mode;
    saveSettings(narratorMode, cloudPreset);
  }

  function setCloudPreset(preset: CampaignSettings['cloud_preset']) {
    if (preset === cloudPreset) return;
    cloudPreset = preset;
    saveSettings(narratorMode, cloudPreset);
  }

  $: showCloudHint = (narratorMode === 'novel' || narratorMode === 'epic') && cloudPreset === 'local';
</script>

{#if !loaded}
  <p class="empty-state">Loading settings...</p>
{:else}
  <div class="section-header">Prose Length</div>
  <p class="settings-description">Controls scene length, sensory detail, and internal monologue depth.</p>

  <div class="settings-group">
    {#each NARRATOR_MODES as mode}
      <button
        class="setting-card"
        class:active={narratorMode === mode.value}
        onclick={() => setNarratorMode(mode.value)}
        disabled={saving}
      >
        <div class="setting-card-header">
          <span class="setting-card-label">{mode.label}</span>
          <span class="setting-card-badge">{mode.words} words</span>
        </div>
        <span class="setting-card-desc">{mode.desc}</span>
      </button>
    {/each}
  </div>

  {#if showCloudHint}
    <p class="cloud-hint">
      For best results in {narratorMode === 'novel' ? 'Novel' : 'Epic'} mode, consider enabling cloud quality below.
    </p>
  {/if}

  <div class="section-header" style="margin-top: 16px;">Cloud Quality</div>
  <p class="settings-description">Route quality-critical roles to cloud LLMs for better prose. Requires API key.</p>

  <div class="settings-group">
    {#each CLOUD_PRESETS as preset}
      <button
        class="setting-card"
        class:active={cloudPreset === preset.value}
        onclick={() => setCloudPreset(preset.value)}
        disabled={saving}
      >
        <div class="setting-card-header">
          <span class="setting-card-label">{preset.label}</span>
          <span class="setting-card-badge">{preset.cost}</span>
        </div>
        <span class="setting-card-desc">{preset.desc}</span>
      </button>
    {/each}
    {#each userPresets as up}
      <button
        class="setting-card"
        class:active={cloudPreset === 'custom'}
        onclick={() => setCloudPreset('custom')}
        disabled={saving}
      >
        <div class="setting-card-header">
          <span class="setting-card-label">{up.name}</span>
          <span class="setting-card-badge">Custom</span>
        </div>
        <span class="setting-card-desc">{up.description || `${Object.keys(up.role_configs).length} roles configured`}</span>
      </button>
    {/each}
  </div>

  <button class="settings-link" onclick={() => goto('/settings')}>
    Manage providers & presets
  </button>

  {#if saving}
    <p class="save-status">Saving...</p>
  {/if}
  {#if error}
    <p class="save-error">{error}</p>
  {/if}
{/if}

<style>
  .settings-description {
    font-size: var(--font-small, 0.85rem);
    color: var(--text-muted);
    margin: 0 0 8px 0;
    line-height: 1.4;
  }

  .settings-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 8px;
  }

  .setting-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px 12px;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    background: transparent;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s ease;
    color: var(--text-primary);
    font-family: inherit;
  }

  .setting-card:hover:not(:disabled) {
    border-color: var(--text-muted);
    background: var(--hud-pill-bg, rgba(255,255,255,0.04));
  }

  .setting-card.active {
    border-color: var(--accent-glow, #4a9eff);
    background: var(--accent-glow, rgba(74, 158, 255, 0.1));
  }

  .setting-card:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .setting-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .setting-card-label {
    font-size: var(--font-body, 0.95rem);
    font-weight: 600;
    color: var(--text-heading, #fff);
  }

  .setting-card-badge {
    font-size: var(--font-small, 0.8rem);
    color: var(--text-muted);
    background: var(--hud-pill-bg, rgba(255,255,255,0.06));
    padding: 2px 8px;
    border-radius: 10px;
  }

  .setting-card-desc {
    font-size: var(--font-small, 0.8rem);
    color: var(--text-muted);
    line-height: 1.4;
  }

  .cloud-hint {
    font-size: var(--font-small, 0.8rem);
    color: var(--color-paragon, #4a9eff);
    margin: 4px 0 8px 0;
    padding: 6px 10px;
    border-left: 2px solid var(--color-paragon, #4a9eff);
    background: rgba(74, 158, 255, 0.06);
    border-radius: 0 4px 4px 0;
  }

  .save-status {
    font-size: var(--font-small, 0.8rem);
    color: var(--text-muted);
    margin-top: 8px;
  }

  .save-error {
    font-size: var(--font-small, 0.8rem);
    color: var(--color-renegade, #ff4a4a);
    margin-top: 8px;
  }

  .settings-link {
    display: block;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: var(--font-small, 0.8rem);
    cursor: pointer;
    padding: 4px 0;
    margin-top: 4px;
    font-family: inherit;
    text-decoration: underline;
    text-decoration-color: var(--border-subtle);
  }

  .settings-link:hover {
    color: var(--text-secondary);
  }
</style>
