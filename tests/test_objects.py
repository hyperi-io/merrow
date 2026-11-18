import json

import pytest

from merrow import config, objects, profile, write
from merrow.graph import Edge, Graph, Group, Node
from merrow.lint import diagram_check as dc

TITLE = "L2 Services -- Demo"
DESCRIPTION = "Events reach the loader through the bus."
LIBRARY = """objects:
  demo.loader: {class: load, label: Loader, subtitle: schema-free insert}
  demo.bus: {class: bus, label: Kafka}
  demo.web: {class: ui, label: Console}
"""
RESTYLED = """objects:
  demo.loader: {class: xform, label: Loader, subtitle: batch insert}
  demo.bus: {class: bus, label: Kafka}
  demo.web: {class: ui, label: Console}
"""
INGEST = Graph(
    [
        Node("bus", object="demo.bus", group="core"),
        Node("loader", object="demo.loader", group="core"),
    ],
    [Edge("bus", "loader", "events")],
    [Group("core", "Core")],
)
QUERY = Graph(
    [Node("loader", "Writer", object="demo.loader"), Node("web", object="demo.web")],
    [Edge("web", "loader", "query"), Edge("web", "loader", optional=True)],
)


def settings_with(monkeypatch, tmp_path, library):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir(exist_ok=True)
    (repo / "merrow.yaml").write_text(library, encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    return config.load()


def written(settings, graph):
    house = profile.load(settings, "house")
    source = write.diagram(graph, house, objects.library(settings), TITLE, DESCRIPTION)
    block = dc.Block("demo.mmd", source, None, None)
    return source, dc.source_problems(block, frozenset(), house)


def test_one_object_change_restyles_every_diagram_using_it(monkeypatch, tmp_path):
    before = settings_with(monkeypatch, tmp_path, LIBRARY)
    ingest, ingest_problems = written(before, INGEST)
    query, query_problems = written(before, QUERY)
    assert ingest_problems == query_problems == []
    assert "class loader load" in ingest
    assert "class loader load" in query
    assert "<span>schema-free insert</span>" in ingest
    assert "<b>Writer</b>" in query, "a node's own label beats its object's"
    assert "web -.-> loader" in query, "an optional path stays, dotted"

    after = settings_with(monkeypatch, tmp_path, RESTYLED)
    for graph in (INGEST, QUERY):
        source, problems = written(after, graph)
        assert problems == []
        assert "class loader xform" in source
        assert "<span>batch insert</span>" in source
        assert "class loader load" not in source


def test_a_written_house_diagram_carries_the_whole_profile(monkeypatch, tmp_path):
    settings = settings_with(monkeypatch, tmp_path, LIBRARY)
    house = profile.load(settings, "house")
    source, _ = written(settings, INGEST)
    assert source.startswith(house.fronts["flowchart"] + "\nflowchart LR\n")
    assert all(f"  {line}\n" in source for line in house.class_lines)
    assert f"  style core {house.boundary}\n" in source
    assert f"  accTitle: {TITLE}\n" in source


@pytest.mark.parametrize(
    ("graph", "said"),
    [
        (Graph([Node("a", object="demo.nothing")]), "unknown object 'demo.nothing'"),
        (Graph([Node("a")]), "no label and no object"),
        (Graph([Node("a", "A", group="nowhere")]), "unknown group 'nowhere'"),
    ],
    ids=["unknown_object", "no_label", "graph_problem"],
)
def test_a_graph_that_cannot_be_drawn_is_refused(monkeypatch, tmp_path, graph, said):
    settings = settings_with(monkeypatch, tmp_path, LIBRARY)
    with pytest.raises(ValueError, match=said):
        written(settings, graph)


def test_an_object_styled_outside_the_profile_is_refused(monkeypatch, tmp_path):
    settings = settings_with(
        monkeypatch, tmp_path, "objects:\n  demo.x: {class: neon, label: X}\n"
    )
    with pytest.raises(ValueError, match="styles as 'neon', not a house class"):
        written(settings, Graph([Node("x", object="demo.x")]))


def test_label_text_is_never_read_as_a_token(monkeypatch, tmp_path):
    settings = settings_with(monkeypatch, tmp_path, LIBRARY)
    source, problems = written(settings, Graph([Node("a", 'Say "{color.ink}"')]))
    assert "<b>Say #quot;{color.ink}#quot;</b>" in source
    assert problems == []


@pytest.mark.parametrize(
    ("shape", "drawn"),
    [
        ("cylinder", '[("<b>Store</b>")]'),
        ("stadium", '(["<b>Store</b>"])'),
        (None, '("<b>Store</b>")'),
    ],
    ids=["cylinder", "stadium", "default_rounded"],
)
def test_an_object_shape_sets_the_brackets(monkeypatch, tmp_path, shape, drawn):
    entry = (
        f"{{class: store, label: Store, shape: {shape}}}"
        if shape
        else "{class: store, label: Store}"
    )
    settings = settings_with(
        monkeypatch, tmp_path, f"objects:\n  demo.store: {entry}\n"
    )
    source, problems = written(settings, Graph([Node("ch", object="demo.store")]))
    assert f"  ch{drawn}\n" in source
    assert problems == []


def test_a_shape_outside_the_profile_is_refused(monkeypatch, tmp_path):
    settings = settings_with(
        monkeypatch,
        tmp_path,
        "objects:\n  demo.x: {class: store, label: X, shape: hexagon}\n",
    )
    with pytest.raises(ValueError, match="has shape 'hexagon', not a house shape"):
        written(settings, Graph([Node("x", object="demo.x")]))


def test_a_node_with_no_object_takes_the_profile_default_class(monkeypatch, tmp_path):
    settings = settings_with(monkeypatch, tmp_path, LIBRARY)
    graph = Graph([Node("repo", "Deploy repo"), Node("web", object="demo.web")])
    source, problems = written(settings, graph)
    assert "  class repo part\n" in source
    assert "  class web ui\n" in source
    assert problems == []


@pytest.mark.parametrize(
    ("built", "expected"),
    [
        (
            {"titles": {"amazon-ec2": "Amazon EC2", "bus": "Generated bus"}},
            {"demo.amazon-ec2": "Amazon EC2", "demo.bus": "Kafka"},
        ),
        (None, {"demo.bus": "Kafka"}),
        ({}, {"demo.bus": "Kafka"}),
    ],
    ids=["pack_built", "pack_not_built", "pack_built_before_titles"],
)
def test_a_pack_titles_become_objects_and_configured_ones_win(
    monkeypatch, tmp_path, built, expected
):
    packs = tmp_path / "packs"
    packs.mkdir()
    if built is not None:
        pack = {"prefix": "demo", "icons": {}, **built}
        (packs / "demo.json").write_text(json.dumps(pack), encoding="utf-8")
    monkeypatch.setenv("MERROW_PACKS_DIR", str(packs))
    settings = settings_with(
        monkeypatch,
        tmp_path,
        "generated_objects:\n  - {pack: demo, id_prefix: demo.}\n"
        "objects:\n  demo.bus: {class: bus, label: Kafka}\n",
    )
    found = objects.library(settings)
    assert {k: v.label for k, v in found.items() if k.startswith("demo.")} == expected
    if built:
        assert found["demo.amazon-ec2"].icon == "demo:amazon-ec2"
