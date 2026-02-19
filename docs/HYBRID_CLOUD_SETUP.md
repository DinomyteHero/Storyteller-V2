# Hybrid Cloud Setup Guide

Storyteller V2 supports a **hybrid local+cloud** LLM approach: lightweight structural roles run on local Ollama, while quality-critical narrative roles are routed to cloud providers (Anthropic Claude) for faster, higher-quality responses.

## Why Hybrid?

| Mode | Turn Latency | Cost/Turn | Quality |
|------|-------------|-----------|---------|
| **Local-only** (Ollama) | 25-50s | $0 | Good (model-dependent) |
| **Hybrid balanced** | 8-15s | ~$0.022 | High |
| **Hybrid quality** | 8-12s | ~$0.045 | Highest |

Local models still handle structural/classification tasks (routing, casting, knowledge graph extraction, memory management) where speed and cost matter more than prose quality. Cloud handles the 4 roles players notice most: Director, Narrator, Choice Crafter, and Mechanic.

## Quick Start (Balanced Preset)

Add to your `.env` file:

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Route the quality-critical quartet to Claude Sonnet
STORYTELLER_DIRECTOR_PROVIDER=anthropic
STORYTELLER_DIRECTOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_CHOICE_CRAFTER_PROVIDER=anthropic
STORYTELLER_CHOICE_CRAFTER_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_MECHANIC_PROVIDER=anthropic
STORYTELLER_MECHANIC_MODEL=claude-sonnet-4-5-20250929
```

That's it. All other roles remain on local Ollama automatically.

## Presets

### Budget (~$0.012/turn, ~$1.20 per 100-turn campaign)

Only the Narrator goes to cloud. Good for getting quality prose while keeping costs minimal.

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_MODEL=claude-sonnet-4-5-20250929
```

### Balanced (~$0.022/turn, ~$2.20 per 100-turn campaign)

The 4 quality-critical roles on cloud. Best balance of quality, speed, and cost.

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
STORYTELLER_DIRECTOR_PROVIDER=anthropic
STORYTELLER_DIRECTOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_CHOICE_CRAFTER_PROVIDER=anthropic
STORYTELLER_CHOICE_CRAFTER_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_MECHANIC_PROVIDER=anthropic
STORYTELLER_MECHANIC_MODEL=claude-sonnet-4-5-20250929
```

### Quality (~$0.045/turn, ~$4.50 per 100-turn campaign)

All narrative + strategic roles on cloud. Maximum quality for everything the player experiences.

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
STORYTELLER_DIRECTOR_PROVIDER=anthropic
STORYTELLER_DIRECTOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_CHOICE_CRAFTER_PROVIDER=anthropic
STORYTELLER_CHOICE_CRAFTER_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_MECHANIC_PROVIDER=anthropic
STORYTELLER_MECHANIC_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_COMPANION_SYSTEM_PROVIDER=anthropic
STORYTELLER_COMPANION_SYSTEM_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_BIBLE_PROVIDER=anthropic
STORYTELLER_BIBLE_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_PROLOGUE_PROVIDER=anthropic
STORYTELLER_PROLOGUE_MODEL=claude-sonnet-4-5-20250929
```

## Cost Estimates by Campaign Length

| Campaign Type | Turns | Budget | Balanced | Quality |
|--------------|-------|--------|----------|---------|
| Short (single arc) | ~30 | $0.36 | $0.66 | $1.35 |
| Medium (3 arcs) | ~100 | $1.20 | $2.20 | $4.50 |
| Long (saga) | ~500 | $6.00 | $11.00 | $22.50 |
| Epic (multi-era) | ~1000 | $12.00 | $22.00 | $45.00 |

## Role-by-Role Breakdown

| Role | Default (Local) | Balanced (Cloud) | Why |
|------|----------------|------------------|-----|
| Director | mistral-nemo | Claude Sonnet | Scene direction quality |
| Narrator | mistral-nemo | Claude Sonnet | Prose quality (player-facing) |
| Choice Crafter | qwen3:8b | Claude Sonnet | KOTOR-style dialogue nuance |
| Mechanic | qwen3:8b | Claude Sonnet | Action resolution context |
| Architect | qwen3:4b | qwen3:4b | Structural, fast is fine |
| Casting | qwen3:4b | qwen3:4b | NPC selection, structural |
| Continuity | qwen3:4b | qwen3:4b | Fact pruning, lightweight |
| Memory | qwen3:8b | qwen3:8b | Post-turn, not latency-critical |
| World Mind | qwen3:8b | qwen3:8b | World sim, background |
| Quest Weaver | qwen3:8b | qwen3:8b | Post-turn, not latency-critical |

## OpenAI Support

You can also use OpenAI models:

```bash
OPENAI_API_KEY=sk-your-key-here
STORYTELLER_NARRATOR_PROVIDER=openai
STORYTELLER_NARRATOR_MODEL=gpt-4o
```

Or OpenAI-compatible providers (e.g., local vLLM, Together AI):

```bash
STORYTELLER_NARRATOR_PROVIDER=openai_compat
STORYTELLER_NARRATOR_MODEL=meta-llama/Llama-3-70b
STORYTELLER_NARRATOR_BASE_URL=https://api.together.xyz/v1
STORYTELLER_NARRATOR_API_KEY=your-together-key
```

## Health Check

The `/health/detail` endpoint reports which roles are using cloud providers and whether they're reachable. At startup, the server logs a summary of all role configurations and probes cloud provider reachability.

## Hardware Recommendations

With hybrid cloud, your local GPU handles fewer LLM calls, reducing VRAM pressure and model swap overhead:

| GPU | Local-Only Performance | Hybrid Performance |
|-----|----------------------|-------------------|
| RTX 4070 12GB | 25-50s/turn | 8-15s/turn |
| RTX 3080 10GB | 30-60s/turn | 8-15s/turn |
| RTX 4090 24GB | 15-30s/turn | 6-12s/turn |
