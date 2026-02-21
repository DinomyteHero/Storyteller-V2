<!--
  Settings Page: V12.0 — Cloud provider management, presets, per-agent overrides.
  API keys are stored in the backend DB. Provider status fetched from backend.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiFetch } from '$lib/api/client';
  import { providers, type ProviderStatus } from '$lib/stores/providers';
  import { presets, type Preset } from '$lib/stores/presets';
  import { preferences } from '$lib/stores/preferences';
  import { ui } from '$lib/stores/ui';
  import { THEME_NAMES } from '$lib/themes/tokens';
  import PresetEditor from '$lib/components/settings/PresetEditor.svelte';
  import type { TestResult } from '$lib/api/campaigns';

  interface AgentModelConfig {
    role: string;
    provider: string;
    model: string;
    base_url: string;
  }

  // Agent role display names and categories
  const AGENT_CATEGORIES: Record<string, { label: string; roles: string[] }> = {
    narrative: {
      label: 'Narrative (Quality-Critical)',
      roles: ['narrator', 'director', 'choice_crafter', 'companion_system'],
    },
    world: {
      label: 'World Building',
      roles: ['architect', 'bible', 'world_mind', 'era_forge'],
    },
    character: {
      label: 'Character & Memory',
      roles: ['biographer', 'casting', 'memory', 'psych_archivist', 'progression'],
    },
    structure: {
      label: 'Structure & Analysis',
      roles: ['arc_weaver', 'arc_screenplay', 'intent_router', 'continuity', 'quest_weaver'],
    },
    special: {
      label: 'Special',
      roles: ['prologue', 'origin', 'mechanic', 'npc_render', 'suggestion_refiner', 'revelation_agent', 'callback_crystallizer'],
    },
    infrastructure: {
      label: 'Infrastructure',
      roles: ['embedding', 'ingestion_tagger', 'kg_extractor', 'campaign_init'],
    },
  };

  const ROLE_LABELS: Record<string, string> = {
    narrator: 'Narrator', director: 'Director', choice_crafter: 'Choice Crafter',
    companion_system: 'Companion System', architect: 'Architect', bible: 'Campaign Bible',
    world_mind: 'World Mind', era_forge: 'Era Forge', biographer: 'Biographer',
    casting: 'Casting', memory: 'Memory', psych_archivist: 'Psych Archivist',
    progression: 'Progression', arc_weaver: 'Arc Weaver', arc_screenplay: 'Arc Screenplay',
    intent_router: 'Intent Router', continuity: 'Continuity', quest_weaver: 'Quest Weaver',
    prologue: 'Prologue', origin: 'Origin Story', mechanic: 'Mechanic',
    npc_render: 'NPC Voice', suggestion_refiner: 'Suggestion Refiner',
    revelation_agent: 'Revelation Agent', callback_crystallizer: 'Callback Crystallizer',
    embedding: 'Embedding', ingestion_tagger: 'Ingestion Tagger',
    kg_extractor: 'Knowledge Graph', campaign_init: 'Campaign Init',
  };

  let providerList = $state<ProviderStatus[]>([]);
  let presetList = $state<Preset[]>([]);
  let editingKey = $state<string | null>(null);
  let keyInput = $state('');
  let savedMessage = $state('');
  let agentConfigs = $state<AgentModelConfig[]>([]);
  let showAdvanced = $state(false);
  let loadingAgents = $state(false);
  let testingProvider = $state<string | null>(null);
  let testResults = $state<Record<string, TestResult>>({});
  let showPresetEditor = $state(false);
  let editingPreset = $state<Preset | null>(null);

  // Sync stores to local state via $effect
  $effect(() => { providerList = $providers; });
  $effect(() => { presetList = $presets; });

  onMount(async () => {
    await Promise.all([providers.load(), presets.load(), preferences.load()]);
  });

  async function loadAgentConfigs() {
    loadingAgents = true;
    try {
      const resp = await apiFetch<{ agents: AgentModelConfig[]; available_providers: ProviderStatus[] }>('/v2/model_config');
      agentConfigs = resp.agents || [];
    } catch {
      // Non-critical
    }
    loadingAgents = false;
  }

  function startEditKey(providerId: string) {
    editingKey = providerId;
    keyInput = '';
  }

  async function saveKey(providerId: string) {
    if (!keyInput.trim()) return;
    await providers.setKey(providerId, keyInput.trim());
    editingKey = null;
    keyInput = '';
    flashSaved();
  }

  async function removeKey(providerId: string) {
    await providers.removeKey(providerId);
    editingKey = null;
    flashSaved();
  }

  function cancelEdit() {
    editingKey = null;
    keyInput = '';
  }

  async function runTest(providerId: string) {
    testingProvider = providerId;
    try {
      const result = await providers.test(providerId);
      testResults = { ...testResults, [providerId]: result };
    } catch {
      testResults = { ...testResults, [providerId]: { ok: false, latency_ms: 0, error: 'Request failed', model_used: null } };
    }
    testingProvider = null;
  }

  function flashSaved() {
    savedMessage = 'Saved';
    setTimeout(() => { savedMessage = ''; }, 2000);
  }

  function goBack() {
    goto('/');
  }

  function openCreatePreset() {
    editingPreset = null;
    showPresetEditor = true;
  }

  function openEditPreset(preset: Preset) {
    editingPreset = preset;
    showPresetEditor = true;
  }

  async function handlePresetSave(name: string, description: string, roleConfigs: Record<string, { provider: string; model: string }>) {
    if (editingPreset) {
      await presets.update(editingPreset.id, { name, description, role_configs: roleConfigs });
    } else {
      await presets.create(name, description, roleConfigs);
    }
    showPresetEditor = false;
    editingPreset = null;
    flashSaved();
  }

  async function handleDeletePreset(presetId: string) {
    await presets.remove(presetId);
    flashSaved();
  }

  let connectedCount = $derived(providerList.filter((p) => p.has_key).length);
  let systemPresets = $derived(presetList.filter((p) => p.is_system));
  let userPresets = $derived(presetList.filter((p) => !p.is_system));
</script>

<div class="settings-page">
  <div class="settings-container">
    <div class="settings-header">
      <button class="btn-back" onclick={goBack}>&larr; Back</button>
      <h1>Settings</h1>
      {#if savedMessage}
        <span class="saved-flash">{savedMessage}</span>
      {/if}
    </div>

    <!-- Cloud Providers -->
    <section class="settings-section">
      <div class="section-header">Cloud LLM Providers</div>
      <p class="section-desc">
        Connect cloud LLM providers for higher-quality prose. API keys are stored
        securely in your backend database.
        {#if connectedCount > 0}
          <span class="connected-badge">{connectedCount} connected</span>
        {/if}
      </p>

      <div class="provider-list">
        {#each providerList as provider}
          <div class="provider-card" class:enabled={provider.has_key}>
            <div class="provider-header">
              <div class="provider-info">
                <span class="provider-name">{provider.label}</span>
                {#if provider.has_key}
                  <span class="status-badge status-active">
                    {provider.key_source === 'env' ? 'Env Var' : 'Connected'}
                  </span>
                {:else}
                  <span class="status-badge status-inactive">Not configured</span>
                {/if}
              </div>
              <div class="provider-actions">
                {#if provider.has_key}
                  <button
                    class="btn btn-small"
                    onclick={() => runTest(provider.provider_id)}
                    disabled={testingProvider === provider.provider_id}
                  >
                    {testingProvider === provider.provider_id ? 'Testing...' : 'Test'}
                  </button>
                {/if}
                <button
                  class="btn btn-small"
                  onclick={() => editingKey === provider.provider_id ? cancelEdit() : startEditKey(provider.provider_id)}
                >
                  {editingKey === provider.provider_id ? 'Cancel' : (provider.has_key ? 'Edit Key' : 'Add Key')}
                </button>
              </div>
            </div>

            {#if provider.has_key && editingKey !== provider.provider_id}
              <div class="provider-detail">
                <span class="detail-label">Key:</span>
                <span class="detail-value mono">{provider.key_preview || '****'}</span>
                <span class="detail-label" style="margin-left: 12px;">Models:</span>
                <span class="detail-value">{provider.models.length}</span>
              </div>
            {/if}

            {#if testResults[provider.provider_id] && editingKey !== provider.provider_id}
              {@const tr = testResults[provider.provider_id]}
              <div class="test-result" class:ok={tr.ok} class:fail={!tr.ok}>
                {#if tr.ok}
                  OK ({tr.latency_ms}ms) — {tr.model_used}
                {:else}
                  Failed: {tr.error}
                {/if}
              </div>
            {/if}

            {#if editingKey === provider.provider_id}
              <div class="edit-form">
                <div class="form-group">
                  <label for="key-{provider.provider_id}">API Key</label>
                  <input
                    id="key-{provider.provider_id}"
                    type="password"
                    bind:value={keyInput}
                    placeholder="Paste your API key"
                  />
                </div>
                <div class="edit-actions">
                  <button class="btn btn-primary btn-small" onclick={() => saveKey(provider.provider_id)}>
                    Save
                  </button>
                  {#if provider.has_key && provider.key_source !== 'env'}
                    <button class="btn btn-danger btn-small" onclick={() => removeKey(provider.provider_id)}>
                      Remove Key
                    </button>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {/each}

        {#if providerList.length === 0}
          <p class="empty-state">Loading providers...</p>
        {/if}
      </div>
    </section>

    <!-- Presets -->
    <section class="settings-section">
      <div class="section-header">Cloud Presets</div>
      <p class="section-desc">
        Presets control which agent roles use cloud LLMs. System presets auto-resolve
        to your connected providers. Create custom presets for fine-grained control.
      </p>

      {#if systemPresets.length > 0}
        <h3 class="subsection-label">System Presets</h3>
        <div class="preset-list">
          {#each systemPresets as sp}
            <div class="preset-card system">
              <div class="preset-header">
                <span class="preset-name">{sp.name}</span>
                <span class="preset-badge">System</span>
              </div>
              <span class="preset-desc">{sp.description}</span>
              <span class="preset-roles">
                {Object.keys(sp.role_configs).length} role{Object.keys(sp.role_configs).length !== 1 ? 's' : ''} configured
              </span>
            </div>
          {/each}
        </div>
      {/if}

      <h3 class="subsection-label" style="margin-top: 12px;">Custom Presets</h3>
      {#if userPresets.length > 0}
        <div class="preset-list">
          {#each userPresets as up}
            <div class="preset-card user">
              <div class="preset-header">
                <span class="preset-name">{up.name}</span>
                <div class="preset-actions">
                  <button class="btn btn-small" onclick={() => openEditPreset(up)}>Edit</button>
                  <button class="btn btn-small btn-danger" onclick={() => handleDeletePreset(up.id)}>Delete</button>
                </div>
              </div>
              {#if up.description}
                <span class="preset-desc">{up.description}</span>
              {/if}
              <span class="preset-roles">
                {Object.keys(up.role_configs).length} role{Object.keys(up.role_configs).length !== 1 ? 's' : ''} configured
              </span>
            </div>
          {/each}
        </div>
      {:else}
        <p class="empty-state" style="padding: 8px 0;">No custom presets yet.</p>
      {/if}

      <button class="btn btn-primary" style="margin-top: 8px;" onclick={openCreatePreset}>
        + Create Custom Preset
      </button>
    </section>

    <!-- Display Settings -->
    <section class="settings-section">
      <div class="section-header">Display</div>

      <div class="setting-row">
        <label for="theme-select">Theme</label>
        <select
          id="theme-select"
          value={$ui.theme}
          onchange={(e) => ui.setTheme((e.target as HTMLSelectElement).value)}
        >
          {#each THEME_NAMES as name}
            <option value={name}>{name}</option>
          {/each}
        </select>
      </div>

      <div class="setting-row">
        <label for="font-scale-select">Text Size</label>
        <select
          id="font-scale-select"
          value={String($ui.fontScale ?? 1.0)}
          onchange={(e) => ui.setFontScale(parseFloat((e.target as HTMLSelectElement).value))}
        >
          <option value="0.8">Small (80%)</option>
          <option value="1.0">Normal (100%)</option>
          <option value="1.2">Large (120%)</option>
          <option value="1.5">Extra Large (150%)</option>
        </select>
      </div>

      <div class="setting-row toggle-row">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.enableStreaming}
            onchange={() => ui.toggleStreaming()}
          />
          Enable SSE Streaming
        </label>
      </div>

      <div class="setting-row toggle-row">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.enableTypewriter}
            onchange={() => ui.toggleTypewriter()}
          />
          Typewriter Effect
        </label>
      </div>

      <div class="setting-row toggle-row">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.showDebug}
            onchange={() => ui.toggleDebug()}
          />
          Show Debug Info
        </label>
      </div>

      <div class="setting-row toggle-row">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$preferences.enable_choice_fallbacks}
            onchange={() => preferences.setChoiceFallbacks(!$preferences.enable_choice_fallbacks)}
          />
          Allow Fallback Choices
        </label>
        <span class="section-desc" style="margin: 0; padding: 2px 0 0 28px; font-size: 0.85em;">
          Show generic choices when LLM fails. Disable for LLM-only mode.
        </span>
      </div>
    </section>

    <!-- Advanced: Per-Agent Model Config -->
    <section class="settings-section">
      <button class="advanced-toggle" onclick={() => { showAdvanced = !showAdvanced; if (showAdvanced && agentConfigs.length === 0) loadAgentConfigs(); }}>
        <span class="section-header" style="border: none; margin: 0; padding: 0;">
          Advanced: Agent Model Config
        </span>
        <span class="toggle-arrow" class:open={showAdvanced}>&rsaquo;</span>
      </button>

      {#if showAdvanced}
        <p class="section-desc">
          Shows which LLM model each agent currently uses. Override individual agents
          via custom presets or per-campaign settings.
        </p>

        {#if loadingAgents}
          <p class="empty-state">Loading agent configuration...</p>
        {:else if agentConfigs.length === 0}
          <p class="empty-state">Could not load agent configuration from backend.</p>
        {:else}
          {#each Object.entries(AGENT_CATEGORIES) as [catKey, category]}
            {@const catAgents = agentConfigs.filter((a) => category.roles.includes(a.role))}
            {#if catAgents.length > 0}
              <div class="agent-category">
                <h3 class="category-label">{category.label}</h3>
                <div class="agent-grid">
                  {#each catAgents as agent}
                    <div class="agent-row">
                      <span class="agent-name">{ROLE_LABELS[agent.role] || agent.role}</span>
                      <span class="agent-provider pill">
                        <span class="label">Provider</span>
                        <span class="value">{agent.provider}</span>
                      </span>
                      <span class="agent-model pill">
                        <span class="label">Model</span>
                        <span class="value">{agent.model}</span>
                      </span>
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
          {/each}
        {/if}
      {/if}
    </section>

    <!-- Version -->
    <p class="version-info">Storyteller AI v12.0</p>
  </div>
</div>

{#if showPresetEditor}
  <PresetEditor
    preset={editingPreset}
    onSave={handlePresetSave}
    onCancel={() => { showPresetEditor = false; editingPreset = null; }}
  />
{/if}

<style>
  .settings-page {
    min-height: 100vh;
    padding: 2rem;
    display: flex;
    justify-content: center;
  }

  .settings-container {
    max-width: 640px;
    width: 100%;
  }

  .settings-header {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 2rem;
  }

  .settings-header h1 {
    font-size: 1.5rem;
    color: var(--text-heading);
    margin: 0;
    flex: 1;
  }

  .btn-back {
    background: none;
    border: 1px solid var(--border-subtle);
    color: var(--text-muted);
    padding: 6px 12px;
    border-radius: var(--panel-radius);
    cursor: pointer;
    font-family: inherit;
    font-size: var(--font-small);
    transition: all 0.15s;
  }

  .btn-back:hover {
    color: var(--text-secondary);
    border-color: var(--border-panel);
  }

  .saved-flash {
    font-size: var(--font-small);
    color: var(--accent-primary);
    animation: fadeOut 2s ease-in-out;
  }

  @keyframes fadeOut {
    0%, 70% { opacity: 1; }
    100% { opacity: 0; }
  }

  .settings-section {
    margin-bottom: 2rem;
  }

  .section-desc {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin: 0 0 12px;
    line-height: 1.5;
  }

  .connected-badge {
    display: inline-block;
    background: rgba(0, 200, 100, 0.12);
    color: #4ade80;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 600;
    margin-left: 4px;
  }

  /* Provider cards */
  .provider-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .provider-card {
    padding: 14px 16px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--panel-radius);
    background: var(--bg-panel);
    transition: border-color 0.15s;
  }

  .provider-card.enabled {
    border-color: var(--border-panel);
  }

  .provider-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .provider-info {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  .provider-actions {
    display: flex;
    gap: 6px;
  }

  .provider-name {
    font-weight: 600;
    color: var(--text-heading);
    font-size: var(--font-body);
  }

  .status-badge {
    font-size: 0.65rem;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
  }

  .status-active {
    color: var(--tone-paragon);
    border: 1px solid var(--tone-paragon);
    opacity: 0.8;
  }

  .status-inactive {
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
  }

  .provider-detail {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
    font-size: var(--font-small);
  }

  .detail-label {
    color: var(--text-muted);
  }

  .detail-value {
    color: var(--text-secondary);
  }

  .detail-value.mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
  }

  .test-result {
    font-size: var(--font-small);
    padding: 4px 10px;
    margin-top: 6px;
    border-radius: 4px;
  }

  .test-result.ok {
    color: #4ade80;
    background: rgba(0, 200, 100, 0.06);
  }

  .test-result.fail {
    color: var(--accent-danger);
    background: rgba(255, 80, 60, 0.06);
  }

  .edit-form {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border-subtle);
  }

  .form-group {
    margin-bottom: 10px;
  }

  .form-group label {
    display: block;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .edit-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }

  .btn-small {
    padding: 4px 12px;
    font-size: var(--font-small);
  }

  .btn-danger {
    color: var(--accent-danger);
    border-color: var(--accent-danger);
  }

  .btn-danger:hover {
    background: rgba(255, 80, 60, 0.1);
  }

  /* Presets */
  .subsection-label {
    font-size: var(--font-small);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 6px;
    font-weight: 600;
  }

  .preset-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .preset-card {
    padding: 10px 14px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--panel-radius);
    background: var(--bg-panel);
  }

  .preset-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .preset-name {
    font-weight: 600;
    color: var(--text-heading);
    font-size: var(--font-body);
  }

  .preset-badge {
    font-size: 0.65rem;
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    padding: 1px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .preset-actions {
    display: flex;
    gap: 6px;
  }

  .preset-desc {
    display: block;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 2px;
  }

  .preset-roles {
    display: block;
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 4px;
  }

  /* Display settings */
  .setting-row {
    margin-bottom: 12px;
  }

  .setting-row label {
    display: block;
    font-size: var(--font-caption);
    color: var(--text-secondary);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .toggle-row {
    margin-bottom: 8px;
  }

  .toggle-label {
    display: flex !important;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    text-transform: none !important;
    font-size: var(--font-body) !important;
    color: var(--text-primary) !important;
  }

  .toggle-label input {
    width: auto;
  }

  /* Advanced agent config */
  .advanced-toggle {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    color: inherit;
    font-family: inherit;
  }

  .toggle-arrow {
    font-size: 1.2rem;
    color: var(--text-muted);
    transition: transform 0.2s;
  }

  .toggle-arrow.open {
    transform: rotate(90deg);
  }

  .agent-category {
    margin-bottom: 14px;
  }

  .category-label {
    font-size: var(--font-small);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 6px;
    font-weight: 600;
  }

  .agent-grid {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .agent-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.02);
    flex-wrap: wrap;
  }

  .agent-name {
    min-width: 140px;
    font-size: var(--font-small);
    font-weight: 600;
    color: var(--text-primary);
  }

  .agent-provider,
  .agent-model {
    font-size: 0.72rem;
  }

  .empty-state {
    color: var(--text-muted);
    font-style: italic;
    font-size: var(--font-body);
    padding: 16px 0;
    text-align: center;
  }

  .version-info {
    text-align: center;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-subtle);
  }
</style>
