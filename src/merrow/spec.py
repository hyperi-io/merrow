"""A diagram file: its title and a Graph, an L2 pattern with fills, or both (DESIGN D9).

The JSON Schema comes from these types, so it can't drift from what merrow reads.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import yaml
from pydantic import ConfigDict, TypeAdapter, with_config

from merrow.graph import Edge, Graph, Group, Node
from merrow.patterns import Pattern, expand


@with_config(ConfigDict(extra="forbid"))
class Fill(TypedDict, total=False):
    """One slot entry when an object id alone won't do."""

    object: str
    label: str
    subtitle: str
    id: str


@with_config(ConfigDict(extra="forbid"))
@dataclass(frozen=True, slots=True)
class Spec:
    """One diagram.

    Attributes:
        title: The `accTitle`: `L<n> <Level name> -- <scope>`.
        description: The `accDescr`: the diagram's content in one or two sentences.
        pattern: An L2 pattern id, expanded from `fills`.
        fills: Each slot's entries: object ids, or `Fill` mappings.
        nodes: Nodes drawn as given, beside any the pattern makes.
        edges: Edges drawn as given.
        groups: Groups drawn as given.
    """

    title: str
    description: str
    pattern: str | None = None
    fills: dict[str, list[str | Fill]] = field(default_factory=dict)
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)


_ADAPTER = TypeAdapter(Spec)


def schema() -> dict[str, Any]:
    """Return the diagram file's JSON Schema."""
    return _ADAPTER.json_schema()


def read(path: Path) -> Spec:
    """Return the diagram a YAML or JSON file describes.

    Raises:
        pydantic.ValidationError: A field is missing, mistyped or unknown.
        yaml.YAMLError: The file isn't YAML (JSON is YAML).
    """
    return _ADAPTER.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")))


def graph(spec: Spec, patterns: dict[str, Pattern]) -> Graph:
    """Return the spec's Graph: its pattern expanded, then its own items added.

    Raises:
        ValueError: The pattern is unknown, or its fills don't fit it.
    """
    found = Graph()
    if spec.pattern:
        if spec.pattern not in patterns:
            raise ValueError(f"no pattern {spec.pattern}")
        found = expand(patterns[spec.pattern], spec.fills)
    found.nodes += spec.nodes
    found.edges += spec.edges
    found.groups += spec.groups
    return found
