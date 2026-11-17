import dataclasses
import io
import zipfile

import pytest

from merrow.convert import pptx
from merrow.model import Source

A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"


def rels(*targets: str) -> str:
    items = "".join(
        f'<Relationship Id="rId{i}" Target="{t}"/>' for i, t in enumerate(targets, 1)
    )
    return f'<Relationships xmlns="{RELS}">{items}</Relationships>'


def box(name: str, line: str, dash: str | None = None) -> str:
    dash_xml = f'<a:prstDash val="{dash}"/>' if dash else ""
    return (
        f'<p:grpSp><p:sp><p:spPr><a:ln w="15875">{line}{dash_xml}</a:ln></p:spPr>'
        f'<p:txBody><a:p><a:r><a:rPr><a:solidFill><a:schemeClr val="tx1"/>'
        f"</a:solidFill></a:rPr><a:t>{name}</a:t></a:r></a:p></p:txBody></p:sp>"
        f'<p:pic><p:blipFill><a:blip r:embed="rId2"/></p:blipFill></p:pic></p:grpSp>'
    )


SOLID = '<a:solidFill><a:srgbClr val="8C4FFF"/></a:solidFill>'
SCHEME = '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'


def slide(*shapes: str, title: str) -> str:
    title_run = (
        f"<p:sp><p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>"
    )
    return f"<p:sld {A} {P} {R}><p:cSld><p:spTree>{title_run}{''.join(shapes)}</p:spTree></p:cSld></p:sld>"


def deck_bytes(groups_slide: str) -> bytes:
    theme = (
        f"<a:theme {A}><a:themeElements><a:clrScheme>"
        '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
        '<a:accent1><a:srgbClr val="00A4A6"/></a:accent1>'
        "</a:clrScheme></a:themeElements></a:theme>"
    )
    parts = {
        "ppt/presentation.xml": "<p/>",
        "ppt/slides/slide1.xml": slide(title="Contents: Groups"),
        "ppt/slides/slide2.xml": slide(title="Groups"),
        "ppt/slides/slide10.xml": groups_slide,
        "ppt/slides/_rels/slide10.xml.rels": rels(
            "../slideLayouts/slideLayout1.xml", "../media/image8.svg"
        ),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": rels(
            "../slideMasters/slideMaster1.xml"
        ),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": rels("../theme/theme2.xml"),
        # A decoy theme the slide doesn't use, listed first.
        "ppt/theme/theme1.xml": theme.replace("00A4A6", "FF0000"),
        "ppt/theme/theme2.xml": theme,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return out.getvalue()


GROUPS = slide(
    box("Virtual private cloud (VPC)", SOLID),
    box("Region", SCHEME, dash="sysDash"),
    box("Region", SCHEME, dash="sysDash"),
    box("A caption long enough that it can't be a group name at all", SOLID),
    title="Groups\t1/5",
)


def groups_source(decks, title=r"^Groups\s+1/\d+"):
    return Source(
        "demo-groups", "pptx", "aws", options={"decks": decks, "slide_title": title}
    )


def test_groups_come_from_the_titled_slide_with_the_slides_own_theme(tmp_path, limits):
    source = tmp_path / "toolkit.zip"
    with zipfile.ZipFile(source, "w") as outer:
        outer.writestr("AWS-Deck_For-Light-BG_0731.pptx", deck_bytes(GROUPS))
        outer.writestr("__MACOSX/._AWS-Deck_For-Light-BG_0731.pptx", b"junk")
    built = pptx.build(
        source, groups_source({"light": r"For-Light-BG_\d+\.pptx$"}), limits
    )
    assert built.name == "aws-groups.json"
    styles = {style["name"]: style for style in built.data["light"]}
    assert list(styles) == ["Virtual private cloud (VPC)", "Region"]
    vpc, region = styles["Virtual private cloud (VPC)"], styles["Region"]
    assert vpc["stroke"] == "#8C4FFF"
    assert vpc["dash"] == "solid"
    assert vpc["stroke_width_pt"] == 1.25
    assert vpc["label_colour"] == "#000000"
    assert vpc["icon_media"] == "ppt/media/image8.svg"
    assert vpc["key"] == "virtual-private-cloud-vpc"
    assert region["stroke"] == "#00A4A6"
    assert region["dash"] == "sysDash"


def test_a_bare_deck_is_read_directly(tmp_path, limits):
    source = tmp_path / "deck.pptx"
    source.write_bytes(deck_bytes(GROUPS))
    built = pptx.build(source, groups_source({"light": "x"}), limits)
    assert built.report == {"light": 2}


@pytest.mark.parametrize(
    ("decks", "title", "max_bytes", "error", "message"),
    [
        ({"dark": r"For-Dark-BG"}, r"^Groups\s+1/", 10**6, LookupError, "no deck"),
        ({"light": r"For-Light-BG"}, r"^Nothing$", 10**6, LookupError, "no slide"),
        ({"light": r"For-Light-BG"}, r"^Groups\s+1/", 10, ValueError, "over 10 bytes"),
    ],
    ids=["missing-deck", "missing-slide", "oversized-deck"],
)
def test_build_fails_loudly(tmp_path, limits, decks, title, max_bytes, error, message):
    source = tmp_path / "toolkit.zip"
    with zipfile.ZipFile(source, "w") as outer:
        outer.writestr("Deck_For-Light-BG_1.pptx", deck_bytes(GROUPS))
        outer.writestr("other.txt", "x")
    with pytest.raises(error, match=message):
        pptx.build(
            source,
            groups_source(decks, title),
            dataclasses.replace(limits, deck_bytes=max_bytes),
        )
