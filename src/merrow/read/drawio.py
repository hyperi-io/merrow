"""draw.io (diagrams.net) files to Graphs, one per page.

A draw.io page is an mxGraph: every cell names its `parent`, a vertex is a box
or a container, and an edge names its `source` and `target` cells. Containment
is the parent chain, so it is exact. Labels are HTML, reduced to text. A page
stored compressed (base64 of raw deflate of URL-encoded XML) is unpacked.
"""

import base64
import binascii
import re
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import unquote

from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import Drawing, skipper

# One page, inflated: a drawing past this is a compression bomb, not a diagram.
MAX_PAGE_BYTES = 20_000_000


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in ("br", "div", "p"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def text(value: str) -> list[str]:
    """Return a cell's label as its non-empty lines of plain text."""
    parser = _Text()
    parser.feed(value or "")
    joined = "".join(parser.parts).replace("\xa0", " ")
    lines = (re.sub(r"\s+", " ", line).strip() for line in joined.split("\n"))
    return [line for line in lines if line]


def _style(raw: str | None) -> dict[str, str]:
    pairs = (part.split("=", 1) for part in (raw or "").split(";") if part)
    return {kv[0]: (kv[1] if len(kv) > 1 else "") for kv in pairs}


def _model(diagram: ET.Element) -> ET.Element | None:
    """Return a page's mxGraphModel, unpacking a compressed page."""
    model = diagram.find("mxGraphModel")
    if model is not None:
        return model
    packed = (diagram.text or "").strip()
    if not packed:
        return None
    try:
        inflater = zlib.decompressobj(-15)
        raw = inflater.decompress(base64.b64decode(packed), MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise ValueError(f"a page inflates past {MAX_PAGE_BYTES} bytes")
        if not inflater.eof:
            raise ValueError("a compressed page is corrupt: the data stops early")
        xml = unquote(raw.decode("utf-8"))
        return ET.fromstring(xml)  # noqa: S314 -- expat refuses entity expansion attacks
    except (binascii.Error, zlib.error, UnicodeDecodeError, ET.ParseError) as error:
        raise ValueError(f"a compressed page is corrupt: {error}") from error


def pages(data: bytes, rules: Mapping[str, object]) -> list[Drawing]:
    """Return every page in a draw.io file as a Graph.

    `rules` holds the `readers.drawio` config: `container` (style keys marking a
    container) and `optional` (style key=value pairs marking an optional edge).

    Raises:
        ValueError: The bytes aren't draw.io XML, a compressed page is corrupt or
            inflates past `MAX_PAGE_BYTES`, or a geometry value isn't a number.
    """
    try:
        root = ET.fromstring(data)  # noqa: S314 -- expat refuses entity expansion attacks
    except ET.ParseError as error:
        raise ValueError(f"not draw.io XML: {error}") from error
    if root.tag not in ("mxGraphModel", "mxfile"):
        raise ValueError(f"not a draw.io file: the root element is <{root.tag}>")
    if root.tag == "mxGraphModel":
        return [_page("page-1", root, rules)]
    found = []
    for number, diagram in enumerate(root.findall("diagram"), 1):
        model = _model(diagram)
        if model is not None:
            found.append(_page(diagram.get("name") or f"page-{number}", model, rules))
    return found


def _cells(model: ET.Element) -> dict[str, ET.Element]:
    """Return every cell by id, with a wrapping object's label moved onto its cell."""
    cells = {c.get("id", ""): c for c in model.iter("mxCell")}
    for wrapper in [*model.iter("UserObject"), *model.iter("object")]:
        inner = wrapper.find("mxCell")
        if inner is not None:
            inner.set("id", wrapper.get("id", ""))
            inner.set("value", wrapper.get("label", ""))
            cells[wrapper.get("id", "")] = inner
    return cells


def _keys(rules: Mapping[str, object], name: str) -> set[str]:
    return {k.strip() for k in str(rules.get(name, "")).split(",") if k.strip()}


def _number(geometry: ET.Element, name: str, cell_id: str) -> float:
    try:
        return float(geometry.get(name, 0))
    except ValueError as error:
        raise ValueError(
            f"cell {cell_id!r}: geometry {name} is not a number"
        ) from error


def _boxes(cells: Mapping[str, ET.Element]) -> dict[str, Box]:
    """Return each vertex's box in page coordinates: geometry is parent-relative."""
    local: dict[str, Box] = {}
    for cell_id, cell in cells.items():
        geometry = cell.find("mxGeometry")
        if cell.get("vertex") == "1" and geometry is not None:
            x, y = _number(geometry, "x", cell_id), _number(geometry, "y", cell_id)
            w = _number(geometry, "width", cell_id)
            h = _number(geometry, "height", cell_id)
            local[cell_id] = (x, y, x + w, y + h)

    def absolute(cell_id: str, depth: int = 0) -> Box:
        x0, y0, x1, y1 = local[cell_id]
        parent = cells[cell_id].get("parent")
        if parent in local and depth < 32:
            px, py, _, _ = absolute(parent, depth + 1)
            return (x0 + px, y0 + py, x1 + px, y1 + py)
        return (x0, y0, x1, y1)

    return {cell_id: absolute(cell_id) for cell_id in local}


def _page(name: str, model: ET.Element, rules: Mapping[str, object]) -> Drawing:
    cells = _cells(model)
    container_keys = _keys(rules, "container")
    title_keys = _keys(rules, "title")
    placeholder = skipper(rules.get("skip_labels"))
    optional = dict(
        pair.split("=", 1)
        for pair in str(rules.get("optional", "")).split(",")
        if "=" in pair
    )
    page = Drawing(name, Graph())
    vertices = {i: c for i, c in cells.items() if c.get("vertex") == "1"}
    has_children = {c.get("parent") for c in vertices.values()}
    groups = {
        i
        for i, c in vertices.items()
        if i in has_children or container_keys & set(_style(c.get("style")))
    }

    def lines_of(cell: ET.Element) -> list[str]:
        found = text(cell.get("value", ""))
        return [
            line for line in found if not (placeholder and placeholder.fullmatch(line))
        ]

    def parent_group(cell: ET.Element) -> str | None:
        own = cell.get("id", "")
        seen = {own}
        parent = cell.get("parent")
        while parent and parent not in groups and parent not in seen:
            seen.add(parent)
            parent = cells[parent].get("parent") if parent in cells else None
        return parent if parent in groups and parent != own else None

    # A shape laid over a container without being parented to it still sits in it.
    by_bounds = nest_by_bounds(_boxes(cells), groups)
    container = {i: parent_group(c) or by_bounds.get(i) for i, c in vertices.items()}

    # An unlabelled container takes its title from a text cell inside it.
    titles: dict[str, str] = {}
    title_cells = set()
    for cell_id, cell in vertices.items():
        holder = container[cell_id]
        is_title = title_keys & set(_style(cell.get("style")))
        if (
            holder
            and is_title
            and cell_id not in groups
            and not lines_of(vertices[holder])
        ):
            lines = lines_of(cell)
            if lines and holder not in titles:
                titles[holder] = lines[0]
                title_cells.add(cell_id)

    for cell_id, cell in vertices.items():
        if cell_id in title_cells:
            continue
        lines = lines_of(cell)
        if cell_id in groups:
            label = lines[0] if lines else titles.get(cell_id, "")
            page.graph.groups.append(Group(cell_id, label, container[cell_id]))
        elif lines:
            subtitle = " ".join(lines[1:]) or None
            page.graph.nodes.append(
                Node(cell_id, lines[0], subtitle, group=container[cell_id])
            )
        else:
            page.dropped.append(f"{cell_id}: unlabelled shape")

    known = {n.id for n in page.graph.nodes} | groups
    for cell_id, cell in cells.items():
        if cell.get("edge") != "1":
            continue
        source, target = cell.get("source"), cell.get("target")
        if source not in known or target not in known:
            page.dropped.append(f"{cell_id}: edge not attached at both ends")
            continue
        style = _style(cell.get("style"))
        is_optional = any(style.get(key) == value for key, value in optional.items())
        label = " ".join(text(cell.get("value", ""))) or None
        page.graph.edges.append(Edge(str(source), str(target), label, is_optional))
    return page
