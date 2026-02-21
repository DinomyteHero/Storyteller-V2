<!--
  Origin Story: A playable backstory flashback before the prologue.
  Dragon Age: Origins style — 3-turn interactive backstory sequence.
  Flow: /create → /origin (3 turns) → /prologue → /play
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiFetch } from '$lib/api/client';
  import { runTurn } from '$lib/api/campaigns';
  import { campaignId, playerId, lastTurnResponse } from '$lib/stores/game';

  interface OriginScreenplay {
    origin_title: string;
    setting_description: string;
    opening_scene: string;
    dilemma: string;
    resolution_hook: string;
    npc_cast: Array<{ name: string; role: string; relationship_to_player?: string }>;
    tone: string;
  }

  let screenplay = $state<OriginScreenplay | null>(null);
  let phase = $state<'loading' | 'intro' | 'playing' | 'complete'>('loading');
  let narrativeText = $state('');
  let suggestedActions = $state<Array<{ label: string; tone?: string }>>([]);
  let customInput = $state('');
  let turnCount = $state(0);
  let isProcessing = $state(false);
  let errorMessage = $state('');

  onMount(async () => {
    const cid = $campaignId;
    if (!cid) {
      goto('/');
      return;
    }
    try {
      const resp = await apiFetch<{ campaign_id: string; world_state: Record<string, unknown> }>(
        `/v2/campaigns/${cid}/world_state`
      );
      const ws = resp.world_state ?? {};
      if (ws.origin_screenplay) {
        screenplay = ws.origin_screenplay as OriginScreenplay;
      }
      if (!ws.origin_mode) {
        // Origin already done or not enabled — go to prologue
        goto('/prologue');
        return;
      }
      phase = 'intro';
    } catch {
      goto('/prologue');
    }
  });

  async function beginOrigin() {
    phase = 'playing';
    if (screenplay) {
      narrativeText = screenplay.opening_scene;
    }
    // Run the first turn to get suggestions
    await runOriginTurn('');
  }

  async function runOriginTurn(input: string) {
    const cid = $campaignId;
    const pid = $playerId;
    if (!cid || !pid) return;

    isProcessing = true;
    errorMessage = '';
    try {
      const resp = await runTurn(cid, pid, input);
      narrativeText = resp.narrated_text || narrativeText;
      suggestedActions = (resp.suggested_actions || []).map((a: any) => ({
        label: typeof a === 'string' ? a : (a.label || a.text || String(a)),
        tone: typeof a === 'object' ? a.tone : undefined,
      }));
      lastTurnResponse.set(resp as any);
      turnCount++;

      // Check if origin is complete (backend will have cleared origin_mode)
      const stateResp = await apiFetch<{ campaign_id: string; world_state: Record<string, unknown> }>(
        `/v2/campaigns/${cid}/world_state`
      );
      const ws = stateResp.world_state ?? {};
      if (!ws.origin_mode) {
        phase = 'complete';
      }
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : 'Something went wrong.';
    } finally {
      isProcessing = false;
    }
  }

  function handleChoice(label: string) {
    if (isProcessing) return;
    customInput = '';
    runOriginTurn(label);
  }

  function handleCustomInput() {
    if (isProcessing || !customInput.trim()) return;
    const input = customInput.trim();
    customInput = '';
    runOriginTurn(input);
  }

  function proceedToPrologue() {
    goto('/prologue');
  }

  function skipOrigin() {
    goto('/prologue');
  }
</script>

<div class="origin-container">
  {#if phase === 'loading'}
    <div class="loading">
      <div class="loading-spinner"></div>
      <p>Loading your origin story...</p>
    </div>

  {:else if phase === 'intro' && screenplay}
    <div class="intro-content fade-in">
      <div class="origin-label">Origin Story</div>
      <h1 class="origin-title">{screenplay.origin_title}</h1>

      <div class="intro-setting">
        <p>{screenplay.setting_description}</p>
      </div>

      {#if screenplay.npc_cast && screenplay.npc_cast.length > 0}
        <div class="intro-cast">
          {#each screenplay.npc_cast as npc}
            <div class="npc-tag">
              <span class="npc-tag-name">{npc.name}</span>
              <span class="npc-tag-role">{npc.role}</span>
            </div>
          {/each}
        </div>
      {/if}

      <div class="intro-actions">
        <button class="btn btn-primary btn-begin" onclick={beginOrigin}>
          Enter the Memory
        </button>
        <button class="btn-skip" onclick={skipOrigin}>
          Skip to Prologue
        </button>
      </div>
    </div>

  {:else if phase === 'playing'}
    <div class="play-content fade-in">
      <div class="play-header">
        <span class="origin-label-small">Origin Story</span>
        {#if screenplay}
          <span class="origin-title-small">{screenplay.origin_title}</span>
        {/if}
      </div>

      <div class="narrative-panel">
        <div class="narrative-text narrative-prose">
          {#each narrativeText.split('\n') as paragraph}
            {#if paragraph.trim()}
              <p>{paragraph}</p>
            {/if}
          {/each}
        </div>

        {#if isProcessing}
          <div class="processing-indicator">
            <span class="processing-dot"></span>
            <span class="processing-dot"></span>
            <span class="processing-dot"></span>
          </div>
        {/if}
      </div>

      {#if errorMessage}
        <p class="error">{errorMessage}</p>
      {/if}

      {#if !isProcessing && suggestedActions.length > 0}
        <div class="choices">
          {#each suggestedActions as action, i}
            <button
              class="choice-card stagger-enter"
              class:tone-paragon={action.tone === 'PARAGON'}
              class:tone-investigate={action.tone === 'INVESTIGATE'}
              class:tone-renegade={action.tone === 'RENEGADE'}
              onclick={() => handleChoice(action.label)}
            >
              {action.label}
            </button>
          {/each}
        </div>
      {/if}

      {#if !isProcessing}
        <div class="custom-input-row">
          <input
            type="text"
            bind:value={customInput}
            placeholder="Or describe your own action..."
            onkeydown={(e) => e.key === 'Enter' && handleCustomInput()}
          />
          <button class="btn btn-send" onclick={handleCustomInput} disabled={!customInput.trim()}>
            Act
          </button>
        </div>
      {/if}
    </div>

  {:else if phase === 'complete'}
    <div class="complete-content fade-in">
      <div class="complete-glow" aria-hidden="true"></div>
      <div class="origin-label">Memory Complete</div>

      <div class="narrative-panel">
        <div class="narrative-text narrative-prose">
          {#each narrativeText.split('\n') as paragraph}
            {#if paragraph.trim()}
              <p>{paragraph}</p>
            {/if}
          {/each}
        </div>
      </div>

      {#if screenplay}
        <p class="transition-text">{screenplay.resolution_hook}</p>
      {/if}

      <button class="btn btn-primary btn-continue" onclick={proceedToPrologue}>
        Continue to Prologue
      </button>
    </div>
  {/if}
</div>

<style>
  .origin-container {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    position: relative;
  }

  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    color: var(--text-muted);
  }

  .loading-spinner {
    width: 32px;
    height: 32px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Intro phase */
  .intro-content {
    max-width: 600px;
    width: 100%;
    text-align: center;
  }

  .origin-label {
    font-family: 'Rajdhani', 'Inter', sans-serif;
    font-size: 0.75rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }

  .origin-title {
    font-size: 2.2rem;
    color: var(--text-heading);
    margin: 0 0 1.5rem;
    line-height: 1.2;
  }

  .intro-setting {
    border-left: 2px solid var(--accent-glow);
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
    text-align: left;
    background: rgba(255, 255, 255, 0.02);
    border-radius: 0 6px 6px 0;
  }

  .intro-setting p {
    color: var(--text-secondary);
    line-height: 1.7;
    font-style: italic;
    margin: 0;
  }

  .intro-cast {
    display: flex;
    gap: 0.5rem;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 2rem;
  }

  .npc-tag {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border: 1px solid var(--border-subtle);
    border-radius: 20px;
    font-size: var(--font-small);
  }

  .npc-tag-name {
    color: var(--text-primary);
    font-weight: 600;
  }

  .npc-tag-role {
    color: var(--text-muted);
    font-size: 0.75rem;
    text-transform: capitalize;
  }

  .intro-actions {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }

  .btn-begin, .btn-continue {
    min-width: 220px;
    padding: 0.8rem 2rem;
    font-size: 1.05rem;
  }

  .btn-skip {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: var(--font-small);
    cursor: pointer;
    padding: 0.4rem 1rem;
    transition: color 0.15s;
    font-family: inherit;
  }

  .btn-skip:hover {
    color: var(--text-secondary);
  }

  /* Play phase */
  .play-content {
    max-width: 700px;
    width: 100%;
  }

  .play-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 1.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .origin-label-small {
    font-family: 'Rajdhani', 'Inter', sans-serif;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding: 2px 8px;
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
  }

  .origin-title-small {
    font-size: var(--font-body);
    color: var(--text-heading);
    font-weight: 600;
  }

  .narrative-panel {
    margin-bottom: 1.5rem;
  }

  .narrative-text p {
    margin-bottom: 0.8em;
  }

  .narrative-text p:last-child {
    margin-bottom: 0;
  }

  .processing-indicator {
    display: flex;
    gap: 6px;
    padding: 1rem 0;
    justify-content: center;
  }

  .processing-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent-primary);
    animation: dotPulse 1.2s ease-in-out infinite;
  }

  .processing-dot:nth-child(2) { animation-delay: 0.2s; }
  .processing-dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes dotPulse {
    0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
    40% { opacity: 1; transform: scale(1.2); }
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 1rem;
  }

  .choice-card {
    text-align: left;
    padding: 12px 16px;
    border: 1px solid var(--border-panel);
    border-left: 3px solid var(--tone-neutral);
    background: var(--bg-panel);
    color: var(--text-primary);
    border-radius: var(--panel-radius);
    cursor: pointer;
    font-size: var(--font-body);
    font-family: inherit;
    transition: all 0.15s ease;
    line-height: 1.5;
  }

  .choice-card:hover {
    border-color: var(--choice-hover-border);
    filter: drop-shadow(var(--choice-hover-glow));
  }

  .choice-card.tone-paragon { border-left-color: var(--tone-paragon); }
  .choice-card.tone-investigate { border-left-color: var(--tone-investigate); }
  .choice-card.tone-renegade { border-left-color: var(--tone-renegade); }

  .custom-input-row {
    display: flex;
    gap: 8px;
  }

  .custom-input-row input {
    flex: 1;
  }

  .btn-send {
    padding: 0.5rem 1rem;
    font-family: 'Rajdhani', 'Inter', sans-serif;
    font-weight: 600;
    font-size: var(--font-body);
  }

  .btn-send:disabled {
    opacity: 0.4;
    cursor: default;
  }

  /* Complete phase */
  .complete-content {
    max-width: 600px;
    width: 100%;
    text-align: center;
    position: relative;
  }

  .complete-glow {
    position: absolute;
    top: -40px;
    left: 50%;
    width: 300px;
    height: 150px;
    transform: translateX(-50%);
    background: var(--accent-glow);
    filter: blur(80px);
    opacity: 0.3;
    pointer-events: none;
  }

  .complete-content .narrative-panel {
    text-align: left;
    position: relative;
  }

  .transition-text {
    color: var(--text-secondary);
    font-style: italic;
    margin: 1.5rem 0 2rem;
    line-height: 1.6;
  }

  .error {
    color: var(--accent-danger);
    font-size: var(--font-small);
    text-align: center;
    margin-bottom: 1rem;
  }

  .fade-in {
    animation: fadeIn 0.5s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @media (prefers-reduced-motion: reduce) {
    .loading-spinner,
    .processing-dot {
      animation: none;
    }
    .fade-in {
      animation: none;
    }
  }
</style>
