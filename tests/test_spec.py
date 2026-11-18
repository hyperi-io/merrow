import json

import pytest
from typer.testing import CliRunner

from merrow.cli import app

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
    ],
)
def test_a_bad_file_is_named(realm, text, said):
    result = validate(realm, text)
    assert result.exit_code == 1
    assert said in result.output, result.output


@pytest.mark.parametrize(
    ("command", "svgs"),
    [("render", ["demo-dark.svg", "demo-light.svg"]), ("write", [])],
    ids=["render_both", "write_mermaid_only"],
)
def test_graph_writes_the_mermaid_and_renders_only_when_asked(realm, command, svgs):
    path = realm / "demo.yaml"
    path.write_text(GOOD, encoding="utf-8")
    out = realm / "out"
    result = runner.invoke(app, ["graph", command, str(path), "--out", str(out)])
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
