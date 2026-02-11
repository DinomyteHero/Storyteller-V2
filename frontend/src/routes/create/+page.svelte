<script lang="ts">
  import { goto } from '$app/navigation';
  import { setupAuto, getEraCompanions } from '$lib/api/campaigns';
  import type { CompanionPreview } from '$lib/api/campaigns';
  import { getEraBackgrounds } from '$lib/api/eras';
  import { streamTurn } from '$lib/api/sse';
  import { runTurn } from '$lib/api/campaigns';
  import {
    creationStep, charName, charGender, charEra,
    selectedBackground, eraBackgrounds, loadingBackgrounds,
    backgroundAnswers, resetCreation
  } from '$lib/stores/creation';
  import { campaignId, playerId, lastTurnResponse } from '$lib/stores/game';
  import {
    startStreaming, appendToken, finishStreaming, failStreaming, resetStreaming
  } from '$lib/stores/streaming';
  import { ui } from '$lib/stores/ui';
  import { ERA_LABELS, CYOA_QUESTIONS, TONE_ICONS } from '$lib/utils/constants';
  import { randomName, getActiveBackgroundQuestions, ERA_DESCRIPTIONS } from '$lib/utils/creation';
  import { saveCampaign } from '$lib/stores/campaigns';
  import type { EraBackground, SetupAutoRequest, BackgroundQuestion } from '$lib/api/types';

  const ERA_OPTIONS = Object.entries(ERA_LABELS).filter(([k]) => k !== 'CUSTOM');

  let isSubmitting = $state(false);
  let errorMessage = $state('');
  let cyoaAnswerIndices = $state<Record<number, number>>({});
  let eraCompanions = $state<CompanionPreview[]>([]);
  let loadingCompanions = $state(false);

  // Load backgrounds when era changes
  $effect(() => {
    const era = $charEra;
    if (era && era !== 'ERA_AGNOSTIC') {
      loadingBackgrounds.set(true);
      getEraBackgrounds(era)
        .then((result) => {
          eraBackgrounds.set(result.backgrounds ?? []);
        })
        .catch(() => {
          eraBackgrounds.set([]);
        })
        .finally(() => {
          loadingBackgrounds.set(false);
        });
    } else {
      eraBackgrounds.set([]);
    }
  });

  // Load companion previews when era changes
  $effect(() => {
    const era = $charEra;
    if (era && era !== 'ERA_AGNOSTIC') {
      loadingCompanions = true;
      getEraCompanions(era)
        .then((result) => {
          eraCompanions = result.companions ?? [];
        })
        .catch(() => {
          eraCompanions = [];
        })
        .finally(() => {
          loadingCompanions = false;
        });
    } else {
      eraCompanions = [];
    }
  });

  // Determine flow mode: backgrounds vs generic CYOA
  let useBackgrounds = $derived($eraBackgrounds.length > 0);

  // Active background questions (dynamic based on condition evaluation)
  let activeQuestions = $derived.by(() => {
    const bg = $selectedBackground;
    if (!bg) return [];
    return getActiveBackgroundQuestions(bg, $backgroundAnswers);
  });

  // Calculate total steps dynamically
  let totalSteps = $derived.by(() => {
    if (useBackgrounds && $selectedBackground) {
      return 3 + activeQuestions.length; // 0: name, 1: background, 2..N: bg questions, last: review
    }
    if (useBackgrounds) {
      return 4; // name, background, at least 1 question placeholder, review
    }
    return 2 + CYOA_QUESTIONS.length; // 0: name, 1..4: generic CYOA, last: review
  });

  function nextStep() {
    creationStep.update((s) => s + 1);
  }

  function prevStep() {
    creationStep.update((s) => Math.max(0, s - 1));
  }

  function selectBackground(bg: EraBackground) {
    selectedBackground.set(bg);
    backgroundAnswers.set({}); // Reset answers when changing background
  }

  function selectBgAnswer(questionId: string, choiceIdx: number) {
    backgroundAnswers.update((a) => ({ ...a, [questionId]: choiceIdx }));
  }

  function selectCyoaChoice(questionIdx: number, choiceIdx: number) {
    cyoaAnswerIndices = { ...cyoaAnswerIndices, [questionIdx]: choiceIdx };
  }

  function handleRandomName() {
    charName.set(randomName());
  }

  async function beginAdventure() {
    if (!$charName.trim()) return;
    isSubmitting = true;
    errorMessage = '';

    try {
      // Build concept from answers
      const concepts: string[] = [];
      let startingLocation: string | null = null;

      if (useBackgrounds && $selectedBackground) {
        // Background-based: extract concepts from background question answers
        for (const q of activeQuestions) {
          const choiceIdx = $backgroundAnswers[q.id];
          if (choiceIdx !== undefined && q.choices[choiceIdx]) {
            const choice = q.choices[choiceIdx];
            if (choice.concept) concepts.push(choice.concept);
            // Check for location_hint in effects
            const effects = (choice as any).effects ?? {};
            if (effects.location_hint && !startingLocation) {
              startingLocation = effects.location_hint;
            }
          }
        }
      } else {
        // Generic CYOA: extract concepts from fallback questions
        for (const [qIdx, cIdx] of Object.entries(cyoaAnswerIndices)) {
          const q = CYOA_QUESTIONS[Number(qIdx)];
          if (q) {
            const choice = q.choices[cIdx];
            if (choice) concepts.push(choice.concept);
          }
        }
      }

      // Convert backgroundAnswers from {questionId: choiceIdx} to {questionId: choiceIdx} (already correct format)
      const bgAnswersForApi: Record<string, number> = {};
      for (const [qId, cIdx] of Object.entries($backgroundAnswers)) {
        bgAnswersForApi[qId] = cIdx;
      }

      const request: SetupAutoRequest = {
        time_period: $charEra,
        genre: null,
        themes: [],
        player_concept: concepts.join('; ') || $charName.trim(),
        starting_location: startingLocation,
        randomize_starting_location: !startingLocation,
        background_id: $selectedBackground?.id ?? null,
        background_answers: bgAnswersForApi,
        player_gender: $charGender,
      };

      const result = await setupAuto(request);
      campaignId.set(result.campaign_id);
      playerId.set(result.player_id);

      // Save campaign to local registry
      saveCampaign({
        campaignId: result.campaign_id,
        playerId: result.player_id,
        playerName: $charName.trim(),
        era: $charEra,
        background: $selectedBackground?.name ?? null,
        createdAt: new Date().toISOString(),
        lastPlayedAt: new Date().toISOString(),
        turnCount: 0,
      });

      // Run the opening turn
      if ($ui.enableStreaming) {
        startStreaming();
        try {
          let finalResponse = null;
          for await (const event of streamTurn(result.campaign_id, result.player_id, '[OPENING_SCENE]')) {
            if (event.type === 'token' && event.text) {
              appendToken(event.text);
            } else if (event.type === 'done') {
              finalResponse = event;
            } else if (event.type === 'error') {
              failStreaming(event.message ?? 'Stream error');
            }
          }
          if (finalResponse) {
            lastTurnResponse.set(finalResponse as any);
          }
          // V3.0: Reset ALL streaming state before navigating to play page.
          // finishStreaming() only sets streamDone=true — streamedText stays
          // truthy, which causes the play page's fullNarrativeText derived
          // to lock onto stale streamed content instead of lastTurnResponse.
          resetStreaming();
        } catch (e) {
          failStreaming(String(e));
        }
      } else {
        const turnResult = await runTurn(result.campaign_id, result.player_id, '[OPENING_SCENE]');
        lastTurnResponse.set(turnResult);
      }

      goto('/play');
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : String(e);
    } finally {
      isSubmitting = false;
    }
  }

  function backToMenu() {
    resetCreation();
    goto('/');
  }
</script>

<div class="creation-container">
  <div class="creation-content">
    <!-- Progress bar -->
    <div class="progress-bar">
      {#each Array(Math.min(totalSteps, 8)) as _, i}
        <div
          class="progress-dot"
          class:active={i <= $creationStep}
          class:current={i === $creationStep}
        ></div>
        {#if i < Math.min(totalSteps, 8) - 1}
          <div class="progress-line" class:active={i < $creationStep}></div>
        {/if}
      {/each}
    </div>
    <p class="step-counter">Step {$creationStep + 1} of {totalSteps}</p>

    <!-- ====================== STEP 0: Name, Gender, Era ====================== -->
    {#if $creationStep === 0}
      <div class="step fade-in">
        <h2>Create Your Character</h2>
        <p class="step-subtitle">Who are you in this galaxy?</p>

        <div class="form-field">
          <label for="char-name">Character Name</label>
          <div class="name-row">
            <input
              id="char-name"
              type="text"
              bind:value={$charName}
              placeholder="Enter your name..."
              maxlength="40"
            />
            <button class="btn name-random" onclick={handleRandomName} title="Random name">
              🎲
            </button>
          </div>
        </div>

        <div class="form-field">
          <label id="gender-label">Gender</label>
          <div class="gender-row" role="group" aria-labelledby="gender-label">
            <button
              class="btn gender-btn"
              class:selected={$charGender === 'male'}
              onclick={() => charGender.set('male')}
            >Male</button>
            <button
              class="btn gender-btn"
              class:selected={$charGender === 'female'}
              onclick={() => charGender.set('female')}
            >Female</button>
          </div>
        </div>

        <div class="form-field">
          <label id="era-label">Choose Your Era</label>
          <div class="era-cards" role="group" aria-labelledby="era-label">
            {#each ERA_OPTIONS as [value, label]}
              <button
                class="card era-card"
                class:selected={$charEra === value}
                onclick={() => {
                  charEra.set(value);
                  selectedBackground.set(null);
                  backgroundAnswers.set({});
                }}
              >
                <div class="era-name">{label}</div>
                {#if ERA_DESCRIPTIONS[value]}
                  <div class="era-desc">{ERA_DESCRIPTIONS[value]}</div>
                {/if}
              </button>
            {/each}
          </div>
        </div>

        <p class="genre-note">Genre will be automatically shaped by your background and location choices.</p>

        <div class="step-actions">
          <button class="btn" onclick={backToMenu}>Back</button>
          <button
            class="btn btn-primary"
            disabled={!$charName.trim()}
            onclick={nextStep}
          >Continue</button>
        </div>
      </div>

    <!-- ====================== STEP 1: Background Selection (if era has them) ====================== -->
    {:else if $creationStep === 1 && useBackgrounds}
      <div class="step fade-in">
        <h2>Choose Your Background</h2>
        <p class="step-subtitle">Your background shapes your starting position, skills, and story</p>

        {#if $loadingBackgrounds}
          <div class="loading-indicator">
            <div class="loading-spinner"></div>
            <span>Loading backgrounds...</span>
          </div>
        {:else}
          <div class="background-cards">
            {#each $eraBackgrounds as bg}
              {@const isSelected = $selectedBackground?.id === bg.id}
              {@const statsStr = Object.entries(bg.starting_stats ?? {}).filter(([,v]) => v > 0).map(([k,v]) => `${k}: ${v}`).join(' | ')}
              <button
                class="card background-card"
                class:selected={isSelected}
                onclick={() => selectBackground(bg)}
              >
                <div class="bg-name">{bg.name}</div>
                <div class="bg-desc">{bg.description}</div>
                {#if statsStr}
                  <div class="bg-stats">{statsStr}</div>
                {/if}
              </button>
            {/each}
          </div>
        {/if}

        <div class="step-actions">
          <button class="btn" onclick={prevStep}>Back</button>
          <button
            class="btn btn-primary"
            disabled={!$selectedBackground}
            onclick={nextStep}
          >Continue</button>
        </div>
      </div>

    <!-- ====================== STEP 2+: Background Questions (dynamic branching) ====================== -->
    {:else if useBackgrounds && $selectedBackground && $creationStep >= 2 && $creationStep < 2 + activeQuestions.length}
      {@const qIdx = $creationStep - 2}
      {@const question = activeQuestions[qIdx]}
      {#if question}
        <div class="step fade-in">
          <h2>{question.title}</h2>
          <p class="step-subtitle">{question.subtitle}</p>

          <div class="cyoa-choices">
            {#each question.choices as choice, cIdx}
              {@const isChosen = $backgroundAnswers[question.id] === cIdx}
              <button
                class="card cyoa-card tone-{(choice.tone ?? 'neutral').toLowerCase()}"
                class:selected={isChosen}
                onclick={() => selectBgAnswer(question.id, cIdx)}
              >
                <div class="cyoa-card-inner">
                  <span class="tone-icon">{TONE_ICONS[(choice.tone ?? 'NEUTRAL').toUpperCase()] ?? '◯'}</span>
                  <span class="cyoa-label">{choice.label}</span>
                </div>
                {#if choice.concept}
                  <div class="cyoa-concept">{choice.concept}</div>
                {/if}
              </button>
            {/each}
          </div>

          <div class="step-actions">
            <button class="btn" onclick={prevStep}>Back</button>
            <button
              class="btn btn-primary"
              disabled={$backgroundAnswers[question.id] === undefined}
              onclick={nextStep}
            >Continue</button>
          </div>
        </div>
      {/if}

    <!-- ====================== Generic CYOA Questions (fallback when no backgrounds) ====================== -->
    {:else if !useBackgrounds && $creationStep >= 1 && $creationStep <= CYOA_QUESTIONS.length}
      {@const questionIdx = $creationStep - 1}
      {@const question = CYOA_QUESTIONS[questionIdx]}
      <div class="step fade-in">
        <h2>{question.title}</h2>
        <p class="step-subtitle">{question.subtitle}</p>

        <div class="cyoa-choices">
          {#each question.choices as choice, cIdx}
            <button
              class="card cyoa-card tone-{choice.tone.toLowerCase()}"
              class:selected={cyoaAnswerIndices[questionIdx] === cIdx}
              onclick={() => selectCyoaChoice(questionIdx, cIdx)}
            >
              <div class="cyoa-card-inner">
                <span class="tone-icon">{TONE_ICONS[choice.tone] ?? '◯'}</span>
                <span class="cyoa-label">{choice.label}</span>
              </div>
            </button>
          {/each}
        </div>

        <div class="step-actions">
          <button class="btn" onclick={prevStep}>Back</button>
          <button
            class="btn btn-primary"
            disabled={cyoaAnswerIndices[questionIdx] === undefined}
            onclick={nextStep}
          >Continue</button>
        </div>
      </div>

    <!-- ====================== REVIEW & BEGIN ====================== -->
    {:else}
      <div class="step fade-in">
        <h2>Ready to Begin</h2>
        <p class="step-subtitle">Review your character</p>

        <div class="review-card card">
          <div class="review-row">
            <span class="review-label">Name</span>
            <span class="review-value">{$charName}</span>
          </div>
          <div class="review-row">
            <span class="review-label">Gender</span>
            <span class="review-value">{$charGender === 'male' ? 'Male' : 'Female'}</span>
          </div>
          <div class="review-row">
            <span class="review-label">Era</span>
            <span class="review-value">{ERA_LABELS[$charEra] ?? $charEra}</span>
          </div>

          {#if $selectedBackground}
            <div class="review-row">
              <span class="review-label">Background</span>
              <span class="review-value">{$selectedBackground.name}</span>
            </div>
            {#each activeQuestions as q}
              {@const choiceIdx = $backgroundAnswers[q.id]}
              {#if choiceIdx !== undefined && q.choices[choiceIdx]}
                <div class="review-row">
                  <span class="review-label">{q.title}</span>
                  <span class="review-value">{q.choices[choiceIdx].label}</span>
                </div>
              {/if}
            {/each}
          {:else}
            {#each Object.entries(cyoaAnswerIndices) as [qIdx, cIdx]}
              {@const q = CYOA_QUESTIONS[Number(qIdx)]}
              {#if q}
                <div class="review-row">
                  <span class="review-label">{q.title}</span>
                  <span class="review-value">{q.choices[cIdx]?.label ?? '—'}</span>
                </div>
              {/if}
            {/each}
          {/if}
        </div>

        <!-- Companion Preview -->
        {#if loadingCompanions}
          <div class="loading-indicator">
            <div class="loading-spinner"></div>
            <span>Loading companions...</span>
          </div>
        {:else if eraCompanions.length > 0}
          <div class="companion-preview">
            <h3 class="companion-preview-heading">Potential Companions</h3>
            <div class="companion-cards">
              {#each eraCompanions as comp}
                <div class="card companion-card">
                  <div class="companion-name">{comp.name}</div>
                  {#if comp.species}
                    <div class="companion-detail"><span class="companion-field">Species:</span> {comp.species}</div>
                  {/if}
                  {#if comp.archetype}
                    <div class="companion-detail"><span class="companion-field">Archetype:</span> {comp.archetype}</div>
                  {/if}
                  {#if comp.voice_belief}
                    <div class="companion-belief">"{comp.voice_belief}"</div>
                  {/if}
                </div>
              {/each}
            </div>
          </div>
        {/if}

        {#if errorMessage}
          <div class="error-banner">{errorMessage}</div>
        {/if}

        <div class="step-actions">
          <button class="btn" onclick={prevStep} disabled={isSubmitting}>Back</button>
          <button
            class="btn btn-primary"
            disabled={isSubmitting}
            onclick={beginAdventure}
          >
            {isSubmitting ? 'Setting up...' : 'Begin Adventure'}
          </button>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .creation-container {
    flex: 1;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 2rem;
    padding-top: 3rem;
  }

  .creation-content {
    max-width: 640px;
    width: 100%;
  }

  /* Progress bar */
  .progress-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin-bottom: 0.5rem;
  }
  .step-counter {
    text-align: center;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-bottom: 1.5rem;
  }
  .progress-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--border-subtle);
    border: 2px solid var(--border-panel);
    transition: all 0.3s ease;
  }
  .progress-dot.active {
    background: var(--accent-primary);
    border-color: var(--accent-primary);
  }
  .progress-dot.current {
    box-shadow: 0 0 8px var(--accent-glow);
    width: 12px;
    height: 12px;
  }
  .progress-line {
    width: 30px;
    height: 2px;
    background: var(--border-subtle);
    transition: background 0.3s ease;
  }
  .progress-line.active {
    background: var(--accent-primary);
  }

  /* Step content */
  .step {
    text-align: center;
  }
  .step h2 {
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
  }
  .step-subtitle {
    color: var(--text-secondary);
    font-size: var(--font-body);
    margin-bottom: 2rem;
  }

  /* Form fields */
  .form-field {
    text-align: left;
    margin-bottom: 1.25rem;
  }
  .form-field > label {
    display: block;
    font-size: var(--font-caption);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
  }

  .name-row {
    display: flex;
    gap: 8px;
  }
  .name-row input {
    flex: 1;
  }
  .name-random {
    padding: 0.5rem 0.75rem;
    font-size: 1.1rem;
  }

  .gender-row {
    display: flex;
    gap: 12px;
  }
  .gender-btn {
    flex: 1;
    padding: 0.6rem;
  }
  .gender-btn.selected {
    border-color: var(--accent-primary);
    background: var(--accent-glow);
    color: var(--text-heading);
  }

  .genre-note {
    font-size: var(--font-caption);
    color: var(--text-muted);
    background: var(--hud-pill-bg);
    padding: 10px;
    border-radius: 6px;
    text-align: center;
    margin-bottom: 1rem;
  }

  /* Era cards */
  .era-cards {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .era-card {
    cursor: pointer;
    text-align: left;
    transition: all 0.2s ease;
    padding: 12px 16px;
  }
  .era-card:hover {
    border-color: var(--choice-hover-border);
    transform: translateY(-1px);
  }
  .era-card.selected {
    border-color: var(--accent-primary);
    background: var(--accent-glow);
  }
  .era-name {
    font-weight: 600;
    color: var(--text-primary);
    font-size: var(--font-body);
  }
  .era-desc {
    font-size: var(--font-small);
    color: var(--text-secondary);
    margin-top: 2px;
  }

  /* Background cards */
  .background-cards {
    display: flex;
    flex-direction: column;
    gap: 10px;
    text-align: left;
  }
  .background-card {
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 14px 16px;
  }
  .background-card:hover {
    border-color: var(--choice-hover-border);
    transform: translateY(-1px);
    box-shadow: var(--choice-hover-glow);
  }
  .background-card.selected {
    border-color: var(--accent-primary);
    background: var(--accent-glow);
    box-shadow: 0 0 16px var(--accent-glow);
  }
  .bg-name {
    font-weight: 700;
    color: var(--text-primary);
    font-size: 1.05rem;
  }
  .bg-desc {
    font-size: var(--font-body);
    color: var(--text-secondary);
    margin-top: 4px;
    line-height: 1.4;
  }
  .bg-stats {
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
  }

  /* Step actions */
  .step-actions {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 2rem;
  }
  .step-actions .btn {
    flex: 1;
  }

  /* CYOA choice cards */
  .cyoa-choices {
    display: flex;
    flex-direction: column;
    gap: 10px;
    text-align: left;
  }
  .cyoa-card {
    cursor: pointer;
    border-left-width: 3px;
    border-left-style: solid;
    border-left-color: var(--tone-color, var(--border-panel));
    transition: all 0.2s ease;
  }
  .cyoa-card:hover {
    border-color: var(--choice-hover-border);
    border-left-color: var(--tone-color, var(--choice-hover-border));
    box-shadow: var(--choice-hover-glow);
    transform: translateY(-1px);
  }
  .cyoa-card.selected {
    border-color: var(--accent-primary);
    border-left-color: var(--tone-color, var(--accent-primary));
    background: var(--accent-glow);
    box-shadow: 0 0 16px var(--accent-glow);
  }
  .cyoa-card-inner {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .tone-icon {
    font-size: 1.2em;
    color: var(--tone-color, var(--text-muted));
  }
  .cyoa-label {
    font-size: var(--font-body);
    color: var(--text-primary);
    font-weight: 500;
  }
  .cyoa-concept {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-style: italic;
    margin-top: 4px;
    margin-left: 30px;
  }

  /* Review card */
  .review-card {
    text-align: left;
    margin-bottom: 1rem;
  }
  .review-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-subtle);
    gap: 16px;
  }
  .review-row:last-child {
    border-bottom: none;
  }
  .review-label {
    font-size: var(--font-caption);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    white-space: nowrap;
  }
  .review-value {
    font-size: var(--font-body);
    color: var(--text-primary);
    text-align: right;
  }

  /* Error / Loading */
  .error-banner {
    padding: 12px;
    border-radius: 8px;
    background: rgba(255, 80, 60, 0.15);
    border: 1px solid var(--accent-danger);
    color: var(--accent-danger);
    font-size: var(--font-body);
    margin-top: 12px;
  }
  .loading-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 32px;
    color: var(--text-secondary);
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

  /* Companion preview */
  .companion-preview {
    margin-top: 1.5rem;
    text-align: left;
  }
  .companion-preview-heading {
    font-size: 1rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.75rem;
    text-align: center;
  }
  .companion-cards {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .companion-card {
    padding: 12px 16px;
    transition: all 0.2s ease;
  }
  .companion-card:hover {
    border-color: var(--choice-hover-border);
    transform: translateY(-1px);
  }
  .companion-name {
    font-weight: 700;
    color: var(--text-primary);
    font-size: 1.05rem;
    margin-bottom: 4px;
  }
  .companion-detail {
    font-size: var(--font-small);
    color: var(--text-secondary);
    margin-top: 2px;
  }
  .companion-field {
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    font-size: var(--font-caption);
  }
  .companion-belief {
    font-size: var(--font-small);
    color: var(--text-muted);
    font-style: italic;
    margin-top: 6px;
  }
</style>
