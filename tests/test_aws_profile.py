import json
import re
from dataclasses import replace

import pytest
import yaml
from typer.testing import CliRunner

from merrow import config, objects, post, profile, render, write
from merrow.cli import app
from merrow.graph import Edge, Graph, Group, Node
from merrow.lint import diagram_check as dc

ICON = {"body": '<rect width="10" height="10" fill="#123456"/>'}
AWS = {
    "prefix": "aws",
    "width": 10,
    "height": 10,
    "icons": {
        "group-region": ICON,
        "group-virtual-private-cloud-vpc": ICON,
        "res-users": ICON,
        "res-users-dark": {"body": '<rect width="10" height="10" fill="#FEDCBA"/>'},
        "amazon-simple-storage-service": ICON,
        "amazon-elastic-kubernetes-service-32": {
            "body": '<rect width="10" height="10" fill="#ED7100"/>'
        },
    },
}
GROUPS = {
    theme: [
        {
            "key": "region",
            "stroke": "#00A4A6",
            "dash": "sysDash",
            "label_colour": ink,
        },
        {
            "key": "virtual-private-cloud-vpc",
            "stroke": "#8C4FFF",
            "dash": "solid",
            "label_colour": "#000000",
        },
    ]
    for theme, ink in (("light", "#000000"), ("dark", "#FFFFFF"))
}
GRAPH = Graph(
    [
        Node("users", object="aws.users"),
        Node("store", object="aws.s3", group="region"),
        Node("app", "Our app", group="vpc"),
    ],
    [Edge("users", "app"), Edge("app", "store")],
    [Group("region", "", object="aws.region"), Group("vpc", "", "region", "aws.vpc")],
)


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "aws.json").write_text(json.dumps(AWS), encoding="utf-8")
    (packs / "aws-groups.json").write_text(json.dumps(GROUPS), encoding="utf-8")
    monkeypatch.setenv("MERROW_PACKS_DIR", str(packs))
    return config.load()


def drawn(settings, name):
    shown = profile.load(settings, name)
    source = write.diagram(
        GRAPH,
        shown,
        objects.library(settings),
        "L2 Services -- Demo",
        "Users reach our app.",
    )
    block = dc.Block("demo.mmd", source, None, None)
    return source, dc.source_problems(block, frozenset(), shown)


FILE = """\
title: L2 Services -- Demo
description: Users reach our store.
profile: aws
groups:
  - {id: region, label: "", object: aws.region}
nodes:
  - {id: users, object: aws.users}
  - {id: store, object: aws.s3, group: region}
edges:
  - {source: users, target: store}
"""


def test_config_get_lists_generated_objects_beside_configured_ones(settings):
    result = CliRunner().invoke(app, ["config", "get"])
    assert result.exit_code == 0, result.output
    found = json.loads(result.output)["objects"]
    assert found["icon.server"]["icon"] == "starter:server", "a shipped pack's icon"
    assert found["aws.lambda"]["label"] == "AWS Lambda", "a configured object"


@pytest.mark.parametrize(("key", "first"), [("", "LR"), ("direction: TB\n", "TB")])
def test_a_files_direction_sets_the_flowchart(settings, tmp_path, key, first):
    (tmp_path / "demo.yaml").write_text(key + FILE, encoding="utf-8")
    written = CliRunner().invoke(app, ["graph", "write", "demo.yaml", "--out", "out"])
    assert written.exit_code == 0, written.output
    source = (tmp_path / "out" / "demo.mmd").read_text(encoding="utf-8")
    assert f"\nflowchart {first}\n" in source
    assert (
        dc.source_problems(
            dc.Block("demo.mmd", source, None, None),
            frozenset(),
            profile.load(settings, "aws"),
        )
        == []
    )


@pytest.mark.parametrize(
    ("flag", "aws_drawn"), [([], True), (["--profile", "house"], False)]
)
def test_a_files_profile_draws_it_unless_a_flag_says_otherwise(
    settings, tmp_path, flag, aws_drawn
):
    (tmp_path / "demo.yaml").write_text(FILE, encoding="utf-8")
    runner = CliRunner()
    validated = runner.invoke(app, ["graph", "validate", "demo.yaml", *flag])
    assert validated.exit_code == 0, validated.output
    written = runner.invoke(app, ["graph", "write", "demo.yaml", "--out", "out", *flag])
    assert written.exit_code == 0, written.output
    source = (tmp_path / "out" / "demo.mmd").read_text(encoding="utf-8")
    assert ("style region fill:none,stroke:#00A4A6" in source) is aws_drawn


@pytest.mark.parametrize("name", ["house", "aws"])
def test_lint_takes_the_profile_from_the_diagrams_frontmatter(settings, tmp_path, name):
    path = tmp_path / "demo.mmd"
    path.write_text(drawn(settings, name)[0], encoding="utf-8")
    assert dc.main([str(path), "--no-render"]) == 0
    assert dc.main([str(path), "--no-render", "--profile", "house"]) == (name == "aws")


def test_aws_group_borders_come_from_the_pack(settings):
    aws = profile.load(settings, "aws")
    assert aws.group_boundaries["region"] == (
        "fill:none,stroke:#00A4A6,stroke-width:1.5px,stroke-dasharray:3 3,color:#000000"
    )
    assert "stroke-dasharray" not in aws.group_boundaries["virtual-private-cloud-vpc"]


@pytest.mark.parametrize("name", ["house", "aws"])
def test_one_graph_draws_clean_under_either_profile(settings, name):
    source, problems = drawn(settings, name)
    assert problems == []
    icons = 'users@{ icon: "aws:res-users", label: "Users", pos: "b", h: 10 }' in source
    assert icons, "both draw an object's icon"
    assert ("style region fill:none,stroke:#00A4A6" in source) is (name == "aws")
    assert (f"{write.GROUP_ICON} region aws:group-region" in source) is (name == "aws")
    assert re.search(r"^  class \S*\bapp\b\S* part$", source, re.M), (
        "no box is classless"
    )


def test_a_missing_group_pack_is_named(settings, tmp_path):
    (tmp_path / "packs" / "aws-groups.json").unlink()
    with pytest.raises(FileNotFoundError, match="merrow pack build aws-groups"):
        profile.load(settings, "aws")


def test_an_unknown_group_style_is_refused(settings, monkeypatch):
    graph = Graph([Node("a", "A", group="z")], [], [Group("z", "Z", object="aws.az")])
    shown = profile.load(settings, "aws")
    with pytest.raises(ValueError, match="group style 'availability-zone'"):
        write.diagram(graph, shown, objects.library(settings), "L2 Services -- X", "X.")


def test_a_dark_render_swaps_icons_that_have_a_dark_variant(settings):
    packs = config.pack_files(settings)
    source = (
        'a@{ icon: "aws:res-users" }\nb@{ icon: "aws:amazon-simple-storage-service" }'
    )
    swapped = post.themed(source, "-dark", packs)
    assert '"aws:res-users-dark"' in swapped
    assert '"aws:amazon-simple-storage-service"' in swapped
    assert post.themed(source, "", packs) == source


def test_render_puts_each_group_icon_in_its_corner(settings, tmp_path):
    source, _ = drawn(settings, "aws")
    written = render.render(
        [render.Diagram("demo", source)], tmp_path / "out", settings
    )
    light = (tmp_path / "out" / "demo-light.svg").read_text(encoding="utf-8")
    dark = (tmp_path / "out" / "demo-dark.svg").read_text(encoding="utf-8")
    assert len(written) == 2
    assert light.count('<svg x="') == 2, "one icon a group"
    assert 'fill="#123456"' in light
    assert dark.startswith("<svg")


@pytest.mark.parametrize(
    ("icon", "says"),
    [
        ("aws:amazon-simple-queue-service", "is not in the built aws pack"),
        (
            "asf-kafka:kafka",
            "the aws profile doesn't draw from. It draws from: aws.",
        ),
    ],
    ids=["missing-from-its-pack", "pack-the-profile-skips"],
)
def test_an_icon_the_profile_cant_draw_is_refused(settings, icon, says):
    library = objects.library(settings) | {
        "x.q": objects.L1Object("x.q", "", "Q", icon=icon)
    }
    shown = profile.load(settings, "aws")
    with pytest.raises(ValueError, match=re.escape(says)):
        write.diagram(
            Graph([Node("q", object="x.q")]), shown, library, "L2 Services -- X", "X."
        )


def test_a_service_group_takes_its_icon_colour(settings):
    graph = Graph(
        [Node("app", "App", group="eks")],
        [],
        [Group("eks", "", object="aws.eks-cluster")],
    )
    shown = profile.load(settings, "aws")
    source = write.diagram(
        graph, shown, objects.library(settings), "L2 Services -- X", "X."
    )
    assert (
        "  style eks fill:none,stroke:#ED7100,stroke-width:1.5px,color:#000000\n"
        in source
    )
    assert f"{write.GROUP_ICON} eks aws:amazon-elastic-kubernetes-service-32" in source
    block = dc.Block("x.mmd", source, None, None)
    assert dc.source_problems(block, frozenset(), shown) == []


def test_a_dark_theme_takes_the_dark_slide_and_ink(settings):
    dark = profile.load(settings, "aws", "dark")
    assert dark.group_boundaries["region"].endswith("color:#FFFFFF")
    assert 'primaryTextColor: "#FFFFFF"' in dark.fronts["flowchart"]
    light = profile.load(settings, "aws", "light")
    assert light.group_boundaries["region"].endswith("color:#000000")
    plain = "classDef part fill:{},stroke:#94A3B8,stroke-width:1.5px,color:{}"
    assert plain.format("#232F3E", "#FFFFFF") in dark.class_lines, (
        "a box on the dark slide"
    )
    assert plain.format("#FFFFFF", "#0F172A") in light.class_lines
    assert dark.boundary.endswith("color:#FFFFFF"), (
        "a plain group's title on the dark slide"
    )
    assert light.boundary.endswith("color:#000000")
    house, house_dark = (
        profile.load(settings, "house"),
        profile.load(settings, "house", "dark"),
    )
    assert replace(house_dark, fronts=house.fronts) == house, (
        "house dark moves icons only"
    )


def test_no_profile_puts_angle_brackets_in_its_css(settings):
    for name in settings.get("profiles"):
        for theme in [None, *settings.get("render")["themes"]]:
            for front in profile.load(settings, name, theme).fronts.values():
                css = yaml.safe_load(front.strip("-\n"))["config"].get("themeCSS", "")
                assert "<" not in css and ">" not in css, (
                    f"{name} {theme}: Mermaid drops config text holding < or >"
                )
