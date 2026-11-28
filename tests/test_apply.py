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


PASTED = """flowchart LR
    accTitle: L2 Services -- Pipeline
    accDescr: A source feeds a store.
    subgraph core["Core"]
        a("<b>Source</b>")
    end
    b("<b>Store</b>")
    a --> b
    class a ingest
    class b store
    {classes}
    style core {boundary}
"""


@pytest.mark.parametrize("stale", ["frontmatter", "class_line", "both"])
def test_a_pasted_house_block_is_refreshed_in_place(settings, stale):
    house = profile.load(settings, "house")
    front = house.fronts["flowchart"]
    classes = list(house.class_lines)
    if stale in ("frontmatter", "both"):
        front = front.replace('    nodeBorder: "#334155"\n', "")
    if stale in ("class_line", "both"):
        classes[0] = classes[0].replace("stroke-width:3px", "stroke-width:1px")
    body = PASTED.format(classes="\n    ".join(classes), boundary=house.boundary)
    source = f"{front}\n{body}"
    assert front != house.fronts["flowchart"] or classes != list(house.class_lines)
    assert apply.managed(source, {}), "a diagram with frontmatter takes the profile"
    out, _, by_ref = applied(settings, source)
    good = PASTED.format(
        classes="\n    ".join(house.class_lines), boundary=house.boundary
    )
    assert out == f"{house.fronts['flowchart']}\n{good}", "same lines, same order"
    assert apply.BEGIN not in out
    assert applied(settings, out)[0] == out
    block = dc.Block("pasted.mmd", out, None, None)
    assert dc.source_problems(block, frozenset(), house, frozenset(by_ref)) == []
    before = dc.Block("pasted.mmd", source, None, None)
    found = dc.source_problems(before, frozenset(), house, frozenset(by_ref))
    assert found, "lint names the stale block"
    if stale != "class_line":
        assert found == [
            "[frontmatter] R9 frontmatter that is not the house block, byte for byte: "
            "`merrow diagram apply` sets it"
        ]


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


@pytest.mark.parametrize("name", ["page.md", "page.mdx", "page.markdown", "PAGE.MD"])
def test_a_markdown_page_changes_only_its_managed_fences(settings, tmp_path, name):
    other = "flowchart LR\n    a --> b\n"
    sequence = "sequenceDiagram\n    a->>b: hi\n"
    page = tmp_path / name
    page.write_text(
        f"# Page\n\n```mermaid\n{HAND}```\n\nText.\n\n```mermaid\n{other}```\n"
        f"\n```mermaid\n{sequence}```\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["diagram", "apply", str(page)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("changed")
    text = page.read_text(encoding="utf-8")
    assert text.startswith("# Page\n"), "the page itself takes no frontmatter"
    assert text.count(apply.BEGIN) == 1
    assert f"```mermaid\n{other}```" in text, "a fence with no object is left alone"
    assert text.count("actorBkg") == 1, "a sequence takes the frontmatter alone"
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


@pytest.mark.parametrize(
    ("bad", "said"),
    [
        (HAND + "    %% merrow:begin\n    c --> d\n", "has no `%% merrow:end`"),
        (HAND + "    %% merrow:end\n", "with no `%% merrow:begin` above it"),
        (
            HAND + "    %% merrow:begin\n    %% merrow:begin\n    %% merrow:end\n",
            "a second `%% merrow:begin`",
        ),
        (None, "No such file"),
    ],
    ids=["no_end", "no_begin", "two_begins", "missing_file"],
)
def test_a_bad_file_exits_2_and_no_file_is_written(settings, tmp_path, bad, said):
    good, other = tmp_path / "good.mmd", tmp_path / "bad.mmd"
    good.write_text(HAND, encoding="utf-8")
    if bad is not None:
        other.write_text(bad, encoding="utf-8")
    result = CliRunner().invoke(app, ["diagram", "apply", str(good), str(other)])
    if bad is None:
        assert isinstance(result.exception, FileNotFoundError), "run() exits 2 on it"
    else:
        assert result.exit_code == 2
        assert said in " ".join(result.output.split())
        assert other.read_text(encoding="utf-8") == bad
    assert good.read_text(encoding="utf-8") == HAND, "the good file waits for the bad"


def test_two_objects_with_one_class_name_are_refused():
    library = {
        "a.b-c": objects.L1Object("a.b-c", "load", "One"),
        "a-b.c": objects.L1Object("a-b.c", "load", "Two"),
    }
    with pytest.raises(ValueError, match="both read as :::a-b-c"):
        objects.by_class_name(library)
