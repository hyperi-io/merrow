"""Destinations: where a diagram is published, and the page it has there."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from merrow.profile import ProfileError, extended

# The limits a destination sets. Node and subgraph counts are a profile's.
_LIMITS = ("column", "max_width", "max_height")


@dataclass(frozen=True, slots=True)
class Destination:
    """Where a diagram is published.

    Attributes:
        name: The destination's key under `destinations`.
        limits: Rendered `column`, `max_width` and `max_height`, in px. A
            diagram wider than `column` is shown scaled to it.
        themes: The themes it renders to SVG, in order, each `render.themes`
            entry with the destination's changes on top.
    """

    name: str
    limits: Mapping[str, int]
    themes: Mapping[str, Mapping[str, Any]]


def load(settings: Any, name: str | None = None) -> Destination:
    """Return the named destination, else the configured one.

    A destination that `extends` another overrides that one's entries, a
    mapping entry key by key.

    Raises:
        ProfileError: The destination, or one it extends, isn't defined, it
            lacks a page limit, it sets a limit that is a profile's, or it
            renders a theme `render.themes` doesn't define.
    """
    name = name or str(settings.get("destination"))
    entry = extended(settings.get("destinations") or {}, name, "destination")
    limits = entry.get("limits") or {}
    for key in limits:
        if key not in _LIMITS:
            raise ProfileError(
                f"destination {name} sets limits.{key}: a destination's limits are "
                f"{', '.join(_LIMITS)}, and node and subgraph counts go in a profile"
            )
    for key in _LIMITS:
        if key not in limits:
            raise ProfileError(f"destination {name} has no limits.{key}")
    pages = settings.get("render")["themes"]
    changed = entry.get("themes") or {}
    themes = {}
    for theme in (entry.get("images") or {}).get("themes") or pages:
        if theme not in pages:
            raise ProfileError(
                f"destination {name} renders theme {theme}, which render.themes "
                "doesn't define"
            )
        themes[str(theme)] = {**pages[theme], **(changed.get(theme) or {})}
    return Destination(name, {key: int(limits[key]) for key in _LIMITS}, themes)
