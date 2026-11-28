import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from merrow.read import pptx

NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
RULES = {"optional_dash": "dash,sysDash", "skip_labels": ["%[^%]+%", r"\d{1,2}"]}


def sp(sid, text, x, y, w, h, placeholder=False):
    ph = "<p:ph/>" if placeholder else ""
    body = (
        f"<p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody>" if text else ""
    )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="s{sid}"/><p:cNvSpPr/><p:nvPr>{ph}</p:nvPr></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm></p:spPr>{body}</p:sp>'
    )


def cxn(cid, start=None, end=None, dash=None):
    st = f'<a:stCxn id="{start}" idx="0"/>' if start else ""
    en = f'<a:endCxn id="{end}" idx="0"/>' if end else ""
    ln = f'<a:ln><a:prstDash val="{dash}"/></a:ln>' if dash else ""
    return (
        f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{cid}" name="c{cid}"/><p:cNvCxnSpPr>{st}{en}</p:cNvCxnSpPr><p:nvPr/></p:nvCxnSpPr>'
        f"<p:spPr>{ln}</p:spPr></p:cxnSp>"
    )


# A group whose children use their own coordinates, scaled 2x onto the slide.
GROUP = (
    '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="50" name="g"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="600" y="100"/><a:ext cx="200" cy="200"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr>'
    + sp(6, "Cache", 10, 10, 20, 20)
    + "</p:grpSp>"
)
SLIDE = (
    f"<p:sld {NS}><p:cSld><p:spTree>"
    + sp(2, "Title here", 0, 0, 100, 10, placeholder=True)
    + sp(3, "Region", 0, 50, 1000, 600)
    + sp(4, "API", 100, 100, 100, 50)
    + sp(5, "Database", 300, 100, 100, 50)
    + sp(7, "3", 120, 300, 10, 10)
    + sp(8, "", 400, 400, 10, 10)
    + GROUP
    + cxn(20, 4, 5)
    + cxn(21, 4, 6, dash="dash")
    + cxn(22, 4)
    + cxn(23, 4, 8)
    + "</p:spTree></p:cSld></p:sld>"
)


def test_a_slide_reads_into_a_graph_with_exact_edges():
    slide = pptx.read_slide(1, ET.fromstring(SLIDE), RULES)
    graph = slide.graph
    nodes = {n.label: n for n in graph.nodes}
    groups = {g.label: g for g in graph.groups}

    assert set(nodes) == {"API", "Database", "Cache"}
    assert set(groups) == {"Region"}
    assert nodes["API"].group == groups["Region"].id
    assert nodes["Cache"].group == groups["Region"].id, (
        "group child coordinates map onto the slide"
    )

    edges = {(e.source, e.target): e for e in graph.edges}
    assert set(edges) == {("4", "5"), ("4", "6")}
    assert edges[("4", "6")].optional is True
    assert edges[("4", "5")].optional is False

    dropped = " ".join(slide.dropped)
    assert "2: slide placeholder" in dropped
    assert "7: no text" in dropped, "a numbered step marker is skipped"
    assert "22: connector not glued" in dropped
    assert "23: connector glued to an unlabelled shape" in dropped
    assert graph.problems() == []


RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def package(parts: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as deck:
        for name, body in parts.items():
            deck.writestr(name, body)
    return out.getvalue()


def test_slides_come_back_in_the_order_the_deck_lists_them():
    parts = {
        "ppt/slides/slide1.xml": SLIDE.replace("Database", "Created first"),
        "ppt/slides/slide2.xml": SLIDE.replace("Database", "Created second"),
        "ppt/presentation.xml": (
            f"<p:presentation {NS} {R}><p:sldIdLst>"
            '<p:sldId id="1" r:id="rId2"/><p:sldId id="2" r:id="rId1"/>'
            "</p:sldIdLst></p:presentation>"
        ),
        "ppt/_rels/presentation.xml.rels": (
            f'<Relationships xmlns="{RELS}">'
            '<Relationship Id="rId1" Target="slides/slide1.xml"/>'
            '<Relationship Id="rId2" Target="slides/slide2.xml"/></Relationships>'
        ),
    }
    shown = [
        (d.name, {n.label for n in d.graph.nodes} & {"Created first", "Created second"})
        for d in pptx.slides(package(parts), RULES)
    ]
    assert shown == [("1", {"Created second"}), ("2", {"Created first"})]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"junk", "not a PPTX package"),
        (b"", "not a PPTX package"),
        (package({"ppt/slides/slide1.xml": "<p:sld"}), "not XML"),
        (
            package({"ppt/slides/slide1.xml": " " * 5_000_100}),
            "over the 5000000 byte limit",
        ),
    ],
    ids=["junk", "empty", "bad-slide", "too-big"],
)
def test_malformed_decks_are_a_value_error(data, message):
    with pytest.raises(ValueError, match=message):
        pptx.slides(data, RULES)
