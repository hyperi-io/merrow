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


def _list(value: object, what: str) -> list[Mapping[str, Any]]:
    """Return `value` as a list of JSON objects, each with an id for an element."""
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValueError(
            f"not a Structurizr workspace: {what} is not a list of objects"
        )
    return value


def _walk(
    elements: list[Mapping[str, Any]], kind: str, parent: str | None
) -> Iterator[tuple[str, Mapping[str, Any], str | None]]:
    for element in elements:
        if "id" not in element:
            raise ValueError(f"not a Structurizr workspace: a {kind} has no id")
        yield kind, element, parent
        child_kind = _CHILDREN.get(kind)
        if child_kind and element.get(child_kind):
            children = _list(
                element[child_kind], f"{kind} {element['id']} {child_kind}"
            )
            yield from _walk(children, child_kind, str(element["id"]))


def read(data: bytes, rules: Mapping[str, object]) -> Drawing:
    """Return a workspace's model as a Graph. `rules` holds `readers.structurizr`.

    Raises:
        ValueError: The bytes aren't a Structurizr workspace: bad JSON, no `model`
            object, or an element or relationship of the wrong shape.
    """
    try:
        workspace = json.loads(data)
    except ValueError as error:
        raise ValueError(
            f"not a Structurizr workspace, the JSON is bad: {error}"
        ) from error
    model = workspace.get("model") if isinstance(workspace, dict) else None
    if not isinstance(model, dict):
        raise ValueError("not a Structurizr workspace: no `model` object")
    optional = {
        t.strip() for t in str(rules.get("optional_tags", "")).split(",") if t.strip()
    }
    drawing = Drawing(str(workspace.get("name") or "workspace"), Graph())
    found = [
        *_walk(_list(model.get("people", []), "people"), "people", None),
        *_walk(
            _list(model.get("softwareSystems", []), "softwareSystems"),
            "softwareSystems",
            None,
        ),
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
        for relation in _list(element.get("relationships", []), "relationships"):
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
