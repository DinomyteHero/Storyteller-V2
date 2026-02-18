<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiFetch } from '$lib/api/client';
  import { campaignId, playerId } from '$lib/stores/game';

  interface PrologueScreenplay {
    prologue_title: string;
    opening_narration?: string;
    inciting_moment: string;
    departure_trigger: string;
    tone: string;
    npc_cast: Array<{ name: string; role: string; motivation?: string }>;
  }

  let screenplay = $state<PrologueScreenplay | null>(null);
  let isCompleting = $state(false);
  let errorMessage = $state('');
  let prologueCompleted = $state(false);

  onMount(async () => {
    const cid = $campaignId;
    if (!cid) {
      goto('/');
      return;
    }
    // Fetch world state to get prologue screenplay
    try {
      const resp = await apiFetch<{ campaign_id: string; world_state: Record<string, unknown> }>(
        `/v2/campaigns/${cid}/world_state`
      );
      const ws = resp.world_state ?? {};
      if (ws.prologue_screenplay) {
        screenplay = ws.prologue_screenplay as PrologueScreenplay;
      }
      if (!ws.prologue_mode) {
        // Prologue already done — redirect to play
        goto('/play');
        return;
      }
    } catch {
      // If we can't load world state, skip prologue
      goto('/play');
    }
  });

  async function completePrologue() {
    const cid = $campaignId;
    if (!cid || isCompleting) return;
    isCompleting = true;
    errorMessage = '';
    try {
      await apiFetch(`/v2/campaigns/${cid}/prologue/complete`, {
        method: 'POST',
        body: JSON.stringify({ player_id: $playerId }),
      });
      prologueCompleted = true;
      // Brief pause to let the "completed" state show before redirecting
      setTimeout(() => goto('/play'), 800);
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : 'Failed to complete prologue';
      isCompleting = false;
    }
  }

  async function skipPrologue() {
    await completePrologue();
  }
</script>

<div class="prologue-container">
  {#if !screenplay}
    <div class="loading">
      <div class="loading-spinner"></div>
      <p>Loading your story...</p>
    </div>
  {:else}
    <div class="prologue-content fade-in">
      <div class="chapter-label">Chapter: Prologue</div>
      <h1 class="prologue-title">{screenplay.prologue_title}</h1>

      {#if screenplay.opening_narration}
        <div class="opening-narration">
          <p>{screenplay.opening_narration}</p>
        </div>
      {/if}

      <div class="story-details">
        <div class="detail-block">
          <h3>The Situation</h3>
          <p>{screenplay.inciting_moment}</p>
        </div>

        {#if screenplay.npc_cast && screenplay.npc_cast.length > 0}
          <div class="detail-block">
            <h3>Characters Present</h3>
            <ul class="npc-list">
              {#each screenplay.npc_cast as npc}
                <li>
                  <span class="npc-name">{npc.name}</span>
                  <span class="npc-role">({npc.role})</span>
                  {#if npc.motivation}
                    <span class="npc-motivation">— {npc.motivation}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          </div>
        {/if}

        <div class="detail-block departure">
          <h3>What Moves You Forward</h3>
          <p>{screenplay.departure_trigger}</p>
        </div>
      </div>

      {#if errorMessage}
        <p class="error">{errorMessage}</p>
      {/if}

      <div class="prologue-actions">
        {#if prologueCompleted}
          <p class="completed-msg">Prologue complete. Beginning your adventure...</p>
        {:else}
          <button
            class="btn btn-primary btn-begin"
            disabled={isCompleting}
            onclick={completePrologue}
          >
            {isCompleting ? 'Starting...' : 'Begin Your Story'}
          </button>
          <button
            class="btn btn-ghost"
            disabled={isCompleting}
            onclick={skipPrologue}
          >
            Skip Prologue
          </button>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .prologue-container {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0a0a0f;
    padding: 2rem;
  }

  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    color: rgba(240, 230, 200, 0.5);
  }

  .loading-spinner {
    width: 32px;
    height: 32px;
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-top-color: #e8c56a;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .prologue-content {
    max-width: 680px;
    width: 100%;
  }

  .fade-in {
    animation: fadeIn 0.6s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .chapter-label {
    font-size: 0.75rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: rgba(232, 197, 106, 0.6);
    margin-bottom: 0.5rem;
  }

  .prologue-title {
    font-size: 2rem;
    color: #f0e6c8;
    margin: 0 0 1.5rem;
    line-height: 1.2;
  }

  .opening-narration {
    border-left: 2px solid rgba(232, 197, 106, 0.3);
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
    background: rgba(232, 197, 106, 0.04);
    border-radius: 0 4px 4px 0;
  }

  .opening-narration p {
    color: rgba(240, 230, 200, 0.8);
    font-style: italic;
    line-height: 1.7;
    margin: 0;
  }

  .story-details {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    margin-bottom: 2rem;
  }

  .detail-block {
    padding: 1rem;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
  }

  .detail-block h3 {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: rgba(232, 197, 106, 0.7);
    margin: 0 0 0.5rem;
  }

  .detail-block p {
    color: rgba(240, 230, 200, 0.8);
    line-height: 1.6;
    margin: 0;
  }

  .detail-block.departure {
    border-color: rgba(232, 197, 106, 0.2);
  }

  .npc-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .npc-list li {
    color: rgba(240, 230, 200, 0.75);
    font-size: 0.9rem;
  }

  .npc-name {
    font-weight: 600;
    color: #f0e6c8;
  }

  .npc-role {
    color: rgba(240, 230, 200, 0.5);
    font-size: 0.85rem;
    margin-left: 0.35rem;
  }

  .npc-motivation {
    color: rgba(240, 230, 200, 0.45);
    font-size: 0.82rem;
    font-style: italic;
    margin-left: 0.35rem;
  }

  .prologue-actions {
    display: flex;
    gap: 1rem;
    flex-direction: column;
    align-items: center;
  }

  .btn {
    padding: 0.6rem 1.4rem;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    cursor: pointer;
    font-size: 0.95rem;
    transition: all 0.15s;
    background: transparent;
    color: rgba(240, 230, 200, 0.85);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: #e8c56a;
    border-color: #e8c56a;
    color: #1a1208;
    font-weight: 600;
  }

  .btn-primary:hover:not(:disabled) {
    background: #f0d07a;
  }

  .btn-begin {
    min-width: 200px;
    padding: 0.8rem 2rem;
    font-size: 1.05rem;
  }

  .btn-ghost {
    border-color: rgba(255, 255, 255, 0.1);
    font-size: 0.85rem;
    color: rgba(240, 230, 200, 0.45);
  }

  .btn-ghost:hover:not(:disabled) {
    color: rgba(240, 230, 200, 0.7);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .completed-msg {
    color: #a0e080;
    font-size: 0.95rem;
  }

  .error {
    color: #e06060;
    font-size: 0.9rem;
    text-align: center;
  }
</style>
