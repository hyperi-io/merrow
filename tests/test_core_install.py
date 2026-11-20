"""A core install, with no extra, writes, applies and source-lints diagrams."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Runs merrow's CLI with every module an extra brings refused, as on a core install.
_CORE = """
import sys
from importlib.abc import MetaPathFinder

EXTRAS = ("playwright", "nvchecker", "pypdfium2", "pydot", "httpx", "scalo.http")


class Refuse(MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name in EXTRAS or name.startswith(tuple(f"{e}." for e in EXTRAS)):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)


sys.meta_path.insert(0, Refuse())
sys.argv = ["merrow", *sys.argv[1:]]
from merrow.cli import run

run()
"""
FILE = """title: L2 Services -- Demo
description: A source feeds a store.
nodes:
  - {id: a, label: Source}
  - {id: b, label: Store}
edges:
  - {source: a, target: b}
"""


def core(tmp_path, *args):
    return subprocess.run(  # noqa: S603 -- this interpreter and a fixed script
        [sys.executable, "-c", _CORE, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        check=False,
    )


@pytest.fixture
def demo(tmp_path):
    (tmp_path / "demo.yaml").write_text(FILE, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "args",
    [
        ["config", "get"],
        ["profile", "show", "house"],
        ["graph", "validate", "demo.yaml"],
        ["graph", "write", "demo.yaml", "--out", "out"],
        ["graph", "schema"],
        ["diagram", "apply", "page.md"],
        ["diagram", "lint", "--no-render", "page.md"],
        ["skill", "install", "--to", "skills"],
    ],
    ids=lambda args: "_".join(args[:2]),
)
def test_a_core_command_needs_no_extra(demo, args):
    page = demo / "page.md"
    page.write_text(
        "# Demo\n\nA source feeds a store.\n\n```mermaid\nflowchart LR\n"
        "  accTitle: L2 Services -- Demo\n  accDescr: A source feeds a store.\n"
        '  a("<b>Source</b>") --> b("<b>Store</b>")\n  %% merrow:begin\n'
        "  %% merrow:end\n```\n\n*Figure 1. L2 Services -- Demo.* Up: top of demo.\n",
        encoding="utf-8",
    )
    if args[:2] == ["diagram", "lint"]:
        assert core(demo, "diagram", "apply", "page.md").returncode == 0
    result = core(demo, *args)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("args", "extra"),
    [
        (["graph", "render", "demo.yaml", "--out", "out"], "render"),
        (["diagram", "lint", "out.mmd"], "render"),
        (["tools", "ensure"], "render"),
        (["pack", "build", "starter-icons"], "packs"),
        (["source", "update", "--lock", "x.yaml"], "packs"),
    ],
    ids=["graph_render", "diagram_lint", "tools_ensure", "pack_build", "source_update"],
)
def test_a_command_that_needs_an_extra_names_it(demo, args, extra):
    (demo / "out.mmd").write_text("flowchart LR\n  a --> b\n", encoding="utf-8")
    result = core(demo, *args)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"merrow[{extra}]" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr


def test_the_extras_hold_what_the_core_refuses():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core_deps = " ".join(project["project"]["dependencies"])
    extras = project["project"]["optional-dependencies"]
    for name in ("playwright", "nvchecker", "pypdfium2", "pydot", "scalo[http]"):
        assert name not in core_deps
    assert "playwright>=" in " ".join(extras["render"])
    assert extras["all"] == ["merrow[render,packs]"]
    json.dumps(extras)
