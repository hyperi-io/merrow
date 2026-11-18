import json

import pytest

from merrow import config, render

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
    assert render.icon_packs(tmp_path) == [aws]
    assert render.icon_packs(tmp_path / "empty") == []


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
        'flowchart LR\n  a@{ icon: "demo:box", label: "A" }\n', encoding="utf-8"
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
        assert svg == (tmp_path / "again" / name).read_text(encoding="utf-8")


def test_render_names_the_diagram_mermaid_rejects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.mmd"
    bad.write_text("flowchart LR\n  a -->\n", encoding="utf-8")
    with pytest.raises(render.RenderError, match="bad"):
        render.render(list(render.diagrams(bad)), tmp_path / "out", config.load())
