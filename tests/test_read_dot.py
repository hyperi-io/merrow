import pytest

from merrow import write
from merrow.read import dot

RULES = {
    "cluster_prefix": "cluster",
    "optional_styles": "dashed,dotted",
    "skip_labels": [],
}

SOURCE = b"""
digraph pipeline {
  node [shape=box];
  subgraph cluster_ingest { label="Ingest"; rx [label="Receiver\\nsyslog"]; }
  subgraph cluster_store {
    label="Store";
    subgraph cluster_hot { label="Hot"; ch [label="ClickHouse"]; }
  }
  plain { console; }
  rx -> topic [label="events"];
  topic -> ch;
  topic -> xf [style=dashed];
}
"""


def test_a_dot_graph_reads_with_clusters_as_groups():
    [drawing] = dot.read(SOURCE, RULES)
    graph = drawing.graph
    nodes = {n.id: n for n in graph.nodes}
    groups = {g.id: g for g in graph.groups}
    assert drawing.name == "pipeline"
    assert nodes["rx"].label == "Receiver"
    assert nodes["rx"].subtitle == "syslog"
    assert nodes["rx"].group == "cluster_ingest"
    assert groups["cluster_hot"].parent == "cluster_store"
    assert nodes["ch"].group == "cluster_hot"
    assert "topic" in nodes and "xf" in nodes, "edge ends become nodes"
    edges = {(e.source, e.target): e for e in graph.edges}
    assert edges[("rx", "topic")].label == "events"
    assert edges[("topic", "xf")].optional is True
    assert graph.problems() == []
    assert "topic -.-> xf" in write.flowchart(graph, "LR")


def test_bad_dot_is_refused():
    with pytest.raises(ValueError):
        dot.read(b"this is not dot {", RULES)
