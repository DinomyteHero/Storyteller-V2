<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { setupAuto, getEraCompanions, patchCharacterName } from '$lib/api/campaigns';
  import type { CompanionPreview } from '$lib/api/campaigns';
  import type { SetupAutoResponse } from '$lib/api/types';
  import { getEraBackgrounds, getEraSpecies } from '$lib/api/eras';
  import { getContentCatalog, getContentDefault, type ContentCatalogEntry } from '$lib/api/content';
  import { streamTurn } from '$lib/api/sse';
  import { runTurn } from '$lib/api/campaigns';
  import {
    creationStep, charName, charGender, charEra, charSettingId, charPeriodId,
    charSpecies, eraSpecies, loadingSpecies,
    selectedBackground, eraBackgrounds, loadingBackgrounds,
    backgroundAnswers, resetCreation
  } from '$lib/stores/creation';
  import SpeciesCard from '$lib/components/creation/SpeciesCard.svelte';
  import { campaignId, playerId, lastTurnResponse } from '$lib/stores/game';
  import {
    startStreaming, appendToken, finishStreaming, failStreaming, resetStreaming
  } from '$lib/stores/streaming';
  import { ui } from '$lib/stores/ui';
  import { ERA_LABELS, CYOA_QUESTIONS, TONE_ICONS } from '$lib/utils/constants';
  import { randomName, getActiveBackgroundQuestions, ERA_DESCRIPTIONS } from '$lib/utils/creation';
  import { saveCampaign } from '$lib/stores/campaigns';
  import type { EraBackground, EraSpecies, SetupAutoRequest, BackgroundQuestion } from '$lib/api/types';

  let contentCatalog = $state<ContentCatalogEntry[]>([]);

  let ERA_OPTIONS = $derived.by(() => {
    if (contentCatalog.length > 0) {
      return contentCatalog.map((c) => ({
        value: c.period_id.toUpperCase(),
        label: c.period_display_name,
        settingId: c.setting_id,
      }));
    }
    return Object.entries(ERA_LABELS)
      .filter(([k]) => k !== 'CUSTOM')
      .map(([value, label]) => ({ value, label, settingId: null }));
  });

  let isSubmitting = $state(false);
  let errorMessage = $state('');
  let cyoaAnswerIndices = $state<Record<number, number>>({});
  let eraCompanions = $state<CompanionPreview[]>([]);
  let loadingCompanions = $state(false);
  let selectedDifficulty = $state<'easy' | 'normal' | 'hard'>('normal');
  let continueSagaContext = $state<{
    saga_id: string | null;
    legacy_id: number | null;
    player_profile_id: string | null;
    saga_chapter: number | null;
  } | null>(null);
  // Character sheet confirmation (phase 2 of setup)
  let setupResult = $state<SetupAutoResponse | null>(null);
  let generatedName = $state('');
  let isStartingAdventure = $state(false);

  const DIFFICULTY_OPTIONS: { value: 'easy' | 'normal' | 'hard'; label: string; desc: string }[] = [
    { value: 'easy', label: 'Easy', desc: 'Forgiving checks, reduced damage. Focus on story.' },
    { value: 'normal', label: 'Normal', desc: 'Balanced challenge. The intended experience.' },
    { value: 'hard', label: 'Hard', desc: 'Punishing checks, increased damage. Every choice matters.' },
  ];

  onMount(async () => {
    try {
      const raw = sessionStorage.getItem('continueSagaContext');
      if (raw) {
        const parsed = JSON.parse(raw) as {
          saga_id?: string | null;
          legacy_id?: number | null;
          player_profile_id?: string | null;
          saga_chapter?: number | null;
        };
        continueSagaContext = {
          saga_id: parsed.saga_id ?? null,
          legacy_id: parsed.legacy_id ?? null,
          player_profile_id: parsed.player_profile_id ?? null,
          saga_chapter: parsed.saga_chapter ?? null,
        };
        sessionStorage.removeItem('continueSagaContext');
      }
    } catch {
      continueSagaContext = null;
    }

    try {
      const [catalogResp, defaultResp] = await Promise.all([
        getContentCatalog(),
        getContentDefault(),
      ]);
      contentCatalog = catalogResp.items ?? [];
      if (defaultResp?.setting_id) charSettingId.set(defaultResp.setting_id);
      if (defaultResp?.period_id) charPeriodId.set(defaultResp.period_id);
      if (defaultResp?.legacy_era_id) charEra.set(defaultResp.legacy_era_id.toUpperCase());
    } catch {
      // Fallback to legacy hardcoded eras
    }
  });

  let sagaBannerLabel = $derived.by(() => {
    if (!continueSagaContext?.saga_id) return '';
    const shortId = continueSagaContext.saga_id.slice(0, 8);
    const chapter = continueSagaContext.saga_chapter;
    if (chapter && chapter > 0) {
      return `Continuing Saga ${shortId} · Prior chapter ${chapter}`;
    }
    return `Continuing Saga ${shortId}`;
  });

  // Load backgrounds and species when era changes
  $effect(() => {
    const era = $charEra;
    if (era && era !== 'ERA_AGNOSTIC') {
      const period = era.toLowerCase();
      charPeriodId.set(period);

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

      // Phase 0.7: load species list for species selection step
      loadingSpecies.set(true);
      getEraSpecies(era)
        .then((result) => {
          eraSpecies.set(result.species ?? []);
        })
        .catch(() => {
          eraSpecies.set([]);
        })
        .finally(() => {
          loadingSpecies.set(false);
        });
    } else {
      eraBackgrounds.set([]);
      eraSpecies.set([]);
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

  // Whether species step should be shown (era has species data)
  let hasSpecies = $derived($eraSpecies.length > 0);

  // Calculate total steps dynamically
  // Steps: 0=name/era, [1=species if hasSpecies], N=background, N+1..M=bg questions, last=review
  let totalSteps = $derived.by(() => {
    const speciesStep = hasSpecies ? 1 : 0;
    if (useBackgrounds && $selectedBackground) {
      return 3 + speciesStep + activeQuestions.length;
    }
    if (useBackgrounds) {
      return 4 + speciesStep;
    }
    return 2 + speciesStep + CYOA_QUESTIONS.length;
  });

  // Step index helpers that account for the optional species step
  let speciesStepIdx = $derived(hasSpecies ? 1 : -1);
  let backgroundStepIdx = $derived(hasSpecies ? 2 : 1);

  function randomItem<T>(items: T[]): T | null {
    if (!items.length) return null;
    return items[Math.floor(Math.random() * items.length)] ?? null;
  }

  function buildQuickStartBackgroundSelections(background: EraBackground): {
    answers: Record<string, number>;
    concepts: string[];
    startingLocation: string | null;
  } {
    const answers: Record<string, number> = {};
    const concepts: string[] = [];
    let startingLocation: string | null = null;
    let guard = 0;

    while (guard < 64) {
      guard += 1;
      const active = getActiveBackgroundQuestions(background, answers);
      const nextQuestion = active.find((q) => answers[q.id] === undefined);
      if (!nextQuestion) break;

      if (!nextQuestion.choices.length) {
        answers[nextQuestion.id] = 0;
        continue;
      }

      const chosenIndex = Math.floor(Math.random() * nextQuestion.choices.length);
      answers[nextQuestion.id] = chosenIndex;
      const chosen = nextQuestion.choices[chosenIndex];
      if (chosen?.concept) concepts.push(chosen.concept);
      const effects = (chosen?.effects ?? {}) as Record<string, unknown>;
      const hint = effects.location_hint;
      if (!startingLocation && typeof hint === 'string' && hint.trim()) {
        startingLocation = hint.trim();
      }
    }

    return { answers, concepts, startingLocation };
  }

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

  async function submitSetupRequest(request: SetupAutoRequest): Promise<void> {
    const result = await setupAuto(request);
    campaignId.set(result.campaign_id);
    playerId.set(result.player_id);
    const sheetName = (result.character_sheet?.name as string | undefined) || $charName.trim();
    generatedName = sheetName;
    setupResult = result;
    creationStep.set(999);
  }

  // Phase 1: Generate character + campaign, then show the sheet for review.
  async function beginAdventure() {
    if (!$charName.trim()) return;
    isSubmitting = true;
    errorMessage = '';

    try {
      // Build concept from answers
      const concepts: string[] = [];
      let startingLocation: string | null = null;

      if (useBackgrounds && $selectedBackground) {
        for (const q of activeQuestions) {
          const choiceIdx = $backgroundAnswers[q.id];
          if (choiceIdx !== undefined && q.choices[choiceIdx]) {
            const choice = q.choices[choiceIdx];
            if (choice.concept) concepts.push(choice.concept);
            const effects = (choice as any).effects ?? {};
            if (effects.location_hint && !startingLocation) {
              startingLocation = effects.location_hint;
            }
          }
        }
      } else {
        for (const [qIdx, cIdx] of Object.entries(cyoaAnswerIndices)) {
          const q = CYOA_QUESTIONS[Number(qIdx)];
          if (q) {
            const choice = q.choices[cIdx];
            if (choice) concepts.push(choice.concept);
          }
        }
      }

      const bgAnswersForApi: Record<string, number> = {};
      for (const [qId, cIdx] of Object.entries($backgroundAnswers)) {
        bgAnswersForApi[qId] = cIdx;
      }

      const request: SetupAutoRequest = {
        setting_id: $charSettingId,
        period_id: $charPeriodId ?? $charEra.toLowerCase(),
        time_period: $charEra,
        genre: null,
        themes: [],
        player_concept: concepts.join('; ') || $charName.trim(),
        starting_location: startingLocation,
        randomize_starting_location: !startingLocation,
        background_id: $selectedBackground?.id ?? null,
        background_answers: bgAnswersForApi,
        player_gender: $charGender,
        player_profile_id: continueSagaContext?.player_profile_id ?? null,
        legacy_id: continueSagaContext?.legacy_id ?? null,
        saga_id: continueSagaContext?.saga_id ?? null,
        difficulty: selectedDifficulty,
        species_id: $charSpecies ?? null,
      };

      await submitSetupRequest(request);
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : String(e);
    } finally {
      isSubmitting = false;
    }
  }

  async function quickStartAdventure() {
    if (isSubmitting || isStartingAdventure) return;
    isSubmitting = true;
    errorMessage = '';

    try {
      const preferredEra = ERA_OPTIONS.find((o) => o.value === 'REBELLION') ?? ERA_OPTIONS[0];
      if (!preferredEra) {
        throw new Error('No playable era is available for Quick Start.');
      }

      const quickName = randomName();
      const quickGender: 'male' | 'female' = Math.random() < 0.5 ? 'male' : 'female';
      const quickPeriodId = preferredEra.value.toLowerCase();

      charName.set(quickName);
      charGender.set(quickGender);
      charEra.set(preferredEra.value);
      charPeriodId.set(quickPeriodId);
      charSettingId.set(preferredEra.settingId);
      selectedDifficulty = 'normal';

      const [bgResp, speciesResp] = await Promise.all([
        getEraBackgrounds(preferredEra.value).catch(() => ({ backgrounds: [] as EraBackground[] })),
        getEraSpecies(preferredEra.value).catch(() => ({ species: [] as EraSpecies[] })),
      ]);

      const backgrounds = bgResp.backgrounds ?? [];
      const speciesList = speciesResp.species ?? [];
      eraBackgrounds.set(backgrounds);
      eraSpecies.set(speciesList);

      const pickedBackground = randomItem(backgrounds);
      const pickedSpecies = randomItem(speciesList);
      selectedBackground.set(pickedBackground ?? null);
      charSpecies.set(pickedSpecies?.id ?? null);

      let quickAnswers: Record<string, number> = {};
      let concepts: string[] = [];
      let startingLocation: string | null = null;
      if (pickedBackground) {
        const built = buildQuickStartBackgroundSelections(pickedBackground);
        quickAnswers = built.answers;
        concepts = built.concepts;
        startingLocation = built.startingLocation;
      }
      backgroundAnswers.set(quickAnswers);

      if (!concepts.length) {
        concepts = ['A determined wanderer stepping into a dangerous opportunity.'];
      }

      const request: SetupAutoRequest = {
        setting_id: preferredEra.settingId,
        period_id: quickPeriodId,
        time_period: preferredEra.value,
        genre: null,
        themes: [],
        player_concept: concepts.join('; '),
        starting_location: startingLocation,
        randomize_starting_location: !startingLocation,
        background_id: pickedBackground?.id ?? null,
        background_answers: quickAnswers,
        player_gender: quickGender,
        player_profile_id: continueSagaContext?.player_profile_id ?? null,
        legacy_id: continueSagaContext?.legacy_id ?? null,
        saga_id: continueSagaContext?.saga_id ?? null,
        difficulty: 'normal',
        species_id: pickedSpecies?.id ?? null,
        quick_start: true,
      };

      await submitSetupRequest(request);
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : String(e);
    } finally {
      isSubmitting = false;
    }
  }

  // Phase 2: Optionally rename, then run the opening turn and enter play.
  async function startAdventure() {
    if (!setupResult) return;
    isStartingAdventure = true;
    errorMessage = '';

    try {
      const cid = setupResult.campaign_id;
      const pid = setupResult.player_id;
      const sheetName = (setupResult.character_sheet?.name as string | undefined) || '';

      // Patch name in DB if the player changed it.
      const trimmedName = generatedName.trim();
      if (trimmedName && trimmedName !== sheetName) {
        await patchCharacterName(cid, pid, trimmedName);
      }

      // Save campaign to local registry (use confirmed name).
      saveCampaign({
        campaignId: cid,
        playerId: pid,
        playerName: trimmedName || sheetName || $charName.trim(),
        era: ($charPeriodId ?? $charEra).toUpperCase(),
        background: $selectedBackground?.name ?? null,
        sagaId: (setupResult as any).saga_id ?? null,
        sagaChapter: (setupResult as any).saga_chapter ?? null,
        createdAt: new Date().toISOString(),
        lastPlayedAt: new Date().toISOString(),
        turnCount: 0,
      });

      // Run the opening turn.
      if ($ui.enableStreaming) {
        startStreaming();
        try {
          let finalResponse = null;
          for await (const event of streamTurn(cid, pid, '[OPENING_SCENE]')) {
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
          resetStreaming();
        } catch (e) {
          failStreaming(String(e));
        }
      } else {
        const turnResult = await runTurn(cid, pid, '[OPENING_SCENE]');
        lastTurnResponse.set(turnResult);
      }

      // Route to prologue if prologue_mode is active, otherwise straight to play
      goto((setupResult as any).prologue_mode ? '/prologue' : '/play');
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : String(e);
    } finally {
      isStartingAdventure = false;
    }
  }

  function backToMenu() {
    resetCreation();
    goto('/');
  }
</script>

<div class="creation-container">
  <div class="creation-content">
    {#if continueSagaContext?.saga_id}
      <div class="saga-banner card" role="status" aria-live="polite">
        <div class="saga-banner-title">{sagaBannerLabel}</div>
        <div class="saga-banner-sub">Legacy context will carry into this campaign's opening threads.</div>
      </div>
    {/if}

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
          <p class="field-label" id="gender-label">Gender</p>
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
          <p class="field-label" id="era-label">Choose Your Era</p>
          <div class="era-cards" role="group" aria-labelledby="era-label">
            {#each ERA_OPTIONS as option}
              <button
                class="card era-card"
                class:selected={$charEra === option.value}
                onclick={() => {
                  charEra.set(option.value);
                  charPeriodId.set(option.value.toLowerCase());
                  charSettingId.set(option.settingId);
                  selectedBackground.set(null);
                  backgroundAnswers.set({});
                }}
              >
                <div class="era-name">{option.label}</div>
                {#if ERA_DESCRIPTIONS[option.value]}
                  <div class="era-desc">{ERA_DESCRIPTIONS[option.value]}</div>
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
            disabled={isSubmitting}
            onclick={quickStartAdventure}
          >{isSubmitting ? 'Setting up...' : 'Quick Start'}</button>
          <button
            class="btn btn-primary"
            disabled={!$charName.trim() || isSubmitting}
            onclick={nextStep}
          >Continue</button>
        </div>
      </div>

    <!-- ====================== STEP 1: Species Selection (Phase 0.7 — when era has species) ====================== -->
    {:else if $creationStep === speciesStepIdx && hasSpecies}
      <div class="step fade-in">
        <h2>Choose Your Species</h2>
        <p class="step-subtitle">Your species shapes your abilities, appearance, and how the galaxy sees you</p>

        {#if $loadingSpecies}
          <div class="loading-indicator">
            <div class="loading-spinner"></div>
            <span>Loading species...</span>
          </div>
        {:else}
          <div class="species-grid">
            {#each $eraSpecies as sp}
              <SpeciesCard
                species={sp}
                selected={$charSpecies === sp.id}
                onclick={() => charSpecies.set(sp.id)}
              />
            {/each}
          </div>
        {/if}

        <div class="step-actions">
          <button class="btn" onclick={prevStep}>Back</button>
          <button
            class="btn btn-primary"
            onclick={nextStep}
          >Continue{$charSpecies ? '' : ' (skip)'}</button>
        </div>
      </div>

    <!-- ====================== Background Selection (if era has them) ====================== -->
    {:else if $creationStep === backgroundStepIdx && useBackgrounds}
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

    <!-- ====================== Background Questions (dynamic branching) ====================== -->
    {:else if useBackgrounds && $selectedBackground && $creationStep > backgroundStepIdx && $creationStep < backgroundStepIdx + 1 + activeQuestions.length}
      {@const qIdx = $creationStep - backgroundStepIdx - 1}
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
    {:else if !useBackgrounds && $creationStep >= 1 && $creationStep <= CYOA_QUESTIONS.length + (hasSpecies ? 1 : 0)}
      {@const questionIdx = $creationStep - 1 - (hasSpecies ? 1 : 0)}
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
    {:else if setupResult}
      <!-- ===== CHARACTER SHEET REVEAL (phase 2 — after setupAuto returns) ===== -->
      <div class="step fade-in">
        <h2>Meet Your Character</h2>
        <p class="step-subtitle">Review what the galaxy made of you — rename if needed, then begin.</p>

        <div class="sheet-card card">
          <!-- Name (editable) -->
          <div class="sheet-section">
            <label class="sheet-label" for="sheet-name">Name</label>
            <div class="name-row">
              <input
                id="sheet-name"
                type="text"
                bind:value={generatedName}
                maxlength="60"
                placeholder="Character name..."
              />
            </div>
          </div>

          <!-- Background prose -->
          {#if setupResult.character_sheet?.background}
            <div class="sheet-section">
              <div class="sheet-label">Background</div>
              <p class="sheet-background">{setupResult.character_sheet.background as string}</p>
            </div>
          {/if}

          <!-- Stats -->
          {#if setupResult.character_sheet?.stats && typeof setupResult.character_sheet.stats === 'object'}
            <div class="sheet-section">
              <div class="sheet-label">Attributes</div>
              <div class="sheet-stats">
                {#each Object.entries(setupResult.character_sheet.stats as Record<string, number>) as [stat, val]}
                  <div class="stat-pill">
                    <span class="stat-name">{stat}</span>
                    <span class="stat-val">{val}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- HP + Location -->
          <div class="sheet-meta">
            {#if setupResult.character_sheet?.hp_current !== undefined}
              <div class="sheet-meta-item">
                <span class="sheet-label">HP</span>
                <span class="sheet-meta-val">{setupResult.character_sheet.hp_current as number}</span>
              </div>
            {/if}
            {#if setupResult.character_sheet?.starting_location}
              <div class="sheet-meta-item">
                <span class="sheet-label">Starting Location</span>
                <span class="sheet-meta-val">
                  {((setupResult.character_sheet.starting_location as string) || '').replace('loc-', '').replace(/-/g, ' ')}
                </span>
              </div>
            {/if}
            {#if setupResult.character_sheet?.starting_planet}
              <div class="sheet-meta-item">
                <span class="sheet-label">Planet</span>
                <span class="sheet-meta-val">{setupResult.character_sheet.starting_planet as string}</span>
              </div>
            {/if}
          </div>
        </div>

        {#if errorMessage}
          <div class="error-banner">{errorMessage}</div>
        {/if}

        <div class="step-actions">
          <button
            class="btn btn-primary"
            disabled={isStartingAdventure || !generatedName.trim()}
            onclick={startAdventure}
          >
            {isStartingAdventure ? 'Beginning story...' : 'Start Your Story'}
          </button>
        </div>
      </div>

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
            <span class="review-value">{(contentCatalog.find((c) => c.period_id.toUpperCase() === $charEra)?.period_display_name) ?? ERA_LABELS[$charEra] ?? $charEra}</span>
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

        <!-- Difficulty Selection -->
        <div class="difficulty-section">
          <h3 class="difficulty-heading">Difficulty</h3>
          <div class="difficulty-cards">
            {#each DIFFICULTY_OPTIONS as opt}
              <button
                class="card difficulty-card"
                class:selected={selectedDifficulty === opt.value}
                onclick={() => selectedDifficulty = opt.value}
              >
                <div class="difficulty-name">{opt.label}</div>
                <div class="difficulty-desc">{opt.desc}</div>
              </button>
            {/each}
          </div>
        </div>

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

  .saga-banner {
    margin-bottom: 1rem;
    padding: 0.75rem 0.9rem;
    text-align: left;
    border-color: rgba(74, 158, 255, 0.35);
    background: linear-gradient(135deg, rgba(74, 158, 255, 0.10), rgba(20, 30, 55, 0.20));
  }
  .saga-banner-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--text-heading);
    letter-spacing: 0.2px;
  }
  .saga-banner-sub {
    margin-top: 0.2rem;
    font-size: var(--font-small);
    color: var(--text-secondary);
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
  .form-field > label,
  .form-field > .field-label {
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
  /* Phase 0.7: Species selection grid */
  .species-grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
    text-align: left;
    max-height: 420px;
    overflow-y: auto;
  }

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

  /* Difficulty section */
  .difficulty-section {
    margin-top: 1.5rem;
    text-align: center;
  }
  .difficulty-heading {
    font-size: 1rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.75rem;
  }
  .difficulty-cards {
    display: flex;
    gap: 8px;
    justify-content: center;
  }
  .difficulty-card {
    flex: 1;
    max-width: 180px;
    padding: 12px 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: center;
  }
  .difficulty-card:hover {
    border-color: var(--choice-hover-border);
    transform: translateY(-1px);
  }
  .difficulty-card.selected {
    border-color: var(--accent);
    background: var(--choice-selected-bg, rgba(74, 158, 255, 0.1));
  }
  .difficulty-name {
    font-weight: 700;
    color: var(--text-primary);
    font-size: 1rem;
    margin-bottom: 4px;
  }
  .difficulty-desc {
    font-size: var(--font-small);
    color: var(--text-secondary);
    line-height: 1.3;
  }

  /* ===== Character sheet reveal ===== */
  .sheet-card {
    text-align: left;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .sheet-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sheet-label {
    font-size: var(--font-caption);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .sheet-background {
    font-size: var(--font-body);
    color: var(--text-primary);
    line-height: 1.55;
    margin: 0;
    font-style: italic;
  }
  .sheet-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .stat-pill {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: var(--hud-pill-bg);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 52px;
  }
  .stat-name {
    font-size: var(--font-caption);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .stat-val {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--accent-primary);
  }
  .sheet-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .sheet-meta-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .sheet-meta-val {
    font-size: var(--font-body);
    color: var(--text-primary);
    text-transform: capitalize;
  }
</style>
