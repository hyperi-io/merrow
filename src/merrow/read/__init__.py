"""Diagram readers: each turns a format into the neutral Graph."""

import re
from dataclasses import dataclass, field

from merrow.graph import Graph


def skipper(patterns: object) -> re.Pattern[str] | None:
    """Return one regex matching any of a reader's `skip_labels`, or None."""
    listed = [str(p) for p in patterns] if isinstance(patterns, list) else []
    return re.compile("|".join(f"(?:{p})" for p in listed)) if listed else None


@dataclass(slots=True)
class Drawing:
    """One diagram a reader produced: a page, a slide or a scene.

    Attributes:
        name: The page or slide name, or its number.
        graph: What it holds.
        dropped: Elements left out and why, for review.
    """

    name: str
    graph: Graph
    dropped: list[str] = field(default_factory=list)
