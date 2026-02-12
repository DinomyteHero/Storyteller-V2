/**
 * Character creation store — wizard step state.
 *
 * Memory only — discarded after campaign setup completes.
 */
import { writable, derived } from 'svelte/store';
import type { EraBackground } from '$lib/api/types';

/** Current wizard step index. */
export const creationStep = writable(0);

/** Character name. */
export const charName = writable('');

/** Character gender. */
export const charGender = writable<'male' | 'female'>('male');

/** Selected era ID (legacy compatibility). */
export const charEra = writable('REBELLION');

/** Selected setting ID (dynamic catalog). */
export const charSettingId = writable<string | null>(null);

/** Selected period ID (dynamic catalog). */
export const charPeriodId = writable<string | null>(null);

/** Selected background (from era pack). */
export const selectedBackground = writable<EraBackground | null>(null);

/** Background question answers: { questionId: choiceIndex }. */
export const backgroundAnswers = writable<Record<string, number>>({});

/** CYOA answers (generic fallback questions): { questionIndex: choiceIndex }. */
export const cyoaAnswers = writable<Record<string, string>>({});

/** Player concept string (built from choices). */
export const playerConcept = writable('');

/** Available era backgrounds (fetched from API). */
export const eraBackgrounds = writable<EraBackground[]>([]);

/** Whether backgrounds are currently loading. */
export const loadingBackgrounds = writable(false);

/** Derived: whether the creation form is valid enough to proceed. */
export const canBeginAdventure = derived(
  [charName, charEra],
  ([$name, $era]) => $name.trim().length > 0 && $era.length > 0
);

/** Reset all creation state. */
export function resetCreation(): void {
  creationStep.set(0);
  charName.set('');
  charGender.set('male');
  charEra.set('REBELLION');
  charSettingId.set(null);
  charPeriodId.set(null);
  selectedBackground.set(null);
  backgroundAnswers.set({});
  cyoaAnswers.set({});
  playerConcept.set('');
  eraBackgrounds.set([]);
  loadingBackgrounds.set(false);
}
