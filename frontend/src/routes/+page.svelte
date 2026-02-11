<script lang="ts">
  import { goto } from '$app/navigation';
  import { ui } from '$lib/stores/ui';
  import { campaignId, playerId, lastTurnResponse } from '$lib/stores/game';
  import { THEME_NAMES } from '$lib/themes/tokens';
  import { getSavedCampaigns, removeCampaign, type SavedCampaign } from '$lib/stores/campaigns';
  import { getState, getTranscript } from '$lib/api/campaigns';
  import { transcript } from '$lib/stores/game';
  import { ERA_LABELS } from '$lib/utils/constants';

  let showSettings = $state(false);
  let showLoadModal = $state(false);
  let savedCampaigns = $state<SavedCampaign[]>([]);
  let loadingCampaignId = $state<string | null>(null);
  let loadError = $state('');

  function handleNewCampaign() {
    goto('/create');
  }

  function handleLoadCampaign() {
    savedCampaigns = getSavedCampaigns();
    loadError = '';
    showLoadModal = true;
  }

  async function resumeCampaign(campaign: SavedCampaign) {
    loadingCampaignId = campaign.campaignId;
    loadError = '';

    try {
      // Load the latest state from the backend
      const state = await getState(campaign.campaignId, campaign.playerId) as Record<string, any>;

      // Set the game stores
      campaignId.set(campaign.campaignId);
      playerId.set(campaign.playerId);

      // Build a TurnResponse-like object from the state
      const turnResponse = {
        narrated_text: state.last_narrated_text ?? 'Welcome back to your adventure...',
        suggested_actions: state.suggested_actions ?? [],
        player_sheet: state.player ?? null,
        inventory: state.inventory ?? [],
        quest_log: state.quest_log ?? {},
        world_time_minutes: state.campaign?.world_state_json?.world_time_minutes ?? null,
        party_status: state.party ?? null,
        faction_reputation: state.faction_reputation ?? state.campaign?.world_state_json?.faction_reputation ?? null,
        news_feed: state.news_feed ?? null,
        warnings: state.warnings ?? [],
      };
      lastTurnResponse.set(turnResponse as any);

      // Try to load the transcript
      try {
        const transcriptResult = await getTranscript(campaign.campaignId);
        transcript.set(transcriptResult.turns ?? []);
      } catch {
        // Non-critical
      }

      showLoadModal = false;
      goto('/play');
    } catch (e) {
      loadError = e instanceof Error ? e.message : String(e);
    } finally {
      loadingCampaignId = null;
    }
  }

  function deleteCampaign(campaignId: string) {
    removeCampaign(campaignId);
    savedCampaigns = getSavedCampaigns();
  }

  function formatDate(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
        + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch {
      return iso;
    }
  }
</script>

<div class="menu-container" role="main">
  <div class="menu-content">
    <!-- Title block -->
    <div class="title-block">
      <h1 class="game-title">Storyteller AI</h1>
      <p class="subtitle">An Interactive Star Wars Narrative</p>
    </div>

    <!-- Menu buttons -->
    <div class="menu-buttons">
      <button class="btn btn-primary menu-btn press-scale" onclick={handleNewCampaign}>
        New Campaign
      </button>
      <button class="btn menu-btn press-scale" onclick={handleLoadCampaign}>
        Load Campaign
      </button>
      <button class="btn menu-btn press-scale" onclick={() => showSettings = true}>
        Settings
      </button>
    </div>

    <!-- Version -->
    <p class="version-tag">v2.16 — KOTOR-Style Interactive Fiction</p>
  </div>
</div>

<!-- Load Campaign modal -->
{#if showLoadModal}
  <div
    class="modal-overlay"
    onclick={() => showLoadModal = false}
    onkeydown={(e) => e.key === 'Escape' && (showLoadModal = false)}
    role="dialog"
    aria-modal="true"
    aria-label="Load Campaign"
    tabindex="0"
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="modal-content load-modal" onclick={(e) => e.stopPropagation()} role="document">
      <h2>Load Campaign</h2>

      {#if loadError}
        <div class="error-banner" role="alert">{loadError}</div>
      {/if}

      {#if savedCampaigns.length === 0}
        <p class="empty-state">No saved campaigns found. Start a new campaign first!</p>
      {:else}
        <div class="campaign-list">
          {#each savedCampaigns as campaign}
            <div class="campaign-entry card" class:loading={loadingCampaignId === campaign.campaignId}>
              <div class="campaign-info">
                <div class="campaign-name">{campaign.playerName}</div>
                <div class="campaign-details">
                  <span class="campaign-era">{ERA_LABELS[campaign.era] ?? campaign.era}</span>
                  {#if campaign.background}
                    <span class="campaign-bg">· {campaign.background}</span>
                  {/if}
                </div>
                <div class="campaign-meta">
                  <span>{campaign.turnCount} {campaign.turnCount === 1 ? 'turn' : 'turns'}</span>
                  <span>·</span>
                  <span>{formatDate(campaign.lastPlayedAt)}</span>
                </div>
              </div>
              <div class="campaign-actions">
                <button
                  class="btn btn-primary campaign-resume press-scale"
                  disabled={loadingCampaignId !== null}
                  onclick={() => resumeCampaign(campaign)}
                >
                  {loadingCampaignId === campaign.campaignId ? 'Loading...' : 'Resume'}
                </button>
                <button
                  class="btn campaign-delete press-scale"
                  disabled={loadingCampaignId !== null}
                  onclick={() => deleteCampaign(campaign.campaignId)}
                  title="Remove from list"
                  aria-label="Remove {campaign.playerName} from saved campaigns"
                >✕</button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <button class="btn" style="margin-top: 16px; width: 100%;" onclick={() => showLoadModal = false}>
        Close
      </button>
    </div>
  </div>
{/if}

<!-- Settings modal -->
{#if showSettings}
  <div
    class="modal-overlay"
    onclick={() => showSettings = false}
    onkeydown={(e) => e.key === 'Escape' && (showSettings = false)}
    role="dialog"
    aria-modal="true"
    aria-label="Settings"
    tabindex="0"
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="modal-content" onclick={(e) => e.stopPropagation()} role="document">
      <h2>Settings</h2>

      <div class="setting-group">
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

      <div class="setting-group">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.enableStreaming}
            onchange={() => ui.toggleStreaming()}
          />
          Enable SSE Streaming
        </label>
      </div>

      <div class="setting-group">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.enableTypewriter}
            onchange={() => ui.toggleTypewriter()}
          />
          Typewriter Effect
        </label>
      </div>

      <div class="setting-group">
        <label class="toggle-label">
          <input
            type="checkbox"
            checked={$ui.showDebug}
            onchange={() => ui.toggleDebug()}
          />
          Show Debug Info
        </label>
      </div>

      <button class="btn" style="margin-top: 16px; width: 100%;" onclick={() => showSettings = false}>
        Close
      </button>
    </div>
  </div>
{/if}

<style>
  .menu-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }

  .menu-content {
    text-align: center;
    max-width: 420px;
    width: 100%;
  }

  .title-block {
    margin-bottom: 3rem;
  }

  .game-title {
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 0.5rem;
    background: linear-gradient(135deg, var(--accent-primary), var(--text-heading));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .subtitle {
    font-size: var(--font-body);
    color: var(--text-secondary);
    font-style: italic;
    letter-spacing: 0.5px;
  }

  .menu-buttons {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 2rem;
  }

  .menu-btn {
    width: 100%;
    padding: 0.8rem 1.5rem;
    font-size: 1rem;
  }

  .version-tag {
    font-size: var(--font-small);
    color: var(--text-muted);
    letter-spacing: 0.3px;
  }

  /* Settings modal overrides */
  .setting-group {
    margin-top: 16px;
  }
  .setting-group label {
    display: block;
    font-size: var(--font-caption);
    color: var(--text-secondary);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
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

  /* Load Campaign modal */
  .load-modal {
    max-width: 560px;
  }
  .campaign-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 16px;
    max-height: 50vh;
    overflow-y: auto;
  }
  .campaign-entry {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    transition: all 0.2s ease;
  }
  .campaign-entry.loading {
    opacity: 0.7;
  }
  .campaign-info {
    flex: 1;
    min-width: 0;
  }
  .campaign-name {
    font-weight: 600;
    color: var(--text-heading);
    font-size: 1rem;
  }
  .campaign-details {
    font-size: var(--font-small);
    color: var(--text-secondary);
    margin-top: 2px;
  }
  .campaign-era {
    font-weight: 500;
  }
  .campaign-bg {
    color: var(--text-muted);
  }
  .campaign-meta {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 2px;
    display: flex;
    gap: 4px;
  }
  .campaign-actions {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-shrink: 0;
  }
  .campaign-resume {
    font-size: var(--font-small);
    padding: 6px 16px;
  }
  .campaign-delete {
    font-size: 0.8rem;
    padding: 4px 8px;
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    background: transparent;
  }
  .campaign-delete:hover {
    color: var(--accent-danger);
    border-color: var(--accent-danger);
  }

  .error-banner {
    padding: 10px;
    border-radius: 8px;
    background: rgba(255, 80, 60, 0.15);
    border: 1px solid var(--accent-danger);
    color: var(--accent-danger);
    font-size: var(--font-body);
    margin-top: 12px;
  }
  .empty-state {
    color: var(--text-muted);
    font-style: italic;
    font-size: var(--font-body);
    padding: 24px 0;
    text-align: center;
  }
</style>
