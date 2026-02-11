"""Theme token system for Storyteller UI.

Two built-in themes:
  - "Rebel Amber"   (warm KOTOR-style console)
  - "Alliance Blue"  (clean Mass Effect sci-fi panels)

Tokens define colors, backgrounds, borders, accents, and typography sizes.
The active theme is stored in st.session_state["theme_name"].
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThemeTokens:
    """All visual tokens needed by UI components."""

    name: str

    # Backgrounds
    bg_app: str  # radial/linear gradient for .stApp
    bg_panel: str  # panel/card background
    bg_input: str  # input field background
    bg_overlay: str  # modal/overlay background

    # Borders
    border_panel: str  # card border color (rgba)
    border_accent: str  # accent border (glow)
    border_subtle: str  # subtle dividers

    # Text
    text_primary: str  # main narrative text
    text_secondary: str  # labels, captions, meta
    text_muted: str  # disabled/placeholder
    text_heading: str  # headings, titles

    # Accents
    accent_primary: str  # main accent (buttons, active states)
    accent_secondary: str  # secondary accent
    accent_glow: str  # glow/shadow color
    accent_danger: str  # danger/warning

    # HUD-specific
    hud_pill_bg: str  # pill/tag background
    hud_pill_border: str  # pill/tag border
    hud_scanline_opacity: str  # scanline overlay opacity (0.0-1.0)

    # Choice cards
    choice_hover_border: str
    choice_hover_glow: str

    # Tone tag colors (KOTOR/ME dialogue wheel)
    tone_paragon: str = "rgba(100, 180, 255, 0.90)"
    tone_investigate: str = "rgba(255, 210, 80, 0.90)"
    tone_renegade: str = "rgba(255, 80, 60, 0.90)"
    tone_neutral: str = "rgba(180, 180, 190, 0.80)"

    # Typography sizes (rem)
    font_narrative: str = "1.06rem"
    font_body: str = "0.95rem"
    font_caption: str = "0.85rem"
    font_heading: str = "1.15rem"
    font_small: str = "0.78rem"
    line_height_narrative: str = "1.65"

    # Spacing
    panel_radius: str = "12px"
    panel_padding: str = "16px 18px"


REBEL_AMBER = ThemeTokens(
    name="Rebel Amber",
    bg_app=(
        "radial-gradient(1200px 900px at 20% 0%, rgba(255, 160, 0, 0.10), transparent 60%),"
        "radial-gradient(900px 700px at 90% 20%, rgba(255, 100, 0, 0.06), transparent 55%),"
        "linear-gradient(180deg, #0a0806 0%, #0d0a07 45%, #0a0806 100%)"
    ),
    bg_panel="rgba(16, 12, 8, 0.75)",
    bg_input="rgba(20, 15, 10, 0.60)",
    bg_overlay="rgba(10, 8, 5, 0.92)",
    border_panel="rgba(255, 160, 0, 0.20)",
    border_accent="rgba(255, 180, 40, 0.35)",
    border_subtle="rgba(255, 160, 0, 0.08)",
    text_primary="rgba(255, 240, 220, 0.95)",
    text_secondary="rgba(210, 185, 150, 0.90)",
    text_muted="rgba(160, 140, 110, 0.60)",
    text_heading="rgba(255, 200, 100, 0.95)",
    accent_primary="rgba(255, 170, 40, 0.90)",
    accent_secondary="rgba(200, 130, 20, 0.80)",
    accent_glow="rgba(255, 160, 0, 0.15)",
    accent_danger="rgba(255, 80, 60, 0.90)",
    hud_pill_bg="rgba(20, 14, 6, 0.55)",
    hud_pill_border="rgba(255, 160, 0, 0.18)",
    hud_scanline_opacity="0.06",
    choice_hover_border="rgba(255, 180, 40, 0.40)",
    choice_hover_glow="0 0 20px rgba(255, 160, 0, 0.12)",
    tone_paragon="rgba(100, 180, 255, 0.90)",
    tone_investigate="rgba(255, 200, 60, 0.90)",
    tone_renegade="rgba(255, 80, 50, 0.90)",
    tone_neutral="rgba(200, 180, 150, 0.80)",
)


ALLIANCE_BLUE = ThemeTokens(
    name="Alliance Blue",
    bg_app=(
        "radial-gradient(1200px 900px at 20% 0%, rgba(0, 210, 255, 0.10), transparent 60%),"
        "radial-gradient(900px 700px at 90% 20%, rgba(100, 180, 255, 0.06), transparent 55%),"
        "linear-gradient(180deg, #050912 0%, #070c14 45%, #050812 100%)"
    ),
    bg_panel="rgba(10, 16, 28, 0.70)",
    bg_input="rgba(8, 14, 24, 0.60)",
    bg_overlay="rgba(5, 9, 18, 0.92)",
    border_panel="rgba(0, 210, 255, 0.22)",
    border_accent="rgba(60, 200, 255, 0.35)",
    border_subtle="rgba(0, 210, 255, 0.08)",
    text_primary="rgba(240, 248, 255, 0.95)",
    text_secondary="rgba(160, 195, 220, 0.90)",
    text_muted="rgba(100, 140, 170, 0.60)",
    text_heading="rgba(120, 220, 255, 0.95)",
    accent_primary="rgba(0, 200, 255, 0.90)",
    accent_secondary="rgba(60, 160, 220, 0.80)",
    accent_glow="rgba(0, 210, 255, 0.15)",
    accent_danger="rgba(255, 80, 80, 0.90)",
    hud_pill_bg="rgba(2, 12, 18, 0.55)",
    hud_pill_border="rgba(0, 210, 255, 0.18)",
    hud_scanline_opacity="0.08",
    choice_hover_border="rgba(60, 200, 255, 0.40)",
    choice_hover_glow="0 0 20px rgba(0, 210, 255, 0.12)",
    tone_paragon="rgba(120, 200, 255, 0.90)",
    tone_investigate="rgba(255, 220, 80, 0.90)",
    tone_renegade="rgba(255, 90, 70, 0.90)",
    tone_neutral="rgba(160, 190, 210, 0.80)",
)


CLEAN_DARK = ThemeTokens(
    name="Clean Dark",
    bg_app="linear-gradient(180deg, #1a1a1a 0%, #2d2d2d 100%)",
    bg_panel="rgba(40, 40, 45, 0.95)",
    bg_input="rgba(30, 30, 35, 0.95)",
    bg_overlay="rgba(20, 20, 25, 0.98)",
    border_panel="rgba(100, 100, 110, 0.4)",
    border_accent="rgba(80, 150, 255, 0.6)",
    border_subtle="rgba(80, 80, 90, 0.25)",
    text_primary="rgba(255, 255, 255, 0.95)",
    text_secondary="rgba(200, 200, 210, 0.95)",
    text_muted="rgba(150, 150, 160, 0.8)",
    text_heading="rgba(120, 180, 255, 1.0)",
    accent_primary="rgba(80, 150, 255, 1.0)",
    accent_secondary="rgba(100, 130, 200, 0.9)",
    accent_glow="rgba(80, 150, 255, 0.3)",
    accent_danger="rgba(255, 90, 90, 1.0)",
    hud_pill_bg="rgba(50, 50, 55, 0.8)",
    hud_pill_border="rgba(100, 100, 110, 0.4)",
    hud_scanline_opacity="0.0",
    choice_hover_border="rgba(80, 150, 255, 0.8)",
    choice_hover_glow="0 0 12px rgba(80, 150, 255, 0.4)",
    tone_paragon="rgba(100, 170, 255, 0.95)",
    tone_investigate="rgba(255, 210, 70, 0.95)",
    tone_renegade="rgba(255, 85, 65, 0.95)",
    tone_neutral="rgba(180, 180, 190, 0.85)",
)


HOLOCRON_ARCHIVE = ThemeTokens(
    name="Holocron Archive",
    bg_app=(
        "radial-gradient(1200px 900px at 50% 0%, rgba(180, 150, 100, 0.08), transparent 60%),"
        "linear-gradient(180deg, #1a1610 0%, #1e1a14 45%, #1a1610 100%)"
    ),
    bg_panel="rgba(28, 24, 18, 0.85)",
    bg_input="rgba(22, 18, 12, 0.70)",
    bg_overlay="rgba(15, 12, 8, 0.95)",
    border_panel="rgba(160, 130, 80, 0.25)",
    border_accent="rgba(200, 170, 100, 0.40)",
    border_subtle="rgba(140, 110, 60, 0.12)",
    text_primary="rgba(230, 220, 200, 0.95)",
    text_secondary="rgba(190, 175, 150, 0.90)",
    text_muted="rgba(150, 135, 110, 0.65)",
    text_heading="rgba(220, 200, 150, 0.95)",
    accent_primary="rgba(200, 170, 100, 0.90)",
    accent_secondary="rgba(170, 140, 80, 0.80)",
    accent_glow="rgba(180, 150, 80, 0.15)",
    accent_danger="rgba(200, 70, 50, 0.90)",
    hud_pill_bg="rgba(22, 18, 12, 0.60)",
    hud_pill_border="rgba(160, 130, 80, 0.20)",
    hud_scanline_opacity="0.0",
    choice_hover_border="rgba(200, 170, 100, 0.45)",
    choice_hover_glow="0 0 16px rgba(180, 150, 80, 0.10)",
    tone_paragon="rgba(120, 180, 220, 0.90)",
    tone_investigate="rgba(220, 190, 80, 0.90)",
    tone_renegade="rgba(200, 70, 50, 0.90)",
    tone_neutral="rgba(180, 170, 150, 0.80)",
    # Book-like typography
    font_narrative="1.1rem",
    line_height_narrative="1.8",
    font_body="0.95rem",
)


THEMES: dict[str, ThemeTokens] = {
    "Clean Dark": CLEAN_DARK,
    "Rebel Amber": REBEL_AMBER,
    "Alliance Blue": ALLIANCE_BLUE,
    "Holocron Archive": HOLOCRON_ARCHIVE,
}

DEFAULT_THEME = "Clean Dark"


def get_theme(name: str | None = None) -> ThemeTokens:
    """Return theme tokens by name (fallback to default)."""
    if name and name in THEMES:
        return THEMES[name]
    return THEMES[DEFAULT_THEME]


def generate_css(theme: ThemeTokens, *, reduce_motion: bool = False) -> str:
    """Generate the full CSS for the Storyteller UI given a theme."""
    motion_transition = "none" if reduce_motion else "all 0.2s ease"
    typewriter_anim = "none" if reduce_motion else ""

    return f"""
<style>
/* ============ STORYTELLER THEME: {theme.name} ============ */

/* === Hide Legacy UI Header === */
header[data-testid="stHeader"] {{
    display: none;
}}
.block-container {{
    padding-top: 2rem;
}}

/* === App background === */
.stApp {{
  background: {theme.bg_app};
  color: {theme.text_primary};
}}

/* === Scrollbar === */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
  background: {theme.border_panel};
  border-radius: 3px;
}}

/* === Panel / Card === */
.st-card {{
  border: 1px solid {theme.border_panel};
  background: {theme.bg_panel};
  box-shadow: 0 0 0 1px {theme.border_subtle} inset, 0 12px 40px rgba(0,0,0,0.35);
  border-radius: {theme.panel_radius};
  padding: {theme.panel_padding};
  transition: {motion_transition};
}}
.st-card:hover {{
  border-color: {theme.border_accent};
  box-shadow: {theme.choice_hover_glow};
}}
.st-card + .st-card {{ margin-top: 10px; }}

/* === Scanline overlay === */
.st-scanline {{ position: relative; }}
.st-scanline::after {{
  content: "";
  pointer-events: none;
  position: absolute;
  inset: 0;
  border-radius: {theme.panel_radius};
  background: repeating-linear-gradient(
    180deg,
    rgba(255,255,255,0.03) 0px,
    rgba(255,255,255,0.03) 1px,
    transparent 2px,
    transparent 6px
  );
  mix-blend-mode: overlay;
  opacity: {theme.hud_scanline_opacity};
}}

/* === HUD bar === */
.st-hud-container {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
  background: {theme.bg_panel};
  border: 1px solid {theme.border_panel};
  border-radius: {theme.panel_radius};
  padding: 12px 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}}

.st-hud-group {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}}

.st-hud-divider {{
  width: 1px;
  height: 24px;
  background: {theme.border_subtle};
  margin: 0 8px;
  display: none; /* Hidden on small screens or by default if wrapping */
}}
@media (min-width: 800px) {{
  .st-hud-divider {{ display: block; }}
}}

.st-pill {{
  display: flex;
  align-items: center;
  background: rgba(0,0,0,0.2);
  border: 1px solid {theme.border_subtle};
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 0.85rem;
  color: {theme.text_secondary};
  white-space: nowrap;
}}
.st-pill strong {{
  color: {theme.text_primary};
  font-weight: 600;
  margin-right: 6px;
  text-transform: uppercase;
  font-size: 0.7rem;
  opacity: 0.8;
  letter-spacing: 0.5px;
}}
.st-pill .value {{
  font-family: 'Courier New', monospace;
  font-weight: 700;
  color: {theme.text_heading};
}}

/* === Scene / Narrative === */
.st-scene-title {{
  font-size: {theme.font_caption};
  text-transform: uppercase;
  letter-spacing: 1.4px;
  color: {theme.text_secondary};
  margin-bottom: 6px;
}}
.st-scene-text {{
  font-size: {theme.font_narrative};
  line-height: {theme.line_height_narrative};
  color: {theme.text_primary};
}}
.st-scene-text .dialogue {{
  color: {theme.text_heading};
  font-style: italic;
}}

/* === Narrative paragraphs === */
.st-scene-text p.st-narrative-para {{
  margin: 0 0 0.8em 0;
}}
.st-scene-text p.st-narrative-para:last-child {{
  margin-bottom: 0;
}}
.st-scene-text p.st-narrative-dialogue {{
  margin: 0.6em 0 0.8em 1.2em;
  padding-left: 0.8em;
  border-left: 2px solid {theme.accent_glow};
  color: {theme.text_heading};
  font-style: italic;
}}

/* === Choice cards === */
.st-card.st-choice-card {{
  min-height: 80px;
  cursor: default;
  transition: {motion_transition};
}}
.st-card.st-choice-card:hover {{
  border-color: {theme.choice_hover_border};
  box-shadow: {theme.choice_hover_glow};
  transform: translateY(-1px);
}}
.st-choice-title {{
  font-weight: 700;
  font-size: {theme.font_body};
  color: {theme.text_primary};
  margin-bottom: 6px;
  line-height: 1.3;
}}
.st-choice-meta {{
  font-size: {theme.font_small};
  color: {theme.text_secondary};
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}}
.st-choice-meta .tag {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid {theme.hud_pill_border};
  background: {theme.hud_pill_bg};
  font-size: {theme.font_small};
  letter-spacing: 0.3px;
}}

/* === Tone-colored choice cards === */
.st-card.st-choice-card {{
  border-left-width: 3px;
  border-left-style: solid;
}}
.st-card.st-tone-paragon {{
  border-left-color: {theme.tone_paragon};
}}
.st-card.st-tone-paragon:hover {{
  box-shadow: 0 0 16px rgba(100, 180, 255, 0.12);
}}
.st-card.st-tone-investigate {{
  border-left-color: {theme.tone_investigate};
}}
.st-card.st-tone-investigate:hover {{
  box-shadow: 0 0 16px rgba(255, 210, 80, 0.12);
}}
.st-card.st-tone-renegade {{
  border-left-color: {theme.tone_renegade};
}}
.st-card.st-tone-renegade:hover {{
  box-shadow: 0 0 16px rgba(255, 80, 60, 0.12);
}}
.st-card.st-tone-neutral {{
  border-left-color: {theme.tone_neutral};
}}
.st-card.st-tone-neutral:hover {{
  box-shadow: {theme.choice_hover_glow};
}}
.st-tone-icon {{
  font-size: 1.1em;
  margin-right: 4px;
  vertical-align: middle;
}}
.st-choice-hint {{
  font-size: {theme.font_small};
  font-style: italic;
  color: {theme.text_muted};
  margin-top: 4px;
  line-height: 1.4;
}}
.st-intent-style {{
  font-style: italic;
  opacity: 0.85;
}}

/* === Section headers === */
.st-section-header {{
  font-size: {theme.font_caption};
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: {theme.text_secondary};
  padding-bottom: 4px;
  border-bottom: 1px solid {theme.border_subtle};
  margin-bottom: 8px;
}}

/* === Sidebar overrides === */
[data-testid="stSidebar"] {{
  background: {theme.bg_overlay};
  border-right: 1px solid {theme.border_subtle};
}}
[data-testid="stSidebar"] .stMarkdown p {{
  color: {theme.text_secondary};
  font-size: {theme.font_caption};
}}

/* === Button theming === */
.stButton > button {{
  border: 1px solid {theme.border_panel};
  background: {theme.bg_panel};
  color: {theme.text_primary};
  transition: {motion_transition};
  font-weight: 500;
  padding: 0.6rem 1rem;
}}
.stButton > button:hover {{
  border-color: {theme.accent_primary};
  background: {theme.hud_pill_bg};
  color: {theme.text_heading};
  box-shadow: {theme.choice_hover_glow};
}}
.stButton > button[kind="primary"] {{
  background: {theme.accent_primary};
  border-color: {theme.accent_primary};
  color: {theme.bg_app};
  font-weight: 600;
}}
.stButton > button[kind="primary"]:hover {{
  background: {theme.accent_secondary};
  border-color: {theme.accent_secondary};
  box-shadow: {theme.choice_hover_glow};
}}

/* === Progress bar (stress) === */
.stProgress > div > div > div {{
  background: {theme.accent_primary};
}}

/* === Expander headers === */
[data-testid="stExpander"] summary {{
  color: {theme.text_secondary};
  font-size: {theme.font_body};
}}

/* === Chat input === */
[data-testid="stChatInput"] {{
  border-color: {theme.border_panel};
  background: transparent;
}}
[data-testid="stChatInput"] textarea {{
    background-color: {theme.bg_input} !important;
    color: {theme.text_primary} !important;
    border: 1px solid {theme.border_panel} !important;
}}
[data-testid="stChatInput"] button {{
    color: {theme.accent_primary} !important;
}}

/* === Text inputs and textareas === */
.stTextInput > div > div > input {{
  background: {theme.bg_input};
  color: {theme.text_primary};
  border: 1px solid {theme.border_panel};
  font-size: {theme.font_body};
}}
.stTextInput > div > div > input:focus {{
  border-color: {theme.accent_primary};
  box-shadow: 0 0 0 1px {theme.accent_primary};
}}
.stTextArea > div > div > textarea {{
  background: {theme.bg_input};
  color: {theme.text_primary};
  border: 1px solid {theme.border_panel};
  font-size: {theme.font_body};
}}
.stTextArea > div > div > textarea:focus {{
  border-color: {theme.accent_primary};
  box-shadow: 0 0 0 1px {theme.accent_primary};
}}

/* === Select boxes === */
.stSelectbox > div > div > div {{
  background: {theme.bg_input};
  color: {theme.text_primary};
  border: 1px solid {theme.border_panel};
}}
.stSelectbox [data-baseweb="select"] > div {{
  background: {theme.bg_input};
  border-color: {theme.border_panel};
}}

/* === Comms / News item === */
.st-news-item {{
  padding: 8px 0;
  border-bottom: 1px solid {theme.border_subtle};
}}
.st-news-source {{
  font-size: {theme.font_small};
  font-weight: 700;
  color: {theme.accent_primary};
}}
.st-news-headline {{
  font-size: {theme.font_body};
  color: {theme.text_primary};
}}
.st-news-urgency {{
  font-size: {theme.font_small};
  color: {theme.text_muted};
}}

/* === High contrast mode === */
.high-contrast .st-card {{
  border-width: 2px;
  background: rgba(0, 0, 0, 0.85);
}}
.high-contrast .st-scene-text {{
  color: #ffffff;
  font-size: 1.12rem;
}}
.high-contrast .st-pill {{
  border-width: 2px;
}}

/* === Context / lore panel === */
.st-context-panel {{
  font-size: {theme.font_small};
  color: {theme.text_muted};
  padding: 6px 10px;
  border: 1px dashed {theme.border_subtle};
  border-radius: 8px;
  margin-top: 8px;
}}
.st-context-panel strong {{
  color: {theme.text_secondary};
}}

/* === Tab styling === */
.stTabs [data-baseweb="tab-list"] {{
  gap: 2px;
}}
.stTabs [data-baseweb="tab"] {{
  color: {theme.text_secondary};
  font-size: {theme.font_caption};
  text-transform: uppercase;
  letter-spacing: 1px;
}}

/* === Info/Warning/Error boxes === */
.stAlert {{
  background: {theme.bg_panel};
  border: 1px solid {theme.border_panel};
  color: {theme.text_primary};
}}

/* === Better contrast for labels === */
.stMarkdown label {{
  color: {theme.text_secondary};
  font-weight: 500;
}}

/* === Column spacing === */
[data-testid="column"] {{
  padding: 0 0.5rem;
}}

/* === Companion Roster === */
.st-companion-roster {{
  margin-top: 8px;
}}
.st-companion-card {{
  transition: {motion_transition};
}}
.st-companion-card:hover {{
  background: rgba(0, 0, 0, 0.25) !important;
  transform: translateX(2px);
}}
.st-affinity-bar {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
}}
.st-loyalty-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.25);
}}

/* === Banter / Companion Dialogue === */
.st-banter-section {{
  margin-top: 16px;
  padding: 10px 14px;
  border-left: 3px solid {theme.tone_investigate};
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.12);
  transition: {motion_transition};
}}
.st-banter-section:hover {{
  background: rgba(0, 0, 0, 0.18);
  border-left-color: {theme.accent_primary};
}}
.st-banter-speaker {{
  font-size: {theme.font_small};
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: {theme.tone_investigate};
  margin-bottom: 4px;
  display: block;
}}
.st-banter-text {{
  font-style: italic;
  opacity: 0.90;
  line-height: 1.5;
}}

/* === Faction Reputation === */
.st-faction-reputation {{
  margin-top: 8px;
}}
.st-faction-reputation > div {{
  transition: {motion_transition};
}}
.st-faction-reputation > div:hover {{
  transform: translateX(2px);
}}

</style>
"""
