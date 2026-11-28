"""PDF pages to Graphs, one per page, rebuilt from what is drawn.

A PDF keeps no shapes or connectors, only ink: paths, text runs and images. A
closed path big enough to hold text is a box. An image or form object of icon
size is an icon, named by the text just below it. A box holding a labelled icon
or another box is a group, titled by the text at its top. A thin path, stroked
or drawn as a filled outline, is a line: touching lines join into one
connector, its free ends snap to the box or group border they touch, and a small
filled shape at an end is an arrowhead marking the target. A numbered step
marker drawn over a line does not break it. Coordinates are points with y down
from the top of the page.
"""

import ctypes
import math
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

import pypdfium2 as pdfium
import pypdfium2.raw as raw

from merrow.graph import Box, Edge, Graph, Group, Node, nest_by_bounds
from merrow.read import Drawing, skipper

type Point = tuple[float, float]
# A PDF matrix: x' = a*x + c*y + e, y' = b*x + d*y + f.
type Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(slots=True)
class _Rules:
    line_width: float
    join: float
    arrowhead: tuple[float, float]
    snap: float
    min_box: float
    icon: tuple[float, float]
    badge: float
    label_gap: float
    word_gap: float
    line_gap: float
    max_label_lines: int
    skip: re.Pattern[str] | None

    @classmethod
    def of(cls, rules: Mapping[str, object]) -> _Rules:
        def num(key: str) -> float:
            try:
                return float(str(rules[key]))
            except (KeyError, ValueError) as error:
                raise ValueError(f"readers.pdf.{key} must be a number") from error

        def pair(key: str) -> tuple[float, float]:
            value = rules.get(key)
            if not isinstance(value, list | tuple) or len(value) != 2:
                raise ValueError(f"readers.pdf.{key} must be [smallest, largest]")
            return float(value[0]), float(value[1])

        return cls(
            num("line_width"),
            num("join"),
            pair("arrowhead"),
            num("snap"),
            num("min_box"),
            pair("icon"),
            num("badge"),
            num("label_gap"),
            num("word_gap"),
            num("line_gap"),
            int(num("max_label_lines")),
            skipper(rules.get("skip_labels")),
        )


@dataclass(slots=True)
class _Run:
    box: Box
    text: str
    style: tuple[str, int]


@dataclass(slots=True)
class _Block:
    """Lines of text stacked close together: one label, title or paragraph."""

    box: Box
    lines: list[tuple[str, tuple[str, int]]]
    taken: bool = False


@dataclass(slots=True)
class _Ink:
    """Every path, text run and image on a page, in page coordinates."""

    # Each path's subpaths: (points, closed), and its filled, stroked, dashed flags.
    paths: list[tuple[list[tuple[list[Point], bool]], bool, bool, bool]] = field(
        default_factory=list
    )
    runs: list[_Run] = field(default_factory=list)
    icons: list[Box] = field(default_factory=list)


def _apply(m: Matrix, x: float, y: float) -> Point:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _then(inner: Matrix, outer: Matrix) -> Matrix:
    a, b, c, d, e, f = inner
    x0, y0 = _apply(outer, e, f)
    ax, bx = _apply(outer, a, b)
    cx, dx = _apply(outer, c, d)
    return (ax - outer[4], bx - outer[5], cx - outer[4], dx - outer[5], x0, y0)


def _matrix(obj: object) -> Matrix:
    m = raw.FS_MATRIX()
    raw.FPDFPageObj_GetMatrix(obj, m)
    return (m.a, m.b, m.c, m.d, m.e, m.f)


def _bounds(obj: object, outer: Matrix, flip: Point) -> Box:
    left, bottom, right, top = (ctypes.c_float() for _ in range(4))
    raw.FPDFPageObj_GetBounds(obj, left, bottom, right, top)
    corners = [
        _apply(outer, x, y)
        for x in (left.value, right.value)
        for y in (bottom.value, top.value)
    ]
    return _box([(x - flip[0], flip[1] - y) for x, y in corners])


def _box(points: list[Point]) -> Box:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _visible(getter, obj: object) -> bool:  # noqa: ANN001 -- a PDFium C function
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    return bool(getter(obj, r, g, b, a)) and a.value > 0


def _subpaths(obj: object, m: Matrix, flip: Point) -> list[tuple[list[Point], bool]]:
    """Return a path's subpaths as on-curve points, each with whether it closes."""
    found: list[tuple[list[Point], bool]] = []
    points: list[Point] = []
    closed, curve = False, 0
    for index in range(raw.FPDFPath_CountSegments(obj)):
        segment = raw.FPDFPath_GetPathSegment(obj, index)
        x, y = ctypes.c_float(), ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(segment, x, y)
        kind = raw.FPDFPathSegment_GetType(segment)
        if kind == raw.FPDF_SEGMENT_MOVETO and points:
            found.append((points, closed))
            points, closed = [], False
        curve = curve + 1 if kind == raw.FPDF_SEGMENT_BEZIERTO else 0
        if curve in (0, 3):
            px, py = _apply(m, x.value, y.value)
            points.append((px - flip[0], flip[1] - py))
            curve = 0
        closed = closed or bool(raw.FPDFPathSegment_GetClose(segment))
    if points:
        found.append((points, closed))
    return found


def _text(obj: object, textpage: object) -> str:
    size = raw.FPDFTextObj_GetText(obj, textpage, None, 0)
    buffer = (ctypes.c_ushort * max(size, 1))()
    raw.FPDFTextObj_GetText(obj, textpage, buffer, size)
    return bytes(buffer).decode("utf-16-le", errors="replace").split("\x00")[0]


def _style(obj: object, m: Matrix) -> tuple[str, int]:
    size = ctypes.c_float()
    raw.FPDFTextObj_GetFontSize(obj, size)
    font = raw.FPDFTextObj_GetFont(obj)
    length = raw.FPDFFont_GetBaseFontName(font, None, 0) if font else 0
    name = ctypes.create_string_buffer(max(length, 1))
    if length:
        raw.FPDFFont_GetBaseFontName(font, name, length)
    scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
    return name.value.decode("latin-1"), round(size.value * scale * 2)


def _collect(page: pdfium.PdfPage, rules: _Rules) -> _Ink:
    """Walk every object, opening forms bigger than an icon, into page ink."""
    ink = _Ink()
    left, _, _, top = page.get_mediabox()
    flip = (left, top)
    textpage = page.get_textpage()

    def children(form: object | None) -> Iterator[object]:
        if form is None:
            for index in range(raw.FPDFPage_CountObjects(page.raw)):
                yield raw.FPDFPage_GetObject(page.raw, index)
        else:
            for index in range(raw.FPDFFormObj_CountObjects(form)):
                yield raw.FPDFFormObj_GetObject(form, index)

    def walk(form: object | None, outer: Matrix) -> None:
        for obj in children(form):
            kind = raw.FPDFPageObj_GetType(obj)
            own = _then(_matrix(obj), outer)
            if kind == raw.FPDF_PAGEOBJ_PATH:
                mode, stroked = ctypes.c_int(), ctypes.c_int()
                raw.FPDFPath_GetDrawMode(obj, mode, stroked)
                filled = mode.value != raw.FPDF_FILLMODE_NONE and _visible(
                    raw.FPDFPageObj_GetFillColor, obj
                )
                inked = bool(stroked.value) and _visible(
                    raw.FPDFPageObj_GetStrokeColor, obj
                )
                if filled or inked:
                    dashed = inked and raw.FPDFPageObj_GetDashCount(obj) > 0
                    ink.paths.append((_subpaths(obj, own, flip), filled, inked, dashed))
            elif kind == raw.FPDF_PAGEOBJ_TEXT:
                m = _matrix(obj)
                text = re.sub(r"\s+", " ", _text(obj, textpage))
                upright = abs(m[1]) <= abs(m[0]) * 0.1 and m[0] > 0
                if text.strip() and upright:
                    ink.runs.append(
                        _Run(_bounds(obj, outer, flip), text, _style(obj, own))
                    )
            elif kind in (raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_FORM):
                box = _bounds(obj, outer, flip)
                side = max(box[2] - box[0], box[3] - box[1])
                if rules.icon[0] <= side <= rules.icon[1]:
                    ink.icons.append(box)
                elif kind == raw.FPDF_PAGEOBJ_FORM and side > rules.icon[1]:
                    walk(obj, own)

    walk(None, _IDENTITY)
    return ink


def _innermost(point: Point, boxes: list[Box]) -> Box | None:
    holding = [b for b in boxes if _within(point, b)]
    return min(holding, key=_area) if holding else None


def _blocks(runs: list[_Run], boxes: list[Box], rules: _Rules) -> list[_Block]:
    """Join text runs into lines on a shared baseline, then lines into blocks.

    Lines join only inside the same box, so a title never swallows the label of
    a box just below it.
    """
    lines: list[tuple[Box, list[_Run]]] = []
    for run in sorted(runs, key=lambda r: (r.box[0], r.box[1])):
        height = run.box[3] - run.box[1]
        middle = (run.box[1] + run.box[3]) / 2
        for index, (box, members) in enumerate(lines):
            tall = max(height, box[3] - box[1])
            gap = run.box[0] - box[2]
            same_row = abs((box[1] + box[3]) / 2 - middle) <= tall / 2
            if same_row and -tall <= gap <= rules.word_gap * tall:
                members.append(run)
                lines[index] = (
                    _box([box[:2], box[2:], run.box[:2], run.box[2:]]),
                    members,
                )
                break
        else:
            lines.append((run.box, [run]))

    def joined(members: list[_Run]) -> str:
        tall = max(run.box[3] - run.box[1] for run in members)
        text = ""
        for before, run in zip([None, *members], members, strict=False):
            space = before and run.box[0] - before.box[2] > 0.25 * tall
            text += (" " if space else "") + run.text
        return re.sub(r"\s+", " ", text).strip()

    blocks: list[_Block] = []
    for box, members in sorted(lines, key=lambda line: (line[0][1], line[0][0])):
        entry = (joined(members), members[0].style)
        height = box[3] - box[1]
        for block in blocks:
            last = block.box
            overlap = min(box[2], last[2]) - max(box[0], last[0])
            gap = box[1] - last[3]
            if (
                overlap > 0
                and -height / 2 <= gap <= rules.line_gap * height
                and _innermost(_centre(box), boxes) == _innermost(_centre(last), boxes)
            ):
                block.lines.append(entry)
                block.box = _box([last[:2], last[2:], box[:2], box[2:]])
                break
        else:
            blocks.append(_Block(box, [entry]))
    return blocks


def _thickness(points: list[Point]) -> float:
    """Twice a polygon's area over its perimeter: the width of a thin outline."""
    ring = [*points, points[0]]
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))) / 2
    perimeter = sum(math.dist(p, q) for p, q in zip(ring, ring[1:]))
    return 2 * area / perimeter if perimeter else 0.0


def _area(box: Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _within(point: Point, box: Box, slack: float = 0.0) -> bool:
    x, y = point
    return (
        box[0] - slack <= x <= box[2] + slack and box[1] - slack <= y <= box[3] + slack
    )


def _centre(box: Box) -> Point:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _to_box(point: Point, box: Box) -> float:
    dx = max(box[0] - point[0], 0.0, point[0] - box[2])
    dy = max(box[1] - point[1], 0.0, point[1] - box[3])
    return math.hypot(dx, dy)


def _to_border(point: Point, box: Box) -> float:
    if not _within(point, box):
        return _to_box(point, box)
    x, y = point
    return min(x - box[0], box[2] - x, y - box[1], box[3] - y)


def _to_segment(point: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = (
        0.0
        if not length
        else ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length
    )
    t = min(1.0, max(0.0, t))
    return math.dist(point, (a[0] + t * dx, a[1] + t * dy))


@dataclass(slots=True)
class _End:
    point: Point
    headed: bool


@dataclass(slots=True)
class _Connector:
    ends: list[_End]
    segments: list[tuple[Point, Point]]
    dashed: bool


def _crosses(a: Point, b: Point, box: Box) -> bool:
    steps = max(1, int(math.dist(a, b) // 2))
    return any(
        _within(
            (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps), box
        )
        for i in range(steps + 1)
    )


class _Sets:
    """Union-find over integers."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        while self.parent.setdefault(item, item) != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _connectors(
    pieces: list[tuple[list[Point], bool, bool]],
    heads: list[list[Point]],
    rules: _Rules,
) -> list[_Connector]:
    """Return each connector's free ends, its segments and whether it is dashed.

    Points closer than `join` merge into one vertex, so a filled outline folds
    onto its centre line. A vertex with one neighbour is an end, unless it rests
    on another line, which makes the two one connector.
    """
    points = [point for subpath, _, _ in pieces for point in subpath]
    vertex = _Sets()
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, point in enumerate(points):
        cell = (int(point[0] // rules.join), int(point[1] // rules.join))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid[(cell[0] + dx, cell[1] + dy)]:
                    if math.dist(point, points[other]) <= rules.join:
                        vertex.join(index, other)
        grid[cell].append(index)

    members: dict[int, list[Point]] = defaultdict(list)
    for index, point in enumerate(points):
        members[vertex.find(index)].append(point)
    where = {v: _centre(_box(found)) for v, found in members.items()}

    links: dict[int, set[int]] = {v: set() for v in members}
    joined = _Sets()
    segments: list[tuple[Point, Point, int]] = []
    start = 0
    for subpath, closed, _ in pieces:
        ids = [vertex.find(i) for i in range(start, start + len(subpath))]
        start += len(subpath)
        pairs = list(zip(ids, ids[1:], strict=False))
        if closed and len(ids) > 2:
            pairs.append((ids[-1], ids[0]))
        for a, b in pairs:
            joined.join(a, b)
            if a != b:
                links[a].add(b)
                links[b].add(a)
                segments.append((where[a], where[b], a))

    leaves = [v for v, near in links.items() if len(near) == 1]
    ends = set(leaves)
    for leaf in leaves:
        for a, b, on in segments:
            if joined.find(on) != joined.find(leaf) and (
                _to_segment(where[leaf], a, b) <= rules.join
            ):
                joined.join(leaf, on)
                ends.discard(leaf)
                break

    tips: dict[int, Point] = {}
    for head in heads:
        box = _box(head)
        near = [(_to_box(where[leaf], box), leaf) for leaf in ends]
        close = [found for found in near if found[0] <= rules.join]
        if not close:
            continue
        leaf = min(close)[1]
        back = where[next(iter(links[leaf]))]
        way = (where[leaf][0] - back[0], where[leaf][1] - back[1])
        tips[leaf] = max(head, key=lambda p: p[0] * way[0] + p[1] * way[1])

    dashed: dict[int, bool] = defaultdict(bool)
    start = 0
    for subpath, _, is_dashed in pieces:
        if subpath:
            root = joined.find(vertex.find(start))
            dashed[root] = dashed[root] or is_dashed
        start += len(subpath)
    found: dict[int, _Connector] = {}
    for a, b, on in segments:
        root = joined.find(on)
        found.setdefault(root, _Connector([], [], dashed[root])).segments.append((a, b))
    for leaf in sorted(ends):
        found[joined.find(leaf)].ends.append(
            _End(tips.get(leaf, where[leaf]), leaf in tips)
        )
    return list(found.values())


def _shapes(
    ink: _Ink, page_box: Box, rules: _Rules
) -> tuple[list[Box], list[tuple[list[Point], bool, bool]], list[list[Point]]]:
    """Sort subpaths into boxes, line pieces and arrowhead candidates."""
    boxes: list[Box] = []
    pieces: list[tuple[list[Point], bool, bool]] = []
    heads: list[list[Point]] = []
    for subpaths, filled, stroked, dashed in ink.paths:
        for points, closed in subpaths:
            box = _box(points)
            side = max(box[2] - box[0], box[3] - box[1])
            shut = closed or (
                len(points) > 2 and math.dist(points[0], points[-1]) < 0.5
            )
            if filled and shut and rules.arrowhead[0] <= side <= rules.arrowhead[1]:
                heads.append(points)
            elif shut and len(points) > 2 and _thickness(points) > rules.line_width:
                small = min(box[2] - box[0], box[3] - box[1]) < rules.min_box
                edges = sum(
                    abs(a - b) <= rules.join for a, b in zip(box, page_box, strict=True)
                )
                backdrop = edges >= 3 or (
                    edges == 2 and _area(box) > _area(page_box) / 2
                )
                if not small and not backdrop:
                    boxes.append(box)
            elif (stroked and not shut) or side > rules.arrowhead[1]:
                pieces.append((points, shut and filled, dashed))
    unique: list[Box] = []
    for box in sorted(boxes, key=_area):
        if not any(
            max(abs(a - b) for a, b in zip(box, kept)) <= rules.join for kept in unique
        ):
            unique.append(box)
    return unique, pieces, heads


def _split(lines: list[tuple[str, tuple[str, int]]]) -> tuple[str, str | None]:
    """Return the leading lines in one style as a label, and the rest as subtitle."""
    count = next(
        (i for i, (_, style) in enumerate(lines) if style != lines[0][1]), len(lines)
    )
    label = " ".join(text for text, _ in lines[:count])
    return label, " ".join(text for text, _ in lines[count:]) or None


def _label_of(
    icon: Box, blocks: list[_Block], boxes: list[Box], rules: _Rules
) -> _Block | None:
    """Return the nearest free text block just below an icon, in the same box."""
    room = _innermost(_centre(icon), boxes)
    below = []
    for block in blocks:
        box = block.box
        gap = box[1] - icon[3]
        off = abs(_centre(box)[0] - _centre(icon)[0])
        if (
            not block.taken
            and -2 <= gap <= rules.label_gap
            and off <= max(box[2] - box[0], icon[2] - icon[0]) / 2
            and _innermost(_centre(box), boxes) == room
        ):
            below.append((gap, id(block), block))
    return min(below)[2] if below else None


def _through(
    connectors: list[_Connector], markers: list[Box], slack: float
) -> list[_Connector]:
    """Join connectors that meet in a step marker: the line runs under it.

    A line ending in a marker joins every line ending in it or passing under it.
    """
    sets = _Sets()
    for marker in markers:
        ending = [
            i
            for i, c in enumerate(connectors)
            if any(_within(e.point, marker, slack) for e in c.ends)
        ]
        passing = [
            i
            for i, c in enumerate(connectors)
            if i not in ending and any(_crosses(a, b, marker) for a, b in c.segments)
        ]
        meeting = ending + passing if ending else []
        for i in meeting[1:]:
            sets.join(i, meeting[0])
    merged: dict[int, _Connector] = {}
    for i, connector in enumerate(connectors):
        kept = [
            e
            for e in connector.ends
            if not any(_within(e.point, m, slack) for m in markers)
        ]
        into = merged.setdefault(sets.find(i), _Connector([], [], False))
        into.ends += kept
        into.dashed = into.dashed or connector.dashed
    return list(merged.values())


def _page(number: int, page: pdfium.PdfPage, rules: _Rules) -> Drawing:
    drawing = Drawing(str(number), Graph())
    left, bottom, right, top = page.get_mediabox()
    page_box: Box = (0.0, 0.0, right - left, top - bottom)
    ink = _collect(page, rules)
    boxes, pieces, heads = _shapes(ink, page_box, rules)
    # A box holding only a skipped label, such as a step number, is a marker. One
    # bigger than an icon is a box that lost its text, not a marker.
    blocks: list[_Block] = []
    markers: list[Box] = []
    for block in _blocks(ink.runs, boxes, rules):
        if not (rules.skip and all(rules.skip.fullmatch(t) for t, _ in block.lines)):
            blocks.append(block)
            continue
        marker = _innermost(_centre(block.box), boxes)
        if marker and _area(marker) <= rules.icon[1] ** 2:
            markers.append(marker)

    nodes: dict[str, tuple[Box, str, str | None]] = {}
    reach: dict[str, Box] = {}
    for index, icon in enumerate(sorted(ink.icons, key=lambda b: (b[1], b[0]))):
        frames = [b for b in boxes if _within(icon[:2], b)]
        frame = min(frames, key=_area) if frames else None
        if frame and max(icon[0] - frame[0], icon[1] - frame[1]) <= rules.badge:
            continue
        block = _label_of(icon, blocks, boxes, rules)
        if block is None:
            drawing.dropped.append(f"icon at {icon[0]:.0f},{icon[1]:.0f}: no label")
            continue
        block.taken = True
        label, subtitle = _split(block.lines)
        nodes[f"i{index}"] = (icon, label, subtitle)
        reach[f"i{index}"] = _box([icon[:2], icon[2:], block.box[:2], block.box[2:]])

    holder = {id(b): _innermost(_centre(b.box), boxes) for b in blocks}
    groups: dict[str, tuple[Box, str]] = {}
    for index, box in enumerate(boxes):
        held = [n for n, (b, _, _) in nodes.items() if _within(_centre(b), box)]
        held += [g for g, (b, _) in groups.items() if _within(_centre(b), box)]
        inside = sorted(
            (b for b in blocks if not b.taken and holder[id(b)] == box),
            key=lambda b: (b.box[1], b.box[0]),
        )
        where = f"box at {box[0]:.0f},{box[1]:.0f}"
        if held:
            top = [b for b in inside if b.box[1] - box[1] <= 2 * rules.label_gap]
            title = top[0] if top else None
            if title:
                title.taken = True
            groups[f"g{index}"] = (box, _split(title.lines)[0] if title else "")
            continue
        if not inside:
            drawing.dropped.append(f"{where}: no text")
            continue
        lines = [line for block in inside for line in block.lines]
        if len(lines) > rules.max_label_lines:
            drawing.dropped.append(f"{where}: {len(lines)} lines of prose")
            continue
        for block in inside:
            block.taken = True
        label, subtitle = _split(lines)
        nodes[f"n{index}"] = (box, label, subtitle)

    bounds = {k: v[0] for k, v in nodes.items()} | {k: v[0] for k, v in groups.items()}
    enclosing = nest_by_bounds(bounds, set(groups))
    for key, (_, label) in groups.items():
        drawing.graph.groups.append(Group(key, label, enclosing.get(key)))
    for key, (_, label, subtitle) in nodes.items():
        drawing.graph.nodes.append(Node(key, label, subtitle, group=enclosing.get(key)))
    for block in blocks:
        if not block.taken:
            drawing.dropped.append(f"text {block.lines[0][0]!r}: belongs to no shape")

    def snap(point: Point) -> str | None:
        on_node = [
            (_to_box(point, reach.get(k, b)), _area(b), k)
            for k, (b, _, _) in nodes.items()
        ]
        on_group = [(_to_border(point, b), _area(b), k) for k, (b, _) in groups.items()]
        for found in (on_node, on_group):
            close = [f for f in found if f[0] <= rules.snap]
            if close:
                return min(close)[2]
        return None

    seen: set[tuple[str, str]] = set()
    for connector in _through(_connectors(pieces, heads, rules), markers, rules.join):
        ends, dashed = connector.ends, connector.dashed
        snapped = [(snap(end.point), end.headed) for end in ends]
        targets = [key for key, headed in snapped if key and headed]
        sources = [key for key, headed in snapped if key and not headed]
        if not targets and len(sources) == 2:
            targets = sources[1:]
            sources = sources[:1]
        elif not sources and len(targets) == 2:
            sources = targets[::-1]
        pairs = [(s, t) for s in sources for t in targets if s != t]
        if not pairs:
            if len(ends) > 1:
                at = ends[0].point
                drawing.dropped.append(
                    f"line at {at[0]:.0f},{at[1]:.0f}: not attached at both ends"
                )
            continue
        for pair in pairs:
            if pair not in seen:
                seen.add(pair)
                drawing.graph.edges.append(Edge(pair[0], pair[1], None, dashed))
    return drawing


def pages(data: bytes, rules: Mapping[str, object]) -> list[Drawing]:
    """Return every page of a PDF as a Graph. `rules` holds `readers.pdf`.

    Raises:
        ValueError: The bytes aren't a PDF PDFium can read, or a `readers.pdf` rule is
            missing or not a number.
    """
    settings = _Rules.of(rules)
    try:
        document = pdfium.PdfDocument(data)
        return [
            _page(i, document[i - 1], settings) for i in range(1, len(document) + 1)
        ]
    except pdfium.PdfiumError as error:
        raise ValueError(f"not a readable PDF: {error}") from error
