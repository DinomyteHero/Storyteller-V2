"""
FastAPI endpoints for player-owned starship management.
Supports acquisition, customization, and upgrade mechanics.
"""

import json
import logging
import sqlite3
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
import yaml

from backend.app.models.starship import (
    PlayerStarship,
    PlayerStarshipCreate,
    PlayerStarshipResponse,
    PlayerStarshipUpgradeRequest,
    PlayerStarshipUpgrades,
    StarshipDefinition,
)

logger = logging.getLogger(__name__)
from backend.app.db.connection import get_db
from backend.app.config import DATA_ROOT

router = APIRouter(prefix="/starships", tags=["starships"])


def _load_starship_definitions() -> dict[str, StarshipDefinition]:
    """Load all starship definitions from starships.yaml."""
    starships_path = DATA_ROOT / "static" / "starships.yaml"
    with starships_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    definitions = {}
    for ship_data in data.get("starships", []):
        try:
            ship = StarshipDefinition.model_validate(ship_data)
            definitions[ship.id] = ship
        except ValidationError as e:
            # Log validation errors but don't crash
            logger.warning(f"Failed to validate starship {ship_data.get('id')}: {e}")

    return definitions


def _get_starship_definition(ship_type: str) -> StarshipDefinition:
    """Get a specific starship definition."""
    definitions = _load_starship_definitions()
    if ship_type not in definitions:
        raise HTTPException(status_code=404, detail=f"Starship type '{ship_type}' not found")
    return definitions[ship_type]


@router.get("/definitions", response_model=List[StarshipDefinition])
def list_starship_definitions(era: Optional[str] = None):
    """
    List all available starship definitions.
    Optionally filter by era.
    """
    definitions = _load_starship_definitions()
    ships = list(definitions.values())

    if era:
        ships = [s for s in ships if s.era.upper() == era.upper()]

    return ships


@router.get("/definitions/{ship_type}", response_model=StarshipDefinition)
def get_starship_definition(ship_type: str):
    """Get a specific starship definition."""
    return _get_starship_definition(ship_type)


@router.get("/campaign/{campaign_id}", response_model=List[PlayerStarshipResponse])
def list_player_starships(campaign_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """
    List all starships owned by a campaign.
    Returns full ship data with definitions and available upgrades.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, campaign_id, ship_type, custom_name, upgrades_json, acquired_at, acquired_method
        FROM player_starships
        WHERE campaign_id = ?
        """,
        (campaign_id,)
    )

    rows = cursor.fetchall()
    if not rows:
        return []

    results = []
    for row in rows:
        upgrades_data = json.loads(row[4]) if row[4] else {}
        upgrades = PlayerStarshipUpgrades.model_validate(upgrades_data)

        player_ship = PlayerStarship(
            id=row[0],
            campaign_id=row[1],
            ship_type=row[2],
            custom_name=row[3],
            upgrades=upgrades,
            acquired_at=row[5],
            acquired_method=row[6],
        )

        # Get definition
        definition = _get_starship_definition(player_ship.ship_type)

        # Calculate available upgrades (exclude already installed)
        available_upgrades = {}
        for slot in ["weapons", "shields", "hyperdrive", "crew_quarters", "utility"]:
            slot_upgrades = getattr(definition.upgrade_slots, slot, [])
            installed = getattr(upgrades, slot, None)
            available_upgrades[slot] = [u for u in slot_upgrades if u != installed]

        results.append(
            PlayerStarshipResponse(
                starship=player_ship,
                definition=definition,
                available_upgrades=available_upgrades,
            )
        )

    return results


@router.post("/campaign/{campaign_id}/acquire", response_model=PlayerStarshipResponse)
def acquire_starship(
    campaign_id: int,
    request: PlayerStarshipCreate,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Acquire a new starship for a campaign.
    Validates that the ship type exists and records acquisition method.
    """
    # Validate ship type exists
    definition = _get_starship_definition(request.ship_type)

    # Check if campaign exists
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns WHERE id = ?", (campaign_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    # Insert new starship
    cursor.execute(
        """
        INSERT INTO player_starships (campaign_id, ship_type, custom_name, upgrades_json, acquired_method)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            campaign_id,
            request.ship_type,
            request.custom_name,
            "{}",
            request.acquired_method,
        )
    )
    conn.commit()

    ship_id = cursor.lastrowid

    # Fetch and return
    cursor.execute(
        """
        SELECT id, campaign_id, ship_type, custom_name, upgrades_json, acquired_at, acquired_method
        FROM player_starships
        WHERE id = ?
        """,
        (ship_id,)
    )
    row = cursor.fetchone()

    upgrades = PlayerStarshipUpgrades()
    player_ship = PlayerStarship(
        id=row[0],
        campaign_id=row[1],
        ship_type=row[2],
        custom_name=row[3],
        upgrades=upgrades,
        acquired_at=row[5],
        acquired_method=row[6],
    )

    # Calculate available upgrades (all slots available for new ship)
    available_upgrades = {
        "weapons": definition.upgrade_slots.weapons,
        "shields": definition.upgrade_slots.shields,
        "hyperdrive": definition.upgrade_slots.hyperdrive,
        "crew_quarters": definition.upgrade_slots.crew_quarters,
        "utility": definition.upgrade_slots.utility,
    }

    return PlayerStarshipResponse(
        starship=player_ship,
        definition=definition,
        available_upgrades=available_upgrades,
    )


@router.patch("/{ship_id}/upgrade", response_model=PlayerStarshipResponse)
def upgrade_starship(
    ship_id: int,
    request: PlayerStarshipUpgradeRequest,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Install an upgrade on a starship.
    Validates that the upgrade is available for the ship type.
    """
    # Fetch ship
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, campaign_id, ship_type, custom_name, upgrades_json, acquired_at, acquired_method
        FROM player_starships
        WHERE id = ?
        """,
        (ship_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Starship {ship_id} not found")

    # Parse current upgrades
    upgrades_data = json.loads(row[4]) if row[4] else {}
    upgrades = PlayerStarshipUpgrades.model_validate(upgrades_data)

    # Get definition
    definition = _get_starship_definition(row[2])

    # Validate slot
    valid_slots = ["weapons", "shields", "hyperdrive", "crew_quarters", "utility"]
    if request.slot not in valid_slots:
        raise HTTPException(status_code=400, detail=f"Invalid slot: {request.slot}")

    # Validate upgrade is available for this ship
    available = getattr(definition.upgrade_slots, request.slot, [])
    if request.upgrade not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Upgrade '{request.upgrade}' not available for slot '{request.slot}'"
        )

    # Install upgrade
    setattr(upgrades, request.slot, request.upgrade)

    # Update DB
    cursor.execute(
        """
        UPDATE player_starships
        SET upgrades_json = ?
        WHERE id = ?
        """,
        (json.dumps(upgrades.model_dump(exclude_none=True)), ship_id)
    )
    conn.commit()

    # Fetch updated ship
    cursor.execute(
        """
        SELECT id, campaign_id, ship_type, custom_name, upgrades_json, acquired_at, acquired_method
        FROM player_starships
        WHERE id = ?
        """,
        (ship_id,)
    )
    row = cursor.fetchone()

    updated_upgrades_data = json.loads(row[4]) if row[4] else {}
    updated_upgrades = PlayerStarshipUpgrades.model_validate(updated_upgrades_data)

    player_ship = PlayerStarship(
        id=row[0],
        campaign_id=row[1],
        ship_type=row[2],
        custom_name=row[3],
        upgrades=updated_upgrades,
        acquired_at=row[5],
        acquired_method=row[6],
    )

    # Calculate remaining available upgrades
    available_upgrades = {}
    for slot in valid_slots:
        slot_upgrades = getattr(definition.upgrade_slots, slot, [])
        installed = getattr(updated_upgrades, slot, None)
        available_upgrades[slot] = [u for u in slot_upgrades if u != installed]

    return PlayerStarshipResponse(
        starship=player_ship,
        definition=definition,
        available_upgrades=available_upgrades,
    )


@router.delete("/{ship_id}")
def delete_starship(ship_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Delete a starship (e.g., if sold or destroyed)."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM player_starships WHERE id = ?", (ship_id,))
    conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Starship {ship_id} not found")

    return {"message": f"Starship {ship_id} deleted successfully"}


@router.patch("/{ship_id}/rename")
def rename_starship(
    ship_id: int,
    custom_name: str,
    conn: sqlite3.Connection = Depends(get_db)
):
    """Rename a player's starship."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE player_starships SET custom_name = ? WHERE id = ?",
        (custom_name, ship_id)
    )
    conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Starship {ship_id} not found")

    return {"message": f"Starship {ship_id} renamed to '{custom_name}'"}
