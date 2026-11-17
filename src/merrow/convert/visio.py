"""Visio stencil masters (`.vssx`) to an Iconify pack.

Each master's geometry is drawn as SVG paths in Visio's units (inches, y up),
then flipped to SVG's y down. Line and fill come from the shape, then its
master, then the style sheet chain. Embedded PNG and JPEG foreign data is
inlined. A master that draws nothing is reported, never dropped silently.
"""

import base64
import io
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from merrow import archive, naming
from merrow.convert import opc
from merrow.model import Built, Limits, Source, tally

V = "{http://schemas.microsoft.com/office/visio/2012/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# Visio LinePattern -> dash lengths in points at a 1 pt line. 0 and 1 are none and solid.
PATTERN_DASH = {2: (4, 3), 3: (1, 2), 4: (4, 2, 1, 2), 9: (8, 4), 10: (2, 2)}
# Visio's own defaults for a shape that sets neither.
DEFAULT_LINE = "#000000"
DEFAULT_FILL = "#FFFFFF"
POINTS_PER_INCH = 72
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "BMP": "image/bmp"}

type Point = tuple[float, float]
# One local transform: pin x/y, loc-pin x/y, angle, flip x/y, width, height.
type Transform = tuple[float, float, float, float, float, float, float, float, float]


@dataclass(slots=True)
class Report:
    """What one conversion did, for the CLI and for review."""

    stencils: int = 0
    masters: int = 0
    icons: int = 0
    no_geometry: list[str] = field(default_factory=list)
    # Built, but part of the artwork is in a format a browser can't show (EMF).
    partial: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    skipped_rows: dict[str, int] = field(default_factory=dict)
    unrendered_foreign: dict[str, int] = field(default_factory=dict)


def _num(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _own(element: ET.Element | None, name: str) -> str | None:
    """Return a cell's value set on this element itself, not inherited."""
    if element is None:
        return None
    for cell in element.findall(f"{V}Cell"):
        if cell.get("N") == name:
            return cell.get("V")
    return None


def _formula(row: ET.Element, name: str) -> str:
    return next(
        (c.get("F", "") for c in row.findall(f"{V}Cell") if c.get("N") == name), ""
    )


def _style_kind(name: str) -> str:
    if name.startswith("Line") or name in ("Rounding", "EndArrow", "BeginArrow"):
        return "LineStyle"
    return "FillStyle" if name.startswith("Fill") else "TextStyle"


class Stencil:
    """One open `.vssx` package: its style sheets and masters."""

    def __init__(self, data: bytes) -> None:
        """Open a stencil from its bytes.

        Raises:
            zipfile.BadZipFile: The bytes are not a Visio package.
            KeyError: The package has no `visio/document.xml`.
        """
        self.zip = zipfile.ZipFile(io.BytesIO(data))
        document = opc.xml(self.zip, "visio/document.xml")
        self.styles = {
            sheet.get("ID"): sheet for sheet in document.iter(f"{V}StyleSheet")
        }
        self.masters: dict[str, tuple[str, str]] = {}
        if "visio/masters/masters.xml" in self.zip.namelist():
            index = "visio/masters/masters.xml"
            rels = opc.relationships(self.zip, index)
            for master in opc.xml(self.zip, index).iter(f"{V}Master"):
                rel = master.find(f"{V}Rel")
                path = rels.get(rel.get(R_ID, "") if rel is not None else "", "")
                self.masters[master.get("ID", "")] = (master.get("NameU") or "", path)

    def master(
        self, master_id: str
    ) -> tuple[str, list[ET.Element], dict[str, str], str]:
        """Return a master's name, top-level shapes, relationships and part path."""
        name, path = self.masters[master_id]
        root = opc.xml(self.zip, path)
        shapes = root.find(f"{V}Shapes")
        rels = opc.relationships(self.zip, path)
        return (
            name,
            list(shapes.findall(f"{V}Shape")) if shapes is not None else [],
            rels,
            path,
        )

    def style_cell(self, style_id: str | None, name: str, depth: int = 0) -> str | None:
        """Return a cell from a style sheet, following its parent styles."""
        sheet = self.styles.get(style_id) if style_id else None
        if sheet is None or depth > 8:
            return None
        value = _own(sheet, name)
        if value is not None:
            return value
        parent = sheet.get(_style_kind(name))
        return self.style_cell(parent, name, depth + 1) if parent != style_id else None

    def cell(self, shape: ET.Element, name: str) -> str | None:
        """Return a shape's cell: its own, else from its style chain."""
        value = _own(shape, name)
        return (
            value
            if value is not None
            else self.style_cell(shape.get(_style_kind(name)), name)
        )


def _colour(value: str | None) -> str | None:
    return value.upper() if value and value.startswith("#") else None


def nurbs(
    start: Point, end: Point, formula: str, size: Point, steps: int
) -> list[Point]:
    """Sample a Visio NURBSTo row: `NURBS(knotLast, degree, xType, yType, x,y,knot,weight, ...)`."""
    found = re.search(r"NURBS\(([^)]*)\)", formula)
    if not found:
        return [end]
    values = [_num(v) for v in found.group(1).split(",")]
    knot_last, degree, x_type, y_type = values[0], int(values[1]), values[2], values[3]
    points = [(start[0], start[1], 0.0, 1.0)]
    rest = values[4:]
    for i in range(0, len(rest) - 3, 4):
        x, y, knot, weight = rest[i : i + 4]
        points.append(
            (
                x * size[0] if x_type == 0 else x,
                y * size[1] if y_type == 0 else y,
                knot,
                weight,
            )
        )
    points.append((end[0], end[1], knot_last, 1.0))
    control = [(p[0], p[1]) for p in points]
    weights = [p[3] for p in points]
    inner = [p[2] for p in points[:-1]]
    knots = [inner[0]] * degree + inner + [knot_last] * (degree + 1)
    last = len(control) - 1
    if len(knots) != last + degree + 2:
        return [end]
    t0, t1 = knots[degree], knots[last + 1]
    sampled = []
    for step in range(1, steps + 1):
        t = t0 + (t1 - t0) * step / steps
        span = (
            max(i for i in range(degree, last + 1) if knots[i] <= t) if t < t1 else last
        )
        d = [
            (control[j][0] * weights[j], control[j][1] * weights[j], weights[j])
            for j in range(span - degree, span + 1)
        ]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + span - degree
                denominator = knots[i + degree - r + 1] - knots[i]
                a = 0 if denominator == 0 else (t - knots[i]) / denominator
                d[j] = (
                    (1 - a) * d[j - 1][0] + a * d[j][0],
                    (1 - a) * d[j - 1][1] + a * d[j][1],
                    (1 - a) * d[j - 1][2] + a * d[j][2],
                )
        x, y, w = d[degree]
        sampled.append((x / w, y / w) if w else (x, y))
    return sampled


def elliptical_arc(
    start: Point, end: Point, control: Point, angle: float, ratio: float
) -> tuple[float, ...] | None:
    """Return SVG arc parameters (rx, ry, rotation, large, sweep) for an EllipticalArcTo, y up."""
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)

    def unrotate(p: Point) -> Point:
        x, y = p[0] * cos_a - p[1] * sin_a, p[0] * sin_a + p[1] * cos_a
        return (x / ratio if ratio else x, y)

    a, b, c = unrotate(start), unrotate(control), unrotate(end)
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    sq = [p[0] ** 2 + p[1] ** 2 for p in (a, b, c)]
    ux = (sq[0] * (b[1] - c[1]) + sq[1] * (c[1] - a[1]) + sq[2] * (a[1] - b[1])) / d
    uy = (sq[0] * (c[0] - b[0]) + sq[1] * (a[0] - c[0]) + sq[2] * (b[0] - a[0])) / d
    radius = math.hypot(a[0] - ux, a[1] - uy)

    def theta(p: Point) -> float:
        return math.atan2(p[1] - uy, p[0] - ux)

    def ccw(s: float, e: float) -> float:
        return (e - s) % (2 * math.pi)

    is_ccw = ccw(theta(a), theta(b)) < ccw(theta(a), theta(c))
    span = ccw(theta(a), theta(c)) if is_ccw else ccw(theta(c), theta(a))
    return (
        radius * ratio,
        radius,
        math.degrees(angle),
        int(span > math.pi),
        int(is_ccw),
    )


def _geometry(
    shape: ET.Element, size: Point, steps: int, skipped: dict[str, int]
) -> Iterator[tuple[list[tuple], bool, bool]]:
    """Yield each shown Geometry section as (segments, no_fill, no_line), in shape-local inches."""
    w, h = size
    for section in shape.findall(f"{V}Section"):
        if section.get("N") != "Geometry" or _own(section, "NoShow") == "1":
            continue
        segments: list[tuple] = []
        current: Point = (0.0, 0.0)
        for row in section.findall(f"{V}Row"):
            kind = row.get("T", "")

            def g(name: str, row: ET.Element = row) -> float:
                return _num(_own(row, name))

            match kind:
                case "MoveTo" | "LineTo":
                    current = (g("X"), g("Y"))
                    segments.append(("M" if kind == "MoveTo" else "L", current))
                case "RelMoveTo" | "RelLineTo":
                    current = (g("X") * w, g("Y") * h)
                    segments.append(("M" if kind == "RelMoveTo" else "L", current))
                case "RelCubBezTo":
                    current = (g("X") * w, g("Y") * h)
                    segments.append(
                        (
                            "C",
                            (g("A") * w, g("B") * h),
                            (g("C") * w, g("D") * h),
                            current,
                        )
                    )
                case "RelQuadBezTo":
                    current = (g("X") * w, g("Y") * h)
                    segments.append(("Q", (g("A") * w, g("B") * h), current))
                case "ArcTo":
                    end, bow = (g("X"), g("Y")), g("A")
                    chord = math.dist(current, end)
                    if abs(bow) < 1e-9 or chord == 0:
                        segments.append(("L", end))
                    else:
                        r = (chord * chord / 4 + bow * bow) / (2 * abs(bow))
                        segments.append(
                            ("A", r, r, 0, int(abs(bow) > chord / 2), int(bow > 0), end)
                        )
                    current = end
                case "EllipticalArcTo" | "RelEllipticalArcTo":
                    # The Rel form gives X, Y, A, B as fractions of the shape's size.
                    sx, sy = (w, h) if kind == "RelEllipticalArcTo" else (1.0, 1.0)
                    end = (g("X") * sx, g("Y") * sy)
                    control = (g("A") * sx, g("B") * sy)
                    arc = elliptical_arc(current, end, control, g("C"), g("D"))
                    segments.append(("A", *arc, end) if arc else ("L", end))
                    current = end
                case "Ellipse":
                    cx, cy = g("X"), g("Y")
                    rx = math.dist((cx, cy), (g("A"), g("B")))
                    ry = math.dist((cx, cy), (g("C"), g("D")))
                    rotation = math.degrees(math.atan2(g("B") - cy, g("A") - cx))
                    p0, p1 = (g("A"), g("B")), (2 * cx - g("A"), 2 * cy - g("B"))
                    segments += [
                        ("M", p0),
                        ("A", rx, ry, rotation, 0, 1, p1),
                        ("A", rx, ry, rotation, 0, 1, p0),
                        ("Z",),
                    ]
                case "NURBSTo":
                    end = (g("X"), g("Y"))
                    segments += [
                        ("L", p)
                        for p in nurbs(current, end, _formula(row, "E"), size, steps)
                    ]
                    current = end
                case "PolylineTo":
                    found = re.search(r"POLYLINE\(([^)]*)\)", _formula(row, "A"))
                    if found:
                        values = [_num(v) for v in found.group(1).split(",")]
                        x_type, y_type, rest = values[0], values[1], values[2:]
                        for i in range(0, len(rest) - 1, 2):
                            x = rest[i] * w if x_type == 0 else rest[i]
                            y = rest[i + 1] * h if y_type == 0 else rest[i + 1]
                            segments.append(("L", (x, y)))
                    current = (g("X"), g("Y"))
                    segments.append(("L", current))
                case _:
                    tally(skipped, kind)
        if segments:
            yield (
                segments,
                _own(section, "NoFill") == "1",
                _own(section, "NoLine") == "1",
            )


def _transform(shape: ET.Element, size: Point) -> Transform:
    def g(name: str) -> float:
        return _num(_own(shape, name))

    return (
        g("PinX"),
        g("PinY"),
        g("LocPinX"),
        g("LocPinY"),
        g("Angle"),
        g("FlipX"),
        g("FlipY"),
        *size,
    )


def _apply(point: Point, t: Transform) -> Point:
    pin_x, pin_y, loc_x, loc_y, angle, flip_x, flip_y, w, h = t
    x, y = point
    x = w - x if flip_x else x
    y = h - y if flip_y else y
    x, y = x - loc_x, y - loc_y
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (pin_x + x * cos_a - y * sin_a, pin_y + x * sin_a + y * cos_a)


@dataclass(slots=True)
class _Drawing:
    """SVG elements in page inches, y up, and every point drawn, for the bounds."""

    elements: list[str] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)


def _draw(
    stencil: Stencil,
    shape: ET.Element,
    chain: list[Transform],
    rels: dict[str, str],
    part: str,
    steps: int,
    report: Report,
    out: _Drawing,
) -> None:
    """Draw a shape and its group children into `out`, in the master's frame."""
    size = (_num(_own(shape, "Width")), _num(_own(shape, "Height")))
    transforms = [*chain, _transform(shape, size)]

    drawn: list[Point] = []

    def place(point: Point) -> Point:
        for t in reversed(transforms):
            point = _apply(point, t)
        drawn.append(point)
        return point

    line = _colour(stencil.cell(shape, "LineColor")) or DEFAULT_LINE
    fill = _colour(stencil.cell(shape, "FillForegnd")) or DEFAULT_FILL
    weight = _num(stencil.cell(shape, "LineWeight"), 0.01) * POINTS_PER_INCH
    pattern = int(_num(stencil.cell(shape, "LinePattern"), 1))
    fill_pattern = int(_num(stencil.cell(shape, "FillPattern"), 1))
    # Visio fills a shape's overlapping sections even-odd, so one path per paint.
    paints: dict[str, list[str]] = {}
    for segments, no_fill, no_line in _geometry(
        shape, size, steps, report.skipped_rows
    ):
        drawn.clear()
        parts = []
        for segment in segments:
            op = segment[0]
            if op in ("M", "L"):
                x, y = place(segment[1])
                parts.append(f"{op}{x:.4f} {y:.4f}")
            elif op in ("C", "Q"):
                coords = " ".join(
                    f"{x:.4f} {y:.4f}" for x, y in (place(p) for p in segment[1:])
                )
                parts.append(f"{op}{coords}")
            elif op == "A":
                rx, ry, rotation, large, sweep, end = segment[1:]
                x, y = place(end)
                parts.append(
                    f"A{rx:.4f} {ry:.4f} {rotation:.2f} {large} {sweep} {x:.4f} {y:.4f}"
                )
            else:
                parts.append("Z")
        paint_fill = "none" if no_fill or fill_pattern == 0 else fill
        stroke = "none" if no_line or pattern == 0 else line
        # An unpainted section is a frame for something else: it draws nothing
        # and must not size the icon.
        if paint_fill == "none" and stroke == "none":
            continue
        out.points.extend(drawn)
        attrs = f'fill="{paint_fill}" stroke="{stroke}"'
        if stroke != "none":
            attrs += f' stroke-width="{weight / POINTS_PER_INCH:.4f}"'
            if pattern in PATTERN_DASH:
                dashes = " ".join(
                    f"{d / POINTS_PER_INCH * weight:.4f}" for d in PATTERN_DASH[pattern]
                )
                attrs += f' stroke-dasharray="{dashes}"'
        paints.setdefault(attrs, []).extend(parts)
    for attrs, parts in paints.items():
        out.elements.append(
            f'<path d="{" ".join(parts)}" {attrs} fill-rule="evenodd"/>'
        )

    foreign = shape.find(f"{V}ForeignData")
    if foreign is not None:
        _draw_foreign(stencil, foreign, size, place, rels, part, report, out)
    children = shape.find(f"{V}Shapes")
    for child in children.findall(f"{V}Shape") if children is not None else []:
        _draw(stencil, child, transforms, rels, part, steps, report, out)


def _draw_foreign(
    stencil: Stencil,
    foreign: ET.Element,
    size: Point,
    place: Callable[[Point], Point],
    rels: dict[str, str],
    part: str,
    report: Report,
    out: _Drawing,
) -> None:
    kind = foreign.get("ForeignType", "?")
    mime = IMAGE_TYPES.get(foreign.get("CompressionType", ""))
    rel = foreign.find(f"{V}Rel")
    target = rels.get(rel.get(R_ID, "")) if rel is not None else None
    if not (target and mime):
        tally(report.unrendered_foreign, kind)
        return
    data = base64.b64encode(stencil.zip.read(target)).decode()
    (x0, y0), (x1, y1) = place((0.0, 0.0)), place(size)
    out.points.extend([(x0, y0), (x1, y1)])
    left, bottom, width, height = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
    out.elements.append(
        f'<image x="{left:.4f}" y="{bottom:.4f}" width="{width:.4f}" height="{height:.4f}" '
        f'transform="translate(0 {2 * bottom + height:.4f}) scale(1 -1)" href="data:{mime};base64,{data}"/>'
    )


def icon(drawing: _Drawing, padding: float) -> dict[str, object]:
    """Return the Iconify entry for a drawing: flipped to y down, padded, sized to its bounds."""
    xs = [p[0] for p in drawing.points]
    ys = [p[1] for p in drawing.points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    width, height = (x1 - x0) + 2 * padding, (y1 - y0) + 2 * padding
    body = f'<g transform="translate({padding - x0:.4f} {y1 + padding:.4f}) scale(1 -1)">{"".join(drawing.elements)}</g>'
    return {"body": body, "width": round(width, 4), "height": round(height, 4)}


def stencil_icons(
    name: str,
    data: bytes,
    rules: list[naming.NameRule],
    steps: int,
    padding: float,
    icons: dict[str, object],
    report: Report,
) -> None:
    """Add every master in one stencil to `icons`, recording what was dropped."""
    stencil = Stencil(data)
    report.stencils += 1
    for master_id in stencil.masters:
        report.masters += 1
        master_name, shapes, rels, part = stencil.master(master_id)
        key = naming.key_for(f"{name}/{master_name}", rules)
        if not isinstance(key, str):
            continue
        if key in icons:
            report.duplicates.append(f"{name}/{master_name}")
            continue
        unrendered_before = sum(report.unrendered_foreign.values())
        try:
            drawing = _Drawing()
            for shape in shapes:
                _draw(stencil, shape, [], rels, part, steps, report, drawing)
        except (KeyError, ValueError, ET.ParseError) as error:
            report.failed.append(f"{name}/{master_name}: {error!r}")
            continue
        if not drawing.points:
            report.no_geometry.append(f"{name}/{master_name}")
            continue
        if sum(report.unrendered_foreign.values()) > unrendered_before:
            report.partial.append(f"{name}/{master_name}")
        icons[key] = icon(drawing, padding)


def build(download: Path, source: Source, limits: Limits) -> Built:
    """Build a source's Iconify pack, `<prefix>.json`, from every stencil in the download.

    The download is a stencil itself, or a directory, zip or tarball holding them.

    Raises:
        ValueError: The download is none of those.
    """
    files = re.compile(source.options["files"])
    rules = naming.rules(source.options["names"])
    steps = int(source.options["curve_steps"])
    padding = float(source.options["padding_in"])
    icons: dict[str, object] = {}
    report = Report()
    if files.search(download.name) and zipfile.is_zipfile(download):
        stencils: Iterator[archive.Member] = iter(
            [archive.Member(download.name, download.read_bytes())]
        )
    else:
        stencils = archive.members(download, files, limits.deck_bytes, limits.ignore)
    for member in stencils:
        stem = PurePosixPath(member.path).stem
        if member.data is None:
            report.failed.append(f"{member.path}: over {limits.deck_bytes} bytes")
            continue
        try:
            stencil_icons(stem, member.data, rules, steps, padding, icons, report)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
            report.failed.append(f"{member.path}: {error!r}")
    report.icons = len(icons)
    return Built(
        f"{source.prefix}.json",
        {"prefix": source.prefix, "icons": icons},
        asdict(report),
    )
