import pytest

from merrow import write
from merrow.graph import Edge, Graph, Group, Node


def pipeline() -> Graph:
    return Graph(
        nodes=[
            Node("rx", "Receiver", "takes events", group="in"),
            Node("topic", 'Topic "raw"', group="bus"),
            Node("end", "Loader", group="out"),
            Node("xf", "Transform", group="opt"),
        ],
        edges=[
            Edge("in", "bus"),
            Edge("bus", "out", "batches"),
            Edge("bus", "opt", optional=True),
            Edge("opt", "out", "enriched", optional=True),
        ],
        groups=[
            Group("dfe", "DFE"),
            Group("in", "Ingest", "dfe"),
            Group("bus", "Bus", "dfe"),
            Group("out", "Load", "dfe"),
            Group("opt", "Optional", "dfe"),
        ],
    )


def test_writer_nests_groups_quotes_labels_and_keeps_optional_paths_dotted():
    text = write.flowchart(pipeline(), "TB")
    assert text.startswith("flowchart TB\n")
    assert 'subgraph dfe["DFE"]' in text
    assert 'topic["Topic #quot;raw#quot;"]' in text
    assert 'rx["Receiver<br/>takes events"]' in text
    assert "n_end[" in text, "a reserved word never becomes an id"
    assert 'bus -->|"batches"| out' in text
    assert "bus -.-> opt" in text
    assert 'opt -.->|"enriched"| out' in text


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        (
            Graph(nodes=[Node("a", "A")], edges=[Edge("a", "ghost")]),
            "names unknown 'ghost'",
        ),
        (Graph(nodes=[Node("a", "A", group="nowhere")]), "unknown group 'nowhere'"),
        (
            Graph(nodes=[Node("a", "A")], groups=[Group("a", "A")]),
            "used more than once",
        ),
        (Graph(groups=[Group("x", "X", "y"), Group("y", "Y", "x")]), "contains itself"),
    ],
    ids=["dangling-edge", "unknown-group", "shared-id", "group-cycle"],
)
def test_a_broken_graph_is_refused_by_name(graph, message):
    assert any(message in problem for problem in graph.problems())
    with pytest.raises(ValueError, match=message.split("'")[0]):
        write.flowchart(graph, "LR")


def test_a_graph_round_trips_through_plain_data():
    graph = pipeline()
    data = graph.to_dict()
    assert "optional" not in data["edges"][0]
    assert data["edges"][2]["optional"] is True
    assert Graph.from_dict(data) == graph


def test_mermaid_ids_are_stable_and_unique():
    taken: dict[str, str] = {}
    assert write.mermaid_id("a-b", taken) == "a_b"
    assert write.mermaid_id("a b", taken) == "a_b_2"
    assert write.mermaid_id("a-b", taken) == "a_b"
    assert write.mermaid_id("3tier", taken) == "n_3tier"


def test_score_counts_what_a_reader_recovered():
    found = pipeline()
    expected = {
        "nodes": ["Receiver", "Loader", "Missing"],
        "edges": [["Ingest", "Bus"], ["Bus", "Nowhere"]],
        "contains": [["Ingest", "Receiver"], ["DFE", "Bus"]],
    }
    assert write.score(found, expected) == {
        "nodes": 2 / 3,
        "edges": 0.5,
        "contains": 1.0,
    }
