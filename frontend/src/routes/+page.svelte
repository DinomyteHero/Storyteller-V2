<script lang="ts">
  import { goto } from '$app/navigation';
  import { ui } from '$lib/stores/ui';
  import { campaignId, playerId, lastTurnResponse } from '$lib/stores/game';
  import { THEME_NAMES } from '$lib/themes/tokens';
  import FirstRunWizard from '$lib/components/FirstRunWizard.svelte';
  import {
    getSavedCampaigns,
    getSavedCampaignMap,
    patchCampaignCache,
    removeCampaign,
    getLastPlayed,
    setLastPlayed,
    type SavedCampaign,
  } from '$lib/stores/campaigns';
  import { getState, getTranscript, listCampaigns } from '$lib/api/campaigns';
  import { transcript } from '$lib/stores/game';
  import { ERA_LABELS } from '$lib/utils/constants';
  import type { CampaignSummary as ApiCampaignSummary } from '$lib/api/types';

  let showSettings = $state(false);
  let showLoadModal = $state(false);
  let savedCampaigns = $state<SavedCampaign[]>([]);
  let loadingCampaignId = $state<string | null>(null);
  let loadingCampaignList = $state(false);
  let listingFromCacheOnly = $state(false);
  let loadError = $state('');
  let lastPlayedCampaign = $state<SavedCampaign | null>(getLastPlayed());
  let resumingLast = $state(false);
  let showFirstRun = $state(false);

  // Check if this is the first time the user visits
  try {
    const done = localStorage.getItem('storyteller-first-run-complete');
    if (!done) {
      showFirstRun = true;
    }
  } catch {
    // localStorage unavailable
  }

  function handleNewCampaign() {
    goto('/create');
  }

  function _mergeCampaignFromApi(item: ApiCampaignSummary, localMap: Record<string, SavedCampaign>): SavedCampaign {
    const cached = localMap[item.campaign_id];
    const now = new Date().toISOString();
    const merged: SavedCampaign = {
      campaignId: item.campaign_id,
      playerId: item.player_id ?? cached?.playerId ?? '',
      playerName: item.player_name ?? cached?.playerName ?? 'Unknown',
      era: (item.time_period ?? cached?.era ?? '').toUpperCase(),
      background: cached?.background ?? null,
      sagaId: item.saga_id ?? cached?.sagaId ?? null,
      sagaChapter: item.saga_chapter ?? cached?.sagaChapter ?? null,
      sagaTitle: cached?.sagaTitle ?? null,
      createdAt: cached?.createdAt ?? now,
      lastPlayedAt: item.updated_at ?? cached?.lastPlayedAt ?? now,
      turnCount: Number(item.current_turn ?? cached?.turnCount ?? 0),
    };
    patchCampaignCache(merged);
    return merged;
  }

  async function handleLoadCampaign() {
    loadingCampaignList = true;
    listingFromCacheOnly = false;
    loadError = '';
    try {
      const localMap = getSavedCampaignMap();
      const server = await listCampaigns(100, 0);
      savedCampaigns = (server.items ?? []).map((item) => _mergeCampaignFromApi(item, localMap));
    } catch (e) {
      listingFromCacheOnly = true;
      savedCampaigns = getSavedCampaigns();
      loadError = `Backend campaign list unavailable. Showing local cache only. ${e instanceof Error ? e.message : ''}`.trim();
    } finally {
      loadingCampaignList = false;
    }
    showLoadModal = true;
  }

  async function resumeCampaign(campaign: SavedCampaign) {
    if (!campaign.playerId) {
      loadError = 'This campaign is missing a player id and cannot be resumed.';
      return;
    }
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

      setLastPlayed(campaign.campaignId);
      showLoadModal = false;
      goto('/play?resumed=1');
    } catch (e) {
      loadError = e instanceof Error ? e.message : String(e);
    } finally {
      loadingCampaignId = null;
      resumingLast = false;
    }
  }

  async function handleContinueStory() {
    if (!lastPlayedCampaign) return;
    resumingLast = true;
    await resumeCampaign(lastPlayedCampaign);
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

  function campaignGroups(): Array<{ key: string; label: string; items: SavedCampaign[] }> {
    const groups = new Map<string, { key: string; label: string; items: SavedCampaign[] }>();
    for (const campaign of savedCampaigns) {
      const sagaKey = campaign.sagaId ? `story:${campaign.sagaId}` : 'standalone';
      const label = campaign.sagaTitle || (campaign.sagaId ? `Story ${campaign.sagaId.slice(0, 8)}` : 'Standalone Campaigns');
      if (!groups.has(sagaKey)) {
        groups.set(sagaKey, { key: sagaKey, label, items: [] });
      }
      groups.get(sagaKey)!.items.push(campaign);
    }
    return Array.from(groups.values());
  }
</script>

<div class="menu-container" role="main">
  <!-- Ambient atmosphere -->
  <div class="atmosphere" aria-hidden="true">
    <div class="atmo-orb atmo-orb-1"></div>
    <div class="atmo-orb atmo-orb-2"></div>
    <div class="atmo-orb atmo-orb-3"></div>
    <div class="atmo-particles">
      {#each Array(12) as _, i}
        <div class="particle" style="--i:{i};"></div>
      {/each}
    </div>
  </div>

  <div class="menu-content">
    <!-- Title block -->
    <div class="title-block">
      <div class="title-glow" aria-hidden="true"></div>
      <h1 class="game-title">Storyteller AI</h1>
      <p class="subtitle">An Interactive Narrative Adventure</p>
    </div>

    <!-- Menu buttons -->
    <div class="menu-buttons">
      {#if lastPlayedCampaign}
        <button
          class="btn btn-primary menu-btn press-scale continue-btn"
          disabled={resumingLast}
          onclick={handleContinueStory}
        >
          {resumingLast ? 'Loading...' : 'Continue Story'}
        </button>
        <div class="continue-card">
          <span class="continue-name">{lastPlayedCampaign.playerName}</span>
          <span class="continue-sep">&middot;</span>
          <span class="continue-era">{ERA_LABELS[lastPlayedCampaign.era] ?? lastPlayedCampaign.era}</span>
          {#if lastPlayedCampaign.turnCount > 0}
            <span class="continue-sep">&middot;</span>
            <span class="continue-turns">{lastPlayedCampaign.turnCount} turns</span>
          {/if}
        </div>
      {/if}
      <button class="btn btn-primary menu-btn press-scale" onclick={handleNewCampaign}>
        New Story
      </button>
      <button class="btn menu-btn press-scale" onclick={handleLoadCampaign}>
        Load Campaign
      </button>
      <button class="btn menu-btn press-scale" onclick={() => goto('/library')}>
        Browse Universes
      </button>
      <button class="btn menu-btn press-scale" onclick={() => goto('/settings')}>
        Settings
      </button>
    </div>

    <!-- Version -->
    <p class="version-tag">v2.16 - Setting-Agnostic Interactive Fiction</p>
  </div>
</div>

<!-- Load Campaign modal -->
{#if showLoadModal}
  <div
    class="modal-overlay"
    onclick={(e) => e.currentTarget === e.target && (showLoadModal = false)}
    onkeydown={(e) => e.key === 'Escape' && (showLoadModal = false)}
    role="dialog"
    aria-modal="true"
    aria-label="Load Campaign"
    tabindex="0"
  >
    <div class="modal-content load-modal" role="document">
      <h2>Load Campaign</h2>

      {#if loadError}
        <div class="error-banner" role="alert">{loadError}</div>
      {/if}

      {#if loadingCampaignList}
        <div class="skeleton-list" aria-label="Loading campaigns">
          {#each Array(3) as _}
            <div class="skeleton-card">
              <div class="skeleton-line skeleton-name"></div>
              <div class="skeleton-line skeleton-detail"></div>
              <div class="skeleton-line skeleton-meta"></div>
            </div>
          {/each}
        </div>
      {:else if savedCampaigns.length === 0}
        <p class="empty-state">No saved campaigns found. Start a new campaign first!</p>
      {:else}
        <div class="campaign-list">
          {#each campaignGroups() as group}
            <div class="campaign-group">
              <h3 class="campaign-group-title">{group.label}</h3>
              {#each group.items as campaign}
                <div class="campaign-entry card" class:loading={loadingCampaignId === campaign.campaignId}>
                  <div class="campaign-info">
                    <div class="campaign-name">
                      {campaign.playerName}
                      {#if campaign.sagaChapter}
                        <span class="campaign-chapter">Chapter {campaign.sagaChapter}</span>
                      {/if}
                    </div>
                    <div class="campaign-details">
                      <span class="campaign-era">{ERA_LABELS[campaign.era] ?? campaign.era}</span>
                      {#if campaign.background}
                        <span class="campaign-bg">- {campaign.background}</span>
                      {/if}
                    </div>
                    <div class="campaign-meta">
                      <span>{campaign.turnCount} {campaign.turnCount === 1 ? 'turn' : 'turns'}</span>
                      <span>-</span>
                      <span>{formatDate(campaign.lastPlayedAt)}</span>
                    </div>
                  </div>
                  <div class="campaign-actions">
                    <button
                      class="btn btn-primary campaign-resume press-scale"
                      disabled={loadingCampaignId !== null || !campaign.playerId}
                      onclick={() => resumeCampaign(campaign)}
                    >
                      {loadingCampaignId === campaign.campaignId ? 'Loading...' : 'Resume'}
                    </button>
                    {#if listingFromCacheOnly}
                      <button
                        class="btn campaign-delete press-scale"
                        disabled={loadingCampaignId !== null}
                        onclick={() => deleteCampaign(campaign.campaignId)}
                        title="Remove from local cache"
                        aria-label="Remove {campaign.playerName} from local cache"
                      >X</button>
                    {/if}
                  </div>
                </div>
              {/each}
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
    onclick={(e) => e.currentTarget === e.target && (showSettings = false)}
    onkeydown={(e) => e.key === 'Escape' && (showSettings = false)}
    role="dialog"
    aria-modal="true"
    aria-label="Settings"
    tabindex="0"
  >
    <div class="modal-content" role="document">
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

<!-- First-run setup wizard -->
{#if showFirstRun}
  <FirstRunWizard ondismiss={() => showFirstRun = false} />
{/if}

<style>
  .menu-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    position: relative;
    overflow: hidden;
  }

  /* === Ambient atmosphere === */
  .atmosphere {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
  }

  .atmo-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0;
    animation: orbFloat 12s ease-in-out infinite;
  }

  .atmo-orb-1 {
    width: 300px;
    height: 300px;
    background: var(--accent-glow);
    top: -80px;
    left: 15%;
    animation-delay: 0s;
  }

  .atmo-orb-2 {
    width: 200px;
    height: 200px;
    background: var(--accent-glow);
    bottom: 10%;
    right: 10%;
    animation-delay: -4s;
  }

  .atmo-orb-3 {
    width: 250px;
    height: 250px;
    background: var(--accent-glow);
    top: 40%;
    left: 60%;
    animation-delay: -8s;
  }

  @keyframes orbFloat {
    0%, 100% { opacity: 0.15; transform: translate(0, 0) scale(1); }
    25% { opacity: 0.25; transform: translate(20px, -15px) scale(1.05); }
    50% { opacity: 0.18; transform: translate(-10px, 10px) scale(0.95); }
    75% { opacity: 0.22; transform: translate(15px, 5px) scale(1.02); }
  }

  .atmo-particles {
    position: absolute;
    inset: 0;
  }

  .particle {
    position: absolute;
    width: 2px;
    height: 2px;
    background: var(--accent-primary);
    border-radius: 50%;
    opacity: 0;
    animation: particleDrift 8s ease-in-out infinite;
    animation-delay: calc(var(--i) * 0.6s);
    left: calc(8% + var(--i) * 7.5%);
    top: calc(20% + sin(var(--i)) * 30%);
  }

  .particle:nth-child(odd) {
    top: 65%;
  }

  .particle:nth-child(3n) {
    width: 3px;
    height: 3px;
  }

  @keyframes particleDrift {
    0%, 100% { opacity: 0; transform: translateY(0); }
    20% { opacity: 0.4; }
    50% { opacity: 0.6; transform: translateY(-40px); }
    80% { opacity: 0.3; }
  }

  .menu-content {
    text-align: center;
    max-width: 420px;
    width: 100%;
    position: relative;
    z-index: 1;
  }

  .title-block {
    margin-bottom: 3rem;
    position: relative;
  }

  .title-glow {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 320px;
    height: 100px;
    transform: translate(-50%, -50%);
    background: var(--accent-glow);
    filter: blur(60px);
    opacity: 0.4;
    animation: titlePulse 4s ease-in-out infinite;
  }

  @keyframes titlePulse {
    0%, 100% { opacity: 0.3; transform: translate(-50%, -50%) scale(1); }
    50% { opacity: 0.5; transform: translate(-50%, -50%) scale(1.1); }
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
    position: relative;
  }

  .subtitle {
    font-size: var(--font-body);
    color: var(--text-secondary);
    font-style: italic;
    letter-spacing: 0.5px;
    position: relative;
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

  .continue-btn {
    box-shadow: 0 0 16px var(--accent-glow);
  }

  .continue-card {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: -6px;
    margin-bottom: 4px;
    flex-wrap: wrap;
  }

  .continue-name {
    color: var(--text-secondary);
    font-weight: 500;
  }

  .continue-sep {
    opacity: 0.4;
  }

  .continue-era {
    color: var(--text-muted);
  }

  .continue-turns {
    color: var(--text-muted);
    font-size: var(--font-small);
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
    gap: 14px;
    margin-top: 16px;
    max-height: 50vh;
    overflow-y: auto;
  }
  .campaign-group {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .campaign-group-title {
    margin: 0;
    font-size: var(--font-small);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
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
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .campaign-chapter {
    font-size: 0.72rem;
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    padding: 1px 6px;
    border-radius: 999px;
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

  /* === Skeleton loaders === */
  .skeleton-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 16px;
  }

  .skeleton-card {
    padding: 14px 16px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--panel-radius);
    background: var(--bg-panel);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .skeleton-line {
    border-radius: 4px;
    background: linear-gradient(
      90deg,
      var(--border-subtle) 25%,
      rgba(255, 255, 255, 0.06) 50%,
      var(--border-subtle) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  .skeleton-name {
    width: 45%;
    height: 16px;
  }

  .skeleton-detail {
    width: 65%;
    height: 12px;
  }

  .skeleton-meta {
    width: 35%;
    height: 10px;
  }

  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Respect reduced motion */
  @media (prefers-reduced-motion: reduce) {
    .atmo-orb,
    .particle,
    .title-glow {
      animation: none;
      opacity: 0.2;
    }
    .skeleton-line {
      animation: none;
    }
  }
</style>
