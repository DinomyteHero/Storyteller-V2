<script lang="ts">
  import { suggestPeriods, generatePack } from '$lib/api/library';
  import type { EraForgePeriodProposal, EraForgeSuggestResponse } from '$lib/api/library';

  interface Props {
    onComplete: () => void;
    onCancel: () => void;
  }
  let { onComplete, onCancel }: Props = $props();

  // Wizard state
  let step = $state<1 | 2 | 3>(1);
  let settingPrompt = $state('');
  let suggestResult = $state<EraForgeSuggestResponse | null>(null);
  let selectedPeriod = $state<EraForgePeriodProposal | null>(null);
  let loading = $state(false);
  let error = $state('');
  let generateResult = $state<{ display_name: string; backgrounds_count: number; species_count: number; canon_characters_count: number } | null>(null);

  async function handleSuggest() {
    if (!settingPrompt.trim()) return;
    loading = true;
    error = '';
    try {
      suggestResult = await suggestPeriods(settingPrompt.trim());
      step = 2;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to suggest periods.';
    } finally {
      loading = false;
    }
  }

  async function handleGenerate() {
    if (!suggestResult || !selectedPeriod) return;
    loading = true;
    error = '';
    step = 3;
    try {
      const result = await generatePack({
        setting_id: suggestResult.setting_id,
        setting_name: suggestResult.setting_name,
        setting_genre: suggestResult.setting_genre,
        period_id: selectedPeriod.period_id,
        display_name: selectedPeriod.display_name,
        time_period: selectedPeriod.time_period,
        summary: selectedPeriod.summary,
        tone: selectedPeriod.tone,
        key_conflicts: selectedPeriod.key_conflicts,
        source_prompt: settingPrompt,
      });
      generateResult = result;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to generate world.';
      step = 2;
    } finally {
      loading = false;
    }
  }

  function handleBack() {
    if (step === 2) {
      step = 1;
      selectedPeriod = null;
    }
  }
</script>

<div class="wizard-container">
  <!-- Step 1: Describe your setting -->
  {#if step === 1}
    <h3 class="wizard-title">Create New World</h3>
    <p class="wizard-desc">Describe a setting and we'll generate a playable world for you.</p>
    <div class="input-group">
      <label for="setting-prompt">Setting Description</label>
      <textarea
        id="setting-prompt"
        bind:value={settingPrompt}
        placeholder="e.g. 'Game of Thrones', 'Cyberpunk Tokyo 2077', 'Ancient Rome during Caesar's reign'..."
        rows="3"
        disabled={loading}
      ></textarea>
    </div>
    {#if error}
      <div class="error-banner" role="alert">{error}</div>
    {/if}
    <div class="wizard-actions">
      <button class="btn" onclick={onCancel}>Cancel</button>
      <button class="btn btn-primary" onclick={handleSuggest} disabled={loading || !settingPrompt.trim()}>
        {loading ? 'Thinking...' : 'Suggest Periods'}
      </button>
    </div>

  <!-- Step 2: Pick a period -->
  {:else if step === 2}
    <h3 class="wizard-title">Choose a Time Period</h3>
    <p class="wizard-desc">
      {suggestResult?.setting_name ?? 'Your setting'} — pick a period to generate.
    </p>
    <div class="period-grid">
      {#each suggestResult?.periods ?? [] as period}
        <button
          class="period-card"
          class:selected={selectedPeriod?.period_id === period.period_id}
          type="button"
          onclick={() => selectedPeriod = period}
        >
          <span class="period-name">{period.display_name}</span>
          <span class="period-time">{period.time_period}</span>
          <p class="period-summary">{period.summary}</p>
          {#if period.tone}
            <span class="period-tone">{period.tone}</span>
          {/if}
        </button>
      {/each}
    </div>
    {#if error}
      <div class="error-banner" role="alert">{error}</div>
    {/if}
    <div class="wizard-actions">
      <button class="btn" onclick={handleBack}>Back</button>
      <button class="btn btn-primary" onclick={handleGenerate} disabled={loading || !selectedPeriod}>
        {loading ? 'Generating...' : 'Generate World'}
      </button>
    </div>

  <!-- Step 3: Loading / Success -->
  {:else if step === 3}
    {#if loading}
      <div class="loading-state">
        <div class="spinner"></div>
        <h3 class="wizard-title">Generating World...</h3>
        <p class="wizard-desc">This may take a minute. The LLM is building backgrounds, species, canon characters, and more.</p>
      </div>
    {:else if generateResult}
      <div class="success-state">
        <h3 class="wizard-title">World Created</h3>
        <p class="wizard-desc">{generateResult.display_name} is ready to play.</p>
        <div class="result-stats">
          <span class="stat-pill">{generateResult.backgrounds_count} backgrounds</span>
          <span class="stat-pill">{generateResult.species_count} species</span>
          <span class="stat-pill">{generateResult.canon_characters_count} canon characters</span>
        </div>
        <div class="wizard-actions">
          <button class="btn btn-primary" onclick={onComplete}>Done</button>
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .wizard-container {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .wizard-title {
    font-family: var(--font-heading, 'Rajdhani', sans-serif);
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text-heading, #e8c56a);
    margin: 0;
  }
  .wizard-desc {
    font-size: 0.82rem;
    color: var(--text-secondary, #aaa);
    margin: 0;
  }
  .input-group {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .input-group label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted, #888);
  }
  .input-group textarea {
    width: 100%;
    padding: 0.6rem;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.15));
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.2);
    color: var(--text-primary, #eee);
    font-size: 0.85rem;
    font-family: inherit;
    resize: vertical;
  }
  .input-group textarea:focus {
    outline: none;
    border-color: var(--accent-primary, #e8c56a);
  }
  .wizard-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .period-grid {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 320px;
    overflow-y: auto;
  }
  .period-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.75rem;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.12));
    border-radius: 6px;
    background: var(--bg-panel, rgba(255, 255, 255, 0.03));
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s, background 0.15s;
    width: 100%;
  }
  .period-card:hover {
    border-color: rgba(255, 255, 255, 0.3);
    background: rgba(255, 255, 255, 0.05);
  }
  .period-card.selected {
    border-color: var(--accent-primary, #e8c56a);
    background: rgba(232, 197, 106, 0.08);
  }
  .period-name {
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-primary, #eee);
  }
  .period-time {
    font-size: 0.72rem;
    color: var(--text-muted, #888);
  }
  .period-summary {
    font-size: 0.78rem;
    color: var(--text-secondary, #aaa);
    margin: 0;
    line-height: 1.35;
  }
  .period-tone {
    font-size: 0.65rem;
    font-style: italic;
    color: var(--text-muted, #777);
  }
  .error-banner {
    padding: 8px 12px;
    border-radius: 6px;
    background: rgba(255, 80, 60, 0.12);
    border: 1px solid var(--accent-danger, #ff5040);
    color: var(--accent-danger, #ff5040);
    font-size: 0.8rem;
  }
  .loading-state, .success-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 2rem 0;
    text-align: center;
  }
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid rgba(255, 255, 255, 0.1);
    border-top-color: var(--accent-primary, #e8c56a);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .result-stats {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  .stat-pill {
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-secondary, #aaa);
  }
</style>
