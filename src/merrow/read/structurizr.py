"""Structurizr workspace JSON (C4 models) to a Graph.

People and software systems sit at the top. A system with containers is a group
holding them, and a container with components is a group holding those. Every
element lists its own relationships, so edges are exact. A relationship tagged
with a configured tag is optional.
"""

import json
from collections.abc import Iterator, Mapping
from typing import Any

from merrow.graph import Edge, Graph, Group, Node
from merrow.read import Drawing

# Each C4 level and the key holding the level below it.
_CHILDREN = {"softwareSystems": "containers", "containers": "components"}


def _walk(
    elements: list[Mapping[str, Any]], kind: str, parent: str | None
) -> Iterator[tuple[str, Mapping[str, Any], str | None]]:
    for element in elements:
        yield kind, element, parent
        child_kind = _CHILDREN.get(kind)
        if child_kind and element.get(child_kind):
            yield from _walk(element[child_kind], child_kind, str(element["id"]))


def read(data: bytes, rules: Mapping[str, object]) -> Drawing:
    """Return a workspace's model as a Graph. `rules` holds `readers.structurizr`.

    Raises:
        json.JSONDecodeError: The bytes aren't JSON.
        KeyError: The JSON has no `model`.
    """
    workspace = json.loads(data)
    model = workspace["model"]
    optional = {
        t.strip() for t in str(rules.get("optional_tags", "")).split(",") if t.strip()
    }
    drawing = Drawing(str(workspace.get("name") or "workspace"), Graph())
    found = [
        *_walk(model.get("people", []), "people", None),
        *_walk(model.get("softwareSystems", []), "softwareSystems", None),
    ]
    for kind, element, parent in found:
        element_id = str(element["id"])
        child_kind = _CHILDREN.get(kind)
        if child_kind and element.get(child_kind):
            drawing.graph.groups.append(
                Group(element_id, element.get("name", element_id), parent)
            )
        else:
            subtitle = element.get("technology") or element.get("description") or None
            drawing.graph.nodes.append(
                Node(
                    element_id, element.get("name", element_id), subtitle, group=parent
                )
            )
    known = {n.id for n in drawing.graph.nodes} | {g.id for g in drawing.graph.groups}
    for _, element, _ in found:
        for relation in element.get("relationships", []):
            source, target = (
                str(relation.get("sourceId")),
                str(relation.get("destinationId")),
            )
            if source not in known or target not in known:
                drawing.dropped.append(
                    f"{relation.get('id')}: relationship to an unknown element"
                )
                continue
            tags = {t.strip() for t in str(relation.get("tags", "")).split(",")}
            label = relation.get("description") or None
            drawing.graph.edges.append(
                Edge(source, target, label, bool(tags & optional))
            )
    return drawing
