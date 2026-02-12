<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { runTurn, getTranscript, completeCampaign } from '$lib/api/campaigns';
  import { streamTurn } from '$lib/api/sse';
  import {
    campaignId, playerId, lastTurnResponse, transcript,
    suggestedActions, playerSheet, inventory,
    partyStatus, factionReputation, newsFeed, turnNumber,
    isGameActive, resetGame,
    dialogueTurn, sceneFrame, npcUtterance, playerResponses, questLog
  } from '$lib/stores/game';
  import {
    isStreaming, streamedText, streamError, showCursor,
    startStreaming, appendToken, finishStreaming, failStreaming, resetStreaming
  } from '$lib/stores/streaming';
  import { ui } from '$lib/stores/ui';
  import { humanizeLocation, formatTimeDelta, safeInt } from '$lib/utils/format';
  import { parseNarrative } from '$lib/utils/narrative';
  import { startTypewriter } from '$lib/utils/typewriter';
  import { announce, trapFocus } from '$lib/utils/a11y';
  import { TONE_ICONS, TONE_LABELS } from '$lib/utils/constants';
  import { touchCampaign } from '$lib/stores/campaigns';
  import type { ActionSuggestion, TurnResponse, TranscriptTurn } from '$lib/api/types';

  // V3.0: KOTOR-soul components
  import DialogueWheel from '$lib/components/choices/DialogueWheel.svelte';
  import NpcSpeech from '$lib/components/narrative/NpcSpeech.svelte';
  import SceneContext from '$lib/components/narrative/SceneContext.svelte';
  import CompanionSidebar from '$lib/components/game/CompanionSidebar.svelte';
  import AlignmentIndicator from '$lib/components/game/AlignmentIndicator.svelte';
  import QuestTracker from '$lib/components/game/QuestTracker.svelte';

  let isSendingTurn = $state(false);
  let narrativeEl: HTMLDivElement | undefined = $state();
  let drawerEl: HTMLElement | undefined = $state();
  let showPreviously = $state(false);
  let isCompleting = $state(false);

  // V3.2: Detect campaign conclusion readiness from warnings
  let conclusionReady = $derived(
    ($lastTurnResponse?.warnings ?? []).some(w => w.includes('[CONCLUSION_READY]'))
  );

  // Typewriter state
  let typewriterRevealLength = $state(0);
  let typewriterActive = $state(false);
  let typewriterCancel: (() => void) | null = null;

  // Choice card entrance key — incremented to re-trigger stagger
  let choiceAnimKey = $state(0);

  // Focus trap cleanup for drawer
  let cleanupTrap: (() => void) | null = null;

  // Redirect to menu if no active game
  onMount(() => {
    if (!$isGameActive) {
      goto('/');
      return;
    }
    // Ensure streaming state is clean when play page mounts
    // (guards against stale isStreaming=true from create page race condition)
    if ($isStreaming) {
      finishStreaming();
    }
    fetchTranscript();
    announce('Game loaded. Use number keys 1 through 4 to select choices.');
  });

  async function fetchTranscript() {
    const cId = $campaignId;
    if (!cId) return;
    try {
      const result = await getTranscript(cId);
      transcript.set(result.turns ?? []);
    } catch {
      // Non-critical — journal just won't have history
    }
  }

  // Derive HUD data from player sheet
  let hudData = $derived.by(() => {
    const ps = $playerSheet;
    const resp = $lastTurnResponse;
    if (!ps) return null;
    const yearLabel = resp?.canonical_year_label || 'Unknown';
    return {
      location: humanizeLocation(ps.location_id),
      planet: humanizeLocation(ps.planet_id),
      yearLabel,
      hp: safeInt(ps.hp_current, 10),
      credits: safeInt(ps.credits, 0),
      stress: safeInt(ps.psych_profile?.stress_level, 0),
      mood: ps.psych_profile?.current_mood ?? '',
    };
  });

  // Full narrative text (from streaming or last turn response)
  let fullNarrativeText = $derived.by(() => {
    if ($isStreaming || $streamedText) {
      return $streamedText || '';
    }
    return $lastTurnResponse?.narrated_text ?? '';
  });

  // Parse narrative paragraphs — typewriter slices the text if active
  let narrativeParagraphs = $derived.by(() => {
    const text = fullNarrativeText;
    if (!text) return [];

    if (typewriterActive && typewriterRevealLength < text.length) {
      // Show only the revealed portion
      return parseNarrative(text.slice(0, typewriterRevealLength));
    }
    return parseNarrative(text);
  });

  // Turn label
  let turnLabel = $derived.by(() => {
    const n = $turnNumber;
    if (n <= 2) return 'OPENING SCENE';
    return `TURN ${n - 1}`;
  });

  // Scene subtitle (location + planet)
  let sceneSubtitle = $derived.by(() => {
    if (!hudData) return '';
    const parts: string[] = [];
    if (hudData.planet && hudData.planet !== '—') parts.push(hudData.planet);
    if (hudData.location && hudData.location !== '—') parts.push(hudData.location);
    return parts.join(' — ');
  });

  // Is this the opening scene? (for mission briefing card)
  let isOpeningScene = $derived($turnNumber <= 2);

  // Previous turns (all except the current one)
  let previousTurns = $derived.by(() => {
    const t = $transcript;
    if (t.length <= 1) return [];
    return t.slice(0, -1);
  });

  // Choices ready? (not streaming, not sending, has choices, typewriter done)
  // V3.0: check both DialogueTurn player_responses (primary) and suggested_actions (fallback)
  let hasChoices = $derived($playerResponses.length > 0 || $suggestedActions.length > 0);
  let choicesReady = $derived(
    !$isStreaming && !isSendingTurn && hasChoices && !typewriterActive
  );

  // Auto-scroll narrative to bottom on new content
  $effect(() => {
    narrativeParagraphs;
    $streamedText;
    typewriterRevealLength;
    if (narrativeEl) {
      narrativeEl.scrollTop = narrativeEl.scrollHeight;
    }
  });

  // Trigger typewriter when lastTurnResponse changes (non-streaming mode)
  $effect(() => {
    const resp = $lastTurnResponse;
    if (!resp?.narrated_text || $isStreaming || $streamedText) return;

    if ($ui.enableTypewriter) {
      // Start typewriter
      typewriterCancel?.();
      typewriterActive = true;
      typewriterRevealLength = 0;

      const handle = startTypewriter(resp.narrated_text, {
        charsPerFrame: 2,
        sentencePause: 60,
        paragraphPause: 150,
        onProgress(len) {
          typewriterRevealLength = len;
        },
        onComplete() {
          typewriterActive = false;
          choiceAnimKey++;
          announce('Choices are now available. Press 1 through 4 to select.');
        },
      });
      typewriterCancel = handle.cancel;
    }
  });

  // Announce new turn narration for screen readers
  $effect(() => {
    const resp = $lastTurnResponse;
    if (resp?.narrated_text && !$isStreaming && !typewriterActive) {
      // Truncate for screen reader — they don't need the full novel
      const summary = resp.narrated_text.slice(0, 200);
      announce(summary + '... Choices available.');
    }
  });

  // Setup focus trap when drawer opens
  $effect(() => {
    if ($ui.drawerOpen && drawerEl) {
      cleanupTrap = trapFocus(drawerEl);
    } else {
      cleanupTrap?.();
      cleanupTrap = null;
    }
  });

  // Announce choice selection after turn completes
  $effect(() => {
    if (!$isStreaming && !isSendingTurn && $suggestedActions.length > 0 && !typewriterActive) {
      choiceAnimKey++; // Re-trigger stagger animation for new choices
    }
  });

  // Keyboard shortcuts
  function handleKeydown(e: KeyboardEvent) {
    // Skip if inside an input field
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT')) return;

    // 1-4 for choices — works with both DialogueTurn (primary) and ActionSuggestion (fallback)
    if (choicesReady) {
      const num = parseInt(e.key);
      const responses = $playerResponses;
      const actions = $suggestedActions;
      const maxChoices = responses.length > 0 ? responses.length : actions.length;
      if (num >= 1 && num <= maxChoices) {
        e.preventDefault();
        if (responses.length > 0) {
          const resp = responses[num - 1];
          handleChoiceInput(resp.display_text, resp.display_text);
        } else {
          const action = actions[num - 1];
          handleChoiceInput(action.intent_text || action.label, action.label);
        }
        return;
      }
    }

    // Space/Enter to skip typewriter
    if (typewriterActive && (e.key === ' ' || e.key === 'Enter')) {
      e.preventDefault();
      typewriterCancel?.();
      typewriterActive = false;
      typewriterRevealLength = fullNarrativeText.length;
      choiceAnimKey++;
      return;
    }

    // Escape to close drawer
    if (e.key === 'Escape') {
      if ($ui.drawerOpen) {
        ui.closeDrawer();
        // Return focus to hamburger
        const hamburger = document.querySelector<HTMLElement>('.hud-hamburger');
        hamburger?.focus();
      }
    }

    // i to toggle info drawer
    if (e.key === 'i' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      ui.toggleDrawer();
    }

    // j for journal shortcut
    if (e.key === 'j' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      ui.openDrawer('journal');
    }
  }

  /** V3.0: Unified choice handler — accepts string input from DialogueWheel or keyboard shortcuts. */
  async function handleChoiceInput(userInput: string, label: string) {
    if (isSendingTurn || $isStreaming) return;
    const cId = $campaignId;
    const pId = $playerId;
    if (!cId || !pId) return;

    isSendingTurn = true;
    resetStreaming();
    typewriterCancel?.();
    typewriterActive = false;

    announce(`Choosing: ${label}. Processing...`);

    try {
      const mode = $lastTurnResponse?.turn_contract?.mode ?? 'SIM';
      const useStreaming = $ui.enableStreaming && mode !== 'PASSAGE';
      if (useStreaming) {
        startStreaming();
        let finalResponse: TurnResponse | null = null;
        let streamErrored = false;
        for await (const event of streamTurn(cId, pId, userInput)) {
          if (event.type === 'token' && event.text) {
            appendToken(event.text);
          } else if (event.type === 'done') {
            finalResponse = event as unknown as TurnResponse;
            finishStreaming();
          } else if (event.type === 'error') {
            streamErrored = true;
            failStreaming(event.message ?? 'Stream error');
          }
        }
        if (finalResponse?.turn_contract) {
          lastTurnResponse.set(finalResponse);
          fetchTranscript();
        } else {
          // Retry deterministic non-stream endpoint if stream fails or ends without done payload
          const result = await runTurn(cId, pId, userInput);
          const msg = streamErrored
            ? 'Streaming interrupted. Recovered via non-stream request.'
            : 'Streaming ended early. Recovered via non-stream request.';
          result.warnings = [...(result.warnings ?? []), msg];
          lastTurnResponse.set(result);
          fetchTranscript();
          finishStreaming();
        }
      } else {
        const result = await runTurn(cId, pId, userInput);
        lastTurnResponse.set(result);
        fetchTranscript();
      }
      // Update campaign in local registry
      touchCampaign(cId, $turnNumber);
    } catch (e) {
      failStreaming(e instanceof Error ? e.message : String(e));
      announce('An error occurred while processing your choice.');
    } finally {
      isSendingTurn = false;
    }
  }

  function handleQuit() {
    typewriterCancel?.();
    resetGame();
    resetStreaming();
    goto('/');
  }

  function stressLabel(level: number): string {
    if (level >= 8) return 'Critical';
    if (level >= 6) return 'High';
    if (level >= 4) return 'Moderate';
    return 'Low';
  }

  // All drawer tabs including journal + quests
  const DRAWER_TABS = ['character', 'companions', 'factions', 'inventory', 'quests', 'comms', 'journal'] as const;
</script>

<svelte:window onkeydown={handleKeydown} />

{#if $isGameActive}
<div class="gameplay-layout" role="main">
  <!-- ======================== HUD BAR ======================== -->
  <header class="hud-bar card scanline" aria-label="Game status bar">
    <div class="hud-left">
      <button
        class="hud-hamburger btn press-scale"
        onclick={() => ui.toggleDrawer()}
        title="Toggle info panel (i)"
        aria-label="Toggle info panel"
        aria-expanded={$ui.drawerOpen}
      >
        ≡
      </button>
      {#if hudData}
        <div class="pill" role="status" aria-label="Location: {hudData.location}">
          <span class="label">LOC</span>
          <span class="value">{hudData.location}</span>
        </div>
        <div class="pill" aria-label="Year: {hudData.yearLabel}">
          <span class="label">YEAR</span>
          <span class="value">{hudData.yearLabel}</span>
        </div>
      {/if}
    </div>
    <div class="hud-right">
      {#if hudData}
        <div class="pill" aria-label="Hit points: {hudData.hp}">
          <span class="label">HP</span>
          <span class="value">{hudData.hp}</span>
        </div>
        <div class="pill" aria-label="Credits: {hudData.credits}">
          <span class="label">CR</span>
          <span class="value">{hudData.credits}</span>
        </div>
        <div
          class="pill stress-pill"
          class:stress-high={hudData.stress >= 7}
          class:stress-mid={hudData.stress >= 4 && hudData.stress < 7}
          aria-label="Stress: {hudData.stress} out of 10, {stressLabel(hudData.stress)}"
        >
          <span class="label">S</span>
          <span class="value">{hudData.stress}</span>
        </div>
        <!-- V3.0: Heat & Alert pills from SceneFrame pressure -->
        {#if $sceneFrame?.pressure?.heat && $sceneFrame.pressure.heat !== 'Low'}
          <div class="pill heat-pill heat-{$sceneFrame.pressure.heat.toLowerCase()}" aria-label="Heat: {$sceneFrame.pressure.heat}">
            <span class="label">🔥</span>
            <span class="value">{$sceneFrame.pressure.heat}</span>
          </div>
        {/if}
        {#if $sceneFrame?.pressure?.alert && $sceneFrame.pressure.alert !== 'Quiet'}
          <div class="pill alert-pill alert-{$sceneFrame.pressure.alert.toLowerCase()}" aria-label="Alert: {$sceneFrame.pressure.alert}">
            <span class="label">⚠</span>
            <span class="value">{$sceneFrame.pressure.alert}</span>
          </div>
        {/if}
      {/if}
      <button
        class="btn hud-quit press-scale"
        onclick={handleQuit}
        title="Quit to menu"
        aria-label="Quit to main menu"
      >✕</button>
    </div>
  </header>

  <!-- ======================== MAIN CONTENT ======================== -->
  <main class="gameplay-main" aria-label="Game narrative and choices">
    <!-- "Previously..." accordion -->
    {#if previousTurns.length > 0 && !isOpeningScene}
      <div class="previously-section">
        <button
          class="previously-toggle"
          onclick={() => showPreviously = !showPreviously}
          aria-expanded={showPreviously}
          aria-controls="previously-content"
        >
          <span class="previously-arrow" class:open={showPreviously}>▸</span>
          Previously... ({previousTurns.length} {previousTurns.length === 1 ? 'turn' : 'turns'})
        </button>
        {#if showPreviously}
          <div class="previously-content fade-in" id="previously-content" role="region" aria-label="Previous turns">
            {#each previousTurns as turn}
              <div class="previous-turn">
                <div class="prev-turn-label">Turn {turn.turn_number}</div>
                <div class="prev-turn-text">{turn.text.slice(0, 200)}{turn.text.length > 200 ? '...' : ''}</div>
                {#if turn.time_cost_minutes}
                  <div class="prev-turn-time">{formatTimeDelta(turn.time_cost_minutes) ?? ''}</div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Mission Briefing (opening scene only) -->
    {#if isOpeningScene && narrativeParagraphs.length > 0 && !$isStreaming && !typewriterActive}
      <div class="mission-briefing card fade-in" role="complementary" aria-label="Mission briefing">
        <div class="mission-header">
          <span class="mission-icon" aria-hidden="true">★</span>
          MISSION BRIEFING
        </div>
        <div class="mission-subtitle">
          {sceneSubtitle || 'A new adventure begins...'}
        </div>
      </div>
    {/if}

    <!-- Narrative viewport -->
    <div
      class="narrative-container"
      bind:this={narrativeEl}
      role="region"
      aria-label="Story narration"
      aria-live="off"
    >
      <div class="turn-header">
        <div class="turn-label">{turnLabel}</div>
        {#if sceneSubtitle}
          <div class="scene-subtitle">{sceneSubtitle}</div>
        {/if}
      </div>

      <!-- V3.0: Scene context bar (topic, pressure, scene type) -->
      <SceneContext sceneFrame={$sceneFrame} />

      <!-- V3.0: NPC utterance data feeds SuggestionRefiner context but is not rendered visually -->
      <!-- NPC dialogue is woven into narrative prose by the Narrator -->

      <div class="narrative-prose">
        {#each narrativeParagraphs as para, i}
          <p class={para.isDialogue ? 'dialogue' : ''} class:fade-in={!$isStreaming && !typewriterActive}>
            {para.text}
          </p>
        {/each}

        {#if $showCursor || typewriterActive}
          <span class="streaming-cursor" aria-hidden="true"></span>
        {/if}
      </div>

      <!-- Skip typewriter hint -->
      {#if typewriterActive}
        <div class="typewriter-skip fade-in" aria-live="polite">
          <button class="btn btn-skip press-scale" onclick={() => {
            typewriterCancel?.();
            typewriterActive = false;
            typewriterRevealLength = fullNarrativeText.length;
            choiceAnimKey++;
          }}>
            Skip <kbd>Space</kbd>
          </button>
        </div>
      {/if}

      {#if $streamError}
        <div class="error-banner" style="margin-top: 16px;" role="alert">
          {$streamError}
        </div>
      {/if}
    </div>

    <!-- V3.0: KOTOR-style dialogue choices (tone-filled, hover-reveal metadata) -->
    {#if choicesReady}
      <DialogueWheel
        playerResponses={$playerResponses}
        suggestedActions={$suggestedActions}
        {choiceAnimKey}
        onChoice={handleChoiceInput}
      />
    {/if}

    {#if isSendingTurn && !$isStreaming}
      <div class="loading-indicator fade-in" role="status" aria-label="Processing your action">
        <div class="loading-spinner" aria-hidden="true"></div>
        <span>Processing your action...</span>
      </div>
    {/if}

    <!-- Debug panel -->
    {#if $ui.showDebug && $lastTurnResponse?.debug}
      <details class="debug-panel card">
        <summary class="debug-header">Debug Info</summary>
        <pre class="debug-content">{JSON.stringify($lastTurnResponse.debug, null, 2)}</pre>
      </details>
    {/if}

    <!-- V3.2: Campaign conclusion banner -->
    {#if conclusionReady}
      <div class="conclusion-banner card" role="alert">
        <p class="conclusion-text">Your story is reaching its conclusion. Ready to end this chapter?</p>
        <button
          class="btn btn-primary conclusion-btn"
          disabled={isCompleting}
          onclick={async () => {
            if (!$campaignId) return;
            isCompleting = true;
            try {
              const result = await completeCampaign($campaignId);
              // Store completion data and navigate to summary page
              sessionStorage.setItem('completionData', JSON.stringify(result));
              sessionStorage.setItem('completionTurns', String($transcript.length));
              sessionStorage.setItem('completionFactions', JSON.stringify($factionReputation ?? {}));
              sessionStorage.setItem('completionParty', JSON.stringify($partyStatus ?? []));
              goto('/complete');
            } catch (e) {
              isCompleting = false;
            }
          }}
        >
          {isCompleting ? 'Completing...' : 'Complete Campaign'}
        </button>
      </div>
    {/if}

    {#if $ui.showDebug && $lastTurnResponse?.warnings && $lastTurnResponse.warnings.length > 0}
      <div class="debug-warnings card" role="status">
        <div class="section-header">Warnings</div>
        {#each $lastTurnResponse.warnings as warning}
          <div class="warning-item">{warning}</div>
        {/each}
      </div>
    {/if}
  </main>

  <!-- ======================== INFO DRAWER ======================== -->
  {#if $ui.drawerOpen}
    <!-- Backdrop -->
    <div
      class="drawer-backdrop"
      onclick={() => ui.closeDrawer()}
      onkeydown={(e) => e.key === 'Escape' && ui.closeDrawer()}
      role="button"
      tabindex="-1"
      aria-label="Close info panel"
    ></div>

    <aside
      class="info-drawer card"
      bind:this={drawerEl}
      aria-label="Game information panel"
    >
      <!-- Mobile drag handle -->
      <div class="drawer-handle" aria-hidden="true"><div class="handle-bar"></div></div>

      <div class="drawer-tabs" role="tablist" aria-label="Information tabs">
        {#each DRAWER_TABS as tab}
          <button
            class="drawer-tab"
            class:active={$ui.drawerTab === tab}
            onclick={() => ui.setDrawerTab(tab)}
            role="tab"
            aria-selected={$ui.drawerTab === tab}
            aria-controls="drawer-panel-{tab}"
            id="drawer-tab-{tab}"
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        {/each}
      </div>

      <div
        class="drawer-content"
        role="tabpanel"
        id="drawer-panel-{$ui.drawerTab}"
        aria-labelledby="drawer-tab-{$ui.drawerTab}"
      >
        <!-- CHARACTER TAB -->
        {#if $ui.drawerTab === 'character' && $playerSheet}
          <div class="section-header">Character Sheet</div>
          <div class="info-row"><span>Name</span><span>{$playerSheet.name}</span></div>
          <div class="info-row"><span>Gender</span><span>{$playerSheet.gender ?? '—'}</span></div>
          <div class="info-row"><span>Background</span><span>{$playerSheet.background ?? '—'}</span></div>
          <div class="info-row"><span>HP</span><span>{$playerSheet.hp_current}</span></div>
          <div class="info-row"><span>Credits</span><span>{$playerSheet.credits ?? 0}</span></div>
          {#if $playerSheet.stats}
            <div class="section-header" style="margin-top: 12px;">Stats</div>
            {#each Object.entries($playerSheet.stats) as [stat, val]}
              <div class="info-row"><span>{stat}</span><span>{val}</span></div>
            {/each}
          {/if}
          {#if $playerSheet.psych_profile}
            <div class="section-header" style="margin-top: 12px;">Mental State</div>
            <div class="info-row"><span>Mood</span><span>{$playerSheet.psych_profile.current_mood}</span></div>
            <div class="info-row">
              <span>Stress</span>
              <span class="stress-value" class:stress-high={$playerSheet.psych_profile.stress_level >= 7} class:stress-mid={$playerSheet.psych_profile.stress_level >= 4 && $playerSheet.psych_profile.stress_level < 7}>
                {$playerSheet.psych_profile.stress_level}/10
              </span>
            </div>
            {#if $playerSheet.psych_profile.active_trauma}
              <div class="info-row"><span>Trauma</span><span class="trauma-value">{$playerSheet.psych_profile.active_trauma}</span></div>
            {/if}
          {/if}

        <!-- COMPANIONS TAB (V2.20: influence/trust/respect/fear) -->
        {:else if $ui.drawerTab === 'companions' && $partyStatus}
          <div class="section-header">Companions</div>
          {#each $partyStatus as companion}
            <div class="companion-card-drawer">
              <div class="companion-name">{companion.name}</div>
              <div class="companion-details">
                <span class="affinity-hearts" aria-label="Affinity: {companion.affinity} out of 100">
                  {#each Array(5) as _, i}
                    <span class:filled={i < Math.round(companion.affinity / 20)} aria-hidden="true">♥</span>
                  {/each}
                </span>
                <span class="affinity-number">
                  {companion.affinity}
                  {#if companion.affinity_delta !== 0}
                    <span class:positive={companion.affinity_delta > 0} class:negative={companion.affinity_delta < 0}>
                      ({companion.affinity_delta > 0 ? '+' : ''}{companion.affinity_delta})
                    </span>
                  {/if}
                </span>
              </div>
              <div class="companion-loyalty">
                {#if companion.influence != null && companion.influence >= 70}
                  <span class="loyalty-badge loyal">LOYAL</span>
                {:else if companion.influence != null && companion.influence >= 30}
                  <span class="loyalty-badge trusted">TRUSTED</span>
                {:else if companion.influence != null && companion.influence > -10}
                  <span class="loyalty-badge ally">ALLY</span>
                {:else if companion.loyalty_progress >= 80}
                  <span class="loyalty-badge loyal">LOYAL</span>
                {:else if companion.loyalty_progress >= 40}
                  <span class="loyalty-badge trusted">TRUSTED</span>
                {:else}
                  <span class="loyalty-badge stranger">STRANGER</span>
                {/if}
                {#if companion.mood_tag}
                  <span class="companion-mood">{companion.mood_tag}</span>
                {/if}
              </div>
              <!-- V2.20: Influence/Trust/Respect/Fear meters -->
              {#if companion.influence != null}
                <div class="companion-meters">
                  <div class="meter-row">
                    <span class="meter-label">Influence</span>
                    <div class="meter-bar-container" role="meter" aria-label="Influence: {companion.influence}" aria-valuenow={companion.influence} aria-valuemin={-100} aria-valuemax={100}>
                      <div class="meter-center-line"></div>
                      <div
                        class="meter-bar"
                        class:positive-bar={companion.influence > 0}
                        class:negative-bar={companion.influence < 0}
                        style="width: {Math.min(Math.abs(companion.influence), 100) / 2}%; {companion.influence >= 0 ? 'left: 50%' : 'right: 50%'}"
                      ></div>
                    </div>
                    <span class="meter-value" class:positive={companion.influence > 0} class:negative={companion.influence < 0}>{companion.influence}</span>
                  </div>
                  {#if companion.trust != null}
                    <div class="meter-row mini">
                      <span class="meter-label">Trust</span>
                      <span class="meter-value">{companion.trust}</span>
                    </div>
                  {/if}
                  {#if companion.respect != null}
                    <div class="meter-row mini">
                      <span class="meter-label">Respect</span>
                      <span class="meter-value">{companion.respect}</span>
                    </div>
                  {/if}
                  {#if companion.fear != null}
                    <div class="meter-row mini">
                      <span class="meter-label">Fear</span>
                      <span class="meter-value">{companion.fear}</span>
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
          {#if $partyStatus.length === 0}
            <p class="empty-state">No companions yet.</p>
          {/if}

        <!-- FACTIONS TAB (V3.0: tier labels) -->
        {:else if $ui.drawerTab === 'factions' && $factionReputation}
          <div class="section-header">Faction Reputation</div>
          {#each Object.entries($factionReputation) as [faction, rep]}
            {@const repNum = Number(rep)}
            {@const tier = repNum >= 51 ? 'ALLIED' : repNum >= 21 ? 'FRIENDLY' : repNum > -21 ? 'NEUTRAL' : repNum > -51 ? 'UNFRIENDLY' : 'HOSTILE'}
            {@const tierClass = tier.toLowerCase()}
            <div class="faction-entry">
              <div class="info-row faction-row">
                <span class="faction-name">{faction}</span>
                <span class="faction-tier {tierClass}">{tier}</span>
              </div>
              <div class="faction-bar-row">
                <div class="faction-bar-container" role="meter" aria-label="{faction} reputation: {rep}" aria-valuenow={repNum} aria-valuemin={-100} aria-valuemax={100}>
                  <div
                    class="faction-bar"
                    class:positive-bar={repNum > 0}
                    class:negative-bar={repNum < 0}
                    style="width: {Math.min(Math.abs(repNum), 100)}%"
                  ></div>
                </div>
                <span class="faction-value" class:positive={repNum > 0} class:negative={repNum < 0}>
                  {repNum > 0 ? '+' : ''}{rep}
                </span>
              </div>
            </div>
          {/each}

        <!-- INVENTORY TAB -->
        {:else if $ui.drawerTab === 'inventory'}
          <div class="section-header">Inventory</div>
          {#if $inventory.length > 0}
            {#each $inventory as item}
              <div class="info-row">
                <span>{item.item_name}</span>
                <span class="item-qty">x{item.quantity}</span>
              </div>
            {/each}
          {:else}
            <p class="empty-state">No items yet.</p>
          {/if}

        <!-- QUESTS TAB -->
        {:else if $ui.drawerTab === 'quests'}
          <div class="section-header">Quest Log</div>
          {#if Object.keys($questLog).length > 0}
            {#each Object.entries($questLog) as [questId, quest]}
              {@const q = quest as Record<string, unknown>}
              {@const status = String(q.status || 'active')}
              {@const stagesCompleted = (q.stages_completed as string[]) || []}
              {@const stageIdx = Number(q.current_stage_idx || 0)}
              <div class="quest-entry quest-{status}">
                <div class="quest-header">
                  <span class="quest-title">{questId.replace(/_/g, ' ').replace(/^quest /, '')}</span>
                  <span class="quest-status-badge status-{status}">{status}</span>
                </div>
                {#if stagesCompleted.length > 0}
                  <div class="quest-progress">
                    Stage {stageIdx + 1} ({stagesCompleted.length} completed)
                  </div>
                {/if}
              </div>
            {/each}
          {:else}
            <p class="empty-state">No active quests.</p>
          {/if}

        <!-- COMMS TAB -->
        {:else if $ui.drawerTab === 'comms'}
          <div class="section-header">Comms / Intel</div>
          {#if $newsFeed && $newsFeed.length > 0}
            {#each $newsFeed as item}
              <div class="news-item">
                <div class="news-header">
                  <span class="news-source">[{item.source_tag}]</span>
                  {#if item.urgency}
                    <span class="news-urgency urgency-{item.urgency.toLowerCase()}">{item.urgency}</span>
                  {/if}
                </div>
                <div class="news-headline">{item.headline}</div>
                <div class="news-body">{item.body}</div>
                {#if item.related_factions.length > 0}
                  <div class="news-factions">
                    {#each item.related_factions as f}
                      <span class="news-faction-tag">{f}</span>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          {:else}
            <p class="empty-state">No intel available.</p>
          {/if}

        <!-- JOURNAL TAB -->
        {:else if $ui.drawerTab === 'journal'}
          <div class="section-header">Journal</div>
          {#if $transcript.length > 0}
            {#each $transcript as turn}
              <div class="journal-entry">
                <div class="journal-turn-header">
                  <span class="journal-turn-num">
                    {turn.turn_number <= 2 ? 'Opening' : `Turn ${turn.turn_number - 1}`}
                  </span>
                  {#if turn.time_cost_minutes}
                    <span class="journal-time">{formatTimeDelta(turn.time_cost_minutes)}</span>
                  {/if}
                </div>
                <div class="journal-text">{turn.text.slice(0, 300)}{turn.text.length > 300 ? '...' : ''}</div>
              </div>
            {/each}
          {:else}
            <p class="empty-state">No journal entries yet.</p>
          {/if}

        {:else}
          <p class="empty-state">No data available.</p>
        {/if}
      </div>
    </aside>
  {/if}

  <!-- V3.0: KOTOR-soul overlays -->
  <CompanionSidebar />
  <QuestTracker />
  <AlignmentIndicator />
</div>
{/if}

<style>
  .gameplay-layout {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  /* ======================== HUD BAR ======================== */
  .hud-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px 16px;
    border-radius: 0;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .hud-left, .hud-right {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .hud-hamburger {
    padding: 4px 10px;
    font-size: 1.2rem;
    border: none;
  }
  .hud-quit {
    padding: 4px 10px;
    font-size: 0.9rem;
    border: none;
    color: var(--text-muted);
  }
  .hud-quit:hover {
    color: var(--accent-danger);
  }
  .stress-high { color: var(--tone-renegade) !important; }
  .stress-high .value { color: var(--tone-renegade) !important; }
  .stress-mid { color: var(--tone-investigate) !important; }
  .stress-mid .value { color: var(--tone-investigate) !important; }

  /* ======================== MAIN CONTENT ======================== */
  .gameplay-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 1.5rem 1rem;
    gap: 1rem;
  }

  /* ======================== PREVIOUSLY ======================== */
  .previously-section {
    margin-bottom: 0.5rem;
  }
  .previously-toggle {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: var(--font-caption);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 4px 0;
    transition: color 0.2s ease;
  }
  .previously-toggle:hover {
    color: var(--text-secondary);
  }
  .previously-arrow {
    display: inline-block;
    transition: transform 0.2s ease;
    font-size: 0.8em;
  }
  .previously-arrow.open {
    transform: rotate(90deg);
  }
  .previously-content {
    padding: 8px 0;
    border-left: 2px solid var(--border-subtle);
    margin-left: 4px;
    padding-left: 12px;
    max-height: 300px;
    overflow-y: auto;
  }
  .previous-turn {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .previous-turn:last-child {
    border-bottom: none;
  }
  .prev-turn-label {
    font-size: var(--font-small);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 2px;
  }
  .prev-turn-text {
    font-size: var(--font-caption);
    color: var(--text-secondary);
    line-height: 1.4;
  }
  .prev-turn-time {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    margin-top: 2px;
  }

  /* ======================== MISSION BRIEFING ======================== */
  .mission-briefing {
    text-align: center;
    border-color: var(--accent-primary);
    background: linear-gradient(180deg, var(--accent-glow) 0%, var(--bg-panel) 100%);
    padding: 16px 20px;
  }
  .mission-header {
    font-size: var(--font-caption);
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--accent-primary);
    font-weight: 700;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .mission-icon {
    font-size: 1.1em;
  }
  .mission-subtitle {
    font-size: var(--font-body);
    color: var(--text-secondary);
    font-style: italic;
  }

  /* ======================== NARRATIVE ======================== */
  .narrative-container {
    flex: 1;
    overflow-y: auto;
    max-height: 55vh;
    padding-right: 8px;
  }
  .turn-header {
    margin-bottom: 12px;
  }
  .turn-label {
    font-size: var(--font-caption);
    text-transform: uppercase;
    letter-spacing: 1.4px;
    color: var(--text-secondary);
  }
  .scene-subtitle {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 2px;
  }

  /* ======================== TYPEWRITER ======================== */
  .typewriter-skip {
    text-align: center;
    margin-top: 8px;
  }
  .btn-skip {
    font-size: var(--font-small);
    padding: 4px 14px;
    opacity: 0.7;
    border: 1px solid var(--border-subtle);
    background: transparent;
  }
  .btn-skip:hover {
    opacity: 1;
  }
  .btn-skip kbd {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    padding: 1px 5px;
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
    background: var(--hud-pill-bg);
    margin-left: 4px;
  }

  /* Choice panel CSS is now in DialogueWheel.svelte */
  .positive { color: var(--tone-paragon); }
  .negative { color: var(--tone-renegade); }

  /* ======================== LOADING ======================== */
  .loading-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-secondary);
    font-size: var(--font-body);
    padding: 16px;
    justify-content: center;
  }
  .loading-spinner {
    width: 20px;
    height: 20px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* ======================== CONCLUSION BANNER ======================== */
  .conclusion-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(135deg, rgba(74, 158, 255, 0.08), rgba(234, 179, 8, 0.08));
    border: 1px solid rgba(234, 179, 8, 0.3);
    margin-top: 1rem;
  }
  .conclusion-text {
    margin: 0;
    color: var(--text-primary);
    font-size: 0.95rem;
  }
  .conclusion-btn {
    white-space: nowrap;
    flex-shrink: 0;
  }

  /* ======================== DEBUG ======================== */
  .debug-panel {
    font-size: var(--font-small);
  }
  .debug-header {
    color: var(--text-secondary);
    cursor: pointer;
    font-size: var(--font-caption);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 4px 0;
  }
  .debug-content {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    overflow-x: auto;
    max-height: 300px;
    white-space: pre-wrap;
    margin-top: 8px;
  }
  .debug-warnings {
    font-size: var(--font-small);
  }
  .warning-item {
    color: var(--tone-investigate);
    padding: 4px 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: var(--font-small);
  }

  /* ======================== ERROR ======================== */
  .error-banner {
    padding: 12px;
    border-radius: 8px;
    background: rgba(255, 80, 60, 0.15);
    border: 1px solid var(--accent-danger);
    color: var(--accent-danger);
    font-size: var(--font-body);
  }

  /* ======================== DRAWER BACKDROP ======================== */
  .drawer-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 199;
    animation: fadeIn 0.15s ease;
  }

  /* ======================== INFO DRAWER ======================== */
  .info-drawer {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 340px;
    max-width: 90vw;
    z-index: 200;
    border-radius: 0;
    border-left: 1px solid var(--border-panel);
    overflow-y: auto;
    padding: 0;
    animation: slideInFromRight 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  }
  @keyframes slideInFromRight {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  /* Mobile drag handle (hidden on desktop) */
  .drawer-handle {
    display: none;
  }

  .drawer-tabs {
    display: flex;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--border-subtle);
    padding: 8px 8px;
    gap: 2px;
    position: sticky;
    top: 0;
    background: var(--bg-overlay);
    z-index: 1;
  }
  .drawer-tab {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: var(--font-small);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    padding: 5px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .drawer-tab:hover {
    background: var(--hud-pill-bg);
    color: var(--text-secondary);
  }
  .drawer-tab.active {
    color: var(--text-heading);
    background: var(--accent-glow);
  }
  .drawer-content {
    padding: 16px;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: var(--font-body);
    color: var(--text-primary);
    gap: 8px;
  }
  .info-row span:first-child {
    color: var(--text-secondary);
    text-transform: capitalize;
  }
  .stress-value.stress-high { color: var(--tone-renegade); font-weight: 700; }
  .stress-value.stress-mid { color: var(--tone-investigate); font-weight: 600; }
  .trauma-value { color: var(--accent-danger); font-style: italic; }
  .item-qty { font-family: 'JetBrains Mono', monospace; }

  /* Quest log drawer */
  .quest-entry {
    padding: 10px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .quest-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .quest-title {
    font-weight: 600;
    text-transform: capitalize;
    color: var(--text-primary);
  }
  .quest-status-badge {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 8px;
    border-radius: 3px;
  }
  .status-active {
    color: var(--tone-investigate);
    border: 1px solid var(--tone-investigate);
  }
  .status-completed {
    color: var(--tone-paragon);
    border: 1px solid var(--tone-paragon);
  }
  .status-failed {
    color: var(--tone-renegade);
    border: 1px solid var(--tone-renegade);
  }
  .status-available {
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
  }
  .quest-progress {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 4px;
  }
  .quest-completed .quest-title {
    text-decoration: line-through;
    opacity: 0.6;
  }

  /* Companion drawer */
  .companion-card-drawer {
    padding: 10px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .companion-name {
    font-weight: 600;
    color: var(--text-heading);
    font-size: var(--font-body);
  }
  .companion-details {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 4px;
  }
  .affinity-hearts {
    display: flex;
    gap: 1px;
    font-size: 0.8rem;
  }
  .affinity-hearts span {
    color: var(--border-subtle);
  }
  .affinity-hearts span.filled {
    color: var(--tone-renegade);
  }
  .affinity-number {
    font-size: var(--font-small);
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
  }
  .companion-loyalty {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-top: 4px;
  }
  .loyalty-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: 700;
  }
  .loyalty-badge.loyal {
    color: var(--tone-paragon);
    border: 1px solid var(--tone-paragon);
  }
  .loyalty-badge.trusted {
    color: var(--tone-investigate);
    border: 1px solid var(--tone-investigate);
  }
  .loyalty-badge.stranger {
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
  }
  .companion-mood {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-style: italic;
  }

  /* Faction reputation bars */
  .faction-row {
    align-items: center;
  }
  .faction-bar-container {
    flex: 1;
    height: 4px;
    background: var(--border-subtle);
    border-radius: 2px;
    overflow: hidden;
    margin: 0 8px;
  }
  .faction-bar {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .positive-bar { background: var(--tone-paragon); }
  .negative-bar { background: var(--tone-renegade); }

  /* News items */
  .news-item {
    padding: 10px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .news-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .news-source {
    font-size: var(--font-small);
    font-weight: 700;
    color: var(--accent-primary);
  }
  .news-urgency {
    font-size: 0.65rem;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 3px;
    font-weight: 600;
    letter-spacing: 0.3px;
  }
  .urgency-high { color: var(--tone-renegade); border: 1px solid var(--tone-renegade); }
  .urgency-medium { color: var(--tone-investigate); border: 1px solid var(--tone-investigate); }
  .urgency-low { color: var(--text-muted); border: 1px solid var(--border-subtle); }
  .news-headline {
    font-size: var(--font-body);
    color: var(--text-primary);
    margin-top: 4px;
    font-weight: 500;
  }
  .news-body {
    font-size: var(--font-small);
    color: var(--text-secondary);
    margin-top: 4px;
    line-height: 1.4;
  }
  .news-factions {
    display: flex;
    gap: 4px;
    margin-top: 6px;
  }
  .news-faction-tag {
    font-size: 0.65rem;
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
    padding: 1px 5px;
  }

  /* Journal tab */
  .journal-entry {
    padding: 10px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .journal-turn-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .journal-turn-num {
    font-size: var(--font-small);
    color: var(--text-heading);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .journal-time {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
  }
  .journal-text {
    font-size: var(--font-caption);
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .empty-state {
    color: var(--text-muted);
    font-style: italic;
    font-size: var(--font-body);
    padding: 16px 0;
  }

  /* ======================== V2.20 COMPANION METERS ======================== */
  .companion-meters {
    margin-top: 6px;
    padding-top: 4px;
    border-top: 1px solid var(--border-subtle);
  }
  .meter-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
  }
  .meter-row.mini {
    padding: 1px 0;
  }
  .meter-label {
    font-size: var(--font-small);
    color: var(--text-muted);
    width: 52px;
    flex-shrink: 0;
  }
  .meter-bar-container {
    flex: 1;
    height: 4px;
    background: var(--border-subtle);
    border-radius: 2px;
    overflow: hidden;
    position: relative;
  }
  .meter-center-line {
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--text-muted);
    opacity: 0.3;
  }
  .meter-bar {
    position: absolute;
    top: 0;
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .meter-value {
    font-size: var(--font-small);
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    width: 30px;
    text-align: right;
    flex-shrink: 0;
  }
  .loyalty-badge.ally {
    color: var(--text-secondary);
    border: 1px solid var(--border-panel);
  }

  /* ======================== V3.0 FACTION TIERS ======================== */
  .faction-entry {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .faction-name {
    font-size: var(--font-body);
    color: var(--text-primary);
    text-transform: capitalize;
  }
  .faction-tier {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 6px;
    border-radius: 3px;
    border: 1px solid;
  }
  .faction-tier.hostile { color: var(--tone-renegade); border-color: var(--tone-renegade); }
  .faction-tier.unfriendly { color: var(--accent-danger); border-color: var(--accent-danger); }
  .faction-tier.neutral { color: var(--text-muted); border-color: var(--border-subtle); }
  .faction-tier.friendly { color: var(--tone-investigate); border-color: var(--tone-investigate); }
  .faction-tier.allied { color: var(--tone-paragon); border-color: var(--tone-paragon); }
  .faction-bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
  }
  .faction-value {
    font-size: var(--font-small);
    font-family: 'JetBrains Mono', monospace;
    width: 32px;
    text-align: right;
    flex-shrink: 0;
  }

  /* ======================== V3.0 HUD HEAT/ALERT PILLS ======================== */
  .heat-pill.heat-noticed {
    color: var(--tone-investigate) !important;
    border-color: var(--tone-investigate) !important;
  }
  .heat-pill.heat-noticed .value { color: var(--tone-investigate) !important; }
  .heat-pill.heat-wanted {
    color: var(--tone-renegade) !important;
    border-color: var(--tone-renegade) !important;
    animation: pulse-hud 2s ease-in-out infinite;
  }
  .heat-pill.heat-wanted .value { color: var(--tone-renegade) !important; }
  .alert-pill.alert-watchful {
    color: var(--tone-investigate) !important;
    border-color: var(--tone-investigate) !important;
  }
  .alert-pill.alert-watchful .value { color: var(--tone-investigate) !important; }
  .alert-pill.alert-lockdown {
    color: var(--tone-renegade) !important;
    border-color: var(--tone-renegade) !important;
    animation: pulse-hud 2s ease-in-out infinite;
  }
  .alert-pill.alert-lockdown .value { color: var(--tone-renegade) !important; }
  @keyframes pulse-hud {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  /* ======================== RESPONSIVE ======================== */
  @media (max-width: 768px) {
    .hud-bar {
      padding: 6px 10px;
    }
    .gameplay-main {
      padding: 1rem 0.75rem;
    }
    .info-drawer {
      width: 100%;
      max-width: 100%;
      top: auto;
      bottom: 0;
      height: 60vh;
      border-left: none;
      border-top: 1px solid var(--border-panel);
      border-radius: var(--panel-radius) var(--panel-radius) 0 0;
      animation: slideInFromBottom 0.25s cubic-bezier(0.22, 1, 0.36, 1);
    }
    @keyframes slideInFromBottom {
      from { transform: translateY(100%); }
      to { transform: translateY(0); }
    }
    /* Show drag handle on mobile */
    .drawer-handle {
      display: flex;
      justify-content: center;
      padding: 8px 0 4px;
    }
    .handle-bar {
      width: 36px;
      height: 4px;
      border-radius: 2px;
      background: var(--border-panel);
    }
    /* Stack HUD pills */
    .hud-left, .hud-right {
      gap: 4px;
    }
    .pill {
      padding: 3px 7px;
      font-size: 0.7rem;
    }
    .pill .label {
      font-size: 0.6rem;
      margin-right: 3px;
    }
  }

  @media (max-width: 480px) {
    .gameplay-main {
      padding: 0.75rem 0.5rem;
    }
    .narrative-container {
      max-height: 45vh;
    }
  }


  /* ======================== V3.3 VISUAL UPGRADE ======================== */
  .hud-bar {
    border-bottom: 1px solid rgba(118, 176, 255, 0.35);
    background:
      linear-gradient(180deg, rgba(9, 18, 40, 0.95), rgba(8, 16, 35, 0.88));
    box-shadow:
      0 12px 30px rgba(0, 0, 0, 0.35),
      inset 0 1px 0 rgba(162, 210, 255, 0.12);
  }

  .gameplay-main {
    max-width: 840px;
    padding: 1.8rem 1.2rem 2rem;
  }

  .mission-briefing {
    border-color: rgba(132, 186, 255, 0.75);
    background:
      radial-gradient(130% 120% at 50% -10%, rgba(122, 180, 255, 0.22), transparent 65%),
      linear-gradient(165deg, rgba(13, 31, 68, 0.92), rgba(10, 22, 49, 0.88));
    box-shadow:
      inset 0 0 0 1px rgba(149, 203, 255, 0.2),
      0 12px 28px rgba(5, 13, 30, 0.46),
      0 0 30px rgba(78, 147, 255, 0.16);
  }

  .mission-header {
    color: #92c3ff;
    text-shadow: 0 0 10px rgba(108, 169, 255, 0.45);
  }

  .mission-subtitle {
    color: #d7e8ff;
  }

  .narrative-container {
    border: 1px solid rgba(112, 167, 240, 0.28);
    border-radius: 12px;
    padding: 14px 16px;
    background:
      linear-gradient(180deg, rgba(11, 23, 51, 0.8), rgba(10, 19, 43, 0.84));
    box-shadow: inset 0 1px 0 rgba(154, 205, 255, 0.12);
  }

  .turn-label {
    color: #86b7fb;
    font-weight: 700;
  }

  .scene-subtitle {
    color: #b4ccef;
  }

  .previously-content {
    border-left-color: rgba(120, 171, 237, 0.5);
  }

  .previous-turn {
    border-bottom-color: rgba(120, 171, 237, 0.25);
  }

  .drawer-backdrop {
    background: rgba(2, 6, 14, 0.68);
    backdrop-filter: blur(2px);
  }

  .info-drawer {
    border-left: 1px solid rgba(118, 176, 255, 0.4);
    background:
      radial-gradient(70% 60% at 20% 0%, rgba(75, 136, 232, 0.18), transparent 72%),
      linear-gradient(180deg, rgba(9, 21, 47, 0.96), rgba(7, 16, 36, 0.94));
    box-shadow: -12px 0 35px rgba(0, 0, 0, 0.45);
  }

  .drawer-tabs {
    border-bottom: 1px solid rgba(114, 168, 239, 0.35);
    background: rgba(8, 18, 42, 0.95);
  }

  .drawer-tab {
    border: 1px solid transparent;
  }

  .drawer-tab:hover {
    background: rgba(86, 142, 228, 0.2);
    border-color: rgba(127, 182, 255, 0.4);
    color: #d6e9ff;
  }

  .drawer-tab.active {
    color: #e4f1ff;
    border-color: rgba(145, 199, 255, 0.48);
    background: linear-gradient(150deg, rgba(78, 138, 226, 0.32), rgba(40, 80, 150, 0.28));
    box-shadow: inset 0 1px 0 rgba(179, 221, 255, 0.24);
  }

  .info-row,
  .quest-entry,
  .warning-item,
  .companion-card-drawer {
    border-bottom-color: rgba(120, 171, 237, 0.25);
  }

</style>
