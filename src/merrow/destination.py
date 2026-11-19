"""Destinations: where a diagram is published, and the page it has there."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from merrow.profile import ProfileError, extended, fill

# The limits a destination sets. Node and subgraph counts are a profile's.
_LIMITS = ("column", "max_width", "max_height")
# What a renderer draws from a fence: every diagram, all but icon nodes, or nothing.
_MERMAID = ("all", "no-icons", "none")


@dataclass(frozen=True, slots=True)
class Destination:
    """Where a diagram is published.

    Attributes:
        name: The destination's key under `destinations`.
        limits: Rendered `column`, `max_width` and `max_height`, in px. A
            diagram wider than `column` is shown scaled to it.
        themes: The themes it renders to SVG, in order, each `render.themes`
            entry with the destination's changes on top.
        mermaid: What its renderer draws from a fence: `all`, `no-icons` or `none`.
        link: An image's link, `{diagram.name}` and `{theme.name}` left to fill.
    """

    name: str
    limits: Mapping[str, int]
    themes: Mapping[str, Mapping[str, Any]]
    mermaid: str
    link: str

    def images(self, icons: bool) -> bool:
        """Return whether a diagram is published here as images, not a fence.

        `icons` is whether the diagram has an icon node.
        """
        return self.mermaid == "none" or (icons and self.mermaid == "no-icons")

    def page_block(self, name: str, source: str, icons: bool) -> str:
        """Return the Markdown that puts a diagram on a page here.

        It is the fence, or one image a theme with the title and `accDescr` as
        alt text, then a caption with its number and parent left to write.

        Raises:
            ProfileError: The diagram goes in as images and the destination
                has no `images.link`.
        """
        said = {
            key: line.split(":", 1)[1].strip()
            for line in source.splitlines()
            for key in ("accTitle", "accDescr")
            if line.strip().startswith(f"{key}:")
        }
        title = said.get("accTitle", "")
        if not self.images(icons):
            shown = [f"```mermaid\n{source.rstrip()}\n```"]
        elif not self.link:
            raise ProfileError(f"destination {self.name} has no images.link")
        else:
            alt = f"{title}. {said.get('accDescr', '')}".strip()
            shown = [
                f"![{alt}]({fill(self.link, {'diagram.name': name, 'theme.name': theme})})"
                for theme in self.themes
            ]
        return "\n".join([*shown, "", f"*Figure N. {title}.* Up: <parent>.", ""])


def load(settings: Any, name: str | None = None) -> Destination:
    """Return the named destination, else the configured one.

    A destination that `extends` another overrides that one's entries, a
    mapping entry key by key.

    Raises:
        ProfileError: The destination, or one it extends, isn't defined, it
            lacks a page limit or `mermaid`, it sets a limit that is a
            profile's, or it renders a theme `render.themes` doesn't define.
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
    mermaid = str(entry.get("mermaid") or "")
    if mermaid not in _MERMAID:
        raise ProfileError(
            f"destination {name} has mermaid {mermaid or 'unset'}: "
            f"one of {', '.join(_MERMAID)}"
        )
    pages = settings.get("render")["themes"]
    changed = entry.get("themes") or {}
    images = entry.get("images") or {}
    themes = {}
    for theme in images.get("themes") or pages:
        if theme not in pages:
            raise ProfileError(
                f"destination {name} renders theme {theme}, which render.themes "
                "doesn't define"
            )
        themes[str(theme)] = {**pages[theme], **(changed.get(theme) or {})}
    return Destination(
        name,
        {key: int(limits[key]) for key in _LIMITS},
        themes,
        mermaid,
        str(images.get("link") or ""),
    )
