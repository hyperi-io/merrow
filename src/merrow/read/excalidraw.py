"""Excalidraw scenes to a Graph.

A shape's label is the text element bound to it (`containerId`). An arrow bound
at both ends (`startBinding`, `endBinding`) is an edge, exact whatever the
layout. A frame is a named container, and a shape drawn inside a larger shape
sits in it, the same bounds rule the other readers use.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import skipper


@dataclass(slots=True)
class Scene:
    """One Excalidraw scene.

    Attributes:
        graph: What it holds.
        dropped: Elements left out and why, for review.
    """

    graph: Graph
    dropped: list[str] = field(default_factory=list)


def _box(element: Mapping[str, Any]) -> Box:
    x, y = float(element.get("x", 0)), float(element.get("y", 0))
    return (
        x,
        y,
        x + float(element.get("width", 0)),
        y + float(element.get("height", 0)),
    )


def read(data: bytes, rules: Mapping[str, object]) -> Scene:
    """Return an Excalidraw scene as a Graph. `rules` holds `readers.excalidraw`.

    Raises:
        json.JSONDecodeError: The bytes aren't an Excalidraw scene.
    """
    elements = [
        e for e in json.loads(data).get("elements", []) if not e.get("isDeleted")
    ]
    shapes = set(str(rules.get("shapes", "")).split(","))
    optional = set(str(rules.get("optional_stroke", "")).split(","))
    skip = skipper(rules.get("skip_labels"))
    scene = Scene(Graph())

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
