"""PowerPoint slides to Graphs, one per slide.

A box with text is a node. A connector glued at both ends (`a:stCxn` and
`a:endCxn`) is an edge, exact whatever the layout. A box whose bounds hold other
boxes is a group, the way a frame on a slide holds its parts. Group shapes nest
their children in their own coordinates, so every box is mapped to slide units.
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field

from merrow.convert import opc
from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import skipper

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}

# A group's child coordinates: (child offset x, y, slide offset x, y, scale x, y).
type Frame = tuple[float, float, float, float, float, float]
_IDENTITY: Frame = (0.0, 0.0, 0.0, 0.0, 1.0, 1.0)


@dataclass(slots=True)
class Slide:
    """One slide read from a deck.

    Attributes:
        number: The slide's position in the deck, from 1.
        graph: What it holds.
        dropped: Shapes and connectors left out and why, for review.
    """

    number: int
    graph: Graph
    dropped: list[str] = field(default_factory=list)


def _text(shape: ET.Element) -> list[str]:
    lines = []
    for paragraph in shape.iter(f"{{{A}}}p"):
        line = "".join(t.text or "" for t in paragraph.iter(f"{{{A}}}t")).strip()
        if line:
            lines.append(re.sub(r"\s+", " ", line))
    return lines


def _box(xfrm: ET.Element | None, frame: Frame) -> Box | None:
    if xfrm is None:
        return None
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    cx, cy, ox, oy, sx, sy = frame
    x = ox + (float(off.get("x", 0)) - cx) * sx
    y = oy + (float(off.get("y", 0)) - cy) * sy
    return (x, y, x + float(ext.get("cx", 0)) * sx, y + float(ext.get("cy", 0)) * sy)


def _child_frame(group: ET.Element, frame: Frame) -> Frame:
    xfrm = group.find("p:grpSpPr/a:xfrm", NS)
    box = _box(xfrm, frame)
    if xfrm is None or box is None:
        return frame
    ch_off, ch_ext = xfrm.find("a:chOff", NS), xfrm.find("a:chExt", NS)
    if ch_off is None or ch_ext is None:
        return frame
    width, height = float(ch_ext.get("cx", 0)) or 1.0, float(ch_ext.get("cy", 0)) or 1.0
    return (
        float(ch_off.get("x", 0)),
        float(ch_off.get("y", 0)),
        box[0],
        box[1],
        (box[2] - box[0]) / width,
        (box[3] - box[1]) / height,
    )


def _walk(tree: ET.Element, frame: Frame, shapes: list, connectors: list) -> None:
    """Collect every shape and connector under `tree`, boxes in slide units."""
    for child in tree:
        tag = child.tag.split("}")[-1]
        if tag == "grpSp":
            _walk(child, _child_frame(child, frame), shapes, connectors)
        elif tag == "sp":
            info = child.find("p:nvSpPr/p:cNvPr", NS)
            box = _box(child.find("p:spPr/a:xfrm", NS), frame)
            if info is not None and box is not None:
                shapes.append((info.get("id", ""), child, box))
        elif tag == "cxnSp":
            connectors.append(child)


def read_slide(number: int, slide: ET.Element, rules: Mapping[str, object]) -> Slide:
    """Return one slide's Graph. `rules` holds the `readers.pptx` config."""
    result = Slide(number, Graph())
    tree = slide.find("p:cSld/p:spTree", NS)
    if tree is None:
        return result
    shapes: list[tuple[str, ET.Element, Box]] = []
    connectors: list[ET.Element] = []
    _walk(tree, _IDENTITY, shapes, connectors)
    optional_dash = {
        d.strip() for d in str(rules.get("optional_dash", "")).split(",") if d.strip()
    }
    placeholder = skipper(rules.get("skip_labels"))

    labelled = {}
    for shape_id, shape, box in shapes:
        is_placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS) is not None
        lines = [
            ln for ln in _text(shape) if not (placeholder and placeholder.fullmatch(ln))
        ]
        if is_placeholder or not lines:
            result.dropped.append(
                f"{shape_id}: {'slide placeholder' if is_placeholder else 'no text'}"
            )
            continue
        labelled[shape_id] = (lines, box)

    boxes = {shape_id: box for shape_id, (_, box) in labelled.items()}
    enclosing = nest_by_bounds(boxes, set(boxes))
    groups = set(enclosing.values())
    for shape_id, (lines, _) in labelled.items():
        if shape_id in groups:
            result.graph.groups.append(
                Group(shape_id, lines[0], enclosing.get(shape_id))
            )
        else:
            subtitle = " ".join(lines[1:]) or None
            result.graph.nodes.append(
                Node(shape_id, lines[0], subtitle, group=enclosing.get(shape_id))
            )

    for connector in connectors:
        start = connector.find("p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn", NS)
        end = connector.find("p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn", NS)
        info = connector.find("p:nvCxnSpPr/p:cNvPr", NS)
        name = info.get("id", "?") if info is not None else "?"
        if start is None or end is None:
            result.dropped.append(f"{name}: connector not glued at both ends")
            continue
        source, target = start.get("id", ""), end.get("id", "")
        if source not in labelled or target not in labelled:
            result.dropped.append(f"{name}: connector glued to an unlabelled shape")
            continue
        dash = connector.find("p:spPr/a:ln/a:prstDash", NS)
        is_optional = dash is not None and dash.get("val") in optional_dash
        result.graph.edges.append(Edge(source, target, None, is_optional))
    return result


def slides(data: bytes, rules: Mapping[str, object]) -> list[Slide]:
    """Return every slide in a deck as a Graph, in deck order.

    Raises:
        zipfile.BadZipFile: The bytes are not a PPTX package.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as deck:
        names = [
            n for n in deck.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
        ]
        ordered = sorted(names, key=lambda n: int(re.sub(r"\D", "", n)))
        return [
            read_slide(i, opc.xml(deck, n), rules) for i, n in enumerate(ordered, 1)
        ]
