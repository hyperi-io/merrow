import contextlib
import json
import re
import sys
from http.server import SimpleHTTPRequestHandler

import pytest
from typer.testing import CliRunner

from merrow import config, destination, render
from merrow.cli import app, run

ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'


def test_markdown_yields_each_mermaid_fence_and_mmd_yields_the_file(tmp_path):
    page = tmp_path / "arch.md"
    page.write_text(
        "# A\n```mermaid\nflowchart LR\n  a --> b\n```\n"
        "```text\nnot a diagram\n```\n```mermaid\nsequenceDiagram\n  a->>b: hi\n```\n",
        encoding="utf-8",
    )
    lone = tmp_path / "one.mmd"
    lone.write_text("flowchart LR\n  x --> y\n", encoding="utf-8")
    names = [d.name for d in render.diagrams(page)] + [
        d.name for d in render.diagrams(lone)
    ]
    assert names == ["arch-1", "arch-2", "one"]
    assert next(render.diagrams(page)).source.startswith("flowchart LR")


def test_only_iconify_packs_are_registered(tmp_path):
    aws = {"prefix": "aws", "icons": {}}
    (tmp_path / "aws.json").write_text(json.dumps(aws), encoding="utf-8")
    (tmp_path / "aws-groups.json").write_text(
        json.dumps({"light": []}), encoding="utf-8"
    )
    assert render.icon_packs(sorted(tmp_path.glob("*.json"))) == [aws]
    assert render.icon_packs([]) == []


def test_render_writes_one_svg_per_theme_with_local_icons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    packs = tmp_path / "packs"
    packs.mkdir()
    pack = {
        "prefix": "demo",
        "icons": {
            "box": {
                "body": '<defs><linearGradient id="g"/></defs>'
                '<rect width="8" height="8" fill="url(#g)"/>',
                "width": 8,
                "height": 8,
            }
        },
    }
    (packs / "demo.json").write_text(json.dumps(pack), encoding="utf-8")
    monkeypatch.setenv("MERROW_PACKS_DIR", str(packs))
    source = tmp_path / "d.mmd"
    source.write_text(
        'flowchart LR\n  a@{ icon: "demo:box", label: "A" }\n  a --> b(["B"])\n'
        "  b --> c\n  a --> c\n",
        encoding="utf-8",
    )
    settings = config.load()

    written = render.render(list(render.diagrams(source)), tmp_path / "out", settings)

    themes = settings.get("render")["themes"]
    assert [w["theme"] for w in written] == list(themes)
    render.render(list(render.diagrams(source)), tmp_path / "again", settings)
    for entry in written:
        name = f"d-{entry['theme']}.svg"
        svg = (tmp_path / "out" / name).read_text(encoding="utf-8")
        assert "<svg" in svg
        assert "IconifyId" not in svg, "icon ids are renamed in order"
        assert not re.search(r' d="[^"]*\d\.\d{3}', svg), "path data to 2 decimals"
        again = (tmp_path / "again" / name).read_text(encoding="utf-8")
        assert svg == again, "a render repeats byte for byte, a stadium included"


def test_render_names_the_diagram_mermaid_rejects(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.mmd"
    bad.write_text("flowchart LR\n  a -->\n", encoding="utf-8")
    with pytest.raises(render.RenderError, match="bad"):
        render.render(list(render.diagrams(bad)), tmp_path / "out", config.load())
    monkeypatch.setattr(
        sys, "argv", ["merrow", "diagram", "render", "bad.mmd", "--out", "o"]
    )
    with pytest.raises(SystemExit) as stopped:
        run()
    assert stopped.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("merrow: bad")
    assert "Traceback" not in err


def test_a_diagram_reaches_no_network(tmp_path, monkeypatch, site):
    root, base = site
    (root / "beacon.png").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    page = tmp_path / "beacon.mmd"
    page.write_text(
        f'flowchart LR\n  a["<img src={base}/beacon.png>"] --> b@{{ img: "{base}/beacon.png" }}\n',
        encoding="utf-8",
    )
    requests: list[str] = []
    original = SimpleHTTPRequestHandler.log_message
    monkeypatch.setattr(
        SimpleHTTPRequestHandler,
        "log_message",
        lambda self, *args: requests.append(self.path) or original(self, *args),
    )
    # An image shape can't load its blocked image, so its render fails by name.
    with contextlib.suppress(render.RenderError):
        render.render(list(render.diagrams(page)), tmp_path / "out", config.load())
    assert requests == []


GITHUB = """destinations:
  github:
    extends: page
    themes:
      dark: {background: "#0D1117"}
"""


@pytest.mark.parametrize("where", ["page", "github", "slide"])
def test_diagram_render_draws_each_theme_in_its_own_look(tmp_path, monkeypatch, where):
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "realm"
    repo.mkdir()
    (repo / "merrow.yaml").write_text(GITHUB, encoding="utf-8")
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    page = tmp_path / "page.md"
    page.write_text(
        "# Login\n\n```mermaid\nsequenceDiagram\n"
        "    accTitle: L4 Detail -- Login\n    accDescr: A sign-in.\n"
        "    a->>b: hi\n```\n",
        encoding="utf-8",
    )
    command = ["diagram", "render", str(page), "--out", "out", "--destination", where]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    pages = destination.load(config.load(), where).themes
    wanted = {
        "page": {"light": "#FFFFFF", "dark": "#1B1B1D"},
        "github": {"light": "#FFFFFF", "dark": "#0D1117"},
        "slide": {"light": "#FFFFFF"},
    }[where]
    assert {theme: look["background"] for theme, look in pages.items()} == wanted
    written = sorted(path.name for path in (tmp_path / "out").iterdir())
    assert written == sorted(f"page-1-{theme}.svg" for theme in wanted)
    for theme, look in pages.items():
        svg = (tmp_path / "out" / f"page-1-{theme}.svg").read_text(encoding="utf-8")
        hexed = look["background"].lstrip("#")
        rgb = ", ".join(str(int(hexed[i : i + 2], 16)) for i in (0, 2, 4))
        assert f"stroke:rgb({rgb})" in svg, f"{theme} halo is its page"
