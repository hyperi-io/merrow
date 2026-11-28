import io
import zipfile

import pytest

from merrow.read import visio

V = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
RULES = {
    "connector_masters": "connector",
    "snap_in": 0.15,
    "optional_patterns": "2,3",
    "skip_labels": [r"\d{1,2}"],
}


def cells(**values: object) -> str:
    return "".join(f'<Cell N="{k}" V="{v}"/>' for k, v in values.items())


def box(sid: int, text: str, x: float, y: float, w: float, h: float) -> str:
    geometry = cells(
        PinX=x + w / 2, PinY=y + h / 2, LocPinX=w / 2, LocPinY=h / 2, Width=w, Height=h
    )
    return f'<Shape ID="{sid}">{geometry}<Text>{text}</Text></Shape>'


def line(sid: int, begin: tuple, end: tuple, pattern: int = 1) -> str:
    ends = cells(
        BeginX=begin[0], BeginY=begin[1], EndX=end[0], EndY=end[1], LinePattern=pattern
    )
    return f'<Shape ID="{sid}">{ends}</Shape>'


PAGE = (
    f"<PageContents {V}><Shapes>"
    + box(1, "Region", 0, 0, 10, 8)
    + box(2, "Web", 1, 1, 2, 1)
    + box(3, "App", 5, 1, 2, 1)
    + box(4, "Queue", 1, 5, 2, 1)
    + box(5, "7", 8, 6, 0.5, 0.5)
    + line(10, (3, 1.5), (5, 1.5))
    + line(11, (5.05, 1.5), (2, 5.1), pattern=2)
    + line(12, (20, 20), (30, 30))
    + "</Shapes><Connects>"
    '<Connect FromSheet="10" FromCell="BeginX" ToSheet="2"/>'
    '<Connect FromSheet="10" FromCell="EndX" ToSheet="3"/>'
    "</Connects></PageContents>"
)


def drawing_bytes() -> bytes:
    parts = {
        "visio/document.xml": f"<VisioDocument {V}/>",
        "visio/pages/pages.xml": f'<Pages {V} {R}><Page NameU="Logical"><Rel r:id="rId1"/></Page></Pages>',
        "visio/pages/_rels/pages.xml.rels": f'<Relationships xmlns="{RELS}"><Relationship Id="rId1" Target="page1.xml"/></Relationships>',
        "visio/pages/page1.xml": PAGE,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        for name, body in parts.items():
            package.writestr(name, body)
    return out.getvalue()


def test_a_visio_page_reads_into_a_graph():
    [page] = visio.pages(drawing_bytes(), RULES)
    graph = page.graph
    assert page.name == "Logical"
    nodes = {n.label: n for n in graph.nodes}
    assert set(nodes) == {"Web", "App", "Queue"}
    assert [g.label for g in graph.groups] == ["Region"]
    assert all(n.group == "1" for n in nodes.values())
    edges = {(e.source, e.target): e for e in graph.edges}
    assert set(edges) == {("2", "3"), ("3", "4")}, "glued, then snapped by position"
    assert edges[("3", "4")].optional is True
    assert any(d.startswith("12:") for d in page.dropped), (
        "a connector touching nothing is reported"
    )
    assert any(d.startswith("5:") for d in page.dropped), (
        "a numbered marker is no label"
    )
    assert graph.problems() == []


def zipped(parts: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        for name, body in parts.items():
            package.writestr(name, body)
    return out.getvalue()


DOCUMENT = {"visio/document.xml": f"<VisioDocument {V}/>"}
PAGES = f'<Pages {V} {R}><Page NameU="P"><Rel r:id="rId1"/></Page></Pages>'


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"junk", "not a Visio package"),
        (b"", "not a Visio package"),
        (zipped({"readme.txt": "x"}), "no part"),
        (zipped({"visio/document.xml": "<VisioDocument"}), "not XML"),
        (zipped({**DOCUMENT, "visio/pages/pages.xml": "<Pages"}), "not XML"),
        (
            zipped(
                {
                    **DOCUMENT,
                    "visio/pages/pages.xml": PAGES,
                    "visio/pages/_rels/pages.xml.rels": f'<Relationships xmlns="{RELS}">'
                    '<Relationship Id="rId1" Target="gone.xml"/></Relationships>',
                }
            ),
            "no part",
        ),
    ],
    ids=["junk", "empty", "no-document", "bad-document", "bad-pages", "missing-page"],
)
def test_malformed_packages_are_a_value_error(data, message):
    with pytest.raises(ValueError, match=message):
        visio.pages(data, RULES)
