"""Setting/period pack loader with legacy era aliases."""
from __future__ import annotations

from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.world.era_pack_models import EraPack


def load_setting_pack(setting_id: str, period_id: str) -> EraPack:
    return CONTENT_REPOSITORY.get_content(setting_id, period_id)


def get_setting_pack(setting_id: str | None, period_id: str | None, *, era_id: str | None = None) -> EraPack | None:
    try:
        return CONTENT_REPOSITORY.get_pack_by_alias(setting_id=setting_id, period_id=period_id, era_id=era_id)
    except FileNotFoundError:
        return None


def clear_setting_pack_cache() -> None:
    CONTENT_REPOSITORY.clear_cache()
