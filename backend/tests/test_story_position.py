from backend.app.core.story_position import (
    initialize_story_position,
    advance_story_position,
    canonical_year_label_from_campaign,
)


def test_initialize_story_position_rebellion_year_label() -> None:
    pos = initialize_story_position(
        setting_id="star_wars",
        period_id="REBELLION",
        campaign_mode="historical",
        world_time_minutes=0,
    )
    assert pos["canonical_year_label"] == "0 ABY"
    assert pos["current_chapter"] == 1


def test_advance_story_position_tracks_chapter_and_divergence() -> None:
    pos = initialize_story_position(
        setting_id="star_wars",
        period_id="NEW_REPUBLIC",
        campaign_mode="sandbox",
        world_time_minutes=0,
    )
    out = advance_story_position(
        story_position=pos,
        world_time_minutes=960,
        campaign_mode="sandbox",
        event_types=["ERA_TRANSITION"],
    )
    assert out["current_chapter"] >= 2
    assert out["retrieval_guardrails"]["max_chapter_index"] == out["current_chapter"]
    assert out["divergence_log"]


def test_canonical_year_label_fallback_for_legacy_campaign() -> None:
    label = canonical_year_label_from_campaign(
        campaign={"time_period": "NEW_REPUBLIC", "world_time_minutes": 0},
        world_state={},
    )
    assert label == "5 ABY"
