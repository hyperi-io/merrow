import json

from merrow import write
from merrow.read import excalidraw

RULES = {
    "shapes": "rectangle,ellipse,diamond",
    "optional_stroke": "dashed,dotted",
    "skip_labels": [r"\d{1,2}"],
}


def box(eid, x, y, w, h, kind="rectangle", **extra):
    return {"id": eid, "type": kind, "x": x, "y": y, "width": w, "height": h, **extra}


def label(eid, container, text):
    return {
        "id": eid,
        "type": "text",
        "containerId": container,
        "originalText": text,
        "x": 0,
        "y": 0,
    }


def arrow(eid, start, end, style="solid"):
    binding = lambda target: {"elementId": target} if target else None  # noqa: E731
    return {
        "id": eid,
        "type": "arrow",
        "startBinding": binding(start),
        "endBinding": binding(end),
        "strokeStyle": style,
    }


SCENE = {
    "elements": [
        {
            "id": "f1",
            "type": "frame",
            "name": "Production",
            "x": 0,
            "y": 0,
            "width": 900,
            "height": 600,
        },
        box("zone", 10, 10, 500, 400, frameId="f1"),
        label("t0", "zone", "Zone A"),
        box("api", 50, 50, 100, 50),
        label("t1", "api", "API\nREST"),
        box("db", 200, 50, 100, 50, kind="ellipse"),
        label("t2", "db", "Database"),
        box("mark", 300, 300, 10, 10),
        label("t3", "mark", "3"),
        box("gone", 700, 500, 50, 50, isDeleted=True),
        arrow("a1", "api", "db"),
        arrow("a2", "api", "zone", style="dashed"),
        arrow("a3", "api", None),
    ]
}


def test_a_scene_reads_into_a_graph():
    scene = excalidraw.read(json.dumps(SCENE).encode(), RULES)
    graph = scene.graph
    nodes = {n.id: n for n in graph.nodes}
    groups = {g.id: g for g in graph.groups}
    assert set(nodes) == {"api", "db"}
    assert nodes["api"].subtitle == "REST"
    assert nodes["api"].group == "zone"
    assert groups["zone"].parent == "f1"
    assert groups["f1"].label == "Production"
    edges = {(e.source, e.target): e for e in graph.edges}
    assert set(edges) == {("api", "db"), ("api", "zone")}
    assert edges[("api", "zone")].optional is True
    assert any("a3" in d for d in scene.dropped)
    assert any("mark" in d for d in scene.dropped), "a numbered marker is no label"
    assert graph.problems() == []
    assert "api -.-> zone" in write.flowchart(graph, "LR")
