"""The one writer from a Graph to Mermaid. Every reader and pattern ends here.

It writes structure only: subgraphs for groups, boxes, arrows and labels. A
profile adds its frontmatter and classes on top (DESIGN D3), so nothing here
names a colour.
"""

import re
from collections.abc import Mapping

from merrow.graph import Graph, Group, Node

# Words Mermaid's flowchart grammar reserves, which can't be an id as written.
_RESERVED = {
    "end",
    "graph",
    "subgraph",
    "flowchart",
    "style",
    "class",
    "classdef",
    "click",
    "linkstyle",
    "direction",
}


def mermaid_id(raw: str, taken: dict[str, str]) -> str:
    """Return a Mermaid-safe id for `raw`, stable and unique across the diagram."""
    if raw in taken:
        return taken[raw]
    base = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_") or "n"
    if base[0].isdigit() or base.lower() in _RESERVED:
        base = f"n_{base}"
    candidate, n = base, 2
    used = set(taken.values())
    while candidate in used:
        candidate, n = f"{base}_{n}", n + 1
    taken[raw] = candidate
    return candidate


def _label(node: Node) -> str:
    text = node.label.replace('"', "#quot;")
    if node.subtitle:
        text += "<br/>" + node.subtitle.replace('"', "#quot;")
    return f'"{text}"'


def flowchart(graph: Graph, direction: str) -> str:
    """Return the graph as a Mermaid flowchart laid out in `direction` (LR, TB).

    Raises:
        ValueError: The graph has problems (dangling ids, shared ids, cycles).
    """
    problems = graph.problems()
    if problems:
        raise ValueError("; ".join(problems))
    ids: dict[str, str] = {}
    children: dict[str | None, list[Group]] = {}
    for group in graph.groups:
        children.setdefault(group.parent, []).append(group)
    members: dict[str | None, list[Node]] = {}
    for node in graph.nodes:
        members.setdefault(node.group, []).append(node)

    lines = [f"flowchart {direction}"]

    def emit(group_id: str | None, indent: str) -> None:
        for node in members.get(group_id, []):
            lines.append(f"{indent}{mermaid_id(node.id, ids)}[{_label(node)}]")
        for group in children.get(group_id, []):
            # Mermaid rejects an empty title, so an untitled group gets a space.
            title = group.label.replace('"', "#quot;") or " "
            lines.append(f'{indent}subgraph {mermaid_id(group.id, ids)}["{title}"]')
            emit(group.id, indent + "  ")
            lines.append(f"{indent}end")

    emit(None, "  ")
    for edge in graph.edges:
        source, target = mermaid_id(edge.source, ids), mermaid_id(edge.target, ids)
        arrow = "-.->" if edge.optional else "-->"
        if edge.label:
            label = edge.label.replace('"', "#quot;").replace("|", "/")
            lines.append(f'  {source} {arrow}|"{label}"| {target}')
        else:
            lines.append(f"  {source} {arrow} {target}")
    return "\n".join(lines) + "\n"


def score(found: Graph, expected: Mapping[str, list]) -> dict[str, float]:
    """Return how much of an expected graph a reader recovered, by label.

    `expected` holds `nodes` (labels), `edges` ([from, to] labels) and
    `contains` ([group, member] labels). Each score is the share recovered, 0 to 1.
    """
    by_id = {n.id: n.label for n in found.nodes} | {g.id: g.label for g in found.groups}
    got_nodes = {n.label for n in found.nodes}
    got_edges = {(by_id.get(e.source), by_id.get(e.target)) for e in found.edges}
    got_contains = {(by_id.get(n.group), n.label) for n in found.nodes if n.group}
    got_contains |= {(by_id.get(g.parent), g.label) for g in found.groups if g.parent}

    def share(wanted: list, got: set) -> float:
        return (
            sum(1 for item in wanted if tuple(item) in got or item in got) / len(wanted)
            if wanted
            else 1.0
        )

    return {
        "nodes": share(list(expected.get("nodes", [])), got_nodes),
        "edges": share([tuple(e) for e in expected.get("edges", [])], got_edges),
        "contains": share(
            [tuple(c) for c in expected.get("contains", [])], got_contains
        ),
    }
