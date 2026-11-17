"""Visio pages (.vsdx, .vstx) to Graphs, one per page.

A shape with text is a node, falling back to its master's text and then its
master's name. A connector glued at both ends (the page's `Connects`) is an edge.
A connector left floating, as template pages often ship them, has each end
snapped to the smallest shape within the configured distance. A shape whose
bounds hold others is a group. Visio units are inches with y up.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping

from merrow.convert import opc
from merrow.convert.visio import Stencil, V, _num, _own
from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import Drawing, skipper

R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _cell(shape: ET.Element, master: ET.Element | None, name: str) -> float:
    value = _own(shape, name)
    return _num(value if value is not None else _own(master, name))


def _text(element: ET.Element | None) -> list[str]:
    found = element.find(f"{V}Text") if element is not None else None
    raw = "".join(found.itertext()) if found is not None else ""
    return [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines() if ln.strip()]


def _snap(
    point: tuple[float, float], boxes: Mapping[str, Box], tolerance: float
) -> str | None:
    x, y = point
    hits = [
        ((b[2] - b[0]) * (b[3] - b[1]), key)
        for key, b in boxes.items()
        if b[0] - tolerance <= x <= b[2] + tolerance
        and b[1] - tolerance <= y <= b[3] + tolerance
    ]
    return min(hits)[1] if hits else None


def pages(data: bytes, rules: Mapping[str, object]) -> list[Drawing]:
    """Return every page of a Visio drawing as a Graph. `rules` holds `readers.visio`.

    Raises:
        zipfile.BadZipFile: The bytes are not a Visio package.
        KeyError: The package has no `visio/document.xml`.
    """
    stencil = Stencil(data)
    index = "visio/pages/pages.xml"
    if index not in stencil.zip.namelist():
        return []
    rels = opc.relationships(stencil.zip, index)
    found = []
    for page in opc.xml(stencil.zip, index).iter(f"{V}Page"):
        rel = page.find(f"{V}Rel")
        part = rels.get(rel.get(R_ID, "") if rel is not None else "", "")
        if part:
            name = page.get("NameU") or page.get("Name") or part
            found.append(_page(name, stencil, opc.xml(stencil.zip, part), rules))
    return found


def _page(
    name: str, stencil: Stencil, root: ET.Element, rules: Mapping[str, object]
) -> Drawing:
    drawing = Drawing(name, Graph())
    skip = skipper(rules.get("skip_labels"))
    connector_name = re.compile(
        str(rules.get("connector_masters", "(?!)")), re.IGNORECASE
    )
    tolerance = float(str(rules.get("snap_in", 0)))
    optional_patterns = {
        int(p) for p in str(rules.get("optional_patterns", "")).split(",") if p.strip()
    }
    shapes_root = root.find(f"{V}Shapes")
    shapes = shapes_root.findall(f"{V}Shape") if shapes_root is not None else []

    def master_of(shape: ET.Element) -> tuple[str, ET.Element | None]:
        master_id = shape.get("Master")
        if not master_id or master_id not in stencil.masters:
            return "", None
        name, top, _, _ = stencil.master(master_id)
        return name, top[0] if top else None

    labels: dict[str, list[str]] = {}
    boxes: dict[str, Box] = {}
    connectors: dict[str, ET.Element] = {}
    for shape in shapes:
        shape_id = shape.get("ID", "")
        master_name, master = master_of(shape)
        is_connector = (
            _own(shape, "BeginX") is not None and _own(shape, "EndX") is not None
        )
        if is_connector or connector_name.search(master_name):
            connectors[shape_id] = shape
            continue
        lines = _text(shape) or _text(master) or ([master_name] if master_name else [])
        lines = [ln for ln in lines if not (skip and skip.fullmatch(ln))]
        if not lines:
            drawing.dropped.append(f"{shape_id}: unlabelled shape")
            continue
        pin_x, pin_y = _cell(shape, master, "PinX"), _cell(shape, master, "PinY")
        loc_x, loc_y = _cell(shape, master, "LocPinX"), _cell(shape, master, "LocPinY")
        width, height = _cell(shape, master, "Width"), _cell(shape, master, "Height")
        boxes[shape_id] = (
            pin_x - loc_x,
            pin_y - loc_y,
            pin_x - loc_x + width,
            pin_y - loc_y + height,
        )
        labels[shape_id] = lines

    enclosing = nest_by_bounds(boxes, set(boxes))
    groups = set(enclosing.values())
    for shape_id, lines in labels.items():
        if shape_id in groups:
            drawing.graph.groups.append(
                Group(shape_id, lines[0], enclosing.get(shape_id))
            )
        else:
            subtitle = " ".join(lines[1:]) or None
            drawing.graph.nodes.append(
                Node(shape_id, lines[0], subtitle, group=enclosing.get(shape_id))
            )

    glued: dict[str, dict[str, str]] = {}
    connects = root.find(f"{V}Connects")
    for connect in connects.findall(f"{V}Connect") if connects is not None else []:
        source, end = connect.get("FromSheet", ""), connect.get("FromCell", "")
        if source in connectors:
            glued.setdefault(source, {})["from" if end == "BeginX" else "to"] = (
                connect.get("ToSheet", "")
            )
    for connector_id, connector in connectors.items():
        ends = glued.get(connector_id, {})
        start = ends.get("from") or _snap(
            (_num(_own(connector, "BeginX")), _num(_own(connector, "BeginY"))),
            boxes,
            tolerance,
        )
        finish = ends.get("to") or _snap(
            (_num(_own(connector, "EndX")), _num(_own(connector, "EndY"))),
            boxes,
            tolerance,
        )
        if start not in labels or finish not in labels or start == finish:
            drawing.dropped.append(
                f"{connector_id}: connector not attached at both ends"
            )
            continue
        label = " ".join(_text(connector)) or None
        pattern = int(_num(_own(connector, "LinePattern"), 1))
        drawing.graph.edges.append(
            Edge(str(start), str(finish), label, pattern in optional_patterns)
        )
    return drawing
