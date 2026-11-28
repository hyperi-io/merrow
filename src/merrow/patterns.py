"""L2 patterns: a Graph with named slots, filled with L1 objects by the caller."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from merrow.graph import Edge, Graph, Group, Node
from merrow.naming import slug


@dataclass(frozen=True, slots=True)
class Slot:
    """One place in a pattern.

    Attributes:
        name: Its key, which edges name.
        title: The group title when the slot holds more than one object.
        optional: May be left empty, which drops it and its edges.
    """

    name: str
    title: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PatternEdge:
    """An edge between two slots, drawn only when its conditions hold.

    Attributes:
        edge: The edge, its ends slot names.
        when: Slots that must be filled.
        unless: Slots that must be empty.
    """

    edge: Edge
    when: frozenset[str] = frozenset()
    unless: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Pattern:
    """A pattern: its slots in path order and the edges between them."""

    id: str
    slots: tuple[Slot, ...]
    edges: tuple[PatternEdge, ...]


def library(settings: Any) -> dict[str, Pattern]:
    """Return every configured pattern by id.

    Raises:
        ValueError: A pattern has no `slots` or `edges`, a slot no `name`, or an
            edge no `source` or `target`.
    """
    found = {}
    for pattern_id, entry in (settings.get("patterns") or {}).items():
        try:
            slots = tuple(
                Slot(s["name"], s.get("title", s["name"]), bool(s.get("optional")))
                for s in entry["slots"]
            )
            edges = tuple(
                PatternEdge(
                    Edge(
                        e["source"],
                        e["target"],
                        e.get("label"),
                        bool(e.get("optional")),
                    ),
                    frozenset(e.get("if") or ()),
                    frozenset(e.get("unless") or ()),
                )
                for e in entry["edges"]
            )
        except KeyError as missing:
            raise ValueError(f"pattern {pattern_id} lacks {missing}") from missing
        found[pattern_id] = Pattern(pattern_id, slots, edges)
    return found


def _node(slot: str, fill: str | Mapping[str, Any], group: str | None) -> Node:
    entry = {"object": fill} if isinstance(fill, str) else dict(fill)
    name = entry.get("label") or str(entry.get("object", "")).rsplit(".", 1)[-1]
    node_id = entry.get("id") or (f"{slot}-{slug(name)}" if group else slot)
    return Node(
        node_id,
        entry.get("label", ""),
        entry.get("subtitle"),
        entry.get("object"),
        group,
    )


def expand(
    pattern: Pattern, fills: Mapping[str, Sequence[str | Mapping[str, Any]]]
) -> Graph:
    """Return the pattern as a Graph, each slot filled from `fills`.

    A fill is an object id, or a mapping of `object`, `label`, `subtitle` and
    `id`. A slot with several fills becomes a group of them.

    Raises:
        ValueError: A required slot is empty, or `fills` names an unknown slot.
    """
    names = {slot.name for slot in pattern.slots}
    unknown = sorted(set(fills) - names)
    if unknown:
        raise ValueError(f"pattern {pattern.id} has no slot {', '.join(unknown)}")
    graph = Graph()
    # The id each filled slot draws as: its group, or its one node, which a fill's `id` renames.
    drawn: dict[str, str] = {}
    for slot in pattern.slots:
        members = list(fills.get(slot.name) or ())
        if not members:
            if not slot.optional:
                raise ValueError(f"pattern {pattern.id} needs slot {slot.name}")
            continue
        group = slot.name if len(members) > 1 else None
        if group:
            graph.groups.append(Group(group, slot.title))
        nodes = [_node(slot.name, fill, group) for fill in members]
        graph.nodes += nodes
        drawn[slot.name] = group or nodes[0].id
    filled = set(drawn)
    for rule in pattern.edges:
        ends = {rule.edge.source, rule.edge.target}
        if ends <= filled and rule.when <= filled and not rule.unless & filled:
            edge = replace(
                rule.edge,
                source=drawn[rule.edge.source],
                target=drawn[rule.edge.target],
            )
            graph.edges.append(edge)
    return graph
