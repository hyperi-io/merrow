import io
import zipfile

import pytest

from merrow.convert import opc, visio
from merrow.model import Source

V = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"


def cells(**values: object) -> str:
    return "".join(f'<Cell N="{name}" V="{value}"/>' for name, value in values.items())


def shape(body: str, **values: object) -> str:
    size = {
        "Width": 1,
        "Height": 1,
        "PinX": 0.5,
        "PinY": 0.5,
        "LocPinX": 0.5,
        "LocPinY": 0.5,
    }
    return f'<Shape ID="1" LineStyle="3">{cells(**{**size, **values})}{body}</Shape>'


def geometry(rows: str, **flags: object) -> str:
    return f'<Section N="Geometry">{cells(**flags)}{rows}</Section>'


SQUARE = geometry(
    '<Row T="MoveTo">' + cells(X=0, Y=0) + "</Row>"
    '<Row T="LineTo">' + cells(X=1, Y=0) + "</Row>"
    '<Row T="LineTo">' + cells(X=1, Y=1) + "</Row>"
    '<Row T="LineTo">' + cells(X=0, Y=0) + "</Row>"
)
REL_ARC = geometry(
    '<Row T="RelMoveTo">' + cells(X=0, Y=0.5) + "</Row>"
    '<Row T="RelEllipticalArcTo">' + cells(X=1, Y=0.5, A=0.5, B=1, C=0, D=1) + "</Row>"
)
INVISIBLE = geometry(
    '<Row T="MoveTo">'
    + cells(X=0, Y=0)
    + '</Row><Row T="LineTo">'
    + cells(X=2, Y=2)
    + "</Row>",
    NoFill=1,
    NoLine=1,
)
EMF = '<ForeignData ForeignType="EnhMetaFile"><Rel r:id="rId1"/></ForeignData>'

MASTERS = {
    "Square": shape(SQUARE),
    "Arc": shape(REL_ARC),
    "Picture only": shape(INVISIBLE + EMF),
    "Box with picture": shape(SQUARE + EMF),
}


def stencil_bytes() -> bytes:
    style = (
        f"<VisioDocument {V}><StyleSheets>"
        '<StyleSheet ID="3" LineStyle="6"/>'
        f'<StyleSheet ID="6">{cells(LineColor="#8c4fff", LineWeight=0.01)}</StyleSheet>'
        "</StyleSheets></VisioDocument>"
    )
    index = "".join(
        f'<Master ID="{n}" NameU="{name}"><Rel r:id="rId{n}"/></Master>'
        for n, name in enumerate(MASTERS, 1)
    )
    parts = {
        "visio/document.xml": style,
        "visio/masters/masters.xml": f"<Masters {V} {R}>{index}</Masters>",
        "visio/masters/_rels/masters.xml.rels": f'<Relationships xmlns="{RELS}">'
        + "".join(
            f'<Relationship Id="rId{n}" Target="master{n}.xml"/>'
            for n in range(1, len(MASTERS) + 1)
        )
        + "</Relationships>",
    }
    for n, body in enumerate(MASTERS.values(), 1):
        parts[f"visio/masters/master{n}.xml"] = (
            f"<MasterContents {V} {R}><Shapes>{body}</Shapes></MasterContents>"
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        for name, body in parts.items():
            package.writestr(name, body)
    return out.getvalue()


def source(**options: object) -> Source:
    defaults = {
        "files": r"\.vssx$",
        "names": [{"match": r"^[^/]+/(.+)$", "key": r"\1"}],
        "curve_steps": 8,
        "padding_in": 0.02,
    }
    return Source("demo", "vssx", "demo", options={**defaults, **options})


@pytest.mark.parametrize(
    "wrapped", [False, True], ids=["bare-stencil", "stencil-in-zip"]
)
def test_masters_become_icons_and_nothing_is_dropped_silently(
    tmp_path, limits, wrapped
):
    data = stencil_bytes()
    if wrapped:
        download = tmp_path / "pack.zip"
        with zipfile.ZipFile(download, "w") as outer:
            outer.writestr("icons/Demo.vssx", data)
            outer.writestr("__MACOSX/icons/._Demo.vssx", b"junk")
    else:
        download = tmp_path / "Demo.vssx"
        download.write_bytes(data)

    built = visio.build(download, source(), limits)

    icons = built.data["icons"]
    assert sorted(icons) == ["arc", "box-with-picture", "square"]
    assert 'stroke="#8C4FFF"' in icons["square"]["body"], (
        "line colour comes through the style chain"
    )
    assert icons["square"]["width"] == pytest.approx(1.04)
    assert "A0.5000 0.5000 " in icons["arc"]["body"], (
        "a half circle across 1 in has radius 0.5"
    )
    assert built.report["stencils"] == 1
    assert built.report["masters"] == 4
    assert built.report["no_geometry"] == ["Demo/Picture only"]
    assert built.report["partial"] == ["Demo/Box with picture"]
    assert built.report["unrendered_foreign"] == {"EnhMetaFile": 2}
    assert built.report["skipped_rows"] == {}


def test_a_name_rule_can_skip_masters(tmp_path, limits):
    download = tmp_path / "Demo.vssx"
    download.write_bytes(stencil_bytes())
    rules = [{"match": "/Arc$", "key": None}, {"match": r"^[^/]+/(.+)$", "key": r"\1"}]
    built = visio.build(download, source(names=rules), limits)
    assert "arc" not in built.data["icons"]


def test_a_broken_stencil_is_reported_not_raised(tmp_path, limits):
    download = tmp_path / "pack.zip"
    with zipfile.ZipFile(download, "w") as outer:
        outer.writestr("Broken.vssx", b"not a zip")
    built = visio.build(download, source(), limits)
    assert built.data["icons"] == {}
    assert built.report["failed"][0].startswith("Broken.vssx")


@pytest.mark.parametrize(
    ("part", "target", "resolved"),
    [
        ("visio/masters/master1.xml", "../media/image1.png", "visio/media/image1.png"),
        ("visio/masters/masters.xml", "master3.xml", "visio/masters/master3.xml"),
        ("ppt/slides/slide1.xml", "/ppt/media/a.svg", "ppt/media/a.svg"),
        ("ppt/slides/slide1.xml", "../../../x.xml", "x.xml"),
    ],
    ids=["parent", "sibling", "absolute", "past-root"],
)
def test_relationship_targets_resolve_inside_the_package(part, target, resolved):
    assert opc.resolve(part, target) == resolved
