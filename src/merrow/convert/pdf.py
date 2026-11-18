"""PDF artwork to an Iconify pack: one icon per PDF, from its first page.

A page drawn only with paths becomes SVG paths. A page with anything else, such
as a shading, an image, text or a nested form, renders to a PNG inside the icon,
so the artwork is never redrawn by hand. Both then go through the SVG converter.
"""

import base64
import ctypes
import functools
import struct
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as raw

from merrow.convert import svg
from merrow.model import Built, Limits, Source

_SVG_NS = "http://www.w3.org/2000/svg"


def _colour(getter, obj) -> tuple[str, float] | None:  # noqa: ANN001 -- a PDFium C function
    """Return a colour as `#rrggbb` and its opacity, or None where PDFium has none."""
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if not getter(obj, r, g, b, a):
        return None
    return f"#{r.value:02x}{g.value:02x}{b.value:02x}", a.value / 255


def _path(obj, left: float, top: float) -> str:  # noqa: ANN001 -- a PDFium page object
    """Return one PDF path object as an SVG `<path>`, in page coordinates."""
    m = raw.FS_MATRIX()
    raw.FPDFPageObj_GetMatrix(obj, m)

    def point(x: float, y: float) -> str:
        page_x = m.a * x + m.c * y + m.e
        page_y = m.b * x + m.d * y + m.f
        return f"{page_x - left:.2f} {top - page_y:.2f}"

    steps, curve = [], []
    for index in range(raw.FPDFPath_CountSegments(obj)):
        segment = raw.FPDFPath_GetPathSegment(obj, index)
        x, y = ctypes.c_float(), ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(segment, x, y)
        kind = raw.FPDFPathSegment_GetType(segment)
        if kind == raw.FPDF_SEGMENT_BEZIERTO:
            curve.append(point(x.value, y.value))
            if len(curve) == 3:
                steps.append("C " + " ".join(curve))
                curve = []
        else:
            move = kind == raw.FPDF_SEGMENT_MOVETO
            steps.append(("M " if move else "L ") + point(x.value, y.value))
        if raw.FPDFPathSegment_GetClose(segment):
            steps.append("Z")

    mode, stroked = ctypes.c_int(), ctypes.c_int()
    raw.FPDFPath_GetDrawMode(obj, mode, stroked)
    attrs = {"d": " ".join(steps), "fill": "none"}
    fill = _colour(raw.FPDFPageObj_GetFillColor, obj)
    if mode.value != raw.FPDF_FILLMODE_NONE and fill:
        attrs["fill"] = fill[0]
        if fill[1] < 1:
            attrs["fill-opacity"] = f"{fill[1]:.3f}"
        if mode.value == raw.FPDF_FILLMODE_ALTERNATE:
            attrs["fill-rule"] = "evenodd"
    stroke = _colour(raw.FPDFPageObj_GetStrokeColor, obj)
    if stroked.value and stroke:
        width = ctypes.c_float()
        raw.FPDFPageObj_GetStrokeWidth(obj, width)
        scale = abs(m.a * m.d - m.b * m.c) ** 0.5
        attrs |= {"stroke": stroke[0], "stroke-width": f"{width.value * scale:.2f}"}
    return "<path " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


def _png(width: int, height: int, stride: int, rgba: bytes) -> bytes:
    """Return RGBA rows as a PNG file."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(
        b"\x00" + rgba[row * stride : row * stride + width * 4] for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def page_svg(data: bytes, raster_px: int) -> tuple[bytes, list[str]]:
    """Return a PDF's first page as SVG, and `rasterised` when it took a PNG.

    `raster_px` is the PNG's longest side.

    Raises:
        ValueError: The bytes aren't a PDF PDFium can read.
    """
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        raise ValueError(f"not a readable PDF: {error}") from error
    page = document[0]
    left, bottom, right, top = page.get_mediabox()
    width, height = right - left, top - bottom
    view = f'viewBox="0 0 {width:.2f} {height:.2f}"'
    objects = list(page.get_objects(max_depth=0))
    if objects and all(o.type == raw.FPDF_PAGEOBJ_PATH for o in objects):
        paths = "".join(_path(o.raw, left, top) for o in objects)
        return f'<svg xmlns="{_SVG_NS}" {view}>{paths}</svg>'.encode(), []
    scale = raster_px / max(width, height)
    bitmap = page.render(
        scale=scale, fill_color=(0, 0, 0, 0), rev_byteorder=True, may_draw_forms=True
    )
    png = _png(bitmap.width, bitmap.height, bitmap.stride, bytes(bitmap.buffer))
    href = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    image = f'<image width="{width:.2f}" height="{height:.2f}" href="{href}"/>'
    return f'<svg xmlns="{_SVG_NS}" {view}>{image}</svg>'.encode(), ["rasterised"]


def build(download: Path, source: Source, limits: Limits) -> Built:
    """Build a source's Iconify pack from its PDFs, `<prefix>.json`.

    Raises:
        ValueError: The download is not a PDF, directory, zip or tarball.
    """
    raster_px = int(source.options["raster_px"])
    return svg.build(
        download, source, limits, functools.partial(page_svg, raster_px=raster_px)
    )
