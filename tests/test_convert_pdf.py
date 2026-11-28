"""PDF artwork to icons: plain paths stay vector, anything else becomes a PNG."""

import ctypes
import io

import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest

from merrow.convert import pdf
from merrow.model import Source


def made_pdf(
    text: bool, rotation: int = 0, box: tuple[int, int, int, int] | None = None
) -> bytes:
    """A 40x20 pt page with an orange square, and a word of text when `text`."""
    document = pdfium.PdfDocument.new()
    page = document.new_page(40, 20)
    page.set_rotation(rotation)
    if box:
        page.set_mediabox(*box)
    square = raw.FPDFPageObj_CreateNewPath(2, 2)
    for x, y in ((18, 2), (18, 18), (2, 18)):
        raw.FPDFPath_LineTo(square, x, y)
    raw.FPDFPath_Close(square)
    raw.FPDFPageObj_SetFillColor(square, 255, 153, 0, 255)
    raw.FPDFPath_SetDrawMode(square, raw.FPDF_FILLMODE_WINDING, False)
    raw.FPDFPage_InsertObject(page.raw, square)
    if text:
        word = raw.FPDFPageObj_NewTextObj(document.raw, b"Helvetica", 8.0)
        chars = ctypes.create_string_buffer("Hi\x00".encode("utf-16-le"))
        raw.FPDFText_SetText(word, ctypes.cast(chars, ctypes.POINTER(ctypes.c_ushort)))
        raw.FPDFPage_InsertObject(page.raw, word)
    raw.FPDFPage_GenerateContent(page.raw)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("text", "body_has", "notes"),
    [
        (False, ['<path d="M 2.00 18.00 L 18.00 18.00', 'fill="#ff9900"'], []),
        (
            True,
            ['<image width="40.00" height="20.00"', "data:image/png;base64,"],
            ["rasterised"],
        ),
    ],
    ids=["paths_stay_vector", "text_rasterises"],
)
def test_a_pdf_page_becomes_svg(text, body_has, notes):
    data, found = pdf.page_svg(made_pdf(text), 64)
    body = data.decode()
    assert body.startswith(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40.00 20.00">'
    )
    for part in body_has:
        assert part in body
    assert found == notes


def test_a_broken_pdf_is_named():
    with pytest.raises(ValueError, match="not a readable PDF"):
        pdf.page_svg(b"%PDF-1.7 nothing here", 64)


def test_a_single_pdf_download_builds_a_pack(tmp_path, limits):
    path = tmp_path / "kafka.pdf"
    path.write_bytes(made_pdf(False))
    names = [{"match": r"^([a-z]+)\.pdf$", "key": r"\1", "title": r"\1"}]
    options = {"files": r"\.pdf$", "names": names, "raster_px": 64, "size": 96}
    built = pdf.build(path, Source("asf-kafka", "pdf", "asf", options=options), limits)
    assert built.name == "asf.json"
    assert list(built.data["icons"]) == ["kafka"]
    assert built.data["titles"] == {"kafka": "Kafka"}
    assert built.report["failed"] == []
    icon = built.data["icons"]["kafka"]
    assert (icon["width"], icon["height"]) == (96, 96), "a 40x20 page squared to 96"
    assert icon["body"].startswith('<g transform="translate(0 24) scale(2.4)">')


@pytest.mark.parametrize(
    ("made", "message"),
    [
        (lambda: made_pdf(False, box=(0, 0, 0, 0)), "no area"),
        (lambda: b"", "not a readable PDF"),
    ],
    ids=["zero-area", "empty"],
)
def test_a_pdf_that_cannot_be_an_icon_is_refused(made, message):
    with pytest.raises(ValueError, match=message):
        pdf.page_svg(made(), 64)


def test_a_rotated_page_keeps_its_turned_shape():
    data, notes = pdf.page_svg(made_pdf(False, rotation=90), 64)
    assert 'viewBox="0 0 20.00 40.00"' in data.decode()
    assert notes == ["rasterised"]
