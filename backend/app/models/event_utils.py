"""Event model utilities."""
from __future__ import annotations

from backend.app.models.events import Event


def ensure_event(e: Event | dict, default_event_type: str = "") -> Event:
    """
    Convert dict to Event if needed.

    This utility handles the common pattern of accepting either Event objects
    or dictionaries and ensuring we have an Event instance.

    Args:
        e: Either an Event object or a dictionary with event data
        default_event_type: Default event_type to use if not present in dict

    Returns:
        Event object

    Examples:
        >>> event = ensure_event({"event_type": "dialogue", "payload": {}})
        >>> isinstance(event, Event)
        True
        >>> event2 = ensure_event(Event(event_type="action"))
        >>> isinstance(event2, Event)
        True
        >>> event3 = ensure_event({"payload": {}}, default_event_type="NPC_SPAWN")
        >>> event3.event_type
        'NPC_SPAWN'
    """
    if isinstance(e, Event):
        return e
    if isinstance(e, dict):
        # Fill in default event_type if not present
        if "event_type" not in e and default_event_type:
            e = {**e, "event_type": default_event_type}
        return Event(**e)
    return e
