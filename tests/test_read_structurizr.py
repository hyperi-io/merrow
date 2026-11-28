import json

import pytest

from merrow import write
from merrow.read import structurizr

RULES = {"optional_tags": "Optional"}
WORKSPACE = {
    "name": "Pipeline",
    "model": {
        "people": [
            {
                "id": "1",
                "name": "Analyst",
                "relationships": [
                    {
                        "id": "r1",
                        "sourceId": "1",
                        "destinationId": "4",
                        "description": "queries",
                    }
                ],
            }
        ],
        "softwareSystems": [
            {
                "id": "2",
                "name": "Pipeline",
                "containers": [
                    {
                        "id": "3",
                        "name": "Loader",
                        "technology": "Rust",
                        "relationships": [
                            {"id": "r2", "sourceId": "3", "destinationId": "4"},
                            {
                                "id": "r3",
                                "sourceId": "3",
                                "destinationId": "5",
                                "tags": "Relationship,Optional",
                            },
                        ],
                    },
                    {"id": "4", "name": "ClickHouse"},
                    {
                        "id": "6",
                        "name": "Engine",
                        "components": [{"id": "5", "name": "Scheduler"}],
                    },
                ],
            },
            {
                "id": "9",
                "name": "Legacy",
                "relationships": [
                    {"id": "r9", "sourceId": "9", "destinationId": "404"}
                ],
            },
        ],
    },
}


def test_a_workspace_reads_with_systems_and_containers_as_groups():
    drawing = structurizr.read(json.dumps(WORKSPACE).encode(), RULES)
    graph = drawing.graph
    nodes = {n.id: n for n in graph.nodes}
    groups = {g.id: g for g in graph.groups}
    assert drawing.name == "Pipeline"
    assert set(groups) == {"2", "6"}
    assert groups["6"].parent == "2"
    assert nodes["3"].subtitle == "Rust"
    assert nodes["5"].group == "6"
    assert nodes["9"].group is None
    edges = {(e.source, e.target): e for e in graph.edges}
    assert edges[("1", "4")].label == "queries"
    assert edges[("3", "5")].optional is True
    assert any("r9" in d for d in drawing.dropped)
    assert graph.problems() == []
    assert "Loader" in write.flowchart(graph, "LR")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"junk", "JSON is bad"),
        (b"[]", "no `model` object"),
        (b"{}", "no `model` object"),
        (b'{"model": {"people": {}}}', "people is not a list of objects"),
        (b'{"model": {"people": [{"name": "x"}]}}', "a people has no id"),
        (
            b'{"model": {"people": [{"id": "1", "relationships": "r"}]}}',
            "relationships is not a list",
        ),
    ],
    ids=["junk", "list", "no-model", "people-dict", "no-id", "relationships-text"],
)
def test_malformed_workspaces_are_a_value_error(data, message):
    with pytest.raises(ValueError, match=message):
        structurizr.read(data, RULES)
