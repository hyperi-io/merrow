import base64
import zlib
from urllib.parse import quote

import pytest

from merrow import write
from merrow.read import drawio

RULES = {
    "container": "container,swimlane,group",
    "optional": "dashed=1",
    "title": "text",
    "skip_labels": ["%[^%]+%"],
}


def cell(cid, parent="1", value="", style="", x=0, y=0, w=10, h=10, **extra):
    attrs = " ".join(f'{k}="{v}"' for k, v in extra.items())
    geo = f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
    return f'<mxCell id="{cid}" parent="{parent}" value="{value}" style="{style}" {attrs}>{geo}</mxCell>'


MODEL = (
    "<mxGraphModel><root>"
    '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + cell("vpc", value="VPC", style="container=1;", vertex="1", w=400, h=300)
    + cell("zone", style="rounded=0;", vertex="1", x=10, y=10, w=200, h=200)
    + cell(
        "zone-title",
        parent="zone",
        value="Zone A",
        style="text;html=1;",
        vertex="1",
        x=5,
        y=5,
        w=60,
        h=20,
    )
    + cell(
        "svc",
        parent="zone",
        value="&lt;b&gt;Service&lt;/b&gt;&lt;br&gt;handles requests",
        vertex="1",
        x=50,
        y=50,
    )
    # Laid over the zone without being parented to it.
    + cell("db", value="Database", vertex="1", x=100, y=150, w=20, h=20)
    + cell("hint", value="%Element-Name%", vertex="1", x=600, y=600)
    + cell("cache", value="Cache", vertex="1", x=700, y=700)
    + cell("e1", value="reads", edge="1", source="svc", target="db")
    + cell("e2", style="dashed=1;", edge="1", source="svc", target="cache")
    + cell("e3", edge="1", source="svc", target="nowhere")
    + "</root></mxGraphModel>"
)


def compressed_file(model: str) -> bytes:
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = deflate.compress(quote(model).encode()) + deflate.flush()
    body = base64.b64encode(packed).decode()
    return f'<mxfile><diagram name="Arch">{body}</diagram></mxfile>'.encode()


def test_a_compressed_page_reads_into_a_nested_graph():
    [page] = drawio.pages(compressed_file(MODEL), RULES)
    graph = page.graph
    assert page.name == "Arch"
    groups = {g.id: g for g in graph.groups}
    nodes = {n.id: n for n in graph.nodes}

    assert groups["zone"].label == "Zone A", (
        "an untitled container takes its text cell's title"
    )
    assert "zone-title" not in nodes
    assert groups["zone"].parent == "vpc", "nested by bounds when not parented"
    assert nodes["svc"].label == "Service"
    assert nodes["svc"].subtitle == "handles requests"
    assert nodes["svc"].group == "zone"
    assert nodes["db"].group == "zone", "laid over the zone, so it sits in it"
    assert "hint" not in nodes, "a template placeholder is no label"

    edges = {(e.source, e.target): e for e in graph.edges}
    assert edges[("svc", "db")].label == "reads"
    assert edges[("svc", "cache")].optional is True
    assert any("e3" in d for d in page.dropped), "a dangling edge is reported"
    assert graph.problems() == []
    assert "svc -.-> cache" in write.flowchart(graph, "LR")


def test_an_uncompressed_model_reads_too():
    [page] = drawio.pages(MODEL.encode(), RULES)
    assert {n.label for n in page.graph.nodes} == {"Service", "Database", "Cache"}


@pytest.mark.parametrize(
    ("value", "lines"),
    [
        ("<div>IBM&nbsp;Cloud</div><div> VPC </div>", ["IBM Cloud", "VPC"]),
        ("Vec&lt;T&gt; and a&lt;b", ["Vec<T> and a<b"]),
        ("one<br/>two<p>three</p>", ["one", "two", "three"]),
    ],
    ids=["divs", "escaped-angle-brackets", "breaks"],
)
def test_text_strips_html_into_lines(value, lines):
    assert drawio.text(value) == lines


def model(*cells: str) -> bytes:
    return (
        '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        + "".join(cells)
        + "</root></mxGraphModel>"
    ).encode()


def test_edges_that_name_each_other_as_parent_do_not_hang_the_read():
    loop = [
        '<mxCell id="e1" edge="1" parent="e2"/>',
        '<mxCell id="e2" edge="1" parent="e1"/>',
        cell("v", parent="e1", value="Service", vertex="1"),
        cell("self", parent="self", value="Self", vertex="1"),
    ]
    [page] = drawio.pages(model(*loop), RULES)
    assert {n.label for n in page.graph.nodes} == {"Service"}
    assert [g.label for g in page.graph.groups] == ["Self"]
    assert page.graph.groups[0].parent is None


def packed(raw: bytes) -> bytes:
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = base64.b64encode(deflate.compress(raw) + deflate.flush())
    return b'<mxfile><diagram name="p">' + body + b"</diagram></mxfile>"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"junk", "not draw.io XML"),
        (b"", "not draw.io XML"),
        (b"<svg/>", "not a draw.io file"),
        (b"<mxfile><diagram>!!!</diagram></mxfile>", "page is corrupt"),
        (packed(b"not url-encoded xml <"), "page is corrupt"),
        (packed(b" " * 10_000), "inflates past 1000 bytes"),
        (model(cell("v", vertex="1", x="wide")), "not a number"),
    ],
    ids=["junk", "empty", "other-xml", "bad-base64", "bad-xml", "bomb", "bad-geometry"],
)
def test_malformed_input_is_a_value_error(monkeypatch, data, message):
    monkeypatch.setattr(drawio, "MAX_PAGE_BYTES", 1000)
    with pytest.raises(ValueError, match=message):
        drawio.pages(data, RULES)
