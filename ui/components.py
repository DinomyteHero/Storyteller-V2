"""Reusable UI primitives for the Storyteller narrative HUD.

All rendering helpers accept a ThemeTokens instance for consistent styling.
Components use Streamlit's st.markdown(unsafe_allow_html=True) for custom HTML.
"""
from __future__ import annotations

import html
import re
from typing import Any

import streamlit as st


def _strip_markdown_artifacts(text: str) -> str:
    """Strip any residual markdown/structural formatting from narrative text.

    This is the last line of defense before HTML rendering. Catches anything
    the narrator post-processor might have missed.
    """
    # Strip markdown bold/italic wrappers: **text**, *text*, __text__, _text_
    # But preserve the content inside
    result = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    result = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", result)
    # Strip markdown headers: ## Something, # Something
    result = re.sub(r"^#{1,3}\s+", "", result, flags=re.MULTILINE)
    # Strip fenced code block markers
    result = re.sub(r"^```\w*\s*$", "", result, flags=re.MULTILINE)
    # Strip section labels: "Scene:", "Narrative:", etc. at line start
    result = re.sub(
        r"^(?:Scene|Narrative|Next Turn|Opening|Summary|Description|Dialogue|"
        r"Action|Response|Output|Result|Setting|Atmosphere|Continue|Continuation)\s*:\s*",
        "",
        result,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    # Collapse multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _format_narrative_html(raw_text: str) -> str:
    """Convert narrator prose into structured HTML paragraphs with dialogue styling."""
    # Clean any markdown/structural artifacts first
    cleaned = _strip_markdown_artifacts(raw_text)
    paragraphs = re.split(r"\n\n+", cleaned.strip())
    if not paragraphs:
        paragraphs = [cleaned]
    html_parts: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Skip paragraphs that are pure structural junk (e.g., just "---" or "{}")
        if re.match(r"^[-=]{3,}$", para) or re.match(r"^\{.*\}$", para, re.DOTALL):
            continue
        escaped = html.escape(para).replace("\n", "<br/>")
        # Detect dialogue: starts with a quote mark or contains speech attribution
        if re.match(r'^["\u201c]', para) or re.match(
            r"^.{0,30}\s+(?:said|says|asked|replied|whispered|growled|muttered)",
            para,
        ):
            html_parts.append(f'<p class="st-narrative-dialogue">{escaped}</p>')
        else:
            html_parts.append(f'<p class="st-narrative-para">{escaped}</p>')
    return "\n".join(html_parts) if html_parts else html.escape(raw_text)


def render_card(content_html: str, *, scanline: bool = True, extra_class: str = "") -> None:
    """Render a themed panel card."""
    classes = "st-card"
    if scanline:
        classes += " st-scanline"
    if extra_class:
        classes += f" {extra_class}"
    st.markdown(f'<div class="{classes}">{content_html}</div>', unsafe_allow_html=True)


def render_hud_bar(
    *,
    planet: str = "",
    location: str = "",
    day: int = 1,
    time_str: str = "00:00",
    hp: int = 0,
    credits: int = 0,
    mood: str = "",
    stress: int = 0,
) -> None:
    """Render the top HUD bar with pill-style stat indicators."""
    
    def _pill(label, value, icon=""):
        return (
            f'<div class="st-pill">'
            f'<strong>{icon + " " if icon else ""}{label}</strong>'
            f'<span class="value">{value}</span>'
            f'</div>'
        )

    # Group 1: World Context
    loc_pills = []
    if planet and planet != "\u2014":
        loc_pills.append(_pill("SYS", html.escape(str(planet)), "🪐"))
    loc_pills.append(_pill("LOC", html.escape(str(location)), "📍"))
    loc_pills.append(_pill("DAY", str(day), "📅"))
    loc_pills.append(_pill("TIME", html.escape(time_str), "⌚"))
    
    # Group 2: Player Status
    stat_pills = []
    stat_pills.append(_pill("HP", str(hp), "❤️"))
    stat_pills.append(_pill("CR", str(credits), "💳"))
    
    if mood and mood != "\u2014":
        stat_pills.append(_pill("MOOD", html.escape(mood), "🧠"))
    
    stress_color = "#ff4b4b" if stress >= 8 else "#ffa421" if stress >= 5 else "inherit"
    stat_pills.append(
        f'<div class="st-pill" style="border-color: {stress_color if stress>=5 else "inherit"}">'
        f'<strong>⚡ STRESS</strong>'
        f'<span class="value" style="color: {stress_color}">{stress}/10</span>'
        f'</div>'
    )

    html_content = f"""
    <div class="st-hud-container st-scanline">
        <div class="st-hud-group">
            {"".join(loc_pills)}
        </div>
        <div class="st-hud-divider"></div>
        <div class="st-hud-group">
            {"".join(stat_pills)}
        </div>
    </div>
    """
    
    st.markdown(html_content, unsafe_allow_html=True)


def render_scene(
    text: str,
    *,
    turn_number: int = 0,
    time_note: str | None = None,
    typewriter: bool = False,
    location: str = "",
    planet: str = "",
) -> None:
    """Render the main narrative scene card."""
    # V2.13: Turn 2 in DB is the first playable turn (setup creates turn 1).
    # Display as "OPENING SCENE" for the first playable turn, then offset by 1.
    if turn_number <= 2 and text and text.strip() not in ("", "(no scene yet)"):
        header = "OPENING SCENE"
    elif turn_number:
        header = f"TURN {turn_number - 1}"
    else:
        header = "CURRENT SCENE"

    # Add location context to the header
    loc_parts = []
    if planet and planet != "\u2014":
        loc_parts.append(html.escape(str(planet)))
    if location and location != "\u2014":
        loc_parts.append(html.escape(str(location)))
    loc_str = " &mdash; ".join(loc_parts) if loc_parts else ""
    if loc_str:
        header = f"{header} &bull; {loc_str}"

    time_bit = f" &bull; {html.escape(time_note)}" if time_note else ""

    if not text or text.strip() == "":
        safe_text = '<em style="opacity: 0.6;">Your story is about to begin...</em>'
    else:
        # Handle companion banter separator (--- followed by italic)
        parts = text.split("\n\n---\n\n")
        safe_text = _format_narrative_html(parts[0])
        if len(parts) > 1:
            for banter in parts[1:]:
                # V2.9: Extract speaker name from banter format: "Name: 'dialogue...'"
                banter_stripped = banter.strip("*").strip()
                speaker_match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*):\s*['\"](.+?)['\"]", banter_stripped, re.DOTALL)

                if speaker_match:
                    speaker_name = speaker_match.group(1)
                    dialogue_text = speaker_match.group(2)
                    banter_html = (
                        f'<div style="margin-top: 16px; padding: 10px 14px; '
                        f'border-left: 3px solid rgba(255, 210, 80, 0.40); '
                        f'border-radius: 6px; background: rgba(0, 0, 0, 0.12);">'
                        f'<div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; '
                        f'letter-spacing: 0.5px; color: rgba(255, 210, 80, 0.90); margin-bottom: 4px;">'
                        f'🗣 {html.escape(speaker_name)}</div>'
                        f'<div style="font-style: italic; opacity: 0.90;">'
                        f'{html.escape(dialogue_text).replace(chr(10), "<br/>")}</div>'
                        f'</div>'
                    )
                else:
                    # Fallback: original format if speaker parsing fails
                    banter_escaped = html.escape(banter_stripped).replace("\n", "<br/>")
                    banter_html = (
                        f'<div style="margin-top: 16px; padding: 10px 14px; '
                        f'border-left: 3px solid rgba(255,255,255,0.15); '
                        f'font-style: italic; opacity: 0.85;">'
                        f'{banter_escaped}</div>'
                    )

                safe_text += banter_html

    scene_html = f"""
<div class="st-scene-title">{header}{time_bit}</div>
<div class="st-scene-text">{safe_text}</div>
"""
    render_card(scene_html)


def render_choice_card(
    label: str,
    *,
    risk: str = "",
    hint: str = "",
    tone_tag: str = "NEUTRAL",
    intent_style: str = "",
    strategy_tag: str = "OPTIMAL",
    theme: "ThemeTokens | None" = None,
) -> None:
    """Render a KOTOR-style choice card with tone coloring."""
    _TONE_DEFAULTS = {
        "PARAGON": ("rgba(100,180,255,0.90)", "&#9826;"),  # diamond
        "INVESTIGATE": ("rgba(255,210,80,0.90)", "&#9672;"),  # target
        "RENEGADE": ("rgba(255,80,60,0.90)", "&#9760;"),  # skull
        "NEUTRAL": ("rgba(180,180,190,0.80)", "&#9678;"),  # circle
    }
    _TONE_ATTR = {
        "PARAGON": "tone_paragon",
        "INVESTIGATE": "tone_investigate",
        "RENEGADE": "tone_renegade",
        "NEUTRAL": "tone_neutral",
    }

    tone_upper = (tone_tag or "NEUTRAL").upper()
    default_color, tone_icon = _TONE_DEFAULTS.get(tone_upper, _TONE_DEFAULTS["NEUTRAL"])
    tone_color = getattr(theme, _TONE_ATTR.get(tone_upper, ""), default_color) if theme else default_color

    # Build metadata tags
    meta_bits = []
    if risk:
        r = risk.lower()
        color = "#ff4b4b" if "risky" in r or "high" in r else "#21c354"
        meta_bits.append(
            f'<span class="tag" style="color:{color};border-color:{color}">'
            f"{html.escape(risk).upper()}</span>"
        )
    if intent_style:
        meta_bits.append(f'<span class="tag st-intent-style">{html.escape(intent_style)}</span>')
    meta_html = f'<div class="st-choice-meta">{" ".join(meta_bits)}</div>' if meta_bits else ""

    # Consequence hint
    hint_html = ""
    if hint:
        hint_html = f'<div class="st-choice-hint">{html.escape(hint)}</div>'

    card_html = (
        f'<div class="st-choice-title">'
        f'<span class="st-tone-icon" style="color:{tone_color}">{tone_icon}</span> '
        f"{html.escape(label)}"
        f"</div>"
        f"{meta_html}"
        f"{hint_html}"
    )

    render_card(card_html, extra_class=f"st-choice-card st-tone-{tone_upper.lower()}")


def render_section_header(title: str) -> None:
    """Render a styled section header."""
    st.markdown(
        f'<div class="st-section-header">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def render_news_item(
    headline: str,
    *,
    source_tag: str = "CIVNET",
    urgency: str = "LOW",
    body: str = "",
    factions: list[str] | None = None,
) -> None:
    """Render a single Comms/Briefing news item."""
    st.markdown(
        f"""<div class="st-news-item">
<span class="st-news-source">[{html.escape(source_tag)}]</span>
<span class="st-news-headline"> {html.escape(headline)}</span>
<div class="st-news-urgency">Urgency: {html.escape(urgency)}</div>
</div>""",
        unsafe_allow_html=True,
    )
    if body or factions:
        with st.expander("Details", expanded=False):
            if body:
                st.write(body)
            if factions:
                st.caption("Related: " + ", ".join(str(f) for f in factions))


def render_journal_entry(
    text: str,
    *,
    turn_number: int = 0,
    time_note: str | None = None,
) -> None:
    """Render a single journal/transcript entry card."""
    # V2.13: Offset turn display by 1 (DB turn 2 = player turn 1)
    display_turn = max(1, turn_number - 1)
    title = f"Turn {display_turn}" + (f" &bull; {html.escape(time_note)}" if time_note else "")
    safe_text = html.escape(text or "").replace("\n", "<br/>")
    render_card(
        f'<div class="st-scene-title">{title}</div>'
        f'<div class="st-scene-text">{safe_text}</div>',
    )


def render_context_panel(
    sources: list[dict[str, Any]],
    *,
    token_stats: dict[str, Any] | None = None,
) -> None:
    """Render the 'Context used' expandable panel showing RAG source titles."""
    if not sources and not token_stats:
        return
    with st.expander("Context used", expanded=False):
        if sources:
            for src in sources[:10]:
                title = src.get("title") or src.get("source") or src.get("book_title") or "Unknown"
                doc_type = src.get("doc_type", "")
                era = src.get("era", "")
                meta_parts = [p for p in [doc_type, era] if p]
                meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""
                st.markdown(
                    f'<div class="st-context-panel"><strong>{html.escape(title)}</strong>{html.escape(meta_str)}</div>',
                    unsafe_allow_html=True,
                )
        if token_stats:
            st.caption(
                f"Tokens — lore: {token_stats.get('lore_tokens', '?')}, "
                f"style: {token_stats.get('style_tokens', '?')}, "
                f"history: {token_stats.get('history_tokens', '?')}"
            )


def render_inventory(items: list[dict[str, Any]]) -> None:
    """Render inventory items."""
    if not items:
        st.caption("(empty)")
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("item_name", "?")
        qty = item.get("quantity", 0)
        st.markdown(
            f'<div class="st-pill" style="margin-bottom:4px">'
            f'<strong>{html.escape(name)}</strong> x{qty}</div>',
            unsafe_allow_html=True,
        )


def render_mental_state(
    mood: str,
    stress: int,
    active_trauma: str | None = None,
) -> None:
    """Render the mental state panel."""
    render_section_header("Mental State")
    st.caption(f"Mood: {mood or chr(0x2014)}")
    st.caption("Stress (0-10)")
    st.progress(max(0, min(10, stress)) / 10.0)
    st.caption(f"{stress}/10")
    if active_trauma:
        st.warning(f"Trauma triggered: {active_trauma}")


def render_faction_reputation(
    faction_reputation: dict[str, int],
    *,
    theme: "ThemeTokens | None" = None,
) -> None:
    """Render faction reputation tracker with color-coded bars.

    Expected schema:
        {
            "Jedi Order": 8,       # -10 (hostile) to +10 (allied)
            "Sith Empire": -5,
            "Hutt Cartel": 2,
            ...
        }
    """
    if not faction_reputation:
        st.caption("(no faction relationships)")
        return

    def _reputation_bar(faction_name: str, reputation: int) -> str:
        """Generate HTML for a single faction reputation bar."""
        # Clamp to -10 to +10 range
        rep = max(-10, min(10, reputation))

        # Calculate bar fill (0-10 scale)
        fill_percent = int(((rep + 10) / 20) * 100)  # Map -10..+10 to 0..100

        # Color gradient based on reputation
        if rep >= 7:
            bar_color = "#21c354"  # Bright green (allied)
        elif rep >= 3:
            bar_color = "#7ed956"  # Light green (friendly)
        elif rep >= -2:
            bar_color = "rgba(180, 180, 190, 0.8)"  # Gray (neutral)
        elif rep >= -6:
            bar_color = "#ffa726"  # Orange (wary)
        else:
            bar_color = "#ff4b4b"  # Red (hostile)

        # Status label
        if rep >= 7:
            status = "ALLIED"
        elif rep >= 3:
            status = "FRIENDLY"
        elif rep >= -2:
            status = "NEUTRAL"
        elif rep >= -6:
            status = "WARY"
        else:
            status = "HOSTILE"

        # Sign prefix
        sign = "+" if rep > 0 else ""

        return f"""
<div style="margin-bottom: 10px;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <span style="font-weight: 600; font-size: 0.9rem;">{html.escape(faction_name)}</span>
        <span style="font-size: 0.75rem; color: {bar_color}; font-weight: 700;">{status}</span>
    </div>
    <div style="display: flex; align-items: center; gap: 8px;">
        <div style="flex: 1; height: 8px; background: rgba(0, 0, 0, 0.3); border-radius: 4px; overflow: hidden;">
            <div style="height: 100%; width: {fill_percent}%; background: {bar_color}; transition: width 0.3s ease;"></div>
        </div>
        <span style="font-family: 'Courier New', monospace; font-size: 0.85rem; color: {bar_color}; min-width: 30px; text-align: right;">
            {sign}{rep}
        </span>
    </div>
</div>
"""

    # Sort factions by reputation (descending)
    sorted_factions = sorted(faction_reputation.items(), key=lambda x: x[1], reverse=True)

    # Build HTML for all factions
    factions_html = "".join(_reputation_bar(name, rep) for name, rep in sorted_factions)

    render_section_header("FACTION STANDING")
    st.markdown(
        f'<div class="st-faction-reputation">{factions_html}</div>',
        unsafe_allow_html=True,
    )


def render_companion_roster(
    party_status: list[dict[str, Any]],
    *,
    theme: "ThemeTokens | None" = None,
) -> None:
    """Render companion roster panel with affinity bars, loyalty stages, and mood indicators.

    Expected party_status schema:
        [
            {
                "id": str,
                "name": str,
                "affinity": int (0-100),
                "loyalty_progress": int (0=STRANGER, 1=TRUSTED, 2=LOYAL),
                "mood_tag": str | None,
            },
            ...
        ]
    """
    if not party_status:
        st.caption("(no active companions)")
        return

    # Loyalty stage names and colors
    _LOYALTY_STAGES = {
        0: ("STRANGER", "rgba(140, 140, 150, 0.8)"),  # gray
        1: ("TRUSTED", "rgba(100, 180, 255, 0.9)"),   # blue (Paragon)
        2: ("LOYAL", "rgba(255, 210, 80, 0.9)"),      # gold (Investigate)
    }

    # Mood tag color mapping
    _MOOD_COLORS = {
        "INTRIGUED": "#21c354",
        "PLEASED": "#21c354",
        "NEUTRAL": "rgba(180, 180, 190, 0.8)",
        "WARY": "#ffa726",
        "DISAPPROVES": "#ffa726",
        "HOSTILE": "#ff4b4b",
    }

    def _affinity_hearts(affinity: int) -> str:
        """Convert 0-100 affinity to heart symbols (♡♡♡♡♡)."""
        num_hearts = min(5, max(1, (affinity // 20) + 1))  # 0-19=1, 20-39=2, ..., 80-100=5
        filled = "♥" * num_hearts
        empty = "♡" * (5 - num_hearts)
        return filled + empty

    # Build HTML for each companion
    companions_html = []
    for comp in party_status:
        name = html.escape(comp.get("name", "Unknown"))
        affinity = max(0, min(100, comp.get("affinity", 0)))
        loyalty_idx = max(0, min(2, comp.get("loyalty_progress", 0)))
        mood_tag = (comp.get("mood_tag") or "NEUTRAL").upper()

        loyalty_label, loyalty_color = _LOYALTY_STAGES.get(loyalty_idx, _LOYALTY_STAGES[0])
        mood_color = _MOOD_COLORS.get(mood_tag, _MOOD_COLORS["NEUTRAL"])
        hearts = _affinity_hearts(affinity)

        # Affinity delta (if available in future schema)
        delta = comp.get("affinity_delta", 0)
        delta_html = ""
        if delta != 0:
            delta_sign = "+" if delta > 0 else ""
            delta_color = "#21c354" if delta > 0 else "#ff4b4b"
            delta_html = f'<span style="color:{delta_color};font-weight:600;margin-left:6px;">({delta_sign}{delta})</span>'

        companion_html = f"""
<div class="st-companion-card" style="
    padding: 10px 14px;
    margin-bottom: 8px;
    border-left: 3px solid {loyalty_color};
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.15);
">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <span style="font-weight: 700; font-size: 0.95rem;">{name}</span>
        <span class="st-loyalty-badge" style="
            font-size: 0.7rem;
            font-weight: 700;
            color: {loyalty_color};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        ">{loyalty_label}</span>
    </div>
    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem;">
        <span class="st-affinity-bar" style="color: #ffa726; font-size: 1rem;">
            {hearts} <span style="font-family: 'Courier New', monospace; margin-left: 4px;">{affinity}/100</span>
        </span>
        <span style="color: {mood_color}; font-size: 0.8rem; font-style: italic;">
            {mood_tag.title()}{delta_html}
        </span>
    </div>
"""
        # V2.20: Influence meter + relationship axes (if present)
        influence = comp.get("influence")
        if influence is not None:
            inf_val = max(-100, min(100, influence))
            inf_pct = int(((inf_val + 100) / 200) * 100)
            inf_color = "#21c354" if inf_val >= 30 else "#ff4b4b" if inf_val <= -30 else "rgba(180,180,190,0.8)"
            sign = "+" if inf_val > 0 else ""
            companion_html += (
                f'<div style="margin-top: 6px;">'
                f'<div style="display: flex; align-items: center; gap: 6px; font-size: 0.8rem;">'
                f'<span style="opacity: 0.7; min-width: 60px;">Influence</span>'
                f'<div style="flex: 1; height: 6px; background: rgba(0,0,0,0.3); border-radius: 3px; overflow: hidden;">'
                f'<div style="height: 100%; width: {inf_pct}%; background: {inf_color};"></div></div>'
                f'<span style="font-family: monospace; min-width: 35px; text-align: right; color: {inf_color};">{sign}{inf_val}</span>'
                f'</div>'
            )
            axes_parts = []
            for axis_key, axis_label in [("trust", "T"), ("respect", "R"), ("fear", "F")]:
                axis_val = comp.get(axis_key)
                if axis_val is not None and axis_val != 0:
                    ax_sign = "+" if axis_val > 0 else ""
                    ax_color = "#21c354" if axis_val > 0 else "#ff4b4b"
                    axes_parts.append(f'<span style="color: {ax_color}; font-size: 0.75rem;">{axis_label}:{ax_sign}{axis_val}</span>')
            if axes_parts:
                companion_html += f'<div style="display: flex; gap: 8px; margin-top: 2px; margin-left: 66px;">{" ".join(axes_parts)}</div>'
            companion_html += '</div>'
        companion_html += '</div>\n'
        companions_html.append(companion_html)

    # Render section header + companion cards
    render_section_header("PARTY ROSTER")
    st.markdown(
        '<div class="st-companion-roster">' + "\n".join(companions_html) + '</div>',
        unsafe_allow_html=True,
    )


def render_kotor_dialogue(
    suggestions: list[dict],
    *,
    theme: "ThemeTokens | None" = None,
) -> str | None:
    """Render KOTOR-style numbered dialogue list.

    Returns the intent_text of the selected option, or None if nothing selected.
    Merges dialogue and action options into a single numbered list.
    """
    if not suggestions:
        return None

    _TONE_DEFAULTS = {
        "PARAGON": ("rgba(100,180,255,0.90)", "&#9826;"),
        "INVESTIGATE": ("rgba(255,210,80,0.90)", "&#9672;"),
        "RENEGADE": ("rgba(255,80,60,0.90)", "&#9760;"),
        "NEUTRAL": ("rgba(180,180,190,0.80)", "&#9678;"),
    }
    _TONE_ATTR = {
        "PARAGON": "tone_paragon",
        "INVESTIGATE": "tone_investigate",
        "RENEGADE": "tone_renegade",
        "NEUTRAL": "tone_neutral",
    }

    # Build the numbered options HTML
    options_html = []
    for idx, sug in enumerate(suggestions):
        num = idx + 1
        label = html.escape((sug.get("label") or "Option").strip())
        tone_tag = (sug.get("tone_tag") or "NEUTRAL").upper()
        hint = sug.get("consequence_hint") or ""
        risk = (sug.get("risk_level") or "").strip().upper()

        default_color, tone_icon = _TONE_DEFAULTS.get(tone_tag, _TONE_DEFAULTS["NEUTRAL"])
        tone_color = getattr(theme, _TONE_ATTR.get(tone_tag, ""), default_color) if theme else default_color

        # Build tag badges (3-tier risk: SAFE=hidden, RISKY=yellow, DANGEROUS=red)
        tags = []
        if risk == "DANGEROUS":
            tags.append(f'<span style="color: #ff4b4b; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">[{html.escape(risk)}] ⓘ</span>')
        elif risk and risk != "SAFE":
            tags.append(f'<span style="color: #ffa726; font-size: 0.75rem; margin-left: 6px;">[{html.escape(risk)}] ⓘ</span>')
        if hint:
            tags.append(f'<span style="color: rgba(180,180,190,0.6); font-size: 0.8rem; font-style: italic; margin-left: 6px;">{html.escape(hint)}</span>')
        tag_html = "".join(tags)

        # V2.9: Risk factors rationale (why is this risky?)
        risk_factors = sug.get("risk_factors") or []
        risk_rationale_html = ""
        if risk_factors and risk in ("RISKY", "DANGEROUS"):
            factors_list = "".join(f'<div style="margin-left: 12px;">→ {html.escape(factor)}</div>' for factor in risk_factors[:3])
            risk_rationale_html = f'<div style="margin-top: 4px; font-size: 0.75rem; opacity: 0.75; line-height: 1.4;">{factors_list}</div>'

        # Extract dialogue preview from intent_text (format: "Say: '...'" or "Ask: '...'")
        intent_raw = (sug.get("intent_text") or "").strip()
        dialogue_preview = ""
        # Use greedy match to capture full dialogue (non-greedy stops at contractions like "don't")
        say_match = re.match(r"(?:Say|Ask):\s*['\"](.+)['\"]$", intent_raw, re.I | re.S)
        if not say_match:
            # Fallback: no outer quotes, grab everything after "Say: " / "Ask: "
            say_match = re.match(r"(?:Say|Ask):\s*(.+)", intent_raw, re.I | re.S)
        if say_match:
            dialogue_preview = say_match.group(1).strip().strip("'\"").strip()

        # Build the option content: label + optional dialogue preview
        if dialogue_preview:
            content_html = (
                f'<span style="font-weight: 600;">{label}</span>'
                f'<br/><span style="font-style: italic; opacity: 0.78; font-size: 0.9rem;">'
                f'&ldquo;{html.escape(dialogue_preview)}&rdquo;</span>'
            )
        else:
            content_html = f'<span style="font-weight: 600;">{label}</span>'

        # V2.9: Risk rationale (display before companion reactions)
        if risk_rationale_html:
            content_html += risk_rationale_html

        # V2.9: Companion reactions (if available)
        companion_reactions = sug.get("companion_reactions") or {}
        if companion_reactions:
            reaction_parts = []
            for comp_id, delta in companion_reactions.items():
                if delta == 0:
                    continue  # Skip neutral reactions
                # Extract short name (e.g., "comp-kira" -> "Kira")
                short_name = comp_id.replace("comp-", "").replace("_", " ").title()
                sign = "+" if delta > 0 else ""
                # Color: green for positive, red for negative
                if delta >= 5:
                    color = "#21c354"  # Bright green
                elif delta >= 1:
                    color = "#7ed956"  # Light green
                elif delta <= -5:
                    color = "#ff4b4b"  # Bright red
                else:
                    color = "#ffa726"  # Orange
                reaction_parts.append(f'<span style="color:{color};font-weight:600;">{short_name} {sign}{delta}</span>')

            if reaction_parts:
                reactions_html = f'<div style="margin-top: 6px; font-size: 0.8rem; opacity: 0.85;">{" │ ".join(reaction_parts)}</div>'
                content_html += reactions_html

        options_html.append(
            f'<div class="st-kotor-option" style="'
            f'padding: 10px 14px; margin-bottom: 6px; '
            f'border-left: 3px solid {tone_color}; '
            f'border-radius: 6px; '
            f'background: rgba(0,0,0,0.15); '
            f'display: flex; align-items: baseline; gap: 10px;">'
            f'<span style="color: {tone_color}; font-weight: 700; font-size: 1.1rem; min-width: 20px;">{num}.</span>'
            f'<span style="color: {tone_color}; font-size: 1rem;">{tone_icon}</span>'
            f'<span style="flex: 1;">{content_html}{tag_html}</span>'
            f'</div>'
        )

    # Render all options as HTML
    st.markdown(
        '<div class="st-kotor-dialogue">' + "\n".join(options_html) + '</div>',
        unsafe_allow_html=True,
    )

    # Render clickable buttons below
    selected = None
    cols_per_row = min(len(suggestions), 5)
    cols = st.columns(cols_per_row)
    for idx, sug in enumerate(suggestions):
        intent = (sug.get("intent_text") or "").strip()
        with cols[idx % cols_per_row]:
            if st.button(
                f"{idx + 1}",
                key=f"kotor_opt_{idx}",
                use_container_width=True,
                disabled=not bool(intent),
            ):
                selected = intent

    return selected


# ---------------------------------------------------------------------------
# V2.17: DialogueTurn rendering
# ---------------------------------------------------------------------------

def render_scene_header(scene_frame: dict, *, theme: "ThemeTokens | None" = None) -> None:
    """Render a scene header bar from a SceneFrame dict."""
    location = html.escape(scene_frame.get("location_name") or "Unknown Location")
    situation = html.escape(scene_frame.get("immediate_situation") or "")
    scene_type = (scene_frame.get("allowed_scene_type") or "dialogue").upper()

    _SCENE_ICONS = {
        "DIALOGUE": "&#128172;",  # speech balloon
        "COMBAT": "&#9876;",      # crossed swords
        "EXPLORATION": "&#128270;",  # magnifying glass
        "TRAVEL": "&#128640;",    # rocket
        "STEALTH": "&#128065;",   # eye
    }
    icon = _SCENE_ICONS.get(scene_type, "&#128172;")

    situation_html = f' &mdash; <span style="opacity: 0.7; font-style: italic;">{situation}</span>' if situation else ""

    # V2.18: Pressure badges (alert/heat from scene context)
    pressure_html = ""
    pressure = scene_frame.get("pressure") or {}
    if pressure:
        _ALERT_ICONS = {"Quiet": "&#128308;", "Watchful": "&#9888;&#65039;", "Lockdown": "&#128680;"}  # 🔴 ⚠️ 🚨
        _HEAT_ICONS = {"Low": "", "Noticed": "&#128064;", "Wanted": "&#128293;"}  # 👀 🔥
        alert = pressure.get("alert", "")
        heat = pressure.get("heat", "")
        badges = []
        if alert and alert != "Quiet":
            alert_icon = _ALERT_ICONS.get(alert, "")
            badges.append(
                f'<span style="margin-left: 10px; padding: 2px 8px; border-radius: 4px; '
                f'background: rgba(255,180,0,0.15); font-size: 0.8rem; opacity: 0.85;">'
                f'{alert_icon} {html.escape(alert)}</span>'
            )
        if heat and heat != "Low":
            heat_icon = _HEAT_ICONS.get(heat, "")
            badges.append(
                f'<span style="margin-left: 6px; padding: 2px 8px; border-radius: 4px; '
                f'background: rgba(255,80,60,0.15); font-size: 0.8rem; opacity: 0.85;">'
                f'{heat_icon} {html.escape(heat)}</span>'
            )
        if badges:
            pressure_html = "".join(badges)

    st.markdown(
        f'<div style="padding: 8px 14px; margin-bottom: 12px; '
        f'border-bottom: 1px solid rgba(180,180,190,0.3); '
        f'font-size: 0.95rem; color: rgba(200,200,210,0.9);">'
        f'<span style="font-weight: 700;">{icon} {location}</span>'
        f'{situation_html}'
        f'{pressure_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_npc_utterance(npc_utterance: dict, *, theme: "ThemeTokens | None" = None) -> None:
    """Render focused NPC dialogue in KOTOR style."""
    speaker = html.escape(npc_utterance.get("speaker_name") or "Narrator")
    text = html.escape(npc_utterance.get("text") or "")
    speaker_id = npc_utterance.get("speaker_id") or "narrator"
    is_narrator = speaker_id == "narrator"

    if not text:
        return

    if is_narrator:
        # Narrator observation: italic, no quotes
        st.markdown(
            f'<div style="padding: 10px 16px; margin-bottom: 12px; '
            f'background: rgba(0,0,0,0.1); border-radius: 8px; '
            f'font-style: italic; color: rgba(200,200,210,0.85); '
            f'line-height: 1.6;">'
            f'{text}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        # NPC dialogue: speaker name header + quoted text
        st.markdown(
            f'<div style="padding: 12px 16px; margin-bottom: 12px; '
            f'background: rgba(0,0,0,0.15); border-radius: 8px; '
            f'border-left: 3px solid rgba(100,180,255,0.7);">'
            f'<div style="font-weight: 700; font-size: 0.9rem; '
            f'color: rgba(100,180,255,0.9); margin-bottom: 6px; '
            f'text-transform: uppercase; letter-spacing: 0.5px;">'
            f'{speaker}</div>'
            f'<div style="font-size: 1.05rem; line-height: 1.6; '
            f'color: rgba(230,230,240,0.95);">'
            f'&ldquo;{text}&rdquo;</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_dialogue_turn(
    dialogue_turn: dict,
    *,
    theme: "ThemeTokens | None" = None,
) -> str | None:
    """Render a complete DialogueTurn: scene header + NPC utterance + player responses.

    Returns the intent_text of the selected option, or None if nothing selected.
    Falls back to render_kotor_dialogue if dialogue_turn is incomplete.
    """
    if not dialogue_turn:
        return None

    scene_frame = dialogue_turn.get("scene_frame")
    npc_utterance = dialogue_turn.get("npc_utterance")
    player_responses = dialogue_turn.get("player_responses") or []

    if not scene_frame or not npc_utterance:
        return None

    # 1. Scene header
    render_scene_header(scene_frame, theme=theme)

    # 2. NPC utterance
    render_npc_utterance(npc_utterance, theme=theme)

    # 3. Player response options (KOTOR numbered list)
    if not player_responses:
        return None

    _TONE_DEFAULTS = {
        "PARAGON": ("rgba(100,180,255,0.90)", "&#9826;"),
        "INVESTIGATE": ("rgba(255,210,80,0.90)", "&#9672;"),
        "RENEGADE": ("rgba(255,80,60,0.90)", "&#9760;"),
        "NEUTRAL": ("rgba(180,180,190,0.80)", "&#9678;"),
    }
    _TONE_ATTR = {
        "PARAGON": "tone_paragon",
        "INVESTIGATE": "tone_investigate",
        "RENEGADE": "tone_renegade",
        "NEUTRAL": "tone_neutral",
    }

    options_html = []
    for idx, resp in enumerate(player_responses):
        num = idx + 1
        display_text = html.escape((resp.get("display_text") or "Option").strip())
        tone_tag = (resp.get("tone_tag") or "NEUTRAL").upper()
        risk = (resp.get("risk_level") or "").strip().upper()
        hint = resp.get("consequence_hint") or ""

        default_color, tone_icon = _TONE_DEFAULTS.get(tone_tag, _TONE_DEFAULTS["NEUTRAL"])
        tone_color = getattr(theme, _TONE_ATTR.get(tone_tag, ""), default_color) if theme else default_color

        tags = []
        if risk == "DANGEROUS":
            tags.append(f'<span style="color: #ff4b4b; font-size: 0.75rem; font-weight: 700; margin-left: 6px;">[{html.escape(risk)}]</span>')
        elif risk and risk != "SAFE":
            tags.append(f'<span style="color: #ffa726; font-size: 0.75rem; margin-left: 6px;">[{html.escape(risk)}]</span>')
        if hint:
            tags.append(f'<span style="color: rgba(180,180,190,0.6); font-size: 0.8rem; font-style: italic; margin-left: 6px;">{html.escape(hint)}</span>')
        tag_html = "".join(tags)

        content_html = f'<span style="font-weight: 600;">{display_text}</span>'

        options_html.append(
            f'<div class="st-kotor-option" style="'
            f'padding: 10px 14px; margin-bottom: 6px; '
            f'border-left: 3px solid {tone_color}; '
            f'border-radius: 6px; '
            f'background: rgba(0,0,0,0.15); '
            f'display: flex; align-items: baseline; gap: 10px;">'
            f'<span style="color: {tone_color}; font-weight: 700; font-size: 1.1rem; min-width: 20px;">{num}.</span>'
            f'<span style="color: {tone_color}; font-size: 1rem;">{tone_icon}</span>'
            f'<span style="flex: 1;">{content_html}{tag_html}</span>'
            f'</div>'
        )

    st.markdown(
        '<div class="st-kotor-dialogue">' + "\n".join(options_html) + '</div>',
        unsafe_allow_html=True,
    )

    # Render clickable buttons
    selected = None
    cols_per_row = min(len(player_responses), 5)
    cols = st.columns(cols_per_row)
    for idx, resp in enumerate(player_responses):
        # Use display_text as the action input (Router will interpret it)
        action = resp.get("action") or {}
        intent_text = resp.get("display_text") or ""
        # For "say" actions, wrap as dialogue
        if action.get("type") == "say" and not intent_text.lower().startswith(("say:", "ask:")):
            intent_text = f"Say: '{intent_text}'"
        with cols[idx % cols_per_row]:
            if st.button(
                f"{idx + 1}",
                key=f"dt_opt_{idx}",
                use_container_width=True,
                disabled=not bool(intent_text),
            ):
                selected = intent_text

    return selected
