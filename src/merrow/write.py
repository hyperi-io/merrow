"""Writers from a Graph to Mermaid. Every reader and pattern ends here.

`flowchart` writes structure only: subgraphs for groups, boxes, arrows and
labels. `house` adds a profile's frontmatter, label form and classes, so no
colour is named here.
"""

import re
from collections.abc import Callable, Mapping, Sequence

from merrow.compose import stages
from merrow.graph import Graph, Group, Node
from merrow.objects import L1Object, bind
from merrow.profile import Profile, fill

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


def _quoted(text: str) -> str:
    return text.replace('"', "#quot;")


def _label(node: Node) -> str:
    text = _quoted(node.label)
    if node.subtitle:
        text += "<br/>" + _quoted(node.subtitle)
    return f'["{text}"]'


def flowchart(
    graph: Graph,
    direction: str,
    label: Callable[[Node], str] = _label,
    head: Sequence[str] = (),
    ids: dict[str, str] | None = None,
    inner: Mapping[str, str] | None = None,
) -> str:
    """Return the graph as a Mermaid flowchart laid out in `direction` (LR, TB).

    `label` gives a node's shape and label, `head` the lines after the
    `flowchart` line, `ids` collects each graph id's Mermaid id, and `inner`
    sets the direction inside a group.

    Raises:
        ValueError: The graph has problems (dangling ids, shared ids, cycles).
    """
    problems = graph.problems()
    if problems:
        raise ValueError("; ".join(problems))
    ids = {} if ids is None else ids
    inner = {} if inner is None else inner
    children: dict[str | None, list[Group]] = {}
    for group in graph.groups:
        children.setdefault(group.parent, []).append(group)
    members: dict[str | None, list[Node]] = {}
    for node in graph.nodes:
        members.setdefault(node.group, []).append(node)

    lines = [f"flowchart {direction}", *(f"  {line}" for line in head)]

    def emit(group_id: str | None, indent: str) -> None:
        for node in members.get(group_id, []):
            lines.append(f"{indent}{mermaid_id(node.id, ids)}{label(node)}")
        for group in children.get(group_id, []):
            # Mermaid rejects an empty title, so an untitled group gets a space.
            title = _quoted(group.label) or " "
            lines.append(f'{indent}subgraph {mermaid_id(group.id, ids)}["{title}"]')
            if group.id in inner:
                lines.append(f"{indent}  direction {inner[group.id]}")
            emit(group.id, indent + "  ")
            lines.append(f"{indent}end")

    emit(None, "  ")
    for edge in graph.edges:
        source, target = mermaid_id(edge.source, ids), mermaid_id(edge.target, ids)
        arrow = "-.->" if edge.optional else "-->"
        if edge.label:
            text = _quoted(edge.label).replace("|", "/")
            lines.append(f'  {source} {arrow}|"{text}"| {target}')
        else:
            lines.append(f"  {source} {arrow} {target}")
    return "\n".join(lines) + "\n"


def house(
    graph: Graph,
    profile: Profile,
    library: Mapping[str, L1Object],
    title: str,
    description: str,
) -> str:
    """Return the graph as a flowchart in `profile`'s look, its objects bound.

    `title` is the `accTitle` (`L<n> <Level> -- <scope>`), `description` the
    `accDescr`. A chain past the profile's `max_ranks` is drawn as pattern B.

    Raises:
        ValueError: The graph has problems, names an unknown object, or an
            object styles as a class the profile doesn't define.
    """
    bound, problems = bind(graph, library)
    styles: dict[str, list[str]] = {}
    for node in bound.nodes:
        known = library.get(node.object) if node.object else None
        if known is not None and known.style not in profile.classes:
            problems.append(
                f"object {known.id!r} styles as {known.style!r}, not a "
                f"{profile.name} class"
            )
        elif known is not None:
            styles.setdefault(known.style, []).append(node.id)
    if problems:
        raise ValueError("; ".join(problems))

    def label(node: Node) -> str:
        form = profile.node_label["subtitle" if node.subtitle else "plain"]
        fields = {"node.label": _quoted(node.label)}
        fields["node.subtitle"] = _quoted(node.subtitle or "")
        return fill(form, fields)

    ids: dict[str, str] = {}
    head = [f"accTitle: {title}", f"accDescr: {description}"]
    layout = stages(bound, profile.max_ranks, profile.stage_title)
    body = flowchart(layout.graph, layout.direction, label, head, ids, layout.inner)
    order = [line.split()[1] for line in profile.class_lines]
    tail = [
        f"class {','.join(mermaid_id(n, ids) for n in styles[name])} {name}"
        for name in sorted(styles, key=order.index)
    ]
    tail += profile.class_lines
    tail += [f"style {ids[g.id]} {profile.boundary}" for g in layout.graph.groups]
    return f"{profile.fronts['flowchart']}\n{body}" + "".join(
        f"  {line}\n" for line in tail
    )


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
