"""Graphviz DOT to Graphs, one per graph in the file.

A node's label is its `label` attribute, else its name. A subgraph whose name
starts with `cluster` is a group, nested as written. An edge whose style is one
of the configured optional styles is optional.
"""

import re
from collections.abc import Mapping

import pydot

from merrow.graph import Edge, Graph, Group, Node
from merrow.read import Drawing, skipper


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return text[1:-1] if len(text) > 1 and text[0] == text[-1] == '"' else text


def read(data: bytes, rules: Mapping[str, object]) -> list[Drawing]:
    """Return every graph in a DOT file as a Graph. `rules` holds `readers.dot`.

    Raises:
        ValueError: The bytes aren't DOT pydot can parse.
    """
    parsed = pydot.graph_from_dot_data(data.decode("utf-8"))
    if not parsed:
        raise ValueError("no graph in the DOT input")
    cluster = str(rules.get("cluster_prefix", "cluster"))
    optional = {
        s.strip() for s in str(rules.get("optional_styles", "")).split(",") if s.strip()
    }
    skip = skipper(rules.get("skip_labels"))
    return [_drawing(g, cluster, optional, skip) for g in parsed]


def _drawing(
    root: pydot.Dot, cluster: str, optional: set[str], skip: re.Pattern[str] | None
) -> Drawing:
    drawing = Drawing(_clean(root.get_name()) or "graph", Graph())
    seen: set[str] = set()

    def visit(graph: pydot.Graph, group: str | None) -> None:
        for node in graph.get_nodes():
            name = _clean(node.get_name())
            if name in ("node", "edge", "graph") or name in seen:
                continue
            seen.add(name)
            lines = [
                ln.strip()
                for ln in _clean(node.get("label") or name).split("\\n")
                if ln.strip()
            ]
            if skip is not None:
                lines = [ln for ln in lines if not skip.fullmatch(ln)]
            subtitle = " ".join(lines[1:]) or None
            drawing.graph.nodes.append(
                Node(name, lines[0] if lines else name, subtitle, group=group)
            )
        for sub in graph.get_subgraphs():
            sub_name = _clean(sub.get_name())
            if sub_name.startswith(cluster):
                label = _clean(sub.get("label")) or sub_name
                drawing.graph.groups.append(Group(sub_name, label, group))
                visit(sub, sub_name)
            else:
                visit(sub, group)
        for edge in graph.get_edges():
            source, target = _clean(edge.get_source()), _clean(edge.get_destination())
            for end in (source, target):
                if end not in seen:
                    seen.add(end)
                    drawing.graph.nodes.append(Node(end, end, group=group))
            label = _clean(edge.get("label")) or None
            style = _clean(edge.get("style"))
            drawing.graph.edges.append(Edge(source, target, label, style in optional))

    visit(root, None)
    return drawing
