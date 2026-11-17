import json

import pytest
from typer.testing import CliRunner

from merrow import apply, config, objects, profile
from merrow.cli import app
from merrow.lint import diagram_check as dc

LIBRARY = """objects:
  demo.receiver: {class: ingest, label: demo-receiver, subtitle: every protocol}
  demo.loader: {class: load, label: demo-loader, subtitle: schema-free insert}
  demo.kafka: {class: bus, label: Kafka}
"""
HAND = """flowchart LR
    accTitle: L2 Services -- Pipeline
    accDescr: The receiver publishes to Kafka and the loader reads it.
    subgraph core["Core"]
        receiver:::demo-receiver
        topic:::demo-kafka
    end
    loader("<b>Loader</b><br/><span>our own words</span>"):::demo-loader
    receiver -->|events| topic
    topic --> loader
"""


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir()
    (repo / "merrow.yaml").write_text(LIBRARY, encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    return config.load()


def applied(settings, source):
    house = profile.load(settings, "house")
    by_ref = objects.by_class_name(objects.library(settings))
    return apply.apply(source, house, by_ref), house, by_ref


def test_apply_sets_both_regions_and_lints_clean(settings):
    out, house, by_ref = applied(settings, HAND)
    assert out.startswith(house.fronts["flowchart"] + "\nflowchart LR\n")
    assert (
        'receiver("<b>demo-receiver</b><br/><span>every protocol</span>"):::demo-receiver'
        in out
    )
    assert '<span>our own words</span>"):::demo-loader' in out, "an own label stays"
    assert "    class receiver ingest\n" in out
    assert "    class topic bus\n" in out
    assert "    class loader load\n" in out
    assert f"    style core {house.boundary}\n" in out
    block = dc.Block("hand.mmd", out, None, None)
    assert dc.source_problems(block, frozenset(), house, frozenset(by_ref)) == []


def test_apply_twice_changes_nothing(settings):
    once, _, _ = applied(settings, HAND)
    twice, _, _ = applied(settings, once)
    assert twice == once


def test_an_object_edit_restyles_on_the_next_apply(settings, tmp_path):
    once, _, _ = applied(settings, HAND)
    (tmp_path / "realm" / "merrow.yaml").write_text(
        LIBRARY.replace("{class: load,", "{class: xform,"), encoding="utf-8"
    )
    restyled = config.load()
    assert objects.library(restyled)["demo.loader"].style == "xform"
    again, _, _ = applied(restyled, once)
    assert "    class loader xform\n" in again
    assert "class loader load" not in again


def test_a_markdown_page_changes_only_its_managed_fences(settings, tmp_path):
    other = "flowchart LR\n    a --> b\n"
    page = tmp_path / "page.md"
    page.write_text(
        f"# Page\n\n```mermaid\n{HAND}```\n\nText.\n\n```mermaid\n{other}```\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["diagram", "apply", str(page)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("changed")
    text = page.read_text(encoding="utf-8")
    assert text.count(apply.BEGIN) == 1
    assert f"```mermaid\n{other}```" in text, "a fence with no object is left alone"
    again = CliRunner().invoke(app, ["diagram", "apply", str(page)])
    assert again.output.startswith("unchanged")


def test_an_object_styled_outside_the_profile_is_refused(settings, tmp_path):
    (tmp_path / "realm" / "merrow.yaml").write_text(
        "objects:\n  x.neon: {class: neon, label: Neon}\n", encoding="utf-8"
    )
    diagram = tmp_path / "x.mmd"
    diagram.write_text("flowchart LR\n    a:::x-neon\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["diagram", "apply", str(diagram)])
    assert result.exit_code == 2
    assert "styles as 'neon'" in result.output


def test_two_objects_with_one_class_name_are_refused():
    library = {
        "a.b-c": objects.L1Object("a.b-c", "load", "One"),
        "a-b.c": objects.L1Object("a-b.c", "load", "Two"),
    }
    with pytest.raises(ValueError, match="both read as :::a-b-c"):
        objects.by_class_name(library)
