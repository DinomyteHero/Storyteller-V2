"""
Starship models for player-owned ships.
Supports acquisition, customization, and companion capacity mechanics.
"""

from typing import Optional, Dict, List
from pydantic import BaseModel, ConfigDict, Field


class StarshipStats(BaseModel):
    """Starship base statistics."""
    combat_rating: int = Field(..., ge=1, le=10, description="Space combat effectiveness (1-10)")
    speed: int = Field(..., ge=1, le=10, description="Sublight maneuverability (1-10)")
    cargo_capacity: int = Field(..., ge=10, description="Tons of cargo")
    crew_requirement: int = Field(..., ge=1, description="Minimum crew to operate")
    companion_capacity: int = Field(..., ge=2, le=12, description="Max companions aboard")
    maintenance_cost: int = Field(..., ge=0, description="Credits per day for fuel/repairs")


class StarshipUpgradeSlots(BaseModel):
    """Starship upgrade slot definitions."""
    weapons: List[str] = Field(default_factory=list, description="Available weapon upgrades")
    shields: List[str] = Field(default_factory=list, description="Available shield upgrades")
    hyperdrive: List[str] = Field(default_factory=list, description="Available hyperdrive upgrades")
    crew_quarters: List[str] = Field(default_factory=list, description="Crew capacity upgrades")
    utility: List[str] = Field(default_factory=list, description="Utility system upgrades")


class StarshipAcquisition(BaseModel):
    """How a starship can be acquired."""
    background: Optional[str] = Field(None, description="Background that grants this ship")
    purchase: Optional[str] = Field(None, description="Purchase price description")
    quest: Optional[str] = Field(None, description="Quest that rewards this ship")
    salvage: Optional[str] = Field(None, description="Salvage scenario description")
    faction_reward: Optional[str] = Field(None, description="Faction reward description")


class StarshipDefinition(BaseModel):
    """Static starship definition from starships.yaml."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Unique starship ID (e.g., ship-reb-yt1300)")
    name: str = Field(..., description="Display name")
    era: str = Field(..., description="Era where this ship is available")
    ship_class: str = Field(..., alias="class", description="Ship class (e.g., light_freighter)")
    manufacturer: str = Field(..., description="Manufacturer name")
    description: str = Field(..., description="Ship lore description")
    stats: StarshipStats
    upgrade_slots: StarshipUpgradeSlots
    acquisition_methods: List[StarshipAcquisition] = Field(default_factory=list)
    base_price: int | None = Field(None, ge=0, description="Base purchase price in credits (None = not for sale)")


class PlayerStarshipUpgrades(BaseModel):
    """Player's current starship upgrades."""
    weapons: Optional[str] = Field(None, description="Installed weapon upgrade")
    shields: Optional[str] = Field(None, description="Installed shield upgrade")
    hyperdrive: Optional[str] = Field(None, description="Installed hyperdrive upgrade")
    crew_quarters: Optional[str] = Field(None, description="Installed crew quarters upgrade")
    utility: Optional[str] = Field(None, description="Installed utility upgrade")


class PlayerStarship(BaseModel):
    """Player's owned starship instance (stored in DB)."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="DB primary key")
    campaign_id: int = Field(..., description="Campaign this ship belongs to")
    ship_type: str = Field(..., description="Starship definition ID (e.g., ship-reb-yt1300)")
    custom_name: Optional[str] = Field(None, description="Player's custom ship name")
    upgrades: PlayerStarshipUpgrades = Field(default_factory=PlayerStarshipUpgrades)
    acquired_at: str = Field(..., description="Acquisition timestamp")
    acquired_method: str = Field(..., description="How the ship was acquired")


class PlayerStarshipCreate(BaseModel):
    """Request to acquire a new starship."""
    ship_type: str = Field(..., description="Starship definition ID")
    custom_name: Optional[str] = Field(None, description="Optional custom ship name")
    acquired_method: str = Field(..., description="How the ship was acquired")


class PlayerStarshipUpgradeRequest(BaseModel):
    """Request to upgrade a starship component."""
    slot: str = Field(..., description="Upgrade slot (weapons, shields, hyperdrive, crew_quarters, utility)")
    upgrade: str = Field(..., description="Upgrade name to install")


class PlayerStarshipResponse(BaseModel):
    """API response for player starship with full definition."""
    starship: PlayerStarship
    definition: StarshipDefinition
    available_upgrades: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Remaining available upgrades per slot"
    )
