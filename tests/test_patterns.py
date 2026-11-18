import json

import pytest

from merrow import compose, config, objects, patterns, profile, write
from merrow.graph import Edge, Graph, Group, Node
from merrow.lint import diagram_check as dc

LIBRARY = """objects:
  x.agent: {class: ext, label: Agent}
  x.syslog: {class: ext, label: Syslog}
  x.receiver: {class: ingest, label: Receiver, subtitle: every protocol}
  x.kafka: {class: bus, label: Kafka}
  x.transform: {class: xform, label: Transform}
  x.loader: {class: load, label: Loader}
  x.clickhouse: {class: store, label: ClickHouse}
  x.console: {class: ui, label: Console}
"""
RESTYLE = {"color": {"role": {"load": {"$value": "#123456"}}}}
FILLS = {
    "senders": ["x.agent", "x.syslog"],
    "intake": ["x.receiver"],
    "bus": ["x.kafka"],
    "loader": ["x.loader"],
    "store": ["x.clickhouse"],
}


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir()
    (repo / "merrow.yaml").write_text(LIBRARY, encoding="utf-8")
    (repo / "restyle.tokens.json").write_text(json.dumps(RESTYLE), encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    return config.load()


def drawn(settings, graph, house=None):
    house = house or profile.load(settings, "house")
    library = objects.library(settings)
    source = write.diagram(graph, house, library, "L2 Services -- Demo", "Data path.")
    block = dc.Block("demo.mmd", source, None, None)
    return source, dc.source_problems(block, frozenset(), house)


def test_an_empty_optional_slot_drops_with_its_edges(settings):
    graph = patterns.expand(patterns.library(settings)["data-path"], FILLS)
    pairs = {(e.source, e.target): e for e in graph.edges}
    assert ("bus", "loader") in pairs
    assert pairs[("bus", "loader")].optional is False, "no transform: the main path"
    assert not any("transform" in pair or "console" in pair for pair in pairs)
    assert [g.id for g in graph.groups] == ["senders"], "two senders make a group"
    assert {n.id for n in graph.nodes if n.group == "senders"} == {
        "senders-agent",
        "senders-syslog",
    }


def test_a_filled_optional_slot_turns_the_direct_edge_into_a_bypass(settings):
    fills = {**FILLS, "transform": ["x.transform"]}
    graph = patterns.expand(patterns.library(settings)["data-path"], fills)
    edges = {(e.source, e.target, e.label, e.optional) for e in graph.edges}
    assert ("bus", "transform", None, False) in edges
    assert ("transform", "loader", None, False) in edges
    assert ("bus", "loader", "bypass", True) in edges
    assert ("bus", "loader", None, False) not in edges


@pytest.mark.parametrize(
    ("fills", "said"),
    [
        ({k: v for k, v in FILLS.items() if k != "store"}, "needs slot store"),
        ({**FILLS, "cache": ["x.kafka"]}, "has no slot cache"),
    ],
    ids=["required_slot_empty", "unknown_slot"],
)
def test_a_bad_fill_is_named(settings, fills, said):
    with pytest.raises(ValueError, match=said):
        patterns.expand(patterns.library(settings)["data-path"], fills)


@pytest.mark.parametrize("transform", [False, True], ids=["direct", "bypass"])
def test_a_pattern_draws_clean_under_two_token_sets(settings, monkeypatch, transform):
    fills = {**FILLS, "transform": ["x.transform"]} if transform else FILLS
    graph = patterns.expand(patterns.library(settings)["data-path"], fills)
    source, problems = drawn(settings, graph)
    assert problems == []
    assert ("-.->|" in source) is transform, "the bypass stays, dotted"
    monkeypatch.setenv(
        "MERROW_PROFILES__HOUSE__TOKENS",
        json.dumps(["profiles/house.tokens.json", "restyle.tokens.json"]),
    )
    restyled = profile.load(config.load(), "house")
    source, problems = drawn(settings, graph, restyled)
    assert problems == []
    assert "stroke:#123456" in source


def chain(length):
    nodes = [Node(f"n{i}", f"Step {i}") for i in range(length)]
    edges = [Edge(f"n{i}", f"n{i + 1}") for i in range(length - 1)]
    return Graph(nodes, edges)


def test_a_long_chain_is_drawn_in_stacked_stages(settings):
    graph = chain(9)
    graph.edges.append(Edge("n1", "n7", "skip", optional=True))
    layout = compose.stages(graph, 4, "Stage {n}")
    assert layout.direction == "TB"
    assert [g.id for g in layout.graph.groups] == ["stage-1", "stage-2", "stage-3"]
    assert layout.inner == {"stage-1": "LR", "stage-2": "LR", "stage-3": "LR"}
    edges = {(e.source, e.target, e.label, e.optional) for e in layout.graph.edges}
    assert ("stage-1", "stage-2", None, False) in edges
    assert ("stage-2", "stage-3", None, False) in edges
    assert ("stage-1", "stage-3", "skip", True) in edges, "the optional path stays"
    assert not any(e[0].startswith("n") and e[1].startswith("stage") for e in edges)
    source, problems = drawn(settings, graph)
    assert problems == []
    assert "flowchart TB" in source
    assert "    direction LR" in source


@pytest.mark.parametrize(
    "graph",
    [chain(4), Graph(chain(6).nodes, [*chain(6).edges, Edge("n5", "n0")])],
    ids=["short", "cycle"],
)
def test_a_short_or_looped_chain_stays_left_to_right(graph):
    layout = compose.stages(graph, 4, "Stage {n}")
    assert layout.direction == "LR"
    assert layout.graph is graph


def forked(length: int) -> Graph:
    """A chain that ends in two unlinked nodes: 13 ranks leave them a stage of their own."""
    base = chain(length)
    last = f"n{length - 1}"
    nodes = [*base.nodes, Node("a", "A"), Node("b", "B")]
    return Graph(nodes, [*base.edges, Edge(last, "a"), Edge(last, "b")])


def boundary_graph(inner: int, second_group: bool = False) -> Graph:
    """A neighbour, a boundary holding a chain of `inner` nodes, and a sink."""
    chain = [f"n{i}" for i in range(inner)]
    nodes = [Node("user", "User"), Node("sink", "Sink")]
    nodes += [Node(n, n.upper(), group="box") for n in chain]
    edges = [Edge("user", chain[0], "uses"), Edge(chain[-1], "sink", "writes")]
    edges += [Edge(a, b) for a, b in zip(chain, chain[1:], strict=False)]
    groups = [Group("box", "System")]
    if second_group:
        groups.append(Group("other", "Other"))
        nodes.append(Node("x", "X", group="other"))
    return Graph(nodes, edges, groups)


@pytest.mark.parametrize(
    ("graph", "after", "stacks"),
    [
        (boundary_graph(5), 3, True),
        (boundary_graph(4), 3, True),
        (boundary_graph(3), 3, False),
        (boundary_graph(5), 0, False),
        (boundary_graph(5, second_group=True), 3, False),
        (
            Graph(
                boundary_graph(5).nodes,
                [*boundary_graph(5).edges, Edge("box", "n2")],
                boundary_graph(5).groups,
            ),
            3,
            True,
        ),
    ],
    ids=[
        "long_inside",
        "one_over",
        "short_inside",
        "off",
        "two_boundaries",
        "box_to_member",
    ],
)
def test_a_long_boundary_is_stacked_with_its_arrows_on_the_group(graph, after, stacks):
    layout = compose.stacked(graph, after)
    assert (layout is not None) is stacks
    if layout is not None:
        assert layout.direction == "TB" and layout.inner == {"box": "LR"}
        crossing = {(e.source, e.target, e.label) for e in layout.graph.edges}
        assert {("user", "box", "uses"), ("box", "sink", "writes")} <= crossing
        assert ("n0", "n1", None) in crossing, "arrows inside stay"


@pytest.mark.parametrize(
    ("graph", "has"),
    [
        (
            boundary_graph(5),
            ["flowchart TB", "    direction LR", 'user -->|"uses"| box'],
        ),
        (forked(12), ["flowchart TB", "subgraph stage_4"]),
    ],
    ids=["boundary_stacked", "stage_never_a_row"],
)
def test_the_house_profile_stacks_a_boundary_and_leaves_stages_unchained(
    settings, graph, has
):
    source, problems = drawn(settings, graph)
    assert problems == []
    for text in has:
        assert text in source
    assert "~~~" not in source
