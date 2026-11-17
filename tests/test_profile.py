import json

import pytest
from typer.testing import CliRunner

from merrow import config, profile
from merrow.cli import app

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
    assert len(full) == 9, "six identity classes and three role classes"
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
