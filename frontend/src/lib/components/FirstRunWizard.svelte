<!--
  FirstRunWizard: Shown on the home screen when the user has never played before.
  Guides through: Welcome → Ollama check → Optional cloud config → Ready to play.
-->
<script lang="ts">
  import { getHealthDetail } from '$lib/api/client';
  import { providers } from '$lib/stores/providers';
  import { goto } from '$app/navigation';

  let step = $state<'welcome' | 'ollama' | 'cloud' | 'ready'>('welcome');
  let ollamaOk = $state(false);
  let ollamaChecking = $state(false);
  let ollamaError = $state('');
  let cloudKeyInput = $state('');
  let cloudProvider = $state<'anthropic' | 'openai'>('anthropic');

  async function checkOllama() {
    ollamaChecking = true;
    ollamaError = '';
    try {
      const detail = await getHealthDetail();
      const ollama = detail.checks?.ollama;
      ollamaOk = !!ollama?.ok;
      if (!ollamaOk) {
        ollamaError = 'Ollama is not running. Start it with: ollama serve';
      }
    } catch {
      ollamaOk = false;
      ollamaError = 'Could not reach the backend. Make sure the server is running.';
    }
    ollamaChecking = false;
  }

  function skipToCloud() {
    step = 'cloud';
  }

  function goToOllamaCheck() {
    step = 'ollama';
    checkOllama();
  }

  function saveCloudKey() {
    if (cloudKeyInput.trim()) {
      providers.setApiKey(cloudProvider, cloudKeyInput.trim());
    }
    step = 'ready';
  }

  function skipCloud() {
    step = 'ready';
  }

  function completeSetup() {
    // Mark first-run as complete
    try {
      localStorage.setItem('storyteller-first-run-complete', 'true');
    } catch {
      // storage unavailable
    }
    goto('/create');
  }

  function dismiss() {
    try {
      localStorage.setItem('storyteller-first-run-complete', 'true');
    } catch {
      // storage unavailable
    }
  }
</script>

<div class="wizard-overlay">
  <div class="wizard-card">
    {#if step === 'welcome'}
      <div class="wizard-step fade-in">
        <h2>Welcome to Storyteller AI</h2>
        <p class="wizard-desc">
          An interactive fiction engine powered by LLMs. Your stories are generated
          locally using Ollama, with optional cloud LLMs for higher quality prose.
        </p>
        <div class="wizard-actions">
          <button class="btn btn-primary" onclick={goToOllamaCheck}>Get Started</button>
          <button class="btn-link" onclick={dismiss}>I've set this up before</button>
        </div>
      </div>

    {:else if step === 'ollama'}
      <div class="wizard-step fade-in">
        <h2>Local LLM Engine</h2>
        <p class="wizard-desc">
          Storyteller uses Ollama to run AI models locally on your machine. This
          keeps your stories private and free.
        </p>

        <div class="check-status">
          {#if ollamaChecking}
            <div class="check-icon checking">...</div>
            <span>Checking Ollama...</span>
          {:else if ollamaOk}
            <div class="check-icon ok">&#10003;</div>
            <span>Ollama is running</span>
          {:else}
            <div class="check-icon fail">&#10007;</div>
            <span class="check-error">{ollamaError}</span>
          {/if}
        </div>

        {#if !ollamaOk && !ollamaChecking}
          <div class="help-box">
            <p>Install Ollama from <strong>ollama.com</strong>, then run:</p>
            <code>ollama serve</code>
            <p style="margin-top: 8px;">Then pull the default model:</p>
            <code>ollama pull qwen3:8b</code>
          </div>
          <div class="wizard-actions">
            <button class="btn btn-primary" onclick={checkOllama}>Retry Check</button>
            <button class="btn" onclick={skipToCloud}>
              Skip (use cloud LLMs instead)
            </button>
          </div>
        {:else if ollamaOk}
          <div class="wizard-actions">
            <button class="btn btn-primary" onclick={() => step = 'cloud'}>
              Next: Cloud Setup (Optional)
            </button>
            <button class="btn" onclick={() => step = 'ready'}>
              Skip — Local Only
            </button>
          </div>
        {/if}
      </div>

    {:else if step === 'cloud'}
      <div class="wizard-step fade-in">
        <h2>Cloud LLM (Optional)</h2>
        <p class="wizard-desc">
          For higher quality prose, you can connect a cloud LLM provider.
          This is completely optional — local Ollama works great on its own.
        </p>

        <div class="cloud-form">
          <div class="form-group">
            <label>Provider</label>
            <select bind:value={cloudProvider}>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>
          <div class="form-group">
            <label>API Key</label>
            <input
              type="password"
              bind:value={cloudKeyInput}
              placeholder={cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'}
            />
          </div>
        </div>

        <div class="wizard-actions">
          <button class="btn btn-primary" onclick={saveCloudKey}>
            {cloudKeyInput.trim() ? 'Save & Continue' : 'Continue Without Cloud'}
          </button>
          <button class="btn-link" onclick={skipCloud}>Skip for now</button>
        </div>
      </div>

    {:else if step === 'ready'}
      <div class="wizard-step fade-in">
        <h2>You're Ready!</h2>
        <p class="wizard-desc">
          Everything is set up. Create your first story — choose a universe,
          build a character, and begin your adventure.
        </p>
        <div class="ready-summary">
          {#if ollamaOk}
            <div class="summary-item ok">Local LLM: Ready</div>
          {:else}
            <div class="summary-item warn">Local LLM: Not detected</div>
          {/if}
          {#if cloudKeyInput.trim()}
            <div class="summary-item ok">Cloud LLM: Configured</div>
          {:else}
            <div class="summary-item neutral">Cloud LLM: Not configured</div>
          {/if}
        </div>
        <div class="wizard-actions">
          <button class="btn btn-primary" onclick={completeSetup}>
            Create Your First Story
          </button>
        </div>
      </div>
    {/if}

    <div class="step-dots">
      {#each ['welcome', 'ollama', 'cloud', 'ready'] as s}
        <div class="dot" class:active={step === s}></div>
      {/each}
    </div>
  </div>
</div>

<style>
  .wizard-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1100;
    animation: fadeIn 0.3s ease;
    padding: 1rem;
  }

  .wizard-card {
    background: var(--bg-overlay);
    border: 1px solid var(--border-panel);
    border-radius: var(--panel-radius);
    padding: 32px;
    max-width: 480px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  .wizard-step {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .wizard-step h2 {
    font-size: 1.3rem;
    color: var(--text-heading);
    margin: 0;
  }

  .wizard-desc {
    color: var(--text-secondary);
    font-size: var(--font-body);
    line-height: 1.6;
    margin: 0;
  }

  .wizard-actions {
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: center;
    margin-top: 8px;
  }

  .wizard-actions .btn {
    width: 100%;
    max-width: 280px;
  }

  .btn-link {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: var(--font-small);
    cursor: pointer;
    padding: 4px;
    font-family: inherit;
    transition: color 0.15s;
  }

  .btn-link:hover {
    color: var(--text-secondary);
  }

  /* Ollama check */
  .check-status {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-subtle);
    font-size: var(--font-body);
    color: var(--text-secondary);
  }

  .check-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.8rem;
    flex-shrink: 0;
  }

  .check-icon.checking {
    border: 2px solid var(--border-subtle);
    color: var(--text-muted);
    animation: spin 1s linear infinite;
  }

  .check-icon.ok {
    background: rgba(0, 200, 100, 0.15);
    color: #4ade80;
    border: 1px solid rgba(0, 200, 100, 0.3);
  }

  .check-icon.fail {
    background: rgba(255, 80, 60, 0.15);
    color: var(--accent-danger);
    border: 1px solid rgba(255, 80, 60, 0.3);
  }

  .check-error {
    color: var(--accent-danger);
    font-size: var(--font-small);
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .help-box {
    padding: 12px 14px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    font-size: var(--font-small);
    color: var(--text-muted);
    line-height: 1.5;
  }

  .help-box p {
    margin: 0;
  }

  .help-box code {
    display: block;
    background: var(--bg-input);
    padding: 6px 10px;
    border-radius: 4px;
    margin-top: 6px;
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  /* Cloud form */
  .cloud-form {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .form-group label {
    font-size: var(--font-small);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  /* Ready summary */
  .ready-summary {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .summary-item {
    font-size: var(--font-small);
    padding: 6px 12px;
    border-radius: 4px;
    border: 1px solid var(--border-subtle);
  }

  .summary-item.ok {
    color: #4ade80;
    border-color: rgba(0, 200, 100, 0.2);
  }

  .summary-item.warn {
    color: var(--accent-danger);
    border-color: rgba(255, 80, 60, 0.2);
  }

  .summary-item.neutral {
    color: var(--text-muted);
  }

  /* Step dots */
  .step-dots {
    display: flex;
    justify-content: center;
    gap: 8px;
    margin-top: 20px;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--border-subtle);
    transition: all 0.2s;
  }

  .dot.active {
    background: var(--accent-primary);
    width: 18px;
    border-radius: 3px;
  }

  .fade-in {
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>
