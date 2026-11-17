"""Pattern B: a long chain recomposed as LR stage groups stacked TB."""

import graphlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from merrow.graph import Edge, Graph, Group


@dataclass(frozen=True, slots=True)
class Layout:
    """A graph and the directions it is written in.

    Attributes:
        graph: The graph, stage groups added when it was recomposed.
        direction: The flowchart's direction.
        inner: The direction inside each group that sets its own.
    """

    graph: Graph
    direction: str
    inner: Mapping[str, str] = field(default_factory=dict)


def _outermost(graph: Graph) -> dict[str, str]:
    """Return each node and group id's outermost enclosing group, else itself."""
    parent = {g.id: g.parent for g in graph.groups}
    parent |= {n.id: n.group for n in graph.nodes}
    found = {}
    for item in parent:
        top = item
        while parent.get(top) is not None:
            top = str(parent[top])
        found[item] = top
    return found


def ranks(graph: Graph) -> dict[str, int] | None:
    """Return each top-level node or group's longest-path rank, None on a cycle."""
    top = _outermost(graph)
    before: dict[str, set[str]] = {unit: set() for unit in top.values()}
    for edge in graph.edges:
        source, target = top[edge.source], top[edge.target]
        if source != target:
            before[target].add(source)
    try:
        order = list(graphlib.TopologicalSorter(before).static_order())
    except graphlib.CycleError:
        return None
    rank: dict[str, int] = {}
    for unit in order:
        rank[unit] = max((rank[p] + 1 for p in before[unit]), default=0)
    return rank


def stages(graph: Graph, max_ranks: int, title: str) -> Layout:
    """Return the graph as pattern B when its chain runs past `max_ranks`, else LR.

    Ranks split evenly into stage groups titled from `title` (`{n}` is the
    stage number). Edges inside a stage stay. Edges between two stages merge
    into one solid stage-to-stage edge, plus one dotted edge for each optional
    label, so a bypass stays on the diagram.
    """
    rank = ranks(graph)
    if rank is None or max(rank.values(), default=0) < max_ranks:
        return Layout(graph, "LR")
    count = max(rank.values()) + 1
    stage_count = math.ceil(count / max_ranks)
    size = math.ceil(count / stage_count)
    stage_ids = [f"stage-{n}" for n in range(1, stage_count + 1)]
    stage = {unit: stage_ids[r // size] for unit, r in rank.items()}
    top = _outermost(graph)

    groups = [Group(s, title.format(n=n)) for n, s in enumerate(stage_ids, 1)]
    groups += [g if g.parent else replace(g, parent=stage[g.id]) for g in graph.groups]
    nodes = [n if n.group else replace(n, group=stage[n.id]) for n in graph.nodes]
    edges: list[Edge] = []
    crossing: dict[tuple[str, str], list[Edge]] = {}
    for edge in graph.edges:
        pair = (stage[top[edge.source]], stage[top[edge.target]])
        if pair[0] == pair[1]:
            edges.append(edge)
        else:
            crossing.setdefault(pair, []).append(edge)
    for (source, target), found in crossing.items():
        solid = {e.label for e in found if not e.optional}
        if solid:
            edges.append(Edge(source, target, solid.pop() if len(solid) == 1 else None))
        for label in dict.fromkeys(e.label for e in found if e.optional):
            edges.append(Edge(source, target, label, optional=True))
    inner = dict.fromkeys(stage_ids, "LR")
    return Layout(Graph(nodes, edges, groups), "TB", inner)
