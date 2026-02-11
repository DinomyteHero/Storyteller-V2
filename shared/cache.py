"""Shared cache registry with reset support for tests."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")

_CACHES: dict[str, Any] = {}


def get_cache_value(name: str, default_factory: Callable[[], T] | None = None) -> T:
    """Return cached value; initialize with default_factory when missing."""
    if name in _CACHES:
        return _CACHES[name]
    if default_factory is None:
        raise KeyError(f"Cache '{name}' not initialized")
    value = default_factory()
    _CACHES[name] = value
    return value


def set_cache_value(name: str, value: T) -> T:
    """Set cache value and return it."""
    _CACHES[name] = value
    return value


def clear_cache(name: str) -> None:
    """Clear a single cache entry."""
    _CACHES.pop(name, None)


def clear_all_caches() -> None:
    """Clear all cached entries."""
    _CACHES.clear()
