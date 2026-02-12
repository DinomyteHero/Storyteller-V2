"""`storyteller models` — show effective role/provider/model configuration."""
from __future__ import annotations

from backend.app.config import MODEL_CONFIG


def register(subparsers) -> None:
    p = subparsers.add_parser("models", help="Show effective model/provider config by role")
    p.set_defaults(func=run)


def run(args) -> int:
    print("Effective LLM model config (after env overrides):")
    print()
    for role in sorted(MODEL_CONFIG):
        cfg = MODEL_CONFIG[role]
        provider = cfg.get("provider", "")
        model = cfg.get("model", "")
        fallback_provider = cfg.get("fallback_provider", "")
        fallback_model = cfg.get("fallback_model", "")
        line = f"- {role}: provider={provider} model={model}"
        if fallback_provider:
            line += f" fallback_provider={fallback_provider}"
        if fallback_model:
            line += f" fallback_model={fallback_model}"
        print(line)

    print("\nOverride pattern:")
    print("  STORYTELLER_<ROLE>_PROVIDER, STORYTELLER_<ROLE>_MODEL, STORYTELLER_<ROLE>_BASE_URL")
    print("Example (Narrator on cloud):")
    print("  STORYTELLER_NARRATOR_PROVIDER=openai")
    print("  STORYTELLER_NARRATOR_MODEL=gpt-5.2-mini")
    print("  STORYTELLER_NARRATOR_API_KEY=<your-key>")
    return 0
