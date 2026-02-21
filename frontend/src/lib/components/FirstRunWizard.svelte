<!--
  FirstRunWizard: Shown on the home screen when the user has never played before.
  Guides through: Welcome → Ollama check → Optional cloud config → Ready to play.
-->
<script lang="ts">
  import { getHealthDetail } from '$lib/api/client';
  import { providers, type ProviderStatus } from '$lib/stores/providers';
  import { goto } from '$app/navigation';

  interface Props {
    ondismiss?: () => void;
  }
  let { ondismiss }: Props = $props();

  let step = $state<'welcome' | 'ollama' | 'cloud' | 'ready'>('welcome');
  let ollamaOk = $state(false);
  let ollamaReachable = $state(false);
  let ollamaChecking = $state(false);
  let ollamaError = $state('');
  let missingModels = $state<string[]>([]);
  let cloudKeyInput = $state('');
  let cloudProvider = $state('anthropic');
  let providerList = $state<ProviderStatus[]>([]);
  let cloudKeySaved = $state(false);
  let testingCloud = $state(false);
  let cloudTestOk = $state<boolean | null>(null);

  // Subscribe to provider store
  providers.subscribe((val) => { providerList = val; });

  // V12.0: All 5 cloud providers
  const CLOUD_PROVIDERS = [
    { id: 'anthropic', label: 'Anthropic (Claude)', placeholder: 'sk-ant-...' },
    { id: 'openai', label: 'OpenAI', placeholder: 'sk-...' },
    { id: 'xai', label: 'xAI (Grok)', placeholder: 'xai-...' },
    { id: 'deepseek', label: 'DeepSeek', placeholder: 'sk-...' },
    { id: 'google', label: 'Google (Gemini)', placeholder: 'AI...' },
  ];

  async function checkOllama() {
    ollamaChecking = true;
    ollamaError = '';
    missingModels = [];
    try {
      const detail = await getHealthDetail();
      const ollama = detail.checks?.ollama;
      ollamaReachable = ollama?.status === 'reachable';
      ollamaOk = !!ollama?.ok;
      missingModels = ollama?.missing_required_models ?? [];
      if (!ollamaReachable) {
        ollamaError = 'Ollama is not running. Start it with: ollama serve';
      } else if (missingModels.length > 0) {
        ollamaError = `Ollama is running but ${missingModels.length} required model${missingModels.length > 1 ? 's are' : ' is'} missing.`;
      }
      // Also load provider statuses
      await providers.load();
    } catch {
      ollamaOk = false;
      ollamaReachable = false;
      ollamaError = 'Could not reach the backend. Make sure the server is running.';
    }
    ollamaChecking = false;
  }

  function skipToCloud() {
    step = 'cloud';
    providers.load();
  }

  function goToOllamaCheck() {
    step = 'ollama';
    checkOllama();
  }

  async function saveCloudKey() {
    if (cloudKeyInput.trim()) {
      await providers.setKey(cloudProvider, cloudKeyInput.trim());
      cloudKeySaved = true;
    }
    step = 'ready';
  }

  async function testCloudProvider() {
    if (!cloudKeyInput.trim()) return;
    testingCloud = true;
    cloudTestOk = null;
    // Save key first, then test
    await providers.setKey(cloudProvider, cloudKeyInput.trim());
    try {
      const result = await providers.test(cloudProvider);
      cloudTestOk = result.ok;
    } catch {
      cloudTestOk = false;
    }
    testingCloud = false;
  }

  function skipCloud() {
    step = 'ready';
  }

  function completeSetup() {
    try {
      localStorage.setItem('storyteller-first-run-complete', 'true');
    } catch {
      // storage unavailable
    }
    ondismiss?.();
    goto('/create');
  }

  function dismiss() {
    try {
      localStorage.setItem('storyteller-first-run-complete', 'true');
    } catch {
      // storage unavailable
    }
    // Run a health check before dismissing so the "I've set this up before" path
    // still validates the environment — but don't block on it
    checkOllama();
    ondismiss?.();
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).catch(() => {});
  }

  $: hasAnyCloudKey = providerList.some((p) => p.has_key);
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

        {#if !ollamaReachable && !ollamaChecking}
          <div class="help-box">
            <p>Install Ollama from <strong>ollama.com</strong>, then run:</p>
            <code>ollama serve</code>
          </div>
          <div class="wizard-actions">
            <button class="btn btn-primary" onclick={checkOllama}>Check Again</button>
            <button class="btn" onclick={skipToCloud}>
              Skip (use cloud LLMs instead)
            </button>
          </div>
        {:else if ollamaReachable && missingModels.length > 0 && !ollamaChecking}
          <div class="help-box">
            <p>Ollama is running, but these models need to be pulled:</p>
            {#each missingModels as model}
              <div class="model-pull-row">
                <code>ollama pull {model}</code>
                <button class="copy-btn" onclick={() => copyToClipboard(`ollama pull ${model}`)} title="Copy command">
                  Copy
                </button>
              </div>
            {/each}
          </div>
          <div class="wizard-actions">
            <button class="btn btn-primary" onclick={checkOllama}>Check Again</button>
            <button class="btn" onclick={() => step = 'cloud'}>
              Next: Cloud Setup (Optional)
            </button>
          </div>
        {:else if ollamaOk && !ollamaChecking}
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
          For higher quality prose, connect a cloud LLM provider.
          This is optional — local Ollama works great on its own.
          You can add more providers later in Settings.
        </p>

        <div class="cloud-form">
          <div class="form-group">
            <label>Provider</label>
            <select bind:value={cloudProvider}>
              {#each CLOUD_PROVIDERS as cp}
                <option value={cp.id}>{cp.label}</option>
              {/each}
            </select>
          </div>
          <div class="form-group">
            <label>API Key</label>
            <input
              type="password"
              bind:value={cloudKeyInput}
              placeholder={CLOUD_PROVIDERS.find((p) => p.id === cloudProvider)?.placeholder || 'Enter API key'}
            />
          </div>
          {#if cloudKeyInput.trim()}
            <button
              class="btn btn-small"
              onclick={testCloudProvider}
              disabled={testingCloud}
              style="align-self: flex-start;"
            >
              {testingCloud ? 'Testing...' : 'Test Connection'}
            </button>
            {#if cloudTestOk === true}
              <span class="test-ok">Connected successfully!</span>
            {:else if cloudTestOk === false}
              <span class="test-fail">Connection failed. Check your API key.</span>
            {/if}
          {/if}
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
        {#if !ollamaReachable && !hasAnyCloudKey}
          <h2>Almost There</h2>
          <p class="wizard-desc">
            Ollama must be running to play. Start it with <code class="inline-code">ollama serve</code>,
            or go back and configure a cloud LLM provider.
          </p>
          <div class="ready-summary">
            <div class="summary-item warn">Local LLM: Not running</div>
            <div class="summary-item neutral">Cloud LLM: Not configured</div>
          </div>
          <div class="wizard-actions">
            <button class="btn btn-primary" onclick={goToOllamaCheck}>
              Check Ollama Again
            </button>
            <button class="btn" onclick={() => step = 'cloud'}>
              Configure Cloud LLM
            </button>
          </div>
        {:else}
          <h2>You're Ready!</h2>
          <p class="wizard-desc">
            Everything is set up. Create your first story — choose a universe,
            build a character, and begin your adventure.
          </p>
          <div class="ready-summary">
            {#if ollamaOk}
              <div class="summary-item ok">Local LLM: Ready</div>
            {:else if ollamaReachable && missingModels.length > 0}
              <div class="summary-item warn">Local LLM: {missingModels.length} model{missingModels.length > 1 ? 's' : ''} missing (may affect quality)</div>
            {:else if !ollamaReachable && hasAnyCloudKey}
              <div class="summary-item warn">Local LLM: Not running (using cloud instead)</div>
            {:else}
              <div class="summary-item warn">Local LLM: Not detected</div>
            {/if}
            {#if hasAnyCloudKey}
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
        {/if}
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

  .model-pull-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
  }

  .model-pull-row code {
    flex: 1;
    margin-top: 0;
  }

  .copy-btn {
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    color: var(--text-muted);
    font-size: 0.75rem;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
    transition: color 0.15s, border-color 0.15s;
    flex-shrink: 0;
  }

  .copy-btn:hover {
    color: var(--text-secondary);
    border-color: var(--accent-primary);
  }

  .inline-code {
    background: var(--bg-input);
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.85rem;
    font-family: monospace;
  }

  .test-ok {
    font-size: var(--font-small);
    color: #4ade80;
  }

  .test-fail {
    font-size: var(--font-small);
    color: var(--accent-danger);
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
