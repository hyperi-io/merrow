"""L1 objects: a thing drawn the same way everywhere, defined once in config."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from merrow.graph import Graph


@dataclass(frozen=True, slots=True)
class L1Object:
    """One `objects` entry.

    Attributes:
        id: Its key, such as `dfe.loader` or `aws.eks`.
        style: The profile class it is drawn with, such as `load` or `ext`.
        label: The name a node takes when it gives none.
        subtitle: The second line a node takes when it gives none.
        icon: An Iconify key, `prefix:name`, for profiles that draw icons.
    """

    id: str
    style: str
    label: str
    subtitle: str | None = None
    icon: str | None = None


def library(settings: Any) -> dict[str, L1Object]:
    """Return every configured object by id.

    Raises:
        KeyError: An entry has no `class` or no `label`.
    """
    found = {}
    for object_id, entry in (settings.get("objects") or {}).items():
        found[object_id] = L1Object(
            object_id,
            str(entry["class"]),
            str(entry["label"]),
            entry.get("subtitle"),
            entry.get("icon"),
        )
    return found


def bind(graph: Graph, objects: Mapping[str, L1Object]) -> tuple[Graph, list[str]]:
    """Return the graph with each node's missing label and subtitle from its object.

    The second value lists what can't be drawn: an unknown object, or a node
    with neither a label nor an object.
    """
    problems = []
    nodes = []
    for node in graph.nodes:
        known = objects.get(node.object) if node.object else None
        if node.object and known is None:
            problems.append(f"node {node.id!r} names unknown object {node.object!r}")
        if known is not None:
            node = replace(
                node,
                label=node.label or known.label,
                subtitle=node.subtitle or known.subtitle,
            )
        if not node.label:
            problems.append(f"node {node.id!r} has no label and no object")
        nodes.append(node)
    return Graph(nodes, list(graph.edges), list(graph.groups)), problems
