/**
 * Onboarding tutorial state — tracks which steps have been shown.
 *
 * Persisted to localStorage so the tutorial only shows once per browser.
 */
import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

const STORAGE_KEY = 'storyteller-onboarding';

export interface OnboardingState {
  completed: boolean;
  currentStep: number;
  dismissed: boolean;
}

export interface TutorialStep {
  id: string;
  title: string;
  description: string;
  targetSelector: string;
  position: 'top' | 'bottom' | 'left' | 'right';
}

export const TUTORIAL_STEPS: TutorialStep[] = [
  {
    id: 'narrative',
    title: 'The Story Unfolds Here',
    description:
      'This is your narrative panel. Each turn, the AI weaves a new chapter of your adventure. Read carefully — choices have consequences.',
    targetSelector: '.narrative-container',
    position: 'bottom',
  },
  {
    id: 'approaches',
    title: 'Choose Your Approach',
    description:
      'These cards suggest different ways to act. Blue is heroic, yellow investigates, red is aggressive. Click a card to use it as your starting point.',
    targetSelector: '.approach-cards-wrap',
    position: 'top',
  },
  {
    id: 'forge',
    title: 'Forge Your Own Path',
    description:
      'Press 5 or F to write your own action. You\'re not limited to the suggestions — type anything you want your character to do.',
    targetSelector: '.forge-panel',
    position: 'top',
  },
  {
    id: 'hud',
    title: 'Your Status at a Glance',
    description:
      'The HUD shows your location, health, credits, and stress. Keep an eye on these — they affect what happens in the story.',
    targetSelector: '.hud-bar',
    position: 'bottom',
  },
  {
    id: 'drawer',
    title: 'Character & World Info',
    description:
      'Click the menu icon to open the info drawer. Here you\'ll find your character sheet, companions, quests, factions, and intel.',
    targetSelector: '.hud-hamburger',
    position: 'bottom',
  },
];

function loadState(): OnboardingState {
  if (!browser) return { completed: false, currentStep: 0, dismissed: false };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return { completed: false, currentStep: 0, dismissed: false, ...parsed };
    }
  } catch {
    // Ignore corrupt data
  }
  return { completed: false, currentStep: 0, dismissed: false };
}

function saveState(state: OnboardingState): void {
  if (!browser) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore quota errors
  }
}

function createOnboardingStore() {
  const initial = loadState();
  const { subscribe, set, update } = writable<OnboardingState>(initial);

  subscribe((val) => saveState(val));

  return {
    subscribe,

    /** Start the tutorial from step 0 */
    start() {
      update((s) => ({ ...s, currentStep: 0, dismissed: false, completed: false }));
    },

    /** Advance to the next step, or mark complete if at end */
    nextStep() {
      update((s) => {
        const next = s.currentStep + 1;
        if (next >= TUTORIAL_STEPS.length) {
          return { ...s, completed: true, currentStep: next };
        }
        return { ...s, currentStep: next };
      });
    },

    /** Go back to previous step */
    prevStep() {
      update((s) => ({
        ...s,
        currentStep: Math.max(0, s.currentStep - 1),
      }));
    },

    /** Dismiss (skip) the entire tutorial */
    dismiss() {
      update((s) => ({ ...s, dismissed: true, completed: true }));
    },

    /** Reset for replay */
    reset() {
      set({ completed: false, currentStep: 0, dismissed: false });
    },
  };
}

export const onboarding = createOnboardingStore();

/** Whether the tutorial overlay should be visible */
export const showTutorial = derived(onboarding, ($s) => !$s.completed && !$s.dismissed);
