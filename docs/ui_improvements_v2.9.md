# UI Improvements V2.9 — SWTOR/KOTOR Theme Enhancement

**Implementation Date**: February 2026
**Version**: V2.9 Gameplay Overhaul UI Layer
**Status**: ✅ Complete (8/10 phases implemented)

---

## Overview

This document describes the SWTOR/KOTOR-themed UI enhancements implemented to surface V2.9 gameplay features (companion system, faction dynamics, risk assessment) while maintaining strict aesthetic alignment with KOTOR 1/2 and Mass Effect dialogue systems.

---

## ✅ Implemented Features

### 1. Companion Roster Panel
**Priority**: ⭐⭐⭐⭐⭐ HIGH IMPACT

**Location**: Sidebar → "Party Roster" expander (expanded by default)

**Visual Design**:
```
┌─────────────────────────────────────┐
│ PARTY ROSTER                        │
├─────────────────────────────────────┤
│ Kira Carsen          TRUSTED        │
│ ♥♥♥♥♡ 42/100        Intrigued (+3)  │
├─────────────────────────────────────┤
│ Ashara Zavros        STRANGER       │
│ ♥♡♡♡♡ 15/100        Neutral         │
└─────────────────────────────────────┘
```

**Features**:
- **Affinity bars**: Heart symbols (♥ filled, ♡ empty) on 0-100 scale
  - 0-19: 1 heart
  - 20-39: 2 hearts
  - 40-59: 3 hearts
  - 60-79: 4 hearts
  - 80-100: 5 hearts
- **Loyalty stages**:
  - STRANGER (gray): loyalty_progress = 0
  - TRUSTED (blue): loyalty_progress = 1
  - LOYAL (gold): loyalty_progress = 2
- **Mood indicators**: Color-coded tags
  - INTRIGUED, PLEASED → green (#21c354)
  - NEUTRAL → gray (rgba(180,180,190,0.8))
  - WARY, DISAPPROVES → orange (#ffa726)
  - HOSTILE → red (#ff4b4b)
- **Affinity delta**: Shows last turn's change (+3, -2) when available

**Data Source**: `TurnResponse.party_status: list[PartyStatusItem]`

**Files Modified**:
- `ui/components.py` (+90 lines): `render_companion_roster()`
- `ui/themes.py` (+22 lines): CSS classes
- `streamlit_app.py` (+3 lines): Sidebar integration

---

### 2. Companion Reaction Previews on Actions
**Priority**: ⭐⭐⭐⭐⭐ HIGH IMPACT

**Location**: KOTOR dialogue wheel (numbered action list)

**Visual Design**:
```
1. ◇ Negotiate peacefully
   "I have credits. We can work this out."
   [SAFE]

   Kira +2  │  Ashara -1
```

**Features**:
- **Reaction display**: Shows affinity delta per active companion
- **Color coding**:
  - +5 or more: bright green (#21c354)
  - +1 to +4: light green (#7ed956)
  - -1 to -4: orange (#ffa726)
  - -5 or less: bright red (#ff4b4b)
- **Separator**: Vertical bar (│) between companions
- **Name extraction**: Converts "comp-kira" → "Kira" (auto-capitalized)
- **Zero filtering**: Neutral reactions (delta=0) are hidden

**Schema Changes**:
- `ActionSuggestion.companion_reactions: dict[str, int]` (state.py)
- `ActionSuggestionLLM.companion_reactions: dict[str, int]` (director_schemas.py)

**Backend Integration**: ⚠️ **Schema ready, Director needs to populate**

**Files Modified**:
- `backend/app/models/state.py` (+1 line)
- `backend/app/models/director_schemas.py` (+1 line)
- `ui/components.py` (+20 lines): Display logic in `render_kotor_dialogue()`

---

### 3. Banter Speaker Attribution
**Priority**: ⭐⭐⭐ MEDIUM IMPACT

**Location**: Main narrative card (scene text)

**Visual Design**:
```
[Main narration text...]

─────────────────────────────────────
🗣 KIRA: "I've got a bad feeling about this..."
─────────────────────────────────────

[More narration...]
```

**Features**:
- **Speaker parsing**: Regex `^([A-Z][a-z]+):\s*['"](.+?)['"]` extracts name + dialogue
- **Visual styling**:
  - Speech bubble icon (🗣)
  - Uppercase speaker name in gold (tone_investigate color)
  - Border-left: 3px gold with rounded corners
  - Italic dialogue text
- **Fallback**: Original gray italic format if parsing fails

**Data Format**: Backend banter already uses `"Name: 'dialogue...'"` format

**Files Modified**:
- `ui/components.py` (+30 lines): Parser in `render_scene()`
- `ui/themes.py` (+27 lines): CSS classes `.st-banter-section`, `.st-banter-speaker`, `.st-banter-text`

---

### 4. Faction Reputation Tracker
**Priority**: ⭐⭐⭐⭐ HIGH IMPACT

**Location**: Sidebar → "Faction Standing" expander (collapsed by default)

**Visual Design**:
```
┌─────────────────────────────────────┐
│ FACTION STANDING                    │
├─────────────────────────────────────┤
│ Jedi Order          ALLIED      +8  │
│ ████████░░░░░░░░░░░░                │
├─────────────────────────────────────┤
│ Sith Empire         WARY        -6  │
│ ████░░░░░░░░░░░░░░░░                │
└─────────────────────────────────────┘
```

**Features**:
- **Reputation scale**: -10 (hostile) to +10 (allied)
- **Status labels**:
  - HOSTILE: rep <= -7
  - WARY: -6 to -3
  - NEUTRAL: -2 to +2
  - FRIENDLY: +3 to +6
  - ALLIED: +7 to +10
- **Color gradient**:
  - Red (#ff4b4b): Hostile
  - Orange (#ffa726): Wary
  - Gray (rgba(180,180,190,0.8)): Neutral
  - Light green (#7ed956): Friendly
  - Bright green (#21c354): Allied
- **Bar fill**: Maps -10..+10 to 0..100% width
- **Sorting**: Factions sorted by reputation (descending)

**Data Source**: `TurnResponse.faction_reputation: dict[str, int]`

**Files Modified**:
- `ui/components.py` (+70 lines): `render_faction_reputation()`
- `ui/themes.py` (+10 lines): CSS classes
- `streamlit_app.py` (+4 lines): Sidebar integration

---

### 5. Risk Level Rationale Display
**Priority**: ⭐⭐⭐⭐ MEDIUM-HIGH IMPACT

**Location**: KOTOR dialogue wheel (below risk badge)

**Visual Design**:
```
3. ☠ Draw your weapon
   [DANGEROUS] ⓘ

   → Outnumbered 3-to-1
   → No cover available
   → Nighttime (low visibility)
```

**Features**:
- **Info icon**: ⓘ next to [DANGEROUS] or [RISKY] badge
- **Factor list**: Up to 3 risk factors displayed with arrow prefix (→)
- **Styling**:
  - Font-size: 0.75rem
  - Opacity: 0.75
  - Indent: 12px margin-left
- **Visibility**: Only shown for RISKY or DANGEROUS actions

**Schema Changes**:
- `ActionSuggestion.risk_factors: list[str]` (state.py)
- `ActionSuggestionLLM.risk_factors: list[str]` (director_schemas.py)

**Backend Integration**: ⚠️ **Schema ready, Director/Mechanic needs to populate**

**Suggested Sources**:
- `mechanic.py::environmental_modifiers()` (outnumbered, no cover, time-of-day)
- Director tactical assessment

**Files Modified**:
- `backend/app/models/state.py` (+1 line)
- `backend/app/models/director_schemas.py` (+1 line)
- `ui/components.py` (+6 lines): Risk rationale HTML generation

---

## 🎨 CSS Theme Enhancements

All CSS classes added to **all 4 themes** (Rebel Amber, Alliance Blue, Clean Dark, Holocron Archive):

### Companion Roster Classes
```css
.st-companion-roster { margin-top: 8px; }
.st-companion-card {
  transition: all 0.2s ease;
  hover: background rgba(0,0,0,0.25), transform translateX(2px);
}
.st-affinity-bar { display: inline-flex; align-items: center; gap: 4px; }
.st-loyalty-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0,0,0,0.25);
}
```

### Banter / Companion Dialogue Classes
```css
.st-banter-section {
  margin-top: 16px;
  padding: 10px 14px;
  border-left: 3px solid {tone_investigate};
  border-radius: 6px;
  background: rgba(0,0,0,0.12);
  transition: all 0.2s ease;
  hover: background rgba(0,0,0,0.18), border-left-color {accent_primary};
}
.st-banter-speaker {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: {tone_investigate};
  margin-bottom: 4px;
  display: block;
}
.st-banter-text {
  font-style: italic;
  opacity: 0.90;
  line-height: 1.5;
}
```

### Faction Reputation Classes
```css
.st-faction-reputation { margin-top: 8px; }
.st-faction-reputation > div {
  transition: all 0.2s ease;
  hover: transform translateX(2px);
}
```

---

## 📊 Data Flow Diagram

```
Backend (v2_campaigns.py:766-815)
  ↓
  TurnResponse {
    party_status: list[PartyStatusItem] ✅
    faction_reputation: dict[str, int] ✅
    suggested_actions: list[ActionSuggestion] {
      companion_reactions: dict[str, int] ⚠️ schema ready
      risk_factors: list[str] ⚠️ schema ready
    }
  }
  ↓
Streamlit (_load_ui_data_once:1295-1320)
  ↓ extracts party_status, faction_reputation
  ↓
Sidebar (_render_right_sidebar:1320-1400)
  ↓ renders expanders
  ↓
UI Components
  ├─ render_companion_roster()
  ├─ render_faction_reputation()
  └─ render_kotor_dialogue() ← includes reactions + risk rationale
```

---

## ⚠️ Backend TODO (to complete features)

### 1. Populate `companion_reactions` in Director
**File**: `backend/app/core/agents/director.py`

**Task**: After generating suggestions, compute companion reaction deltas

**Pseudocode**:
```python
# In DirectorAgent.complete() after generating suggestions:
for suggestion in suggestions:
    suggestion.companion_reactions = {}
    for comp_id in active_party:
        # Use existing compute_companion_reactions() logic
        delta = _predict_affinity_delta(
            suggestion.tone_tag,
            suggestion.category,
            comp_personality_traits[comp_id]
        )
        if delta != 0:
            suggestion.companion_reactions[comp_id] = delta
```

**Existing Utilities**:
- `backend/app/core/companion_reactions.py::compute_companion_reactions()`
- Companion personality data in `data/companions.yaml` (108 companions with motivation, speech_quirk)

---

### 2. Populate `risk_factors` in Director/Mechanic
**Files**:
- `backend/app/core/agents/director.py` (tactical assessment)
- `backend/app/core/agents/mechanic.py` (environmental modifiers)

**Task**: Extract risk factors from environmental context

**Pseudocode**:
```python
# Option A: Director generates risk factors during suggestion creation
for suggestion in suggestions:
    if suggestion.risk_level in ("RISKY", "DANGEROUS"):
        suggestion.risk_factors = []

        # Tactical factors
        if enemy_count > player_party_count:
            suggestion.risk_factors.append(f"Outnumbered {enemy_count}-to-{player_party_count}")

        # Environmental factors (from mechanic.environmental_modifiers)
        env_mods = environmental_modifiers(state)
        if env_mods.get("no_cover"):
            suggestion.risk_factors.append("No cover available")
        if env_mods.get("time_of_day") == "NIGHT":
            suggestion.risk_factors.append("Nighttime (low visibility)")

        # Inventory factors
        if not has_weapon(player_inventory):
            suggestion.risk_factors.append("No weapon equipped")
```

**Existing Utilities**:
- `backend/app/core/agents/mechanic.py::environmental_modifiers()`
- `backend/app/models/state.py::GameState.present_npcs` (for outnumbered calculation)

---

## 🧪 Testing Guide

### Manual Testing Checklist

#### Companion Roster
- [ ] Start new campaign with 2+ companions
- [ ] Take 3-5 turns to build affinity
- [ ] Check sidebar "Party Roster" expander
- [ ] Verify heart icons update (♥♥♥♡♡)
- [ ] Verify loyalty stages transition (STRANGER → TRUSTED → LOYAL)
- [ ] Verify mood tags display with correct colors
- [ ] Test all 4 themes (Rebel Amber, Alliance Blue, Clean Dark, Holocron Archive)

#### Banter Speaker Attribution
- [ ] Play turn that generates companion banter
- [ ] Check narrative card for `---` separator
- [ ] Verify speaker name appears in gold with 🗣 icon
- [ ] Verify dialogue text is italic
- [ ] Test fallback: manually inject malformed banter (should still render)

#### Faction Reputation
- [ ] Perform actions that affect multiple factions
- [ ] Check sidebar "Faction Standing" expander
- [ ] Verify reputation bars fill correctly (0-100%)
- [ ] Verify status labels (HOSTILE, WARY, NEUTRAL, FRIENDLY, ALLIED)
- [ ] Verify color gradient (red → gray → green)
- [ ] Verify factions are sorted by reputation (descending)

#### Companion Reactions (once backend populated)
- [ ] Check KOTOR dialogue wheel
- [ ] Verify companion names appear under actions
- [ ] Verify color coding (+5 = bright green, -5 = bright red)
- [ ] Verify zero deltas are hidden
- [ ] Test with 1, 2, 3+ companions

#### Risk Rationale (once backend populated)
- [ ] Check DANGEROUS actions show [DANGEROUS] ⓘ
- [ ] Verify risk factors display below badge
- [ ] Verify up to 3 factors shown with arrow prefix (→)
- [ ] Verify only RISKY/DANGEROUS actions show rationale (SAFE actions hidden)

---

## 📈 Impact Metrics

| Feature | Lines Added | Files Modified | User Value | SWTOR/KOTOR Alignment |
|---------|-------------|----------------|------------|----------------------|
| Companion Roster | ~90 | 3 | ⭐⭐⭐⭐⭐ | ✅ Heart affinity (KOTOR) |
| Reaction Previews | ~30 | 3 | ⭐⭐⭐⭐⭐ | ✅ Companion influence (KOTOR 2) |
| Banter Attribution | ~30 | 2 | ⭐⭐⭐ | ✅ Party banter (ME2/3) |
| Faction Tracker | ~70 | 3 | ⭐⭐⭐⭐ | ✅ Reputation bars (KOTOR) |
| Risk Rationale | ~10 | 3 | ⭐⭐⭐⭐ | ✅ Tactical info (ME3) |
| **TOTAL** | **~230** | **4 unique** | **HIGH** | **AUTHENTIC** |

---

## 🎮 SWTOR/KOTOR Alignment Checklist

All features adhere to authentic KOTOR/Mass Effect design language:

- ✅ **Blue/Gold/Red tone colors** (Paragon/Investigate/Renegade)
- ✅ **Heart affinity bars** (KOTOR companion system)
- ✅ **Loyalty stages** (Mass Effect 2/3 loyalty missions)
- ✅ **Faction reputation bars** (KOTOR light/dark alignment UI)
- ✅ **Numbered dialogue wheel** (KOTOR 1/2 conversation format)
- ✅ **Console/HUD aesthetics** (scanlines, pills, glows, gradients)
- ✅ **Speech bubble icons** (ME2/3 party banter indicators)
- ✅ **Risk badges with info icons** (ME3 tactical overlay)

---

## 🚀 Future Enhancements (Phase 2)

### Medium Priority (UI-only)
- **Enhanced HUD animations**: CSS keyframes for stat changes (stress pulse, credit gain glow)
- **Genre confirmation**: Character creation step to override auto-assignment
- **Inter-party tension warnings**: Banner in companion roster when conflicts arise
- **NPC encounter roster**: "Present" panel showing named NPCs + background figures

### Low Priority
- **Accessibility enhancements**: ARIA labels, focus indicators, screen reader support
- **Radial dialogue wheel**: Custom Streamlit component (requires JavaScript)
- **Character portraits**: Image generation or asset library integration
- **Faction relationship matrix**: Graph visualization (complex)

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| V2.9.0 | 2026-02-08 | Initial implementation: Companion roster, banter attribution, faction tracker, reaction previews (schema), risk rationale (schema) |

---

## 🔗 References

- **Plan File**: `C:\Users\lbouw\.claude\plans\ethereal-jumping-bonbon.md`
- **Project Memory**: `C:\Users\lbouw\.claude\projects\C--Users-lbouw-OneDrive-Documents-StoryTeller\memory\MEMORY.md`
- **Architecture Docs**: `docs/00_overview.md` through `docs/09_call_graph.md`
- **API Reference**: `API_REFERENCE.md`

---

**Implementation Status**: ✅ **Complete** (8/10 phases)
**Backend Integration Status**: ⚠️ **Schema ready, population pending**
**Testing Status**: 🧪 **Ready for manual testing**
**Documentation Status**: ✅ **Complete**
