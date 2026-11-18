import json

import pytest
from typer.testing import CliRunner

from merrow import config, objects, profile, write
from merrow.cli import app
from merrow.graph import Edge, Graph, Group, Node
from merrow.lint import diagram_check as dc

REALM = {"color": {"role": {"load": {"$type": "color", "$value": "#123456"}}}}


def realm(monkeypatch, tmp_path, merrow_yaml, tokens=None):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir()
    (repo / "merrow.yaml").write_text(merrow_yaml, encoding="utf-8")
    if tokens is not None:
        (repo / "realm.tokens.json").write_text(json.dumps(tokens), encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    return config.load()


def luminance(hex_colour):
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_every_full_weight_class_border_reads_at_3_to_1_on_paper(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    house = profile.load(config.load(), "house")
    paper = luminance("#FFFFFF")
    full = [ln for ln in house.class_lines if "stroke-width:3px" in ln]
    assert len(full) == 9, "six data-flow classes and three role classes"
    for line in full:
        stroke = line.split("stroke:")[1][:7]
        ratio = (paper + 0.05) / (luminance(stroke) + 0.05)
        assert ratio >= 3, f"{line}: {ratio:.2f} to 1"


def test_a_realm_token_file_restyles_every_alias_to_it(monkeypatch, tmp_path):
    settings = realm(
        monkeypatch,
        tmp_path,
        "profiles:\n  house:\n    tokens: [profiles/house.tokens.json, realm.tokens.json]\n",
        REALM,
    )
    house = profile.load(settings)
    assert "classDef load fill:#FFFFFF,stroke:#123456," in "\n".join(house.class_lines)
    assert "stroke:#123456" in house.boundary, "color.group aliases color.role.load"
    assert 'clusterBorder: "#123456"' in house.fronts["flowchart"]
    assert ".load .label-icon{color:#123456}" in house.fronts["flowchart"]
    assert "#0072B2" not in house.fronts["flowchart"]


BRAND = """profiles:
  brand:
    extends: house
    tokens: [profiles/house.tokens.json, realm.tokens.json]
    themes:
      dark:
        tokens: [profiles/house.tokens.json, realm.tokens.json, dark.tokens.json]
"""
NAVY = {"color": {"group": {"$type": "color", "$value": "#000647"}}}
BLUE = {"color": {"group": {"$type": "color", "$value": "#2EA4F6"}}}


def test_a_profile_extending_house_restyles_it_per_theme(monkeypatch, tmp_path):
    settings = realm(monkeypatch, tmp_path, BRAND, NAVY)
    (tmp_path / "realm" / "dark.tokens.json").write_text(
        json.dumps(BLUE), encoding="utf-8"
    )
    house = profile.load(settings, "house")
    light = profile.load(settings, "brand", "light")
    dark = profile.load(settings, "brand", "dark")
    assert "stroke:#0072B2" in house.boundary, "house is untouched"
    assert "stroke:#000647" in light.boundary
    assert "stroke:#2EA4F6" in dark.boundary
    assert light.class_lines == house.class_lines, "only the group colour moved"
    assert light.limits == house.limits, "the rest comes from house"


@pytest.mark.parametrize(
    ("theme", "icon"), [("light", "#334155"), ("dark", "#CBD5E1")], ids=str
)
def test_house_paints_monochrome_icons_for_each_theme(
    monkeypatch, tmp_path, theme, icon
):
    monkeypatch.chdir(tmp_path)
    house = profile.load(config.load(), "house", theme)
    assert f'nodeBorder: "{icon}"' in house.fronts["flowchart"]


@pytest.mark.parametrize(
    ("merrow_yaml", "said"),
    [
        (
            "profiles:\n  a: {extends: b}\n  b: {extends: a}\n",
            "profiles extend in a loop: a -> b -> a",
        ),
        ("profiles:\n  a: {extends: a}\n", "profiles extend in a loop: a -> a"),
        ("profiles:\n  a: {extends: nothing}\n", "no profile nothing"),
    ],
    ids=["loop", "self", "missing_parent"],
)
def test_a_broken_extends_is_named(monkeypatch, tmp_path, merrow_yaml, said):
    settings = realm(monkeypatch, tmp_path, merrow_yaml)
    with pytest.raises(profile.ProfileError, match=said):
        profile.load(settings, "a")


@pytest.mark.parametrize(
    ("merrow_yaml", "env", "family"),
    [
        ("{}\n", None, "Inter, -apple-system"),
        (
            "font: [Arial, Helvetica, sans-serif]\n",
            None,
            "Arial, Helvetica, sans-serif",
        ),
        ("{}\n", "Verdana, sans-serif", "Verdana, sans-serif"),
        ("font: Arial\n", "", "Inter, -apple-system"),
    ],
    ids=["profile_font", "forced_list", "forced_by_env", "empty_env_unforces"],
)
def test_a_forced_font_replaces_every_font_family(
    monkeypatch, tmp_path, merrow_yaml, env, family
):
    if env is not None:
        monkeypatch.setenv("MERROW_FONT", env)
    house = profile.load(realm(monkeypatch, tmp_path, merrow_yaml))
    for front in house.fronts.values():
        assert f"fontFamily: {family}" in front
    if family != "Inter, -apple-system":
        assert all("Inter" not in front for front in house.fronts.values())


@pytest.mark.parametrize(
    ("merrow_yaml", "tokens", "error", "said"),
    [
        (
            "profiles:\n  house:\n    class_defaults:\n      color: '{color.nope}'\n",
            None,
            profile.ProfileError,
            "no token color.nope",
        ),
        (
            "profiles:\n  house:\n    tokens: [profiles/house.tokens.json, realm.tokens.json]\n",
            {
                "color": {
                    "ink": {"$value": "{color.paper}"},
                    "paper": {"$value": "{color.ink}"},
                }
            },
            profile.ProfileError,
            "nest deeper",
        ),
        ("profile: nothing\n", None, profile.ProfileError, "no profile nothing"),
        (
            "profiles:\n  house:\n    tokens: [missing.tokens.json]\n",
            None,
            FileNotFoundError,
            "missing.tokens.json",
        ),
    ],
    ids=["unknown_token", "alias_loop", "unknown_profile", "missing_token_file"],
)
def test_a_broken_profile_is_named(
    monkeypatch, tmp_path, merrow_yaml, tokens, error, said
):
    settings = realm(monkeypatch, tmp_path, merrow_yaml, tokens)
    with pytest.raises(error, match=said):
        profile.load(settings)


def test_profile_show_prints_the_blocks_lint_holds_diagrams_to(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    house = profile.load(config.load(), "house")
    runner = CliRunner()
    shown = runner.invoke(app, ["profile", "show"])
    assert shown.exit_code == 0
    assert shown.output.startswith(house.fronts["flowchart"] + "\n")
    assert all(line in shown.output for line in house.class_lines)
    other = runner.invoke(app, ["profile", "show", "house", "--family", "other"])
    assert other.output == house.fronts["other"] + "\n"
    assert runner.invoke(app, ["profile", "show", "--family", "gantt"]).exit_code == 2


KUBE = """profiles:
  k8s:
    extends: house
    icon_node: '@{ icon: "{node.icon}", label: "{node.text}", pos: "b", h: {node.size} }'
    icon_packs: [k8s]
objects:
  k8s.api: {label: API server, icon: "k8s:api"}
  k8s.kubelet: {label: kubelet, icon: "k8s:kubelet"}
  k8s.k-proxy: {label: kube-proxy, icon: "k8s:k-proxy"}
"""


def test_a_reference_repo_draws_another_publishers_icons_in_the_house_look(
    monkeypatch, tmp_path
):
    packs = tmp_path / "packs"
    packs.mkdir()
    icon = {"body": "<rect/>", "height": 17}
    pack = {
        "prefix": "k8s",
        "icons": dict.fromkeys(["api", "kubelet", "k-proxy"], icon),
    }
    (packs / "k8s.json").write_text(json.dumps(pack), encoding="utf-8")
    monkeypatch.setenv("MERROW_PACKS_DIR", str(packs))
    settings = realm(monkeypatch, tmp_path, KUBE)
    graph = Graph(
        [
            Node("kubelet", object="k8s.kubelet", group="nodes"),
            Node("kproxy", object="k8s.k-proxy", group="nodes"),
            Node("api", object="k8s.api", group="cp"),
        ],
        [Edge("nodes", "api")],
        [Group("nodes", "Nodes x2"), Group("cp", "Control plane")],
    )
    shown = profile.load(settings, "k8s")
    source = write.diagram(
        graph,
        shown,
        objects.library(settings),
        "L2 Services -- Cluster",
        "Nodes call the API server.",
    )
    assert 'api@{ icon: "k8s:api", label: "API server", pos: "b", h: 17 }' in source
    assert "direction LR" in source and "kubelet ~~~ kproxy" in source
    block = dc.Block("cluster.mmd", source, None, None)
    assert dc.source_problems(block, frozenset(), shown) == []
