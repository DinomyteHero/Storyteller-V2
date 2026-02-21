<!--
  Settings Page: Global LLM provider management and app configuration.
  API keys are stored locally in the browser — never sent to an external server.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { providers, type ProviderConfig } from '$lib/stores/providers';
  import { ui } from '$lib/stores/ui';
  import { THEME_NAMES } from '$lib/themes/tokens';

  let providerList = $state<ProviderConfig[]>([]);
  let editingKey = $state<string | null>(null);
  let keyInput = $state('');
  let urlInput = $state('');
  let showKeyFor = $state<string | null>(null);
  let savedMessage = $state('');

  // Subscribe to provider store
  providers.subscribe((val) => {
    providerList = val;
  });

  function startEditKey(providerId: string) {
    const provider = providerList.find((p) => p.id === providerId);
    editingKey = providerId;
    keyInput = provider?.apiKey || '';
    urlInput = provider?.baseUrl || '';
  }

  function saveKey(providerId: string) {
    providers.setApiKey(providerId, keyInput.trim());
    if (urlInput.trim()) {
      providers.updateProvider(providerId, { baseUrl: urlInput.trim() });
    }
    editingKey = null;
    keyInput = '';
    urlInput = '';
    flashSaved();
  }

  function removeKey(providerId: string) {
    providers.removeApiKey(providerId);
    editingKey = null;
    flashSaved();
  }

  function cancelEdit() {
    editingKey = null;
    keyInput = '';
    urlInput = '';
  }

  function toggleKeyVisibility(providerId: string) {
    showKeyFor = showKeyFor === providerId ? null : providerId;
  }

  function maskKey(key: string): string {
    if (!key) return '';
    if (key.length <= 8) return '****';
    return key.slice(0, 4) + '...' + key.slice(-4);
  }

  function flashSaved() {
    savedMessage = 'Saved';
    setTimeout(() => { savedMessage = ''; }, 2000);
  }

  function goBack() {
    goto('/');
  }
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

    <!-- LLM Providers -->
    <section class="settings-section">
      <div class="section-header">LLM Providers</div>
      <p class="section-desc">
        Configure cloud LLM providers for higher-quality prose. API keys are stored
        locally in your browser and only sent to your backend server.
      </p>

      <div class="provider-list">
        {#each providerList as provider}
          <div class="provider-card" class:enabled={provider.enabled}>
            <div class="provider-header">
              <div class="provider-info">
                <span class="provider-name">{provider.label}</span>
                {#if provider.enabled}
                  <span class="status-badge status-active">Active</span>
                {:else}
                  <span class="status-badge status-inactive">Not configured</span>
                {/if}
              </div>
              {#if provider.id !== 'ollama'}
                <button
                  class="btn btn-small"
                  onclick={() => editingKey === provider.id ? cancelEdit() : startEditKey(provider.id)}
                >
                  {editingKey === provider.id ? 'Cancel' : (provider.apiKey ? 'Edit' : 'Configure')}
                </button>
              {/if}
            </div>

            {#if provider.id === 'ollama'}
              <div class="provider-detail">
                <span class="detail-label">Endpoint:</span>
                <span class="detail-value">{provider.baseUrl || 'http://localhost:11434'}</span>
              </div>
              <p class="provider-note">
                Ollama runs locally and requires no API key. Make sure it's running
                with <code>ollama serve</code>.
              </p>
            {:else if provider.apiKey && editingKey !== provider.id}
              <div class="provider-detail">
                <span class="detail-label">API Key:</span>
                <span class="detail-value">
                  {showKeyFor === provider.id ? provider.apiKey : maskKey(provider.apiKey)}
                </span>
                <button class="btn-icon" onclick={() => toggleKeyVisibility(provider.id)}>
                  {showKeyFor === provider.id ? 'Hide' : 'Show'}
                </button>
              </div>
              {#if provider.baseUrl}
                <div class="provider-detail">
                  <span class="detail-label">Base URL:</span>
                  <span class="detail-value">{provider.baseUrl}</span>
                </div>
              {/if}
            {/if}

            {#if editingKey === provider.id}
              <div class="edit-form">
                <div class="form-group">
                  <label for="key-{provider.id}">API Key</label>
                  <input
                    id="key-{provider.id}"
                    type="password"
                    bind:value={keyInput}
                    placeholder={provider.apiKeyEnvVar ? `Paste your ${provider.apiKeyEnvVar}` : 'Enter API key'}
                  />
                </div>
                {#if provider.id === 'openai_compat'}
                  <div class="form-group">
                    <label for="url-{provider.id}">Base URL</label>
                    <input
                      id="url-{provider.id}"
                      type="text"
                      bind:value={urlInput}
                      placeholder="https://api.example.com/v1"
                    />
                  </div>
                {/if}
                <div class="edit-actions">
                  <button class="btn btn-primary btn-small" onclick={() => saveKey(provider.id)}>
                    Save
                  </button>
                  {#if provider.apiKey}
                    <button class="btn btn-danger btn-small" onclick={() => removeKey(provider.id)}>
                      Remove Key
                    </button>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>
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
    </section>

    <!-- Version -->
    <p class="version-info">Storyteller AI v2.16</p>
  </div>
</div>

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
    margin-bottom: 6px;
  }

  .provider-info {
    display: flex;
    align-items: center;
    gap: 8px;
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
    min-width: 60px;
  }

  .detail-value {
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
  }

  .btn-icon {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 0.7rem;
    cursor: pointer;
    padding: 2px 6px;
    font-family: inherit;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .btn-icon:hover {
    color: var(--text-secondary);
  }

  .provider-note {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 6px;
    line-height: 1.4;
  }

  .provider-note code {
    background: var(--bg-input);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.8rem;
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

  .version-info {
    text-align: center;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-subtle);
  }
</style>
