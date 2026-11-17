import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from merrow.cli import app, run


def write_repo(root, name, body):
    repo = root / name
    repo.mkdir()
    (repo / "merrow.yaml").write_text(body, encoding="utf-8")
    return repo


def config_get(monkeypatch, repos):
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(r) for r in repos]))
    result = CliRunner().invoke(app, ["config", "get"])
    return result


def test_version_and_default_config_boot(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert "0.1.0" in runner.invoke(app, ["--version"]).output
    result = runner.invoke(app, ["config", "get"])
    assert result.exit_code == 0
    assert json.loads(result.output)["references"] == []


@pytest.mark.parametrize(
    ("order", "colour"),
    [
        (("acme-diagrams", "jo-personal"), "#222222"),
        (("jo-personal", "acme-diagrams"), "#111111"),
    ],
)
def test_later_reference_layer_wins_whatever_the_repo_names(
    monkeypatch, tmp_path, order, colour
):
    monkeypatch.chdir(tmp_path)
    bodies = {
        "acme-diagrams": "colour: '#111111'\norg_only: kept\n",
        "jo-personal": "colour: '#222222'\n",
    }
    repos = [write_repo(tmp_path, name, bodies[name]) for name in order]
    result = config_get(monkeypatch, repos)
    assert result.exit_code == 0
    settings = json.loads(result.output)
    assert settings["colour"] == colour
    assert settings["org_only"] == "kept"
    assert settings["reference_file"] == "merrow.yaml"


def test_listed_repo_without_data_file_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "no-data"
    empty.mkdir()
    result = config_get(monkeypatch, [empty])
    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)


def test_the_installed_command_prints_a_missing_repo_as_one_line(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(tmp_path / "gone")]))
    monkeypatch.setattr(sys, "argv", ["merrow", "profile", "show"])
    with pytest.raises(SystemExit) as stopped:
        run()
    assert stopped.value.code == 2
    assert (
        capsys.readouterr().err
        == f"merrow: reference repo {tmp_path / 'gone'} has no merrow.yaml\n"
    )


@pytest.mark.parametrize(
    ("mode", "under_home"), [("local", True), ("auto", False)], ids=["local", "auto"]
)
def test_a_cli_keeps_user_dirs_inside_a_container(
    monkeypatch, tmp_path, mode, under_home
):
    from merrow import config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("container", "docker")
    monkeypatch.setenv("MERROW_RUNTIME_MODE", mode)
    cache = config.cache_dir(config.load())
    assert cache.is_relative_to(Path.home()) is under_home
