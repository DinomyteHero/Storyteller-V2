"""Core game engine: event store, state reducer, pipeline nodes, and agent orchestration."""
from .event_store import get_current_turn_number, append_events, get_events
from .state_reducer import initial_state, apply_event, reduce_events

__all__ = [
    "get_current_turn_number",
    "append_events",
    "get_events",
    "initial_state",
    "apply_event",
    "reduce_events",
]
