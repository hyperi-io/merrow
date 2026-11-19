import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from merrow import spec
from merrow.cli import app

ROOT = Path(__file__).resolve().parents[1]

LIBRARY = """objects:
  x.agent: {class: ext, label: Agent}
  x.receiver: {class: ingest, label: Receiver}
  x.kafka: {class: bus, label: Kafka}
  x.loader: {class: load, label: Loader}
  x.clickhouse: {class: store, label: ClickHouse}
"""
GOOD = """title: L2 Services -- Demo
description: Agents send events through Kafka to ClickHouse.
pattern: data-path
fills:
  senders: [x.agent]
  intake: [x.receiver]
  bus: [x.kafka]
  loader: [{object: x.loader, subtitle: schema-free insert}]
  store: [x.clickhouse]
"""
runner = CliRunner()


@pytest.fixture
def realm(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir()
    (repo / "merrow.yaml").write_text(LIBRARY, encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    return tmp_path


def validate(realm, text):
    path = realm / "demo.yaml"
    path.write_text(text, encoding="utf-8")
    return runner.invoke(app, ["graph", "validate", str(path)])


def test_the_schema_forbids_fields_merrow_does_not_read(realm):
    result = runner.invoke(app, ["graph", "schema"])
    schema = json.loads(result.output)
    assert schema["required"] == ["title", "description"]
    assert {"pattern", "fills", "nodes", "edges", "groups"} <= set(schema["properties"])
    assert schema["$defs"]["Node"]["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_a_pattern_file_validates(realm):
    result = validate(realm, GOOD)
    assert result.exit_code == 0, result.output
    assert result.output.startswith("ok")


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (GOOD.replace("pattern:", "patern:"), "patern"),
        (GOOD + "nodes: [{id: extra, lable: Extra}]\n", "lable"),
        (GOOD.replace("data-path", "no-such"), "no pattern no-such"),
        (GOOD.replace("[x.agent]", "[x.nothing]"), "unknown object 'x.nothing'"),
        (GOOD.replace("L2 Services -- Demo", "Demo"), "R8 `accTitle`"),
        (GOOD.replace("description: Agents", "summary: Agents"), "description"),
        (GOOD.replace("  store: [x.clickhouse]\n", ""), "needs slot store"),
        ("title: [unclosed\n", "flow sequence"),
        (
            GOOD + "nodes: [{id: q, label: Archive invoice?, subtitle: s}]\n",
            "quote a value",
        ),
        (
            GOOD + "nodes: [{id: q, label: Kafka, subtitle: pulls, SaaS Kafka}]\n",
            "a comma in an unquoted value",
        ),
    ],
    ids=[
        "misspelt_key",
        "misspelt_node_field",
        "unknown_pattern",
        "unknown_object",
        "bad_title",
        "missing_description",
        "empty_required_slot",
        "not_yaml",
        "bare_question_mark",
        "comma_splits_a_value",
    ],
)
def test_a_bad_file_is_named(realm, text, said):
    result = validate(realm, text)
    assert result.exit_code == 1
    assert said in result.output, result.output


@pytest.mark.parametrize(
    ("command", "svgs"),
    [
        (["render"], ["demo-dark.svg", "demo-light.svg"]),
        (["render", "--destination", "slide"], ["demo-light.svg"]),
        (["write"], []),
    ],
    ids=["render_both", "render_for_a_slide", "write_mermaid_only"],
)
def test_graph_writes_the_mermaid_and_renders_only_when_asked(realm, command, svgs):
    path = realm / "demo.yaml"
    path.write_text(GOOD, encoding="utf-8")
    out = realm / "out"
    result = runner.invoke(app, ["graph", *command, str(path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "<span>schema-free insert</span>" in (out / "demo.mmd").read_text(
        encoding="utf-8"
    )
    assert sorted(p.name for p in out.glob("*.svg")) == svgs


@pytest.mark.parametrize("command", ["write", "render"])
@pytest.mark.parametrize(
    ("files", "said"),
    [
        ({"a/demo.yaml": GOOD.replace("[x.agent]", "[x.nothing]")}, "unknown object"),
        ({"a/demo.yaml": GOOD, "b/demo.yaml": GOOD}, "both write demo"),
    ],
    ids=["bad_file", "same_stem"],
)
def test_graph_names_bad_input_and_writes_nothing(realm, command, files, said):
    paths = []
    for name, text in files.items():
        path = realm / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    out = realm / "out"
    result = runner.invoke(app, ["graph", command, *paths, "--out", str(out)])
    assert result.exit_code == 2
    assert said in result.output, result.output
    assert not out.exists() or not any(out.iterdir())


def test_validate_prints_json_with_every_problem(realm):
    good, bad = realm / "good.yaml", realm / "bad.yaml"
    good.write_text(GOOD, encoding="utf-8")
    bad.write_text(GOOD.replace("[x.agent]", "[x.nothing]"), encoding="utf-8")
    result = runner.invoke(app, ["graph", "validate", "--json", str(good), str(bad)])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report[str(good)] == []
    assert "unknown object 'x.nothing'" in report[str(bad)][0]


def test_skill_install_copies_the_packaged_skill(realm):
    result = runner.invoke(app, ["skill", "install", "--to", str(realm / "skills")])
    assert result.exit_code == 0, result.output
    installed = realm / "skills" / "merrow-diagrams" / "SKILL.md"
    assert result.output.strip() == str(installed)
    text = installed.read_text(encoding="utf-8")
    assert text.startswith("---\nname: merrow-diagrams\n")
    assert "merrow graph validate" in text
    for name in ("diagrams.md", "diagram-templates.md"):
        rules = installed.parent / name
        assert not rules.is_symlink(), f"{name} is a copy, not a link into the checkout"
        assert rules.read_bytes() == (ROOT / "style" / name).read_bytes()


def test_yes_no_and_on_stay_labels(tmp_path):
    path = tmp_path / "d.yaml"
    path.write_text(
        "title: L4 Detail -- Ask\ndescription: A choice.\n"
        "nodes:\n  - {id: a, label: yes}\n  - {id: b, label: on}\n"
        "edges:\n  - {source: a, target: b, label: no, optional: true}\n",
        encoding="utf-8",
    )
    read = spec.read(path)
    assert [n.label for n in read.nodes] == ["yes", "on"]
    assert read.edges[0].label == "no"
    assert read.edges[0].optional is True, "true and false stay booleans"


INLINE = """title: L4 Detail -- Order
description: An order waits on stock.
objects:
  flow.gate: {label: "In stock?", class: decision, shape: diamond}
  x.kafka: {label: Order topic, class: bus}
nodes:
  - {id: gate, object: flow.gate}
  - {id: topic, object: x.kafka}
edges:
  - {source: topic, target: gate}
"""


def test_a_files_own_objects_draw_and_win_for_that_file_only(realm):
    path = realm / "order.yaml"
    path.write_text(INLINE, encoding="utf-8")
    out = realm / "out"
    result = runner.invoke(app, ["graph", "write", str(path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    source = (out / "order.mmd").read_text(encoding="utf-8")
    assert 'gate{"<b>In stock?</b>"}' in source
    assert "  class gate decision\n" in source
    assert '"<b>Order topic</b>"' in source, "the file's entry wins over the library"
    good = realm / "demo.yaml"
    good.write_text(GOOD, encoding="utf-8")
    runner.invoke(app, ["graph", "write", str(good), "--out", str(out)])
    assert "Kafka" in (out / "demo.mmd").read_text(encoding="utf-8"), "only that file"


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ('{label: "In stock?",', '{lable: "In stock?",', "lable"),
        ("{label: Order topic, class: bus}", "{class: bus}", "label"),
    ],
    ids=["misspelt_key", "no_label"],
)
def test_a_bad_inline_object_is_named(realm, old, new, said):
    result = validate(realm, INLINE.replace(old, new))
    assert result.exit_code == 1
    assert said in result.output, result.output
