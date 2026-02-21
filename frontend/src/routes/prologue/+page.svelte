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
  let phase = $state<'loading' | 'crawl' | 'ready'>('loading');
  let crawlDone = $state(false);
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
      if (ws.prologue_screenplay) {
        screenplay = ws.prologue_screenplay as PrologueScreenplay;
      }
      if (!ws.prologue_mode) {
        goto('/play');
        return;
      }
      // Show cinematic crawl, then transition to briefing
      phase = 'crawl';
      setTimeout(() => {
        crawlDone = true;
        phase = 'ready';
      }, 6000);
    } catch {
      goto('/play');
    }
  });

  function enterGame() {
    goto('/play');
  }

  function skipToGame() {
    goto('/play');
  }
</script>

<div class="prologue-container">
  {#if phase === 'loading'}
    <div class="loading">
      <div class="loading-spinner"></div>
      <p>Loading your story...</p>
    </div>

  {:else if phase === 'crawl' && screenplay}
    <div class="crawl-container" role="status" aria-live="polite">
      <div class="crawl-text">
        <div class="crawl-chapter">Prologue</div>
        <h1 class="crawl-title">{screenplay.prologue_title}</h1>
        {#if screenplay.opening_narration}
          <p class="crawl-narration">{screenplay.opening_narration}</p>
        {/if}
      </div>
      <button class="skip-crawl" onclick={() => { phase = 'ready'; crawlDone = true; }}>
        Skip
      </button>
    </div>

  {:else if phase === 'ready' && screenplay}
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
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      </div>

      {#if errorMessage}
        <p class="error">{errorMessage}</p>
      {/if}

      <div class="prologue-actions">
        <button class="btn btn-primary btn-begin" onclick={enterGame}>
          Begin Your Story
        </button>
        <p class="prologue-hint">Your prologue will play out as the first scenes of the game.</p>
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

  /* Opening crawl */
  .crawl-container {
    width: 100%;
    max-width: 600px;
    text-align: center;
    animation: crawlFade 6s ease-in-out;
    position: relative;
  }

  .crawl-text {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .crawl-chapter {
    font-size: 0.8rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: rgba(232, 197, 106, 0.5);
  }

  .crawl-title {
    font-size: 2.5rem;
    color: #e8c56a;
    margin: 0;
    line-height: 1.2;
    animation: crawlTitleReveal 2s ease-out;
  }

  .crawl-narration {
    font-size: 1.1rem;
    color: rgba(240, 230, 200, 0.7);
    line-height: 1.8;
    font-style: italic;
    font-family: 'Noto Serif', serif;
    animation: crawlTextReveal 3s ease-out 1s both;
  }

  .skip-crawl {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    background: none;
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: rgba(240, 230, 200, 0.35);
    padding: 0.4rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.15s;
  }

  .skip-crawl:hover {
    color: rgba(240, 230, 200, 0.7);
    border-color: rgba(255, 255, 255, 0.3);
  }

  @keyframes crawlFade {
    0% { opacity: 0; transform: translateY(30px); }
    15% { opacity: 1; transform: translateY(0); }
    85% { opacity: 1; }
    100% { opacity: 1; }
  }

  @keyframes crawlTitleReveal {
    from { opacity: 0; transform: scale(0.9); }
    to { opacity: 1; transform: scale(1); }
  }

  @keyframes crawlTextReveal {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* Briefing content */
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

  .prologue-actions {
    display: flex;
    gap: 1rem;
    flex-direction: column;
    align-items: center;
  }

  .prologue-hint {
    font-size: 0.8rem;
    color: rgba(240, 230, 200, 0.35);
    text-align: center;
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

  .error {
    color: #e06060;
    font-size: 0.9rem;
    text-align: center;
  }
</style>
