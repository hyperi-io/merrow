"""Excalidraw scenes to a Graph.

A shape's label is the text element bound to it (`containerId`). An arrow bound
at both ends (`startBinding`, `endBinding`) is an edge, exact whatever the
layout. A frame is a named container, and a shape drawn inside a larger shape
sits in it, the same bounds rule the other readers use.
"""

import json
import re
from collections.abc import Mapping
from typing import Any

from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import Drawing, skipper


def _number(element: Mapping[str, Any], name: str) -> float:
    try:
        return float(element.get(name) or 0)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"element {element.get('id')!r}: {name} is not a number"
        ) from error


def _box(element: Mapping[str, Any]) -> Box:
    x, y = _number(element, "x"), _number(element, "y")
    return (x, y, x + _number(element, "width"), y + _number(element, "height"))


def _elements(data: bytes) -> list[Mapping[str, Any]]:
    """Return a scene's live elements, each a JSON object with an id."""
    try:
        scene = json.loads(data)
    except ValueError as error:
        raise ValueError(
            f"not an Excalidraw scene, the JSON is bad: {error}"
        ) from error
    found = scene.get("elements", []) if isinstance(scene, dict) else None
    if not isinstance(found, list):
        raise ValueError("not an Excalidraw scene: no `elements` list")
    for number, element in enumerate(found):
        if not isinstance(element, dict) or not isinstance(element.get("id"), str):
            raise ValueError(f"not an Excalidraw scene: element {number} has no id")
    return [e for e in found if not e.get("isDeleted")]


def read(data: bytes, rules: Mapping[str, object]) -> Drawing:
    """Return an Excalidraw scene as a Graph. `rules` holds `readers.excalidraw`.

    Raises:
        ValueError: The bytes aren't an Excalidraw scene: bad JSON, no `elements`
            list, an element with no id, or a field of the wrong type.
    """
    elements = _elements(data)
    try:
        return _scene(elements, rules)
    except (AttributeError, TypeError, KeyError) as error:
        raise ValueError(
            f"not an Excalidraw scene, a field has the wrong type: {error}"
        ) from error


def _scene(elements: list[Mapping[str, Any]], rules: Mapping[str, object]) -> Drawing:
    shapes = {s.strip() for s in str(rules.get("shapes", "")).split(",") if s.strip()}
    optional = {
        s.strip() for s in str(rules.get("optional_stroke", "")).split(",") if s.strip()
    }
    skip = skipper(rules.get("skip_labels"))
    scene = Drawing("scene", Graph())

    labels: dict[str, list[str]] = {}
    for element in elements:
        if element.get("type") == "text" and element.get("containerId"):
            raw = element.get("originalText") or element.get("text") or ""
            lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.split("\n")]
            kept = [ln for ln in lines if ln and not (skip and skip.fullmatch(ln))]
            labels[element["containerId"]] = kept

    frames = {e["id"]: e for e in elements if e.get("type") == "frame"}
    boxes = {
        e["id"]: _box(e)
        for e in elements
        if e.get("type") in shapes and labels.get(e["id"])
    }
    enclosing = nest_by_bounds(boxes, set(boxes))
    groups = set(enclosing.values())

    for frame_id, frame in frames.items():
        scene.graph.groups.append(Group(frame_id, frame.get("name") or ""))
    for element in elements:
        element_id = element.get("id", "")
        if element.get("type") not in shapes:
            continue
        lines = labels.get(element_id)
        if not lines:
            scene.dropped.append(f"{element_id}: unlabelled {element.get('type')}")
            continue
        parent = enclosing.get(element_id) or element.get("frameId")
        if element_id in groups:
            scene.graph.groups.append(Group(element_id, lines[0], parent))
        else:
            subtitle = " ".join(lines[1:]) or None
            scene.graph.nodes.append(Node(element_id, lines[0], subtitle, group=parent))

    known = {n.id for n in scene.graph.nodes} | {g.id for g in scene.graph.groups}
    for element in elements:
        if element.get("type") != "arrow":
            continue
        start = (element.get("startBinding") or {}).get("elementId")
        end = (element.get("endBinding") or {}).get("elementId")
        if start not in known or end not in known:
            scene.dropped.append(f"{element.get('id')}: arrow not bound at both ends")
            continue
        label = " ".join(labels.get(element.get("id", ""), [])) or None
        is_optional = element.get("strokeStyle") in optional
        scene.graph.edges.append(Edge(str(start), str(end), label, is_optional))
    return scene
