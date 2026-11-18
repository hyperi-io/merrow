"""PDF pages read back from ink: boxes, icons, labels and arrows drawn with PDFium."""

import ctypes
import io

import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest

from merrow.read import pdf

RULES = {
    "line_width": 3,
    "join": 3,
    "arrowhead": [3, 14],
    "snap": 8,
    "min_box": 10,
    "icon": [12, 120],
    "badge": 3,
    "label_gap": 12,
    "word_gap": 0.6,
    "line_gap": 1.0,
    "max_label_lines": 4,
    "skip_labels": [r"\d{1,2}"],
}
WIDTH, HEIGHT = 300, 200


class Page:
    """A page drawn in y-down points, the way the reader reports them."""

    def __init__(self, document: pdfium.PdfDocument) -> None:
        self.document = document
        self.page = document.new_page(WIDTH, HEIGHT)

    def _path(self, points, *, close, fill=None, stroke=None, dash=False):
        (x, y), *rest = points
        path = raw.FPDFPageObj_CreateNewPath(x, HEIGHT - y)
        for x, y in rest:
            raw.FPDFPath_LineTo(path, x, HEIGHT - y)
        if close:
            raw.FPDFPath_Close(path)
        if fill:
            raw.FPDFPageObj_SetFillColor(path, *fill, 255)
        if stroke:
            raw.FPDFPageObj_SetStrokeColor(path, *stroke, 255)
            raw.FPDFPageObj_SetStrokeWidth(path, 1.0)
        if dash:
            pattern = (ctypes.c_float * 2)(3.0, 2.0)
            raw.FPDFPageObj_SetDashArray(path, pattern, 2, 0.0)
        mode = raw.FPDF_FILLMODE_WINDING if fill else raw.FPDF_FILLMODE_NONE
        raw.FPDFPath_SetDrawMode(path, mode, bool(stroke))
        raw.FPDFPage_InsertObject(self.page.raw, path)

    def box(self, x, y, w, h, fill=(255, 255, 255), stroke=(0, 0, 0)):
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        self._path(corners, close=True, fill=fill, stroke=stroke)

    def text(self, x, y, words, size=8.0):
        run = raw.FPDFPageObj_NewTextObj(self.document.raw, b"Helvetica", size)
        chars = ctypes.create_string_buffer(f"{words}\x00".encode("utf-16-le"))
        raw.FPDFText_SetText(run, ctypes.cast(chars, ctypes.POINTER(ctypes.c_ushort)))
        raw.FPDFPageObj_Transform(run, 1, 0, 0, 1, x, HEIGHT - y - size)
        raw.FPDFPage_InsertObject(self.page.raw, run)

    def icon(self, x, y, side):
        image = raw.FPDFPageObj_NewImageObj(self.document.raw)
        bitmap = pdfium.PdfBitmap.new_native(4, 4, raw.FPDFBitmap_BGRA)
        bitmap.fill_rect((0, 128, 255, 255), 0, 0, 4, 4)
        raw.FPDFImageObj_SetBitmap(None, 0, image, bitmap.raw)
        raw.FPDFImageObj_SetMatrix(image, side, 0, 0, side, x, HEIGHT - y - side)
        raw.FPDFPage_InsertObject(self.page.raw, image)

    def line(self, *points, dash=False):
        self._path(list(points), close=False, stroke=(0, 0, 0), dash=dash)

    def head(self, tip, toward):
        """A filled triangle pointing at `tip`, coming from `toward`."""
        (x, y), (fx, fy) = tip, toward
        dx, dy = (x - fx) / abs(x - fx or y - fy), (y - fy) / abs(x - fx or y - fy)
        base = (x - 6 * dx, y - 6 * dy)
        wing = (-dy * 3, dx * 3)
        corners = [
            tip,
            (base[0] + wing[0], base[1] + wing[1]),
            (base[0] - wing[0], base[1] - wing[1]),
        ]
        self._path(corners, close=True, fill=(0, 0, 0))

    def outline(self, start, end, width=1.2):
        """A horizontal line drawn as a thin filled shape, as PowerPoint exports do."""
        (x0, y), (x1, _) = start, end
        corners = [
            (x0, y - width / 2),
            (x1, y - width / 2),
            (x1, y + width / 2),
            (x0, y + width / 2),
        ]
        self._path(corners, close=True, fill=(0, 0, 0))


def made(*draws) -> bytes:
    """A PDF with one page per drawing function."""
    document = pdfium.PdfDocument.new()
    for draw in draws:
        page = Page(document)
        draw(page)
        raw.FPDFPage_GenerateContent(page.page.raw)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def diagram(page: Page) -> None:
    """Region holds Web, App and an icon. Queue sits outside, behind a step marker."""
    page.box(10, 10, 200, 150, fill=None)
    page.text(16, 14, "Region")
    page.box(30, 40, 50, 24)
    page.text(38, 48, "Web")
    page.box(130, 40, 50, 24)
    page.text(138, 48, "App")
    page.icon(40, 100, 24)
    page.text(36, 128, "Store")
    page.text(36, 137, "object storage", size=6.0)
    page.box(240, 120, 50, 24)
    page.text(248, 128, "Queue")
    page.box(240, 20, 54, 80, fill=(230, 230, 230), stroke=None)
    for row in range(6):
        page.text(244, 24 + row * 12, f"Step {row} text")
    page.box(184, 124, 18, 18)
    page.text(190, 128, "1")
    page.text(100, 175, "Loose caption")
    page.line((80, 52), (124, 52))
    page.head((130, 52), (80, 52))
    page.line((155, 64), (155, 133), (184, 133))
    page.outline((202, 133), (234, 133))
    page.head((240, 133), (200, 133))
    page.line((52, 100), (52, 64), dash=True)
    page.line((90, 180), (120, 190))


def test_a_pdf_page_reads_into_a_graph():
    [page] = pdf.pages(made(diagram), RULES)
    graph = page.graph
    assert page.name == "1"
    nodes = {n.label: n for n in graph.nodes}
    assert set(nodes) == {"Web", "App", "Store", "Queue"}
    assert nodes["Store"].subtitle == "object storage", "a smaller second line"
    [region] = graph.groups
    assert region.label == "Region"
    assert {n.label for n in graph.nodes if n.group == region.id} == {
        "Web",
        "App",
        "Store",
    }
    named = {n.id: n.label for n in graph.nodes}
    edges = {(named[e.source], named[e.target]): e for e in graph.edges}
    assert set(edges) == {("Web", "App"), ("App", "Queue"), ("Store", "Web")}, (
        "stroked, outlined and through a step marker"
    )
    assert edges[("Store", "Web")].optional is True
    assert edges[("Web", "App")].optional is False
    assert any("6 lines of prose" in d for d in page.dropped)
    assert any("Loose caption" in d for d in page.dropped)
    assert any("not attached at both ends" in d for d in page.dropped)
    assert graph.problems() == []


def empty(page: Page) -> None:
    del page


def text_only(page: Page) -> None:
    page.text(20, 20, "Just a note")


@pytest.mark.parametrize(
    ("draw", "dropped"),
    [(empty, []), (text_only, ["text 'Just a note': belongs to no shape"])],
    ids=["empty_page", "text_only"],
)
def test_a_page_with_no_diagram_reads_empty(draw, dropped):
    [page] = pdf.pages(made(draw), RULES)
    assert (page.graph.nodes, page.graph.edges, page.graph.groups) == ([], [], [])
    assert page.dropped == dropped


def test_a_broken_pdf_is_named():
    with pytest.raises(ValueError, match="not a readable PDF"):
        pdf.pages(b"%PDF-1.7 nothing here", RULES)
