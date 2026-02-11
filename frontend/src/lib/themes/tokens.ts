/**
 * Theme token system — ported from ui/themes.py.
 *
 * Each theme defines CSS custom property values. The active theme class
 * is set on <body> and all components read from var(--xxx).
 */

export interface ThemeTokens {
  name: string;
  className: string;

  // Backgrounds
  bgApp: string;
  bgPanel: string;
  bgInput: string;
  bgOverlay: string;

  // Borders
  borderPanel: string;
  borderAccent: string;
  borderSubtle: string;

  // Text
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textHeading: string;

  // Accents
  accentPrimary: string;
  accentSecondary: string;
  accentGlow: string;
  accentDanger: string;

  // HUD
  hudPillBg: string;
  hudPillBorder: string;
  hudScanlineOpacity: string;

  // Choice cards
  choiceHoverBorder: string;
  choiceHoverGlow: string;

  // Tone colors
  toneParagon: string;
  toneInvestigate: string;
  toneRenegade: string;
  toneNeutral: string;

  // Typography
  fontNarrative: string;
  fontBody: string;
  fontCaption: string;
  fontHeading: string;
  fontSmall: string;
  lineHeightNarrative: string;

  // Spacing
  panelRadius: string;
  panelPadding: string;
}

export const CLEAN_DARK: ThemeTokens = {
  name: 'Clean Dark',
  className: 'theme-clean-dark',
  bgApp: 'linear-gradient(180deg, #1a1a1a 0%, #2d2d2d 100%)',
  bgPanel: 'rgba(40, 40, 45, 0.95)',
  bgInput: 'rgba(30, 30, 35, 0.95)',
  bgOverlay: 'rgba(20, 20, 25, 0.98)',
  borderPanel: 'rgba(100, 100, 110, 0.4)',
  borderAccent: 'rgba(80, 150, 255, 0.6)',
  borderSubtle: 'rgba(80, 80, 90, 0.25)',
  textPrimary: 'rgba(255, 255, 255, 0.95)',
  textSecondary: 'rgba(200, 200, 210, 0.95)',
  textMuted: 'rgba(150, 150, 160, 0.8)',
  textHeading: 'rgba(120, 180, 255, 1.0)',
  accentPrimary: 'rgba(80, 150, 255, 1.0)',
  accentSecondary: 'rgba(100, 130, 200, 0.9)',
  accentGlow: 'rgba(80, 150, 255, 0.3)',
  accentDanger: 'rgba(255, 90, 90, 1.0)',
  hudPillBg: 'rgba(50, 50, 55, 0.8)',
  hudPillBorder: 'rgba(100, 100, 110, 0.4)',
  hudScanlineOpacity: '0.0',
  choiceHoverBorder: 'rgba(80, 150, 255, 0.8)',
  choiceHoverGlow: '0 0 12px rgba(80, 150, 255, 0.4)',
  toneParagon: 'rgba(100, 170, 255, 0.95)',
  toneInvestigate: 'rgba(255, 210, 70, 0.95)',
  toneRenegade: 'rgba(255, 85, 65, 0.95)',
  toneNeutral: 'rgba(180, 180, 190, 0.85)',
  fontNarrative: '1.06rem',
  fontBody: '0.95rem',
  fontCaption: '0.85rem',
  fontHeading: '1.15rem',
  fontSmall: '0.78rem',
  lineHeightNarrative: '1.65',
  panelRadius: '12px',
  panelPadding: '16px 18px',
};

export const REBEL_AMBER: ThemeTokens = {
  name: 'Rebel Amber',
  className: 'theme-rebel-amber',
  bgApp:
    'radial-gradient(1200px 900px at 20% 0%, rgba(255, 160, 0, 0.10), transparent 60%),' +
    'radial-gradient(900px 700px at 90% 20%, rgba(255, 100, 0, 0.06), transparent 55%),' +
    'linear-gradient(180deg, #0a0806 0%, #0d0a07 45%, #0a0806 100%)',
  bgPanel: 'rgba(16, 12, 8, 0.75)',
  bgInput: 'rgba(20, 15, 10, 0.60)',
  bgOverlay: 'rgba(10, 8, 5, 0.92)',
  borderPanel: 'rgba(255, 160, 0, 0.20)',
  borderAccent: 'rgba(255, 180, 40, 0.35)',
  borderSubtle: 'rgba(255, 160, 0, 0.08)',
  textPrimary: 'rgba(255, 240, 220, 0.95)',
  textSecondary: 'rgba(210, 185, 150, 0.90)',
  textMuted: 'rgba(160, 140, 110, 0.60)',
  textHeading: 'rgba(255, 200, 100, 0.95)',
  accentPrimary: 'rgba(255, 170, 40, 0.90)',
  accentSecondary: 'rgba(200, 130, 20, 0.80)',
  accentGlow: 'rgba(255, 160, 0, 0.15)',
  accentDanger: 'rgba(255, 80, 60, 0.90)',
  hudPillBg: 'rgba(20, 14, 6, 0.55)',
  hudPillBorder: 'rgba(255, 160, 0, 0.18)',
  hudScanlineOpacity: '0.06',
  choiceHoverBorder: 'rgba(255, 180, 40, 0.40)',
  choiceHoverGlow: '0 0 20px rgba(255, 160, 0, 0.12)',
  toneParagon: 'rgba(100, 180, 255, 0.90)',
  toneInvestigate: 'rgba(255, 200, 60, 0.90)',
  toneRenegade: 'rgba(255, 80, 50, 0.90)',
  toneNeutral: 'rgba(200, 180, 150, 0.80)',
  fontNarrative: '1.06rem',
  fontBody: '0.95rem',
  fontCaption: '0.85rem',
  fontHeading: '1.15rem',
  fontSmall: '0.78rem',
  lineHeightNarrative: '1.65',
  panelRadius: '12px',
  panelPadding: '16px 18px',
};

export const ALLIANCE_BLUE: ThemeTokens = {
  name: 'Alliance Blue',
  className: 'theme-alliance-blue',
  bgApp:
    'radial-gradient(1200px 900px at 20% 0%, rgba(0, 210, 255, 0.10), transparent 60%),' +
    'radial-gradient(900px 700px at 90% 20%, rgba(100, 180, 255, 0.06), transparent 55%),' +
    'linear-gradient(180deg, #050912 0%, #070c14 45%, #050812 100%)',
  bgPanel: 'rgba(10, 16, 28, 0.70)',
  bgInput: 'rgba(8, 14, 24, 0.60)',
  bgOverlay: 'rgba(5, 9, 18, 0.92)',
  borderPanel: 'rgba(0, 210, 255, 0.22)',
  borderAccent: 'rgba(60, 200, 255, 0.35)',
  borderSubtle: 'rgba(0, 210, 255, 0.08)',
  textPrimary: 'rgba(240, 248, 255, 0.95)',
  textSecondary: 'rgba(160, 195, 220, 0.90)',
  textMuted: 'rgba(100, 140, 170, 0.60)',
  textHeading: 'rgba(120, 220, 255, 0.95)',
  accentPrimary: 'rgba(0, 200, 255, 0.90)',
  accentSecondary: 'rgba(60, 160, 220, 0.80)',
  accentGlow: 'rgba(0, 210, 255, 0.15)',
  accentDanger: 'rgba(255, 80, 80, 0.90)',
  hudPillBg: 'rgba(2, 12, 18, 0.55)',
  hudPillBorder: 'rgba(0, 210, 255, 0.18)',
  hudScanlineOpacity: '0.08',
  choiceHoverBorder: 'rgba(60, 200, 255, 0.40)',
  choiceHoverGlow: '0 0 20px rgba(0, 210, 255, 0.12)',
  toneParagon: 'rgba(120, 200, 255, 0.90)',
  toneInvestigate: 'rgba(255, 220, 80, 0.90)',
  toneRenegade: 'rgba(255, 90, 70, 0.90)',
  toneNeutral: 'rgba(160, 190, 210, 0.80)',
  fontNarrative: '1.06rem',
  fontBody: '0.95rem',
  fontCaption: '0.85rem',
  fontHeading: '1.15rem',
  fontSmall: '0.78rem',
  lineHeightNarrative: '1.65',
  panelRadius: '12px',
  panelPadding: '16px 18px',
};

export const HOLOCRON_ARCHIVE: ThemeTokens = {
  name: 'Holocron Archive',
  className: 'theme-holocron-archive',
  bgApp:
    'radial-gradient(1200px 900px at 50% 0%, rgba(180, 150, 100, 0.08), transparent 60%),' +
    'linear-gradient(180deg, #1a1610 0%, #1e1a14 45%, #1a1610 100%)',
  bgPanel: 'rgba(28, 24, 18, 0.85)',
  bgInput: 'rgba(22, 18, 12, 0.70)',
  bgOverlay: 'rgba(15, 12, 8, 0.95)',
  borderPanel: 'rgba(160, 130, 80, 0.25)',
  borderAccent: 'rgba(200, 170, 100, 0.40)',
  borderSubtle: 'rgba(140, 110, 60, 0.12)',
  textPrimary: 'rgba(230, 220, 200, 0.95)',
  textSecondary: 'rgba(190, 175, 150, 0.90)',
  textMuted: 'rgba(150, 135, 110, 0.65)',
  textHeading: 'rgba(220, 200, 150, 0.95)',
  accentPrimary: 'rgba(200, 170, 100, 0.90)',
  accentSecondary: 'rgba(170, 140, 80, 0.80)',
  accentGlow: 'rgba(180, 150, 80, 0.15)',
  accentDanger: 'rgba(200, 70, 50, 0.90)',
  hudPillBg: 'rgba(22, 18, 12, 0.60)',
  hudPillBorder: 'rgba(160, 130, 80, 0.20)',
  hudScanlineOpacity: '0.0',
  choiceHoverBorder: 'rgba(200, 170, 100, 0.45)',
  choiceHoverGlow: '0 0 16px rgba(180, 150, 80, 0.10)',
  toneParagon: 'rgba(120, 180, 220, 0.90)',
  toneInvestigate: 'rgba(220, 190, 80, 0.90)',
  toneRenegade: 'rgba(200, 70, 50, 0.90)',
  toneNeutral: 'rgba(180, 170, 150, 0.80)',
  fontNarrative: '1.1rem',
  fontBody: '0.95rem',
  fontCaption: '0.85rem',
  fontHeading: '1.15rem',
  fontSmall: '0.78rem',
  lineHeightNarrative: '1.8',
  panelRadius: '12px',
  panelPadding: '16px 18px',
};

export const THEMES: Record<string, ThemeTokens> = {
  'Clean Dark': CLEAN_DARK,
  'Rebel Amber': REBEL_AMBER,
  'Alliance Blue': ALLIANCE_BLUE,
  'Holocron Archive': HOLOCRON_ARCHIVE,
};

export const DEFAULT_THEME = 'Clean Dark';

export const THEME_NAMES = Object.keys(THEMES);

/**
 * Convert a ThemeTokens object into a CSS string of custom property declarations.
 * Used by the layout to inject theme variables on <body>.
 */
export function themeToCssVars(theme: ThemeTokens): string {
  return `
    --bg-app: ${theme.bgApp};
    --bg-panel: ${theme.bgPanel};
    --bg-input: ${theme.bgInput};
    --bg-overlay: ${theme.bgOverlay};
    --border-panel: ${theme.borderPanel};
    --border-accent: ${theme.borderAccent};
    --border-subtle: ${theme.borderSubtle};
    --text-primary: ${theme.textPrimary};
    --text-secondary: ${theme.textSecondary};
    --text-muted: ${theme.textMuted};
    --text-heading: ${theme.textHeading};
    --accent-primary: ${theme.accentPrimary};
    --accent-secondary: ${theme.accentSecondary};
    --accent-glow: ${theme.accentGlow};
    --accent-danger: ${theme.accentDanger};
    --hud-pill-bg: ${theme.hudPillBg};
    --hud-pill-border: ${theme.hudPillBorder};
    --hud-scanline-opacity: ${theme.hudScanlineOpacity};
    --choice-hover-border: ${theme.choiceHoverBorder};
    --choice-hover-glow: ${theme.choiceHoverGlow};
    --tone-paragon: ${theme.toneParagon};
    --tone-investigate: ${theme.toneInvestigate};
    --tone-renegade: ${theme.toneRenegade};
    --tone-neutral: ${theme.toneNeutral};
    --font-narrative: ${theme.fontNarrative};
    --font-body: ${theme.fontBody};
    --font-caption: ${theme.fontCaption};
    --font-heading: ${theme.fontHeading};
    --font-small: ${theme.fontSmall};
    --line-height-narrative: ${theme.lineHeightNarrative};
    --panel-radius: ${theme.panelRadius};
    --panel-padding: ${theme.panelPadding};
  `;
}
