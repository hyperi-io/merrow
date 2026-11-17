import base64
import zlib
from urllib.parse import quote

from merrow import write
from merrow.read import drawio

RULES = {
    "container": "container,swimlane,group",
    "optional": "dashed=1",
    "title": "text",
    "placeholder": "%[^%]+%",
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


def test_text_strips_html_into_lines():
    assert drawio.text(
        "&lt;div&gt;IBM&amp;nbsp;Cloud&lt;/div&gt;&lt;div&gt; VPC &lt;/div&gt;"
    ) == ["IBM Cloud", "VPC"]
