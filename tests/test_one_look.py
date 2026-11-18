"""Diagrams from six formats come out in one look: merrow's main promise."""

import json
import xml.etree.ElementTree as ET

import pytest
import test_read_dot
import test_read_drawio
import test_read_excalidraw
import test_read_pptx
import test_read_structurizr
import test_read_visio

from merrow import config, objects, profile, write
from merrow.lint import diagram_check as dc
from merrow.read import dot, drawio, excalidraw, pptx, structurizr, visio

READ = {
    "drawio": lambda: drawio.pages(
        test_read_drawio.MODEL.encode(), test_read_drawio.RULES
    )[0],
    "pptx": lambda: pptx.read_slide(
        1, ET.fromstring(test_read_pptx.SLIDE), test_read_pptx.RULES
    ),
    "visio": lambda: visio.pages(
        test_read_visio.drawing_bytes(), test_read_visio.RULES
    )[0],
    "excalidraw": lambda: excalidraw.read(
        json.dumps(test_read_excalidraw.SCENE).encode(), test_read_excalidraw.RULES
    ),
    "dot": lambda: dot.read(test_read_dot.SOURCE, test_read_dot.RULES)[0],
    "structurizr": lambda: structurizr.read(
        json.dumps(test_read_structurizr.WORKSPACE).encode(),
        test_read_structurizr.RULES,
    ),
}


@pytest.mark.parametrize("source", sorted(READ))
def test_every_format_draws_in_the_same_look(monkeypatch, tmp_path, source):
    monkeypatch.chdir(tmp_path)
    settings = config.load()
    house = profile.load(settings, "house")
    drawing = READ[source]()
    mermaid = write.diagram(
        drawing.graph,
        house,
        objects.library(settings),
        "L4 Detail -- Imported",
        f"A diagram read from {source}.",
    )
    assert mermaid.startswith(house.fronts["flowchart"] + "\n"), "the same frontmatter"
    assert all(f"  {line}\n" in mermaid for line in house.class_lines), (
        "the same classes"
    )
    block = dc.Block(f"{source}.mmd", mermaid, None, None)
    assert dc.source_problems(block, frozenset(), house) == []
