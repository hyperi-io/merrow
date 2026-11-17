"""The neutral Graph every path produces: diagram readers, L2 patterns and AI output.

A Graph says what is connected to what and what sits inside what. It carries no
style and no layout: a profile's writer turns it into Mermaid.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Node:
    """One box.

    Attributes:
        id: Unique in the graph.
        label: The name a reader sees. Empty takes its object's label.
        subtitle: A second line, such as what the thing does.
        object: The L1 object it is, such as `dfe.loader` or `aws.eks`.
        group: The id of the group it sits in, if any.
    """

    id: str
    label: str = ""
    subtitle: str | None = None
    object: str | None = None
    group: str | None = None


@dataclass(frozen=True, slots=True)
class Edge:
    """One arrow, from `source` to `target`, each a node or group id.

    Attributes:
        source: Where the arrow starts.
        target: Where it ends.
        label: Text on the arrow.
        optional: A path that may not be taken: drawn dotted, never dropped.
    """

    source: str
    target: str
    label: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class Group:
    """A boundary that exists: a system, a stage, a region.

    Attributes:
        id: Unique in the graph, never shared with a node.
        label: Its title.
        parent: The id of the group it sits in, if any.
        object: The L1 object it is, such as `aws.vpc`.
    """

    id: str
    label: str
    parent: str | None = None
    object: str | None = None


@dataclass(slots=True)
class Graph:
    """Nodes, edges and groups, in the order they were added."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)

    def problems(self) -> list[str]:
        """Return what makes the graph unusable: dangling references, shared ids, cycles."""
        found = []
        node_ids = [n.id for n in self.nodes]
        group_ids = [g.id for g in self.groups]
        everything = node_ids + group_ids
        for duplicate in sorted({i for i in everything if everything.count(i) > 1}):
            found.append(f"id {duplicate!r} is used more than once")
        known = set(everything)
        groups = set(group_ids)
        for node in self.nodes:
            if node.group is not None and node.group not in groups:
                found.append(f"node {node.id!r} is in unknown group {node.group!r}")
        parents = {g.id: g.parent for g in self.groups}
        for group in self.groups:
            if group.parent is not None and group.parent not in groups:
                found.append(f"group {group.id!r} is in unknown group {group.parent!r}")
            seen, current = set(), group.parent
            while current is not None and current not in seen:
                seen.add(current)
                current = parents.get(current)
            if group.id in seen:
                found.append(f"group {group.id!r} contains itself")
        for edge in self.edges:
            for end in (edge.source, edge.target):
                if end not in known:
                    found.append(
                        f"edge {edge.source!r} -> {edge.target!r} names unknown {end!r}"
                    )
        return found

    def to_dict(self) -> dict[str, Any]:
        """Return the graph as plain data, for YAML or JSON."""
        return {
            "nodes": [_set_fields(n) for n in self.nodes],
            "edges": [_set_fields(e) for e in self.edges],
            "groups": [_set_fields(g) for g in self.groups],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Graph:
        """Return the graph plain data describes.

        Raises:
            TypeError: An entry has a field the model doesn't know.
        """
        return cls(
            nodes=[Node(**n) for n in data.get("nodes", [])],
            edges=[Edge(**e) for e in data.get("edges", [])],
            groups=[Group(**g) for g in data.get("groups", [])],
        )


def _set_fields(item: Node | Edge | Group) -> dict[str, Any]:
    """Return an item's fields, leaving out the ones not set."""
    return {
        key: value for key, value in asdict(item).items() if value not in (None, False)
    }


type Box = tuple[float, float, float, float]


def nest_by_bounds(
    boxes: Mapping[str, Box], groups: set[str], tolerance: float = 0.0
) -> dict[str, str]:
    """Return each item's smallest enclosing group, from page-coordinate boxes.

    For formats that place shapes over a container without parenting them: a
    draw.io cell on a zone, a PPTX shape on a frame, a Visio page shape. A box is
    (left, top, right, bottom). An item inside no group is left out.
    """

    def inside(inner: Box, outer: Box) -> bool:
        return (
            inner[0] >= outer[0] - tolerance
            and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance
            and inner[3] <= outer[3] + tolerance
        )

    def area(box: Box) -> float:
        return (box[2] - box[0]) * (box[3] - box[1])

    nested = {}
    for item, box in boxes.items():
        enclosing = [
            (area(boxes[g]), g)
            for g in groups
            if g != item
            and g in boxes
            and area(boxes[g]) > area(box)
            and inside(box, boxes[g])
        ]
        if enclosing:
            nested[item] = min(enclosing)[1]
    return nested
