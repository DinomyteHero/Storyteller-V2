"""Storyteller AI — Narrative HUD (legacy Python UI).

Sci-fi console UI with two themes (Rebel Amber / Alliance Blue),
campaign creation, turn-based gameplay, HUD sidebar, and debug panel.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time

import streamlit as st

from ui.api_client import (
    DEFAULT_BASE_URL,
    setup_auto,
    get_state,
    get_transcript,
    get_world_state,
    get_rumors,
    get_era_locations,
    get_era_backgrounds,
    run_turn,
    run_turn_stream,
)
from ui.themes import THEMES, DEFAULT_THEME, get_theme, generate_css
from ui.components import (
    render_hud_bar,
    render_scene,
    render_journal_entry,
    render_news_item,
    render_section_header,
    render_context_panel,
    render_inventory,
    render_mental_state,
    render_kotor_dialogue,
    render_dialogue_turn,
    render_companion_roster,
    render_faction_reputation,
)
from ui.preferences import load_preferences, save_preferences

DEFAULT_ERA = os.getenv("DEFAULT_ERA", "ERA_AGNOSTIC")
SUGGESTED_ACTIONS_TARGET_UI = int(os.getenv("SUGGESTED_ACTIONS_TARGET_UI", "6"))


_LOCATION_DISPLAY_NAMES: dict[str, str] = {
    "loc-cantina": "Cantina",
    "loc-tavern": "Cantina",  # legacy alias
    "loc-marketplace": "Marketplace",
    "loc-market": "Marketplace",  # legacy alias
    "loc-docking-bay": "Docking Bay",
    "loc-docks": "Docking Bay",  # legacy alias
    "loc-lower-streets": "Lower Streets",
    "loc-street": "Lower Streets",  # legacy alias
    "loc-hangar": "Hangar Bay",
    "loc-spaceport": "Spaceport",
    "loc-command-center": "Command Center",
    "loc-med-bay": "Med Bay",
    "loc-jedi-temple": "Jedi Temple",
}


def humanize_location(loc_id: str | None) -> str:
    """Convert a raw location ID into a readable Star Wars-appropriate name.

    Uses a known lookup table first, then falls back to generic cleanup.
    """
    if not loc_id or loc_id == "\u2014":
        return "\u2014"
    raw = loc_id.strip()
    if not raw:
        return "\u2014"
    # Check known display names first
    display = _LOCATION_DISPLAY_NAMES.get(raw.lower())
    if display:
        return display
    # Fallback: strip prefix and title-case
    cleaned = raw
    for prefix in ("loc-", "loc_", "location-", "location_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return raw
    return cleaned.title()
_TYPEWRITER_MS_PER_WORD = int(os.getenv("TYPEWRITER_MS_PER_WORD", "30"))
ERA_LABELS = {
    "ERA_AGNOSTIC": "Agnostic",
    "OLD_REPUBLIC": "Old Republic",
    "HIGH_REPUBLIC": "High Republic",
    "CLONE_WARS": "Clone Wars",
    "REBELLION": "Rebellion",
    "NEW_JEDI_ORDER": "New Jedi Order",
    "NEW_REPUBLIC": "New Republic",
    "LEGACY": "Legacy",
    "CUSTOM": "Custom...",
}


def world_clock_parts(world_time_minutes: int) -> tuple[int, str]:
    """Return (day, time_str). day = (world_time // 1440) + 1; time_str = HH:MM from remainder."""
    if world_time_minutes is None or world_time_minutes < 0:
        world_time_minutes = 0
    day = (world_time_minutes // 1440) + 1
    remainder = world_time_minutes % 1440
    hour = remainder // 60
    minute = remainder % 60
    time_str = f"{hour:02d}:{minute:02d}"
    return day, time_str


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def _format_time_delta(minutes: int) -> str | None:
    minutes = _safe_int(minutes, 0)
    if minutes <= 0:
        return None
    if minutes >= 60:
        hrs = minutes / 60.0
        return f"+{hrs:.0f} hrs" if hrs == int(hrs) else f"+{hrs:.1f} hrs"
    return f"+{minutes} min"


def init_session():
    """Initialize session state with defaults, then overlay persisted prefs."""
    defaults = {
        "screen": "menu",  # menu, character_creation, gameplay
        "campaign_id": None,
        "player_id": None,
        "base_url": DEFAULT_BASE_URL,
        "last_turn_response": None,
        "show_debug": False,
        "ui_mode": "STORY",
        # Character creation temp state
        "char_name": "",
        "char_concept": "",
        "char_era": "REBELLION",
        "char_genre": None,  # V2.7: Optional genre overlay for narrative style
        "char_gender": "male",  # V2.8: Player character gender
        "char_themes": "",
        "char_start_mode": "Auto",
        "char_starting_location": "",
        "cyoa_step": 0,
        "cyoa_answers": {},
        "char_background_id": None,
        "char_background_data": None,  # cached background dict from API
        "_era_backgrounds_cache": {},
        "_era_locations_cache": {},
        # Theme preferences
        "theme_name": DEFAULT_THEME,
        "typewriter_effect": False,
        "reduce_motion": False,
        "high_contrast": False,
        "typewriter_ms": _TYPEWRITER_MS_PER_WORD,
        "streaming_enabled": True,  # V2.8: SSE streaming for Narrator
        "state_cache": None,
        # Internal flag: True after first init (prevents re-loading prefs on rerun)
        "_prefs_loaded": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Overlay persisted preferences (only once per session)
    if not st.session_state._prefs_loaded:
        saved = load_preferences()
        for k, v in saved.items():
            st.session_state[k] = v
        st.session_state._prefs_loaded = True


def _persist_prefs() -> None:
    """Save current UI preferences to disk."""
    save_preferences({
        "theme_name": st.session_state.theme_name,
        "typewriter_effect": st.session_state.typewriter_effect,
        "reduce_motion": st.session_state.reduce_motion,
        "high_contrast": st.session_state.high_contrast,
        "ui_mode": st.session_state.ui_mode,
        "show_debug": st.session_state.show_debug,
        "streaming_enabled": st.session_state.streaming_enabled,
    })


def _get_cached_era_locations(era_id: str, base_url: str) -> list[dict]:
    cache = st.session_state.get("_era_locations_cache")
    if not isinstance(cache, dict):
        cache = {}
        st.session_state["_era_locations_cache"] = cache

    key = f"{base_url}|{era_id}"
    if key in cache and isinstance(cache.get(key), list):
        return cache.get(key) or []

    try:
        resp = get_era_locations(era_id, base_url=base_url)
        locs = resp.get("locations") or []
        if not isinstance(locs, list):
            locs = []
    except Exception:
        locs = []

    cache[key] = locs
    return locs


def _render_settings_sidebar() -> None:
    """Render the Settings section in the sidebar."""
    render_section_header("Settings")

    # Theme selector
    theme_names = list(THEMES.keys())
    current_idx = theme_names.index(st.session_state.theme_name) if st.session_state.theme_name in theme_names else 0
    st.session_state.theme_name = st.selectbox(
        "Theme",
        theme_names,
        index=current_idx,
        help="Visual theme for the narrative console.",
    )

    # UI mode
    st.session_state.ui_mode = st.radio(
        "Mode",
        ["STORY", "GM"],
        index=0 if st.session_state.ui_mode == "STORY" else 1,
        help="STORY: narrative-first. GM: shows extra panels (mental state, inventory, quests).",
    )

    # Toggles
    st.session_state.show_debug = st.checkbox(
        "Debug panel",
        value=st.session_state.show_debug,
        help="Show debug data from the last turn.",
    )
    st.session_state.typewriter_effect = st.checkbox(
        "Typewriter effect",
        value=st.session_state.typewriter_effect,
        help="Animate narrative text appearance.",
    )
    st.session_state.reduce_motion = st.checkbox(
        "Reduce motion",
        value=st.session_state.reduce_motion,
        help="Disable animations and transitions.",
    )
    st.session_state.high_contrast = st.checkbox(
        "High contrast",
        value=st.session_state.high_contrast,
        help="Increase border and text contrast.",
    )
    st.session_state.streaming_enabled = st.checkbox(
        "Stream narration",
        value=st.session_state.streaming_enabled,
        help="Stream narrative text word-by-word from the LLM (SSE). Faster perceived response time.",
    )

    # Typewriter speed (debug only)
    if st.session_state.show_debug:
        st.session_state.typewriter_ms = st.slider(
            "Typewriter ms/word",
            min_value=5, max_value=200,
            value=st.session_state.get("typewriter_ms", _TYPEWRITER_MS_PER_WORD),
            help="Milliseconds per word for the typewriter effect.",
        )

    # API URL
    base_url = st.text_input("API base URL", value=st.session_state.base_url)
    st.session_state.base_url = base_url.rstrip("/") or DEFAULT_BASE_URL

    # Persist preferences on every sidebar render
    _persist_prefs()


def _render_main_menu() -> None:
    """Render the main menu screen."""
    theme = get_theme(st.session_state.theme_name)

    # Center the menu
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # Title
        st.markdown(
            '<div style="text-align: center; font-size: 3rem; font-weight: 700; '
            f'color: {theme.text_heading}; margin-bottom: 1rem; letter-spacing: 4px;">'
            'STORYTELLER AI</div>',
            unsafe_allow_html=True,
        )
        
        st.markdown(
            '<div style="text-align: center; font-size: 1.1rem; '
            f'color: {theme.text_secondary}; margin-bottom: 3rem;">'
            'A Narrative RPG Experience</div>',
            unsafe_allow_html=True,
        )
        
        # Menu buttons
        if st.button("🎮 New Campaign", use_container_width=True, type="primary"):
            st.session_state.screen = "character_creation"
            st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("📚 Load Campaign", use_container_width=True):
            st.info("Load campaign functionality coming soon! For now, use 'New Campaign' to start.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("⚙️ Settings", use_container_width=True):
            st.info("Settings are available in the sidebar")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("❓ Help", use_container_width=True):
            with st.expander("How to Play", expanded=True):
                st.markdown("""
                ### Welcome to Storyteller AI!
                
                **Getting Started:**
                1. Click "New Campaign" to create your character
                2. Choose your era and customize your character
                3. Begin your adventure!
                
                **During Gameplay:**
                - Read the narrative in the Scene tab
                - Choose from suggested actions or type your own
                - Check the Journal tab to review past events
                - Use the sidebar to view intel, inventory, and quests
                
                **Tips:**
                - Be creative with your actions!
                - The AI adapts to your choices
                - Change themes in Settings for different visual styles
                """)


_CYOA_QUESTIONS = [
    {
        "title": "What drives you?",
        "subtitle": "This shapes your personality and approach",
        "choices": [
            {
                "label": "Justice and protecting the innocent",
                "concept": "driven by justice",
                "tone": "PARAGON",
                "icon": "&#9826;",
            },
            {
                "label": "Knowledge and understanding the Force",
                "concept": "seeker of forbidden knowledge",
                "tone": "INVESTIGATE",
                "icon": "&#9672;",
            },
            {
                "label": "Survival -- the galaxy owes you nothing",
                "concept": "a survivor who trusts no one",
                "tone": "RENEGADE",
                "icon": "&#9760;",
            },
            {
                "label": "Credits and the thrill of the deal",
                "concept": "lives for the next score",
                "tone": "NEUTRAL",
                "icon": "&#9678;",
            },
        ],
    },
    {
        "title": "Where did you come from?",
        "subtitle": "This determines your starting location and background",
        "choices": [
            {
                "label": "The underworld",
                "concept": "raised among smugglers and outcasts",
                "tone": "RENEGADE",
                "icon": "&#9760;",
                "location_hint": ["loc-cantina", "loc-lower-streets"],
            },
            {
                "label": "Military service",
                "concept": "veteran of military service",
                "tone": "NEUTRAL",
                "icon": "&#9678;",
                "location_hint": ["loc-command-center", "loc-hangar"],
            },
            {
                "label": "The spacelanes",
                "concept": "a spacer who never called one place home",
                "tone": "INVESTIGATE",
                "icon": "&#9672;",
                "location_hint": ["loc-docking-bay", "loc-spaceport"],
            },
            {
                "label": "A quiet world -- until it wasn't",
                "concept": "from a peaceful world shattered by conflict",
                "tone": "PARAGON",
                "icon": "&#9826;",
                "location_hint": ["loc-marketplace"],
            },
        ],
    },
    {
        "title": "What happened that changed everything?",
        "subtitle": "This seeds your story's opening thread",
        "choices": [
            {
                "label": "I lost someone. I need answers.",
                "concept": "haunted by a loss that demands answers",
                "tone": "PARAGON",
                "icon": "&#9826;",
                "thread": "A personal mystery: who is responsible, and what really happened?",
            },
            {
                "label": "I saw something I shouldn't have.",
                "concept": "carrying a dangerous secret",
                "tone": "INVESTIGATE",
                "icon": "&#9672;",
                "thread": "A dangerous secret: someone powerful wants what you know.",
            },
            {
                "label": "I have a debt that can't be paid in credits.",
                "concept": "bound by an unpayable obligation",
                "tone": "NEUTRAL",
                "icon": "&#9678;",
                "thread": "An obligation that follows you: the debt must be settled, one way or another.",
            },
            {
                "label": "Everything was taken from me.",
                "concept": "forged by loss into something harder",
                "tone": "RENEGADE",
                "icon": "&#9760;",
                "thread": "Survival and defiance: rebuild or take revenge.",
            },
        ],
    },
    {
        "title": "What's your edge?",
        "subtitle": "This gives you a starting advantage",
        "choices": [
            {
                "label": "I can talk my way out of anything",
                "concept": "silver-tongued negotiator",
                "tone": "PARAGON",
                "icon": "&#9826;",
                "stat_hint": {"charisma": 3},
            },
            {
                "label": "I'm handy with a blaster",
                "concept": "deadly accurate in a firefight",
                "tone": "RENEGADE",
                "icon": "&#9760;",
                "stat_hint": {"combat": 3},
            },
            {
                "label": "I know how to disappear",
                "concept": "a ghost when they need to be",
                "tone": "NEUTRAL",
                "icon": "&#9678;",
                "stat_hint": {"stealth": 3},
            },
            {
                "label": "I can fix or hack anything",
                "concept": "a technical genius",
                "tone": "INVESTIGATE",
                "icon": "&#9672;",
                "stat_hint": {"tech": 3},
            },
        ],
    },
]


def _evaluate_condition(condition: str | None, answers: dict, questions: list) -> bool:
    """Evaluate a background question condition like 'loyalty.tone == PARAGON'."""
    if not condition:
        return True
    try:
        parts = condition.split(".")
        if len(parts) != 2:
            return True
        q_id = parts[0]
        field_check = parts[1]  # e.g., "tone == PARAGON"
        # Find question answer by q_id
        for q in questions:
            if q.get("id") == q_id:
                choice_idx = answers.get(q_id)
                if choice_idx is None:
                    return False
                choice = q["choices"][choice_idx]
                if "==" in field_check:
                    field, expected = [s.strip() for s in field_check.split("==")]
                    return str(choice.get(field, "")).upper() == expected.upper()
                return True
        return True
    except Exception:
        return True


def _get_active_bg_questions(background: dict, answers: dict) -> list:
    """Return the list of background questions that pass their conditions."""
    questions = background.get("questions", [])
    active = []
    for q in questions:
        if _evaluate_condition(q.get("condition"), answers, questions):
            active.append(q)
    return active


def _render_character_creation() -> None:
    """Render SWTOR-style CYOA character creation wizard with era-specific backgrounds."""
    import random

    theme = get_theme(st.session_state.theme_name)
    step = st.session_state.cyoa_step
    answers = st.session_state.cyoa_answers

    # Determine if we have era backgrounds
    era = st.session_state.char_era
    backgrounds = []
    if era and era != "ERA_AGNOSTIC":
        cache_key = era
        if cache_key not in st.session_state._era_backgrounds_cache:
            try:
                result = get_era_backgrounds(era, base_url=st.session_state.base_url)
                st.session_state._era_backgrounds_cache[cache_key] = result.get("backgrounds", [])
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).error(
                    "Failed to fetch backgrounds for era %s: %s", era, e, exc_info=True
                )
                st.session_state._era_backgrounds_cache[cache_key] = []
        backgrounds = st.session_state._era_backgrounds_cache.get(cache_key, [])

    use_backgrounds = bool(backgrounds)
    if era and era != "ERA_AGNOSTIC" and not backgrounds:
        st.warning("Could not load era backgrounds. Is the backend running? Using generic questions.")
    bg_data = st.session_state.char_background_data

    # Calculate total steps dynamically
    if use_backgrounds and bg_data:
        active_qs = _get_active_bg_questions(bg_data, answers)
        total_steps = 3 + len(active_qs)  # step 0: name+era+genre, step 1: background, steps 2-N: bg questions, last: review
    elif use_backgrounds:
        total_steps = 4  # name+era+genre, background select, at least 1 question, review
    else:
        total_steps = 2 + len(_CYOA_QUESTIONS)  # fallback generic

    # Random name generators
    first_names = ["Kira", "Dax", "Jace", "Mara", "Tycho", "Nomi", "Cade", "Jaina", "Corran", "Tahiri", "Kyle", "Bastila", "Revan", "Meetra", "Carth"]
    last_names = ["Sunrider", "Durron", "Katarn", "Jade", "Antilles", "Skywalker", "Solo", "Fel", "Horn", "Shan", "Onasi", "Veila", "Bel Iblis"]

    col1, col2, col3 = st.columns([1, 3, 1])

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(
            '<div style="text-align: center; font-size: 2rem; font-weight: 700; '
            f'color: {theme.text_heading}; margin-bottom: 0.5rem; letter-spacing: 3px;">'
            'CHARACTER CREATION</div>',
            unsafe_allow_html=True,
        )

        # Progress bar
        progress = step / max(total_steps - 1, 1)
        st.progress(progress)
        st.caption(f"Step {step + 1} of {total_steps}")
        st.markdown("<br>", unsafe_allow_html=True)

        # === STEP 0: Name + Era + Genre ===
        if step == 0:
            st.markdown(
                f'<div style="font-size: 1.2rem; color: {theme.text_primary}; margin-bottom: 0.5rem;">'
                'Character Name</div>',
                unsafe_allow_html=True,
            )
            name_col, random_col = st.columns([4, 1])
            with name_col:
                char_name = st.text_input(
                    "Name",
                    value=st.session_state.char_name,
                    placeholder="Enter your character's name",
                    label_visibility="collapsed",
                )
                st.session_state.char_name = char_name
            with random_col:
                if st.button("Random", key="random_name"):
                    st.session_state.char_name = f"{random.choice(first_names)} {random.choice(last_names)}"
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            # V2.8: Gender selection
            st.markdown(
                f'<div style="font-size: 1.2rem; color: {theme.text_primary}; margin-bottom: 0.5rem;">'
                'Gender</div>',
                unsafe_allow_html=True,
            )
            gender_options = ["male", "female"]
            gender_labels = {"male": "Male", "female": "Female"}
            gender_cols = st.columns(2)
            for g_idx, g_val in enumerate(gender_options):
                with gender_cols[g_idx]:
                    is_sel = st.session_state.char_gender == g_val
                    if st.button(
                        gender_labels[g_val],
                        key=f"gender_{g_val}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state.char_gender = g_val
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown(
                f'<div style="font-size: 1.2rem; color: {theme.text_primary}; margin-bottom: 0.5rem;">'
                'Choose Your Era</div>',
                unsafe_allow_html=True,
            )

            era_descriptions = {
                "REBELLION": "Fight against the tyranny of the Galactic Empire (0-4 ABY)",
                "NEW_REPUBLIC": "Rebuild after the Empire's fall. Thrawn returns. (5-19 ABY)",
                "NEW_JEDI_ORDER": "The Yuuzhan Vong invasion threatens the galaxy (25-29 ABY)",
                "LEGACY": "Darth Krayt's Sith Empire. Three-way war. (130-138 ABY)",
                "ERA_AGNOSTIC": "No specific era -- maximum freedom",
            }
            era_values = ["REBELLION", "NEW_REPUBLIC", "NEW_JEDI_ORDER", "LEGACY", "ERA_AGNOSTIC"]

            for era_val in era_values:
                is_selected = st.session_state.char_era == era_val
                border_color = theme.accent_primary if is_selected else theme.border_panel
                bg_color = theme.hud_pill_bg if is_selected else theme.bg_panel

                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(
                        f'<div style="padding: 10px; border: 2px solid {border_color}; background: {bg_color}; '
                        f'border-radius: 8px; margin-bottom: 8px;">'
                        f'<div style="font-size: 1rem; color: {theme.text_primary}; font-weight: 600;">'
                        f'{ERA_LABELS.get(era_val, era_val)}</div>'
                        f'<div style="font-size: 0.85rem; color: {theme.text_secondary};">'
                        f'{era_descriptions.get(era_val, "")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with col_b:
                    st.markdown("<br>", unsafe_allow_html=True)
                    btn_label = "Selected" if is_selected else "Select"
                    if st.button(
                        btn_label,
                        key=f"era_{era_val}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                        disabled=is_selected,
                    ):
                        st.session_state.char_era = era_val
                        # Reset background when era changes
                        st.session_state.char_background_id = None
                        st.session_state.char_background_data = None
                        st.session_state.cyoa_answers = {}
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            # V2.10: Genre is auto-assigned based on background + starting location
            st.markdown(
                f'<div style="font-size: 0.9rem; color: {theme.text_secondary}; '
                f'background: {theme.hud_pill_bg}; padding: 10px; border-radius: 6px; '
                f'margin-bottom: 0.5rem; text-align: center;">'
                f'Genre will be automatically shaped by your background and location choices.</div>',
                unsafe_allow_html=True,
            )

            st.markdown("<br>", unsafe_allow_html=True)

            nav_back, nav_next = st.columns(2)
            with nav_back:
                if st.button("Back to Menu", use_container_width=True):
                    st.session_state.screen = "menu"
                    st.session_state.cyoa_step = 0
                    st.session_state.cyoa_answers = {}
                    st.session_state.char_background_id = None
                    st.session_state.char_background_data = None
                    st.rerun()
            with nav_next:
                if st.button("Next", use_container_width=True, type="primary"):
                    if not st.session_state.char_name.strip():
                        st.error("Please enter a character name!")
                    else:
                        # Retry background fetch if cache was empty (backend may have just started)
                        _era = st.session_state.char_era
                        if _era and _era != "ERA_AGNOSTIC" and not st.session_state._era_backgrounds_cache.get(_era):
                            try:
                                _result = get_era_backgrounds(_era, base_url=st.session_state.base_url)
                                st.session_state._era_backgrounds_cache[_era] = _result.get("backgrounds", [])
                            except Exception:
                                pass  # fallback to generic CYOA
                        st.session_state.cyoa_step = 1
                        st.rerun()

        # === STEP 1: Background Selection (era-specific) or first generic CYOA ===
        elif step == 1 and use_backgrounds:
            st.markdown(
                f'<div style="text-align: center; font-size: 1.4rem; color: {theme.text_heading}; '
                f'margin-bottom: 0.5rem; font-weight: 600;">Choose Your Background</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="text-align: center; font-size: 0.9rem; color: {theme.text_muted}; '
                f'margin-bottom: 1.5rem;">Your background shapes your starting position, skills, and story</div>',
                unsafe_allow_html=True,
            )

            current_bg_id = st.session_state.char_background_id

            for bg in backgrounds:
                bg_id = bg.get("id", "")
                bg_name = bg.get("name", "Unknown")
                bg_desc = bg.get("description", "")
                bg_stats = bg.get("starting_stats", {})
                is_selected = current_bg_id == bg_id
                border = theme.accent_primary if is_selected else theme.border_panel
                bg_color = theme.hud_pill_bg if is_selected else theme.bg_panel

                # Stats preview
                stats_str = " | ".join(f"{k}: {v}" for k, v in bg_stats.items() if v > 0)

                col_card, col_btn = st.columns([4, 1])
                with col_card:
                    st.markdown(
                        f'<div style="padding: 14px 16px; border: 2px solid {border}; background: {bg_color}; '
                        f'border-radius: 10px; margin-bottom: 10px;">'
                        f'<div style="font-size: 1.1rem; color: {theme.text_primary}; font-weight: 700;">'
                        f'{bg_name}</div>'
                        f'<div style="font-size: 0.9rem; color: {theme.text_secondary}; margin-top: 4px;">'
                        f'{bg_desc}</div>'
                        f'<div style="font-size: 0.8rem; color: {theme.text_muted}; margin-top: 6px; '
                        f'font-family: monospace;">{stats_str}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    btn_text = "Chosen" if is_selected else "Choose"
                    if st.button(
                        btn_text,
                        key=f"bg_{bg_id}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                        disabled=is_selected,
                    ):
                        st.session_state.char_background_id = bg_id
                        st.session_state.char_background_data = bg
                        st.session_state.cyoa_answers = {}  # Reset answers when changing background
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            nav_back, nav_next = st.columns(2)
            with nav_back:
                if st.button("Back", use_container_width=True):
                    st.session_state.cyoa_step = 0
                    st.rerun()
            with nav_next:
                if st.button("Next", use_container_width=True, type="primary"):
                    if not st.session_state.char_background_id:
                        st.error("Please choose a background!")
                    else:
                        st.session_state.cyoa_step = 2
                        st.rerun()

        # === BACKGROUND QUESTIONS (dynamic branching) ===
        elif use_backgrounds and bg_data and step >= 2:
            active_qs = _get_active_bg_questions(bg_data, answers)
            review_step = 2 + len(active_qs)

            if step < review_step:
                q_idx = step - 2
                if q_idx < len(active_qs):
                    question = active_qs[q_idx]
                    q_id = question.get("id", f"q{q_idx}")

                    _TONE_COLORS = {
                        "PARAGON": theme.tone_paragon,
                        "INVESTIGATE": theme.tone_investigate,
                        "RENEGADE": theme.tone_renegade,
                        "NEUTRAL": theme.tone_neutral,
                    }

                    st.markdown(
                        f'<div style="text-align: center; font-size: 1.4rem; color: {theme.text_heading}; '
                        f'margin-bottom: 0.5rem; font-weight: 600;">{question.get("title", "")}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.9rem; color: {theme.text_muted}; '
                        f'margin-bottom: 1.5rem;">{question.get("subtitle", "")}</div>',
                        unsafe_allow_html=True,
                    )

                    current_answer = answers.get(q_id)
                    choices = question.get("choices", [])

                    for c_idx, choice in enumerate(choices):
                        tone = choice.get("tone", "NEUTRAL")
                        color = _TONE_COLORS.get(tone, theme.tone_neutral)
                        is_chosen = current_answer == c_idx

                        border = theme.accent_primary if is_chosen else theme.border_panel
                        bg = theme.hud_pill_bg if is_chosen else theme.bg_panel

                        # Tone icons
                        tone_icons = {"PARAGON": "&#9826;", "INVESTIGATE": "&#9672;", "RENEGADE": "&#9760;", "NEUTRAL": "&#9678;"}
                        icon = tone_icons.get(tone, "&#9678;")

                        col_card, col_btn = st.columns([4, 1])
                        with col_card:
                            st.markdown(
                                f'<div style="padding: 12px 14px; border: 2px solid {border}; background: {bg}; '
                                f'border-left: 4px solid {color}; border-radius: 8px; margin-bottom: 8px;">'
                                f'<span style="color: {color}; font-size: 1.1em; margin-right: 8px;">{icon}</span>'
                                f'<span style="color: {theme.text_primary}; font-weight: 600;">{choice.get("label", "")}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                        with col_btn:
                            st.markdown("<br>", unsafe_allow_html=True)
                            btn_text = "Chosen" if is_chosen else "Choose"
                            if st.button(
                                btn_text,
                                key=f"bgq_{q_id}_{c_idx}",
                                use_container_width=True,
                                type="primary" if is_chosen else "secondary",
                                disabled=is_chosen,
                            ):
                                st.session_state.cyoa_answers[q_id] = c_idx
                                st.rerun()

                    st.markdown("<br>", unsafe_allow_html=True)

                    nav_back, nav_next = st.columns(2)
                    with nav_back:
                        if st.button("Back", use_container_width=True):
                            st.session_state.cyoa_step = step - 1
                            st.rerun()
                    with nav_next:
                        if st.button("Next", use_container_width=True, type="primary"):
                            if q_id not in answers:
                                st.error("Please make a choice before continuing!")
                            else:
                                # Recalculate active questions after this answer (conditions may change)
                                st.session_state.cyoa_step = step + 1
                                st.rerun()

            # === REVIEW STEP (background-aware) ===
            else:
                st.markdown(
                    f'<div style="text-align: center; font-size: 1.4rem; color: {theme.text_heading}; '
                    f'margin-bottom: 1rem; font-weight: 600;">Your Character</div>',
                    unsafe_allow_html=True,
                )

                # Compile from background answers
                char_name = st.session_state.char_name.strip()
                era_label = ERA_LABELS.get(st.session_state.char_era, st.session_state.char_era)
                bg_name = bg_data.get("name", "Unknown")
                concept_parts = []
                location_hint = None
                thread_seed = None

                for q in active_qs:
                    q_id = q.get("id", "")
                    choice_idx = answers.get(q_id, 0)
                    choices = q.get("choices", [])
                    if choice_idx < len(choices):
                        choice = choices[choice_idx]
                        concept_parts.append(choice.get("concept", ""))
                        effects = choice.get("effects", {})
                        if effects.get("location_hint") and not location_hint:
                            location_hint = effects["location_hint"]
                        if effects.get("thread_seed") and not thread_seed:
                            thread_seed = effects["thread_seed"]

                concept_str = ", ".join(p for p in concept_parts if p)

                summary_items = [
                    ("Name", char_name),
                    ("Era", era_label),
                    ("Background", bg_name),
                    ("Concept", concept_str.capitalize() if concept_str else "Adventurer"),
                ]
                if st.session_state.char_genre:
                    genre_display = {
                        "space_western": "Space Western", "heist_caper": "Heist Caper",
                        "noir_detective": "Noir Detective", "espionage_thriller": "Espionage Thriller",
                        "military_tactical": "Military Tactical", "political_thriller": "Political Thriller",
                        "survival_horror": "Survival Horror", "court_intrigue": "Court Intrigue",
                        "gothic_romance": "Gothic Romance", "mythic_quest": "Mythic Quest",
                    }.get(st.session_state.char_genre, st.session_state.char_genre)
                    summary_items.append(("Genre", genre_display))
                if thread_seed:
                    summary_items.append(("Opening Thread", thread_seed))

                for label, value in summary_items:
                    st.markdown(
                        f'<div style="padding: 8px 12px; border: 1px solid {theme.border_panel}; '
                        f'background: {theme.bg_panel}; border-radius: 8px; margin-bottom: 6px;">'
                        f'<span style="color: {theme.text_secondary}; font-size: 0.85rem; '
                        f'text-transform: uppercase; letter-spacing: 1px;">{label}</span><br/>'
                        f'<span style="color: {theme.text_primary}; font-weight: 600;">{value}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Answer recap
                st.markdown("<br>", unsafe_allow_html=True)
                for q in active_qs:
                    q_id = q.get("id", "")
                    choice_idx = answers.get(q_id, 0)
                    choices = q.get("choices", [])
                    if choice_idx < len(choices):
                        st.caption(f'{q.get("title", "")} **{choices[choice_idx].get("label", "")}**')

                # Player agency reminder
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    f'<div style="text-align: center; font-size: 0.9rem; color: {theme.text_muted}; '
                    f'margin-top: 1rem; font-style: italic;">'
                    'This is YOUR character. You control all their actions — the AI narrates the world, but never decides what your character does.</div>',
                    unsafe_allow_html=True,
                )

                st.markdown("<br>", unsafe_allow_html=True)

                nav_back, nav_start = st.columns(2)
                with nav_back:
                    if st.button("Back", use_container_width=True):
                        st.session_state.cyoa_step = step - 1
                        st.rerun()
                with nav_start:
                    if st.button("Begin Adventure", use_container_width=True, type="primary"):
                        try:
                            player_concept = f"{char_name} -- {bg_name}: {concept_str}"
                            with st.spinner("Creating your adventure... (this may take 1-2 minutes while the AI generates your world)"):
                                out = setup_auto(
                                    base_url=st.session_state.base_url,
                                    time_period=st.session_state.char_era,
                                    genre=st.session_state.char_genre,
                                    themes=[],
                                    player_concept=player_concept,
                                    starting_location=location_hint,
                                    background_id=st.session_state.char_background_id,
                                    background_answers=answers,
                                    player_gender=st.session_state.char_gender,
                                )
                                st.session_state.campaign_id = out["campaign_id"]
                                st.session_state.player_id = out["player_id"]
                                st.session_state.state_cache = None

                            with st.spinner("Setting the scene..."):
                                opening_input = "[OPENING_SCENE]"
                                if thread_seed:
                                    opening_input += f" {thread_seed}"
                                else:
                                    opening_input += " Look around and take in the surroundings"
                                opening_resp = run_turn(
                                    st.session_state.campaign_id,
                                    st.session_state.player_id,
                                    opening_input,
                                    base_url=st.session_state.base_url,
                                    debug=st.session_state.show_debug,
                                )
                                st.session_state.last_turn_response = opening_resp
                                st.session_state.state_cache = None
                                st.session_state.cyoa_step = 0
                                st.session_state.cyoa_answers = {}
                                st.session_state.char_background_id = None
                                st.session_state.char_background_data = None
                                st.session_state.screen = "gameplay"
                                st.rerun()
                        except Exception as e:
                            if st.session_state.campaign_id:
                                st.session_state.last_turn_response = None
                                st.session_state.cyoa_step = 0
                                st.session_state.cyoa_answers = {}
                                st.session_state.screen = "gameplay"
                                st.rerun()
                            else:
                                st.error(f"Failed to create campaign: {e}")

        # === FALLBACK: Generic CYOA (ERA_AGNOSTIC or no backgrounds) ===
        elif 1 <= step <= len(_CYOA_QUESTIONS):
            q_idx = step - 1
            question = _CYOA_QUESTIONS[q_idx]

            st.markdown(
                f'<div style="text-align: center; font-size: 1.4rem; color: {theme.text_heading}; '
                f'margin-bottom: 0.5rem; font-weight: 600;">{question["title"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="text-align: center; font-size: 0.9rem; color: {theme.text_muted}; '
                f'margin-bottom: 1.5rem;">{question["subtitle"]}</div>',
                unsafe_allow_html=True,
            )

            _TONE_COLORS = {
                "PARAGON": theme.tone_paragon,
                "INVESTIGATE": theme.tone_investigate,
                "RENEGADE": theme.tone_renegade,
                "NEUTRAL": theme.tone_neutral,
            }

            current_answer = answers.get(f"q{q_idx}")

            for c_idx, choice in enumerate(question["choices"]):
                tone = choice.get("tone", "NEUTRAL")
                color = _TONE_COLORS.get(tone, theme.tone_neutral)
                icon = choice.get("icon", "&#9678;")
                is_chosen = current_answer == c_idx

                border = theme.accent_primary if is_chosen else theme.border_panel
                bg = theme.hud_pill_bg if is_chosen else theme.bg_panel

                col_card, col_btn = st.columns([4, 1])
                with col_card:
                    st.markdown(
                        f'<div style="padding: 12px 14px; border: 2px solid {border}; background: {bg}; '
                        f'border-left: 4px solid {color}; border-radius: 8px; margin-bottom: 8px;">'
                        f'<span style="color: {color}; font-size: 1.1em; margin-right: 8px;">{icon}</span>'
                        f'<span style="color: {theme.text_primary}; font-weight: 600;">{choice["label"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    st.markdown("<br>", unsafe_allow_html=True)
                    btn_text = "Chosen" if is_chosen else "Choose"
                    if st.button(
                        btn_text,
                        key=f"cyoa_{q_idx}_{c_idx}",
                        use_container_width=True,
                        type="primary" if is_chosen else "secondary",
                        disabled=is_chosen,
                    ):
                        st.session_state.cyoa_answers[f"q{q_idx}"] = c_idx
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            nav_back, nav_next = st.columns(2)
            with nav_back:
                if st.button("Back", use_container_width=True):
                    st.session_state.cyoa_step = step - 1
                    st.rerun()
            with nav_next:
                if st.button("Next", use_container_width=True, type="primary"):
                    if f"q{q_idx}" not in answers:
                        st.error("Please make a choice before continuing!")
                    else:
                        st.session_state.cyoa_step = step + 1
                        st.rerun()

        # === GENERIC REVIEW STEP (ERA_AGNOSTIC fallback) ===
        elif not use_backgrounds and step == 2 + len(_CYOA_QUESTIONS):
            st.markdown(
                f'<div style="text-align: center; font-size: 1.4rem; color: {theme.text_heading}; '
                f'margin-bottom: 1rem; font-weight: 600;">Your Character</div>',
                unsafe_allow_html=True,
            )

            concept_parts = []
            location_hint = None
            thread_seed = None

            for q_idx, question in enumerate(_CYOA_QUESTIONS):
                choice_idx = answers.get(f"q{q_idx}", 0)
                choice = question["choices"][choice_idx]
                concept_parts.append(choice["concept"])
                if "location_hint" in choice and not location_hint:
                    location_hint = choice["location_hint"][0] if choice["location_hint"] else None
                if "thread" in choice and not thread_seed:
                    thread_seed = choice["thread"]

            char_name = st.session_state.char_name.strip()
            era_label = ERA_LABELS.get(st.session_state.char_era, st.session_state.char_era)
            concept_str = ", ".join(concept_parts)

            summary_items = [
                ("Name", char_name),
                ("Era", era_label),
                ("Concept", concept_str.capitalize()),
            ]
            if st.session_state.char_genre:
                genre_display = {
                    "space_western": "Space Western", "heist_caper": "Heist Caper",
                    "noir_detective": "Noir Detective", "espionage_thriller": "Espionage Thriller",
                    "military_tactical": "Military Tactical", "political_thriller": "Political Thriller",
                    "survival_horror": "Survival Horror", "court_intrigue": "Court Intrigue",
                    "gothic_romance": "Gothic Romance", "mythic_quest": "Mythic Quest",
                }.get(st.session_state.char_genre, st.session_state.char_genre)
                summary_items.append(("Genre", genre_display))
            if thread_seed:
                summary_items.append(("Inciting Incident", thread_seed))

            for label, value in summary_items:
                st.markdown(
                    f'<div style="padding: 8px 12px; border: 1px solid {theme.border_panel}; '
                    f'background: {theme.bg_panel}; border-radius: 8px; margin-bottom: 6px;">'
                    f'<span style="color: {theme.text_secondary}; font-size: 0.85rem; '
                    f'text-transform: uppercase; letter-spacing: 1px;">{label}</span><br/>'
                    f'<span style="color: {theme.text_primary}; font-weight: 600;">{value}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)
            for q_idx, question in enumerate(_CYOA_QUESTIONS):
                choice_idx = answers.get(f"q{q_idx}", 0)
                choice = question["choices"][choice_idx]
                st.caption(f'{question["title"]} **{choice["label"]}**')

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f'<div style="text-align: center; font-size: 0.9rem; color: {theme.text_muted}; '
                f'margin-top: 1rem; font-style: italic;">'
                'This is YOUR character. You control all their actions — the AI narrates the world, but never decides what your character does.</div>',
                unsafe_allow_html=True,
            )

            st.markdown("<br>", unsafe_allow_html=True)

            nav_back, nav_start = st.columns(2)
            with nav_back:
                if st.button("Back", use_container_width=True):
                    st.session_state.cyoa_step = step - 1
                    st.rerun()
            with nav_start:
                if st.button("Begin Adventure", use_container_width=True, type="primary"):
                    try:
                        player_concept = f"{char_name} -- {concept_str}"
                        with st.spinner("Creating your adventure... (this may take 1-2 minutes while the AI generates your world)"):
                            out = setup_auto(
                                base_url=st.session_state.base_url,
                                time_period=st.session_state.char_era,
                                genre=st.session_state.char_genre,
                                themes=[],
                                player_concept=player_concept,
                                starting_location=location_hint,
                                player_gender=st.session_state.char_gender,
                            )
                            st.session_state.campaign_id = out["campaign_id"]
                            st.session_state.player_id = out["player_id"]
                            st.session_state.state_cache = None

                        with st.spinner("Setting the scene..."):
                            opening_input = "[OPENING_SCENE]"
                            if thread_seed:
                                opening_input += f" {thread_seed}"
                            else:
                                opening_input += " Look around and take in the surroundings"
                            opening_resp = run_turn(
                                st.session_state.campaign_id,
                                st.session_state.player_id,
                                opening_input,
                                base_url=st.session_state.base_url,
                                debug=st.session_state.show_debug,
                            )
                            st.session_state.last_turn_response = opening_resp
                            st.session_state.state_cache = None
                            st.session_state.cyoa_step = 0
                            st.session_state.cyoa_answers = {}
                            st.session_state.screen = "gameplay"
                            st.rerun()
                    except Exception as e:
                        if st.session_state.campaign_id:
                            st.session_state.last_turn_response = None
                            st.session_state.cyoa_step = 0
                            st.session_state.cyoa_answers = {}
                            st.session_state.screen = "gameplay"
                            st.rerun()
                        else:
                            st.error(f"Failed to create campaign: {e}")


def _get_cached_state(campaign_id: str, player_id: str, base_url: str) -> dict:
    """Fetch state at most once per render cycle; reuse session cache until invalidated."""
    cache = st.session_state.get("state_cache")
    if isinstance(cache, dict):
        if (
            cache.get("campaign_id") == campaign_id
            and cache.get("player_id") == player_id
            and cache.get("base_url") == base_url
            and isinstance(cache.get("state"), dict)
        ):
            return cache.get("state") or {}
    state = get_state(campaign_id, player_id, base_url=base_url)
    st.session_state.state_cache = {
        "campaign_id": campaign_id,
        "player_id": player_id,
        "base_url": base_url,
        "state": state,
    }
    return state


def _resolve_state_data(campaign_id: str, player_id: str, last_resp: dict | None) -> dict:
    """Resolve all state data needed for the UI from last_resp and API fallbacks."""
    base = st.session_state.base_url
    fetched_state: dict | None = None

    def _state_once() -> dict:
        nonlocal fetched_state
        if fetched_state is None:
            fetched_state = _get_cached_state(campaign_id, player_id, base)
        return fetched_state or {}

    # World time
    world_time_minutes = None
    if last_resp:
        world_time_minutes = last_resp.get("world_time_minutes")
    if world_time_minutes is None:
        try:
            state = _state_once()
            world_time_minutes = (state.get("campaign") or {}).get("world_time_minutes", 0)
        except Exception:
            pass
    world_time_minutes = int(world_time_minutes) if world_time_minutes is not None else 0

    # Player sheet
    player_sheet = (last_resp.get("player_sheet") or {}) if last_resp else {}
    if not player_sheet:
        try:
            player_sheet = (_state_once().get("player") or {})
        except Exception:
            player_sheet = {}

    # Psych profile
    psych = player_sheet.get("psych_profile") if isinstance(player_sheet, dict) else {}
    if psych is None or not isinstance(psych, dict):
        psych = {}
    if not psych:
        try:
            psych = (_state_once().get("player") or {}).get("psych_profile") or {}
        except Exception:
            psych = {}
    psych = psych if isinstance(psych, dict) else {}

    # News feed
    news_feed = (last_resp.get("news_feed") if last_resp else None) or []
    if not news_feed:
        try:
            news_feed = ((_state_once().get("campaign") or {}).get("news_feed") or [])
        except Exception:
            news_feed = []

    # Inventory
    inv = (last_resp.get("inventory") if last_resp else None) or []
    if not inv and last_resp is None:
        try:
            inv = (_state_once().get("player") or {}).get("inventory") or []
        except Exception:
            pass

    # Quest log
    quest = (last_resp.get("quest_log") if last_resp else {}) or {}
    if not quest:
        try:
            ws = get_world_state(campaign_id, base_url=base)
            quest = ws.get("world_state") or {}
        except Exception:
            pass

    # Suggestions
    suggestions = (last_resp.get("suggested_actions") if last_resp else None) or []
    if not suggestions:
        try:
            suggestions = (_state_once().get("suggested_actions") or [])
        except Exception:
            pass
    suggestions = suggestions[: max(1, SUGGESTED_ACTIONS_TARGET_UI)]

    # V2.17: DialogueTurn (canonical scene + NPC utterance + player responses)
    dialogue_turn = (last_resp.get("dialogue_turn") if last_resp else None)

    # V2.7: Extract character identity data
    char_name = player_sheet.get("name") or "Unknown"
    background = player_sheet.get("background") or ""
    cyoa_answers = player_sheet.get("cyoa_answers") or {}
    time_period = ""
    try:
        time_period = (_state_once().get("campaign") or {}).get("time_period") or ""
    except Exception:
        pass

    # V2.9: Extract companion party status (if available)
    party_status = (last_resp.get("party_status") if last_resp else None) or []

    # V2.9: Extract faction reputation (if available)
    faction_reputation = (last_resp.get("faction_reputation") if last_resp else None) or {}

    return {
        "world_time_minutes": world_time_minutes,
        "player_sheet": player_sheet,
        "psych": psych,
        "news_feed": news_feed,
        "inventory": inv,
        "quest": quest,
        "suggestions": suggestions,
        "character_name": char_name,
        "background": background,
        "cyoa_answers": cyoa_answers,
        "time_period": time_period,
        "party_status": party_status,
        "faction_reputation": faction_reputation,
    }


def _render_right_sidebar(data: dict, campaign_id: str) -> None:
    """Render the right-hand HUD sidebar (Comms, Inventory, Quests, etc.)."""
    base = st.session_state.base_url
    news_feed = data["news_feed"]
    inv = data["inventory"]
    quest = data["quest"]
    psych = data["psych"]
    party_status = data.get("party_status") or []
    faction_reputation = data.get("faction_reputation") or {}

    mood = psych.get("current_mood") or "\u2014"
    stress = psych.get("stress_level")
    stress_val = max(0, min(10, int(stress))) if stress is not None else 0
    active_trauma = psych.get("active_trauma")

    # V2.7: Character Identity Panel (always visible)
    with st.expander("Character", expanded=True):
        char_name = data.get("character_name") or "Unknown"
        era = data.get("time_period") or "Unknown Era"
        background = data.get("background") or ""
        cyoa_answers = data.get("cyoa_answers") or {}

        st.markdown(f"**{char_name}**")
        st.caption(f"Era: {era}")

        if background:
            st.markdown(f"_{background}_")

        if cyoa_answers:
            st.divider()
            if cyoa_answers.get("motivation"):
                st.caption(f"Motivation: {cyoa_answers['motivation']}")
            if cyoa_answers.get("origin"):
                st.caption(f"Origin: {cyoa_answers['origin']}")
            if cyoa_answers.get("inciting_incident"):
                st.caption(f"Inciting Incident: {cyoa_answers['inciting_incident']}")
            if cyoa_answers.get("edge"):
                st.caption(f"Edge: {cyoa_answers['edge']}")

    # V2.9: Party Roster (companions with affinity/loyalty)
    if party_status:
        with st.expander("Party Roster", expanded=True):
            theme = get_theme(st.session_state.get("theme_name"))
            render_companion_roster(party_status, theme=theme)

    # V2.9: Faction Standing (reputation tracker)
    if faction_reputation:
        with st.expander("Faction Standing", expanded=False):
            theme = get_theme(st.session_state.get("theme_name"))
            render_faction_reputation(faction_reputation, theme=theme)

    # Comms / Briefing
    with st.expander("Comms / Briefing", expanded=True):
        if not news_feed:
            st.caption("(no intel)")
        else:
            for item in news_feed[:10]:
                if not isinstance(item, dict):
                    continue
                render_news_item(
                    headline=(item.get("headline") or "\u2014").strip(),
                    source_tag=(item.get("source_tag") or "CIVNET").strip(),
                    urgency=(item.get("urgency") or "LOW").strip(),
                    body=(item.get("body") or "").strip(),
                    factions=item.get("related_factions") or [],
                )

    # GM-only panels
    if st.session_state.ui_mode == "GM":
        with st.expander("Mental State", expanded=False):
            render_mental_state(mood, stress_val, active_trauma)

        with st.expander("Inventory", expanded=False):
            render_inventory(inv)

        with st.expander("Quest / World Notes", expanded=False):
            if not quest:
                st.caption("(none)")
            else:
                for k, v in quest.items():
                    st.write(f"- {k}: {v}")

    # Actions
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Main Menu", use_container_width=True):
            st.session_state.screen = "menu"
            st.session_state.campaign_id = None
            st.session_state.player_id = None
            st.session_state.last_turn_response = None
            st.session_state.state_cache = None
            st.rerun()
    with col2:
        if st.button("Ingestion", use_container_width=True, help="Open the Ingestion Studio"):
            st.info("Run: start_ingestion_ui.bat (separate window)")


def _render_debug_panel(last_resp: dict, campaign_id: str) -> None:
    """Render the debug panel below the main content."""
    debug = last_resp.get("debug") or {}
    with st.expander("Debug (last turn)", expanded=False):
        render_section_header("Router Intent")
        st.json(debug.get("router_intent"))

        render_section_header("Mechanic Output")
        st.json(debug.get("mechanic_output"))

        render_section_header("Warnings")
        warnings = last_resp.get("warnings") or []
        if warnings:
            for w in warnings:
                st.markdown(f"- {w}")
        else:
            st.caption("(none)")

        render_section_header("Director Output")
        director_output = {
            "director_instructions": debug.get("director_instructions"),
            "suggested_actions": last_resp.get("suggested_actions"),
            "present_npcs": debug.get("present_npcs"),
        }
        st.json(director_output)

        render_section_header("Hidden Events")
        hidden_events = debug.get("world_sim_events") or []
        if hidden_events:
            st.json(hidden_events)
        else:
            st.caption("(none)")

        render_section_header("Rumors")
        new_rumors = debug.get("new_rumors") or []
        if new_rumors:
            for r in new_rumors:
                st.markdown(f"- {r}")
        else:
            st.caption("(none)")

        # Context stats (when DEV_CONTEXT_STATS enabled)
        context_stats = debug.get("context_stats")
        if context_stats:
            render_section_header("Context Stats")
            st.json(context_stats)

        # Lore sources used
        lore_sources = debug.get("lore_sources") or debug.get("rag_sources") or []
        if lore_sources:
            render_section_header("RAG Sources")
            render_context_panel(lore_sources, token_stats=context_stats)

        active_factions = debug.get("active_factions")
        if active_factions is None:
            try:
                ws = get_world_state(campaign_id, base_url=st.session_state.base_url)
                active_factions = (ws.get("world_state") or {}).get("active_factions")
            except Exception:
                pass
        with st.expander("World State: active_factions", expanded=False):
            if active_factions:
                st.json(active_factions)
            else:
                st.caption("(none)")


def main():
    st.set_page_config(page_title="Storyteller AI", layout="wide", initial_sidebar_state="auto")
    init_session()

    # Inject themed CSS
    theme = get_theme(st.session_state.theme_name)
    st.markdown(generate_css(theme, reduce_motion=st.session_state.reduce_motion), unsafe_allow_html=True)

    # High contrast class on body
    if st.session_state.high_contrast:
        st.markdown('<style>.stApp { font-size: 1.02rem; } .st-card { border-width: 2px; }</style>', unsafe_allow_html=True)

    # --- Route to appropriate screen ---
    if st.session_state.screen == "menu":
        # Minimal sidebar for menu
        with st.sidebar:
            render_section_header("Settings")
            theme_names = list(THEMES.keys())
            current_idx = theme_names.index(st.session_state.theme_name) if st.session_state.theme_name in theme_names else 0
            st.session_state.theme_name = st.selectbox("Theme", theme_names, index=current_idx)
            _persist_prefs()
        _render_main_menu()
        return
    
    elif st.session_state.screen == "character_creation":
        # Minimal sidebar for character creation
        with st.sidebar:
            render_section_header("Settings")
            theme_names = list(THEMES.keys())
            current_idx = theme_names.index(st.session_state.theme_name) if st.session_state.theme_name in theme_names else 0
            st.session_state.theme_name = st.selectbox("Theme", theme_names, index=current_idx)
            _persist_prefs()
        _render_character_creation()
        return
    
    elif st.session_state.screen == "gameplay":
        # Full sidebar for gameplay
        with st.sidebar:
            _render_settings_sidebar()
        
        # Check if we have an active campaign
        if not st.session_state.campaign_id or not st.session_state.player_id:
            st.session_state.screen = "menu"
            st.rerun()
            return

    # --- Active campaign (gameplay screen) ---
    campaign_id = st.session_state.campaign_id
    player_id = st.session_state.player_id
    last_resp = st.session_state.last_turn_response

    # Resolve all state data
    data = _resolve_state_data(campaign_id, player_id, last_resp)
    day, time_str = world_clock_parts(data["world_time_minutes"])
    player_sheet = data["player_sheet"]
    hp_current = _safe_int((player_sheet or {}).get("hp_current"), 0)
    credits_val = _safe_int((player_sheet or {}).get("credits"), 0)
    location_id = humanize_location((player_sheet or {}).get("location_id"))
    planet_name = (player_sheet or {}).get("planet_id") or ""
    psych = data["psych"]
    mood = psych.get("current_mood") or "\u2014"
    stress = psych.get("stress_level")
    stress_val = max(0, min(10, int(stress))) if stress is not None else 0
    suggestions = data["suggestions"]

    # Transcript
    try:
        tdata = get_transcript(campaign_id, limit=100, base_url=st.session_state.base_url)
        turns = tdata.get("turns") or []
        turns_chrono = list(reversed(turns))
    except Exception as e:
        st.warning(f"Transcript: {e}")
        turns_chrono = []

    latest_turn = turns_chrono[-1] if turns_chrono else {}
    latest_turn_number = latest_turn.get("turn_number", 0) if isinstance(latest_turn, dict) else 0
    latest_scene_text = (latest_turn.get("text") or "").strip() if isinstance(latest_turn, dict) else ""
    if not latest_scene_text and last_resp:
        latest_scene_text = (last_resp.get("narrated_text") or "").strip()
    latest_time_note = None
    if isinstance(latest_turn, dict):
        latest_time_note = _format_time_delta(
            latest_turn.get("time_cost_minutes") or latest_turn.get("time_cost") or 0
        )

    def _run_action(intent: str) -> None:
        use_streaming = st.session_state.streaming_enabled and not st.session_state.show_debug
        if use_streaming:
            _run_action_streaming(intent)
        else:
            _run_action_blocking(intent)

    def _run_action_blocking(intent: str) -> None:
        with st.status("Calibrating narrative systems...", expanded=False) as status:
            status.update(label="Connecting to backend...", state="running")
            resp = run_turn(
                campaign_id,
                player_id,
                intent,
                base_url=st.session_state.base_url,
                debug=st.session_state.show_debug,
            )
            status.update(label="Narrative received.", state="complete")
        st.session_state.last_turn_response = resp
        st.session_state.state_cache = None
        st.session_state.pop("_typewriter_shown_turn", None)
        st.rerun()

    def _run_action_streaming(intent: str) -> None:
        """Stream narration via SSE: show tokens as they arrive."""
        placeholder = st.empty()
        accumulated = ""
        resp = None
        try:
            for event in run_turn_stream(
                campaign_id,
                player_id,
                intent,
                base_url=st.session_state.base_url,
            ):
                etype = event.get("type", "")
                if etype == "token":
                    accumulated += event.get("text", "")
                    placeholder.markdown(
                        f'<div style="font-size: 1.05rem; line-height: 1.7; '
                        f'color: rgba(220,220,230,0.95); padding: 8px 0;">'
                        f'{accumulated}</div>',
                        unsafe_allow_html=True,
                    )
                elif etype == "done":
                    resp = event
                elif etype == "error":
                    st.error(f"Streaming error: {event.get('message', 'Unknown error')}")
                    return
        except Exception as e:
            st.error(f"Streaming connection failed: {e}")
            # Fallback to blocking call
            _run_action_blocking(intent)
            return

        if resp:
            st.session_state.last_turn_response = resp
            st.session_state.state_cache = None
            st.session_state.pop("_typewriter_shown_turn", None)
            # Mark this turn as already shown via streaming (skip typewriter)
            st.session_state["_typewriter_shown_turn"] = -1
            st.rerun()

    # --- Main layout: narrative viewport (left+center) + HUD rail (right) ---
    main_col, rail_col = st.columns([3, 1], gap="large")

    with main_col:
        # HUD bar
        render_hud_bar(
            planet=planet_name,
            location=location_id,
            day=day,
            time_str=time_str,
            hp=hp_current,
            credits=credits_val,
            mood=mood,
            stress=stress_val,
        )

        # Story recap: show condensed previous turns so the player knows where they are
        if turns_chrono and len(turns_chrono) > 1:
            # Show the previous turn(s) as a brief "previously..." recap
            prev_turns = turns_chrono[:-1]  # all except latest
            recap_texts = []
            for t in prev_turns[-2:]:  # last 2 previous turns at most
                if not isinstance(t, dict):
                    continue
                text = (t.get("text") or "").strip()
                if text:
                    # Truncate long recap to ~80 words
                    words = text.split()
                    if len(words) > 80:
                        text = " ".join(words[:80]) + "..."
                    recap_texts.append(text)
            if recap_texts:
                with st.expander("Previously...", expanded=False):
                    for rt in recap_texts:
                        st.markdown(
                            f'<div style="font-size: 0.9rem; color: rgba(200,200,210,0.7); '
                            f'line-height: 1.5; margin-bottom: 12px; font-style: italic;">'
                            f'{rt}</div>',
                            unsafe_allow_html=True,
                        )

        # Opening crawl: show character situation briefing on turn 1
        if latest_turn_number <= 1 and player_sheet:
            char_name = (player_sheet or {}).get("name", "")
            char_bg = (player_sheet or {}).get("background", "")
            if char_name and char_bg:
                st.markdown(
                    f'<div style="'
                    f'background: linear-gradient(135deg, rgba(30,40,60,0.95), rgba(20,25,40,0.95)); '
                    f'border: 1px solid rgba(100,180,255,0.3); border-radius: 8px; '
                    f'padding: 16px 20px; margin-bottom: 16px; '
                    f'font-family: monospace;">'
                    f'<div style="color: rgba(100,180,255,0.9); font-size: 0.75rem; '
                    f'text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px;">'
                    f'Mission Briefing</div>'
                    f'<div style="color: rgba(220,220,230,0.95); font-size: 0.95rem; line-height: 1.6;">'
                    f'<strong>{char_name}</strong> &mdash; {char_bg}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Era transition interstitial: detect when era changes between turns
        current_era = data.get("time_period") or ""
        prev_era = st.session_state.get("_last_known_era", "")
        if current_era and prev_era and current_era != prev_era:
            from backend.app.core.era_transition import ERA_DISPLAY_NAMES, ERA_TIME_GAPS
            prev_display = ERA_DISPLAY_NAMES.get(prev_era.upper(), prev_era)
            next_display = ERA_DISPLAY_NAMES.get(current_era.upper(), current_era)
            gap_key = f"{prev_era.upper()}->{current_era.upper()}"
            time_gap = ERA_TIME_GAPS.get(gap_key, "Time passes. The galaxy transforms.")
            st.markdown(
                f'<div style="'
                f'background: linear-gradient(135deg, rgba(10,10,30,0.98), rgba(30,20,50,0.95)); '
                f'border: 1px solid rgba(200,180,100,0.4); border-radius: 12px; '
                f'padding: 32px 28px; margin: 24px 0; text-align: center; '
                f'font-family: serif;">'
                f'<div style="color: rgba(200,180,100,0.6); font-size: 0.7rem; '
                f'text-transform: uppercase; letter-spacing: 4px; margin-bottom: 16px;">'
                f'Era Transition</div>'
                f'<div style="color: rgba(200,180,100,0.9); font-size: 1.3rem; '
                f'margin-bottom: 12px;">The chapter of {prev_display} draws to a close.</div>'
                f'<div style="color: rgba(180,180,200,0.7); font-size: 1rem; '
                f'font-style: italic; margin-bottom: 16px;">{time_gap}</div>'
                f'<div style="color: rgba(200,180,100,0.9); font-size: 1.3rem;">'
                f'A new chapter begins: {next_display}.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if current_era:
            st.session_state["_last_known_era"] = current_era

        # Scene + Journal tabs
        tabs = st.tabs(["Scene", "Journal"])

        with tabs[0]:
            # Main narrative
            use_typewriter = (
                st.session_state.typewriter_effect
                and not st.session_state.reduce_motion
                and latest_scene_text
                and last_resp is not None
                and not st.session_state.get("_typewriter_shown_turn") == latest_turn_number
            )
            if use_typewriter:
                # Render the card header via static HTML, then stream the text
                render_scene(
                    "",
                    turn_number=latest_turn_number,
                    time_note=latest_time_note,
                    typewriter=False,
                    location=location_id,
                    planet=planet_name,
                )

                def _word_stream():
                    delay = st.session_state.get("typewriter_ms", _TYPEWRITER_MS_PER_WORD) / 1000.0
                    words = latest_scene_text.split(" ")
                    for w in words:
                        yield w + " "
                        time.sleep(delay)

                st.write_stream(_word_stream)
                st.session_state["_typewriter_shown_turn"] = latest_turn_number
            else:
                render_scene(
                    latest_scene_text,
                    turn_number=latest_turn_number,
                    time_note=latest_time_note,
                    typewriter=False,
                    location=location_id,
                    planet=planet_name,
                )

            # Context used (lightweight lore display)
            if last_resp and st.session_state.show_debug:
                debug = last_resp.get("debug") or {}
                lore_sources = debug.get("lore_sources") or debug.get("rag_sources") or []
                context_stats = debug.get("context_stats")
                if lore_sources or context_stats:
                    render_context_panel(lore_sources, token_stats=context_stats)

            # V2.17: DialogueTurn rendering (scene + NPC dialogue + player responses)
            selected_intent = None
            if dialogue_turn:
                st.markdown("<br>", unsafe_allow_html=True)
                selected_intent = render_dialogue_turn(dialogue_turn, theme=theme)
            if selected_intent is None and not dialogue_turn:
                # Fallback: KOTOR-style numbered dialogue list (pre-V2.17)
                if suggestions:
                    st.markdown("<br>", unsafe_allow_html=True)
                    render_section_header("What do you do?")
                    selected_intent = render_kotor_dialogue(suggestions, theme=theme)
                else:
                    st.caption("(No suggested actions available yet.)")
            if selected_intent:
                try:
                    _run_action(selected_intent)
                except Exception as e:
                    st.error(str(e))

            # V2.13: Free-text input removed — KOTOR-style suggestion buttons are the sole interaction

        with tabs[1]:
            # Journal / transcript
            if not turns_chrono:
                st.caption("(no journal entries)")
            else:
                for t in turns_chrono:
                    if not isinstance(t, dict):
                        continue
                    turn_num = t.get("turn_number", 0)
                    time_note = _format_time_delta(
                        t.get("time_cost_minutes") or t.get("time_cost") or 0
                    )
                    render_journal_entry(
                        t.get("text") or "",
                        turn_number=turn_num,
                        time_note=time_note,
                    )

    # Right sidebar (HUD panels)
    with rail_col:
        _render_right_sidebar(data, campaign_id)

    # Debug panel (full width, below main content)
    if st.session_state.show_debug and last_resp:
        _render_debug_panel(last_resp, campaign_id)


if __name__ == "__main__":
    main()
