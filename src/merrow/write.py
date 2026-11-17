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


GROUP_ICON = "%% merrow:group-icon"


def misfits(profile: Profile, known: L1Object) -> list[str]:
    """Return why an object can't be drawn in the profile: its class or shape."""
    found = []
    if known.style and known.style not in profile.classes:
        found.append(
            f"{known.id} styles as {known.style!r}, not a {profile.name} class"
        )
    if known.shape is not None and known.shape not in profile.shapes:
        found.append(
            f"{known.id} has shape {known.shape!r}, not a {profile.name} shape"
        )
    return found


def profile_label(profile: Profile, node: Node, shape: str | None = None) -> str:
    """Return a node's shape and label in the profile's label form."""
    form = profile.node_label["subtitle" if node.subtitle else "plain"]
    opening, closing = profile.shapes[shape or profile.default_shape]
    fields = {"node.label": _quoted(node.label), "shape.open": opening}
    fields |= {"node.subtitle": _quoted(node.subtitle or ""), "shape.close": closing}
    return fill(form, fields)


def _icon_node(form: str, node: Node, icon: str, size: int) -> str:
    text = _quoted(node.label) + (
        f"<br/>{_quoted(node.subtitle)}" if node.subtitle else ""
    )
    return fill(form, {"node.icon": icon, "node.text": text, "node.size": str(size)})


def _group_style(profile: Profile, known: L1Object | None, problems: list[str]) -> str:
    """Return a group's boundary style: its object's group style, else the profile's."""
    name = known.group_style if known else None
    if known is None or not name or not profile.group_boundaries:
        return profile.boundary
    if name not in profile.group_boundaries:
        problems.append(
            f"{known.id} has group style {name!r}, not a {profile.name} one"
        )
    return profile.group_boundaries.get(name, profile.boundary)


def diagram(
    graph: Graph,
    profile: Profile,
    library: Mapping[str, L1Object],
    title: str,
    description: str,
) -> str:
    """Return the graph as a flowchart in `profile`'s look, its objects bound.

    `title` is the `accTitle` (`L<n> <Level> -- <scope>`), `description` the
    `accDescr`. A chain past the profile's `max_ranks` is drawn as pattern B.
    Where the profile draws icons, a node whose object has one is drawn as it.

    Raises:
        ValueError: The graph has problems, names an unknown object, or an
            object's class, shape or group style isn't the profile's.
    """
    bound, problems = bind(graph, library)
    styles: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for node in bound.nodes:
        known = library.get(node.object) if node.object else None
        if known is not None:
            wrong = misfits(profile, known)
            problems += wrong
            if wrong:
                continue
        if known is not None and known.icon and profile.icon_node:
            size = profile.icon_sizes.get(known.icon)
            if size is None:
                problems.append(f"{known.id} icon {known.icon} is in no built pack")
                continue
            labels[node.id] = _icon_node(profile.icon_node, node, known.icon, size)
            continue
        style = (known.style if known else "") or profile.default_class
        styles.setdefault(style, []).append(node.id)
        labels[node.id] = profile_label(profile, node, known.shape if known else None)
    layout = stages(bound, profile.max_ranks, profile.stage_title)
    group_objects = {
        g.id: library.get(g.object) if g.object else None for g in layout.graph.groups
    }
    group_styles = {
        group_id: _group_style(profile, known, problems)
        for group_id, known in group_objects.items()
    }
    if problems:
        raise ValueError("; ".join(problems))

    ids: dict[str, str] = {}
    head = [f"accTitle: {title}", f"accDescr: {description}"]
    body = flowchart(
        layout.graph,
        layout.direction,
        lambda node: labels[node.id],
        head,
        ids,
        layout.inner,
    )
    order = [line.split()[1] for line in profile.class_lines]
    tail = [
        f"class {','.join(mermaid_id(n, ids) for n in styles[name])} {name}"
        for name in sorted(styles, key=order.index)
    ]
    tail += profile.class_lines
    tail += [f"style {ids[gid]} {style}" for gid, style in group_styles.items()]
    if profile.group_icons:
        tail += [
            f"{GROUP_ICON} {ids[gid]} {known.icon}"
            for gid, known in group_objects.items()
            if known is not None and known.icon
        ]
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
