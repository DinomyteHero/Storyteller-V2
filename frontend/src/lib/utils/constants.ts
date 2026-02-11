/**
 * UI constants — ported from streamlit_app.py.
 */

/** Display names for raw location IDs. */
export const LOCATION_DISPLAY_NAMES: Record<string, string> = {
  'loc-cantina': 'Cantina',
  'loc-tavern': 'Cantina',
  'loc-marketplace': 'Marketplace',
  'loc-market': 'Marketplace',
  'loc-docking-bay': 'Docking Bay',
  'loc-docks': 'Docking Bay',
  'loc-lower-streets': 'Lower Streets',
  'loc-street': 'Lower Streets',
  'loc-hangar': 'Hangar Bay',
  'loc-spaceport': 'Spaceport',
  'loc-command-center': 'Command Center',
  'loc-med-bay': 'Med Bay',
  'loc-jedi-temple': 'Jedi Temple',
};

/** Human-friendly era names (synced with backend era packs). */
export const ERA_LABELS: Record<string, string> = {
  REBELLION: 'Age of Rebellion',
  NEW_REPUBLIC: 'New Republic',
  NEW_JEDI_ORDER: 'New Jedi Order',
  LEGACY: 'Legacy',
  DARK_TIMES: 'The Dark Times',
  KOTOR: 'Knights of the Old Republic',
  // Removed: ERA_AGNOSTIC, OLD_REPUBLIC, HIGH_REPUBLIC, CLONE_WARS, CUSTOM (not implemented in backend)
};

/** Default era for new campaigns. */
export const DEFAULT_ERA = 'REBELLION';

/** Tone tag icon characters. */
export const TONE_ICONS: Record<string, string> = {
  PARAGON: '◇',
  INVESTIGATE: '◈',
  RENEGADE: '☠',
  NEUTRAL: '◯',
};

/** Tone tag display labels. */
export const TONE_LABELS: Record<string, string> = {
  PARAGON: 'Paragon',
  INVESTIGATE: 'Investigate',
  RENEGADE: 'Renegade',
  NEUTRAL: 'Neutral',
};

/** CYOA character creation questions (fallback when no era background). */
export const CYOA_QUESTIONS = [
  {
    title: 'What drives you?',
    subtitle: 'This shapes your personality and approach',
    choices: [
      { label: 'Justice and protecting the innocent', concept: 'driven by justice', tone: 'PARAGON' },
      { label: 'Knowledge and understanding the Force', concept: 'seeker of forbidden knowledge', tone: 'INVESTIGATE' },
      { label: 'Survival — the galaxy owes you nothing', concept: 'a survivor who trusts no one', tone: 'RENEGADE' },
      { label: 'Credits and the thrill of the deal', concept: 'lives for the next score', tone: 'NEUTRAL' },
    ],
  },
  {
    title: 'Where did you come from?',
    subtitle: 'This determines your starting location and background',
    choices: [
      { label: 'The underworld', concept: 'raised among smugglers and outcasts', tone: 'RENEGADE' },
      { label: 'Military service', concept: 'veteran of military service', tone: 'NEUTRAL' },
      { label: 'The spacelanes', concept: 'a spacer who never called one place home', tone: 'INVESTIGATE' },
      { label: 'A quiet world — until it wasn\'t', concept: 'from a peaceful world shattered by conflict', tone: 'PARAGON' },
    ],
  },
  {
    title: 'What happened that changed everything?',
    subtitle: 'This seeds your story\'s opening thread',
    choices: [
      { label: 'I lost someone. I need answers.', concept: 'haunted by a loss that demands answers', tone: 'PARAGON' },
      { label: 'I saw something I shouldn\'t have.', concept: 'carrying a dangerous secret', tone: 'INVESTIGATE' },
      { label: 'I have a debt that can\'t be paid in credits.', concept: 'bound by an unpayable obligation', tone: 'NEUTRAL' },
      { label: 'Everything was taken from me.', concept: 'forged by loss into something harder', tone: 'RENEGADE' },
    ],
  },
  {
    title: 'What\'s your edge?',
    subtitle: 'This gives you a starting advantage',
    choices: [
      { label: 'I can talk my way out of anything', concept: 'silver-tongued negotiator', tone: 'PARAGON' },
      { label: 'I\'m handy with a blaster', concept: 'deadly accurate in a firefight', tone: 'RENEGADE' },
      { label: 'I know how to disappear', concept: 'a ghost when they need to be', tone: 'NEUTRAL' },
      { label: 'I can fix or hack anything', concept: 'a technical genius', tone: 'INVESTIGATE' },
    ],
  },
];
