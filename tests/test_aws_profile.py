import json
import re
from dataclasses import replace

import pytest
import yaml

from merrow import config, objects, post, profile, render, write
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


def test_an_icon_in_no_built_pack_is_refused(settings):
    graph = Graph([Node("q", object="aws.sqs")])
    shown = profile.load(settings, "aws")
    with pytest.raises(
        ValueError, match="aws:amazon-simple-queue-service is in no built pack"
    ):
        write.diagram(graph, shown, objects.library(settings), "L2 Services -- X", "X.")


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
