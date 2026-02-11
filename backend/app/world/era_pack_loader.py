"""Legacy era pack loader wrappers backed by setting-pack repository."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.app.world.setting_pack_loader import clear_setting_pack_cache, get_setting_pack
from backend.app.world.era_pack_models import EraPack

logger = logging.getLogger(__name__)


def load_era_pack(era: str) -> EraPack:
    if not era or not str(era).strip():
        raise ValueError("era is required to load an era pack")
    pack = get_setting_pack(None, None, era_id=era)
    if pack is None:
        raise FileNotFoundError(f"No era pack found for '{era}'")
    return pack


def get_era_pack(era: str | None) -> EraPack | None:
    if not era or not str(era).strip():
        return None
    try:
        return load_era_pack(era)
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to load era pack '%s': %s", era, exc, exc_info=True)
        return None


def load_all_era_packs(pack_dir: Path | None = None) -> list[EraPack]:
    if pack_dir is not None:
        import os

        os.environ["ERA_PACK_DIR"] = str(pack_dir)
    from backend.app.content.repository import CONTENT_REPOSITORY

    return CONTENT_REPOSITORY.load_all_packs()


def clear_era_pack_cache() -> None:
    clear_setting_pack_cache()
