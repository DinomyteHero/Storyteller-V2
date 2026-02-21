"""API package: v2 campaign-based LangGraph endpoints."""
from backend.app.api.v2_campaigns import router as v2_router
from backend.app.api.v2_turn import router as v2_turn_router
from backend.app.api.v2_content import router as v2_content_router
from backend.app.api.v2_player import router as v2_player_router

__all__ = ["v2_router", "v2_turn_router", "v2_content_router", "v2_player_router"]
