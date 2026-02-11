/**
 * Character creation utilities — ported from the legacy Python UI.
 *
 * Handles background question condition evaluation and random name generation.
 */
import type { BackgroundQuestion, BackgroundChoice, EraBackground } from '$lib/api/types';

/**
 * Evaluate a background question condition like 'loyalty.tone == PARAGON'.
 * Returns true if the condition passes (question should be shown).
 */
export function evaluateCondition(
  condition: string | null,
  answers: Record<string, number>,
  questions: BackgroundQuestion[]
): boolean {
  if (!condition) return true;
  try {
    const parts = condition.split('.');
    if (parts.length !== 2) return true;
    const qId = parts[0];
    const fieldCheck = parts[1]; // e.g., "tone == PARAGON"

    for (const q of questions) {
      if (q.id === qId) {
        const choiceIdx = answers[qId];
        if (choiceIdx === undefined) return false;
        const choice = q.choices[choiceIdx];
        if (!choice) return false;
        if (fieldCheck.includes('==')) {
          const [field, expected] = fieldCheck.split('==').map((s) => s.trim());
          const actual = String((choice as unknown as Record<string, unknown>)[field] ?? '').toUpperCase();
          return actual === expected.toUpperCase();
        }
        return true;
      }
    }
    return true;
  } catch {
    return true;
  }
}

/**
 * Get the active (visible) background questions based on current answers.
 * Questions with conditions that don't pass are filtered out.
 */
export function getActiveBackgroundQuestions(
  background: EraBackground,
  answers: Record<string, number>
): BackgroundQuestion[] {
  return (background.questions ?? []).filter((q) =>
    evaluateCondition(q.condition, answers, background.questions ?? [])
  );
}

/** Random first names for name generation. */
const FIRST_NAMES = [
  'Kira', 'Dax', 'Jace', 'Mara', 'Tycho', 'Nomi', 'Cade', 'Jaina',
  'Corran', 'Tahiri', 'Kyle', 'Bastila', 'Revan', 'Meetra', 'Carth',
];

/** Random last names for name generation. */
const LAST_NAMES = [
  'Sunrider', 'Durron', 'Katarn', 'Jade', 'Antilles', 'Skywalker',
  'Solo', 'Fel', 'Horn', 'Shan', 'Onasi', 'Veila', 'Bel Iblis',
];

/** Generate a random Star Wars-ish character name. */
export function randomName(): string {
  const first = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
  const last = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
  return `${first} ${last}`;
}

/** Era descriptions for the selection cards (synced with backend era packs). */
export const ERA_DESCRIPTIONS: Record<string, string> = {
  REBELLION: 'Imperial oppression, Rebel Alliance, underdog resistance (0-4 ABY)',
  NEW_REPUBLIC: "Post-Empire rebuilding, Thrawn's return, fragile peace (5-19 ABY)",
  NEW_JEDI_ORDER: 'Yuuzhan Vong invasion, galaxy under siege, desperate survival (25-29 ABY)',
  LEGACY: "Darth Krayt's Sith Empire, three-way war, shattered galaxy (130-138 ABY)",
  DARK_TIMES: 'Jedi Purge, Order 66 aftermath, Empire rises, hope fades (19-0 BBY)',
  KOTOR: 'Ancient Old Republic, Jedi-Sith eternal conflict, Force mysteries (~3954 BBY)',
};
