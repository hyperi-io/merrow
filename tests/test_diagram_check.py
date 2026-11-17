# Project:   merrow
# File:      tests/test_diagram_check.py
# Purpose:   Unit tests for the source pass, page parsing and verdicts of merrow.lint.diagram_check
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""The diagram checker's source pass, page parsing and layout verdicts.

The render pass needs Chrome and the pinned Mermaid bundle, so it runs by hand,
not here.
"""

import re
from pathlib import Path

import pytest

from merrow import config, profile
from merrow.lint import diagram_check as dc

PROFILE = profile.load(config.load(), "house")
FLOW_FRONT = PROFILE.fronts["flowchart"]
OTHER_FRONT = PROFILE.fronts["other"]
ROOT = Path(__file__).resolve().parents[1]
STANDARD_PATH = ROOT / "style" / "diagrams.md"
STANDARD = STANDARD_PATH.read_text(encoding="utf-8")
_COLOUR = STANDARD.split("\n## Colour\n", 1)[1].split("\n## ", 1)[0]
CLASS_LINES = frozenset(
    line.strip()
    for line in _COLOUR.splitlines()
    if line.strip().startswith("classDef ")
)
DEFAULT = "classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A"
GOOD = f"""flowchart LR
    accTitle: L2 Services -- DFE
    accDescr: Sources publish to a topic and the loader writes tables.
    sources["Sources"] -->|events| topic[("Topic")]
    {DEFAULT}
"""
CAPTION = "*Figure 2. L2 Services -- DFE.* Up: [L1 Context -- DFE](../overview.md)."
MEASURED = {
    "ok": True,
    "width": 900,
    "height": 300,
    "nodes": 6,
    "groups": 1,
    "edges": 5,
    "busiest": 3,
    "busiest_name": "Loader",
    "crossings": [],
    "through": [],
    "overlaps": [],
    "skips": [],
    "backward": [],
}


def _problems(
    source: str, intro: str | None = None, caption: str | None = None
) -> list[str]:
    return dc.source_problems(
        dc.Block("page.md:1", source, intro, caption), CLASS_LINES, PROFILE
    )


def test_the_standard_lists_its_eight_class_lines():
    assert len(CLASS_LINES) == 8
    assert DEFAULT in CLASS_LINES


def test_the_script_carries_the_standards_class_lines():
    assert dc.CLASS_LINES == CLASS_LINES


def test_the_render_bundle_is_the_version_merrows_lock_pins():
    lock = (ROOT / "src" / "merrow" / "node" / "package-lock.json").read_text(
        encoding="utf-8"
    )
    assert (
        f'"node_modules/mermaid": {{\n      "version": "{dc.mermaid_version()}"' in lock
    )


def test_every_template_in_the_standard_passes_the_source_pass():
    blocks, page = dc.page_blocks(STANDARD_PATH)
    assert page == []
    assert len(blocks) == 8
    assert {
        block.name: dc.source_problems(block, CLASS_LINES, PROFILE) for block in blocks
    } == {block.name: [] for block in blocks}


@pytest.mark.parametrize(
    ("row", "limit"),
    [
        ("Proportion", dc.MIN_RATIO),
        ("Rendered height", dc.MAX_HEIGHT),
        ("Natural width (SVG `viewBox`)", dc.MAX_WIDTH),
        ("Nodes", dc.MAX_NODES),
        ("Subgraphs", dc.MAX_SUBGRAPHS),
        ("Arrows", dc.EXTRA_ARROWS),
        ("Arrows on one node", dc.MAX_NODE_ARROWS),
    ],
)
def test_a_limit_matches_the_standards_layout_table(row, limit):
    cell = re.search(rf"^\| {re.escape(row)} \| (.+?) \|$", STANDARD, re.MULTILINE)
    assert cell, f"the Layout table has no `{row}` row"
    assert float(re.search(r"\d+(?:\.\d+)?", cell.group(1)).group()) == limit


@pytest.mark.parametrize(
    ("phrase", "limit"),
    [
        (r"(\d+) colour classes or fewer", dc.MAX_COLOUR_CLASSES),
        (r"(\d+) participants or fewer", dc.MAX_PARTICIPANTS),
    ],
)
def test_a_limit_matches_the_standards_prose(phrase, limit):
    assert int(re.search(phrase, STANDARD).group(1)) == limit


@pytest.mark.parametrize(
    "caption",
    [CAPTION, CAPTION.replace("*", "_")],
    ids=["asterisk", "prettier-underscore"],
)
def test_a_diagram_to_the_standard_has_no_source_problems(caption):
    assert (
        _problems(
            GOOD,
            "Every event reaches DFE's tables through one topic and the loader.",
            caption,
        )
        == []
    )


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ("flowchart LR", "graph LR", "R2 `graph`"),
        ("flowchart LR", "flowchart TD", "R2 direction `TD`"),
        ("flowchart LR", "flowchart TB", "a vertical chain"),
        ("flowchart LR", "gantt", "`gantt` is not one of the five"),
        ("flowchart LR", "stateDiagram-v2", "needs `direction LR`"),
        ("    accTitle: L2 Services -- DFE\n", "", "R7 no `accTitle`"),
        ("L2 Services -- DFE", "The services of DFE", "R8 `accTitle`"),
        ("L2 Services -- DFE", "L2 Containers -- DFE", "R8 `accTitle`"),
        (
            "    accDescr: Sources publish to a topic and the loader writes tables.\n",
            "",
            "R7 no `accDescr`",
        ),
        (
            "flowchart LR",
            "%%{init: {'theme': 'forest'}}%%\nflowchart LR",
            "R9 an init directive",
        ),
        (DEFAULT, f"style sources fill:#f00\n    {DEFAULT}", "R9 `style`"),
        (
            DEFAULT,
            f'click sources href "https://example.com"\n    {DEFAULT}',
            "R9 `style`",
        ),
        ("-->|events|", "==>", "a thick arrow"),
        ("-->|events|", "<-->", "a double-headed arrow"),
        ('sources["Sources"]', 'sources(("Sources"))', "R6 an outline"),
        (
            'sources["Sources"]',
            'sources@{ shape: hex, label: "Sources" }',
            "R6 an outline",
        ),
        ('sources["Sources"]', 'sources("Sources")', "R6 an outline"),
        ('sources["Sources"]', "sources(Sources)", "R6 an outline"),
        ('sources["Sources"]', 'sources>"Sources"]', "R6 an outline"),
        (DEFAULT, f"class sources core\n    {DEFAULT}", "R5 class `core` is applied"),
        ("#64748B", "#64748C", "R5 a class line differs"),
        (DEFAULT, "", "R5 the `default` class line is missing"),
        ('sources["Sources"]', 'class["Sources"]', "a reserved word as a node id"),
        ('sources["Sources"]', 'sources["Env &#123;x&#125;"]', "an HTML entity"),
        (DEFAULT, "\n    ".join(sorted(CLASS_LINES)), "R5 6 colour classes"),
    ],
)
def test_a_source_fault_is_named(old, new, said):
    assert old in GOOD
    found = _problems(GOOD.replace(old, new))
    assert any(said in problem for problem in found), found


@pytest.mark.parametrize(
    "label",
    ['sources["a == b"]', 'sources["f((x)) <--> g{{y}}"]', 'sources["style guide"]'],
    ids=["equals", "brackets", "a_word_that_is_a_keyword"],
)
def test_quoted_label_text_is_never_read_as_syntax(label):
    assert _problems(GOOD.replace('sources["Sources"]', label)) == []


_HOUSE = STANDARD.split("\n## House style\n", 1)[1].split("\n## ", 1)[0]
_HOUSE_FENCES = re.findall(
    r"^```(?:yaml|text)\n(.*?)^```$", _HOUSE, re.MULTILINE | re.DOTALL
)
BOUNDARY = f"style edge {PROFILE.boundary}"
HOUSE = (
    FLOW_FRONT
    + """
flowchart LR
    accTitle: L2 Services -- DFE
    accDescr: The receiver publishes to a topic and the loader writes tables.
    subgraph edge["Edge"]
        receiver("<b>dfe-receiver</b><br/><span>HTTP intake</span>")
    end
    receiver -->|events| topic[("<b>Kafka</b>")]
    class receiver ingest
    class topic bus
"""
    + "".join(f"  {line}\n" for line in PROFILE.class_lines)
    + f"  {BOUNDARY}\n"
)
OTHER = (
    OTHER_FRONT
    + "\nsequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    a->>b: Call\n"
)


def test_the_standard_shows_the_house_profiles_generated_blocks():
    flow_front, other_front, classes = _HOUSE_FENCES
    assert flow_front.rstrip("\n") == FLOW_FRONT
    assert other_front.rstrip("\n") == OTHER_FRONT
    assert frozenset(line.strip() for line in classes.splitlines()) == frozenset(
        PROFILE.class_lines
    )
    assert PROFILE.boundary in _HOUSE


@pytest.mark.parametrize("source", [HOUSE, OTHER], ids=["flowchart", "sequence"])
def test_a_house_diagram_has_no_source_problems(source):
    assert _problems(source) == []


@pytest.mark.parametrize(
    ("source", "said"),
    [
        (
            "---\nconfig:\n  theme: dark\n---\n" + GOOD,
            "R9 frontmatter that is not the house block",
        ),
        (
            HOUSE.replace("look: neo", "look: classic"),
            "R9 frontmatter that is not the house block",
        ),
        (
            OTHER.replace(OTHER_FRONT, FLOW_FRONT),
            "R9 frontmatter that is not the house block",
        ),
        (
            HOUSE.replace(FLOW_FRONT, OTHER_FRONT),
            "R9 frontmatter that is not the house block",
        ),
        (
            "---\nconfig:\n  theme: base\n" + GOOD,
            "R9 frontmatter that is not the house block",
        ),
        (
            HOUSE.replace("  classDef part", "  classDef pert"),
            "R5 the house class lines are incomplete, missing: part",
        ),
        (HOUSE.replace("stroke:#334155", "stroke:#334156"), "R5 a class line differs"),
        (
            HOUSE.replace(BOUNDARY, BOUNDARY.replace("style edge", "style dfe")),
            "which is no subgraph",
        ),
        (
            HOUSE.replace(f"  {BOUNDARY}\n", ""),
            "subgraph `edge` has no house boundary line",
        ),
        (HOUSE.replace(BOUNDARY, "style edge fill:#f00"), "R9 `style`"),
        (HOUSE.replace("-->|events|", "==>"), "a thick arrow"),
        (HOUSE.replace('topic[("', 'topic{{"').replace('")]', '"}}'), "R6 an outline"),
        (OTHER + "    classDef x fill:#fff\n", "takes no colour"),
    ],
)
def test_a_house_fault_is_named(source, said):
    found = _problems(source)
    assert any(said in problem for problem in found), found


@pytest.mark.parametrize(
    ("source", "said"),
    [
        (
            f"sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    {DEFAULT}\n",
            "takes no colour",
        ),
        (
            "sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n"
            + "".join(f"    participant p{n}\n" for n in range(7)),
            "7 participants",
        ),
        (
            "sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n"
            + "".join(f"    p{n}->>p{n + 1}: Call\n" for n in range(6)),
            "7 participants",
        ),
        (
            "sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    box Aqua Loader\n",
            "a coloured `box`",
        ),
        (
            "sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    rect rgb(1, 2, 3)\n",
            "a coloured `box`",
        ),
    ],
    ids=[
        "coloured_sequence",
        "seven_participants",
        "seven_named_in_messages",
        "coloured_box",
        "rect",
    ],
)
def test_a_sequence_fault_is_named(source, said):
    assert any(said in problem for problem in _problems(source))


@pytest.mark.parametrize(
    ("arrows", "flagged"),
    [
        ('bridge["Bridge"] --> vec["Vector"]\n    vec -.-> bridge', True),
        ("bridge --> vec\n    vec -->|ack| bridge", True),
        ('intake["Intake"] --> vec["Vector"]\n    vec -.-> reply["Return"]', False),
        ('read["dfe.main-x"] --> write["Write"]', False),
    ],
    ids=["dotted_back", "labelled_back", "split_boxes", "dots_in_a_label"],
)
def test_arrows_both_ways_between_one_pair_are_named(arrows, flagged):
    source = GOOD.replace("flowchart LR", f"flowchart LR\n    {arrows}", 1)
    assert (
        any("arrows both ways" in problem for problem in _problems(source)) is flagged
    )


@pytest.mark.parametrize(
    ("numbers", "flagged"),
    [([1, 2], False), ([3, 4], True), ([1, 3], True)],
    ids=["from_one", "continued", "gap"],
)
def test_a_pages_figures_number_from_one(tmp_path, monkeypatch, numbers, flagged):
    monkeypatch.chdir(tmp_path)
    page = Path("page.md")
    fences = "".join(
        f"Intro {n}.\n\n```mermaid\nflowchart LR\n```\n\n*Figure {n}. L4 Detail -- X.* Up: top of r.\n\n"
        for n in numbers
    )
    page.write_text(fences, encoding="utf-8")
    _, problems = dc.page_blocks(page)
    assert any("figures are numbered" in problem for problem in problems) is flagged


def test_an_up_or_down_link_to_the_pages_h1_anchor_is_named(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "extractors.md").write_text(
        "# Extractors\n\nBody.\n", encoding="utf-8"
    )
    page = Path("README.md")
    caption = "*Figure 1. L3 Components -- Fetcher.* Up: top of dfe-fetcher. Down: [L4 Detail -- Extractors](docs/extractors.md#extractors), [Other](docs/extractors.md#body)."
    page.write_text(
        f"# Fetcher\n\nThe fetcher pulls from sources.\n\n```mermaid\nflowchart LR\n```\n\n{caption}\n",
        encoding="utf-8",
    )
    _, problems = dc.page_blocks(page)
    assert problems == [
        "README.md:5 R8 a link to the page's H1 anchor `#extractors`: link the page itself"
    ]


@pytest.mark.parametrize(
    ("lines", "flagged"),
    [(DEFAULT, True), ("", False)],
    ids=["with_default", "without"],
)
def test_a_state_diagram_takes_no_default_class_line(lines, flagged):
    source = f"stateDiagram-v2\n    direction LR\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    [*] --> Open\n    {lines}\n"
    assert (
        any("takes no `default` class line" in problem for problem in _problems(source))
        is flagged
    )


def test_an_uncoloured_box_and_six_participants_are_allowed():
    source = (
        "sequenceDiagram\n    accTitle: L4 Detail -- X\n    accDescr: Y.\n    box Loader\n"
        "    participant loader as Loader\n    end\n    topic->>loader: Poll batch\n    loader-->>topic: Ack\n"
    )
    assert _problems(source) == []


@pytest.mark.parametrize(
    ("intro", "caption", "said"),
    [
        ("This diagram shows DFE.", CAPTION, "R7 the intro announces the diagram"),
        (
            "Below is the flow through DFE.",
            CAPTION,
            "R7 the intro announces the diagram",
        ),
        (
            "The following diagram maps DFE.",
            CAPTION,
            "R7 the intro announces the diagram",
        ),
        ("The diagram below maps DFE.", CAPTION, "R7 the intro announces the diagram"),
        (
            "DFE writes every event through one loader.",
            "The loader then writes rows.",
            "R7 no caption",
        ),
        ("DFE writes every event through one loader.", "", "R7 no caption"),
        (
            "DFE writes every event through one loader.",
            "*Figure 2. L2 Services -- DFE.*",
            "R8 the caption's `Up:` names no parent",
        ),
        (
            "DFE writes every event through one loader.",
            "*Figure 2. L2 Services -- DFE.* Up: the overview.",
            "R8 the caption's `Up:` names no parent",
        ),
    ],
    ids=[
        "intro_announces",
        "intro_below_is",
        "intro_following_diagram",
        "intro_diagram_below",
        "prose_as_caption",
        "no_caption",
        "no_up_link",
        "up_names_nothing",
    ],
)
def test_a_wrapper_fault_is_named(intro, caption, said):
    found = _problems(GOOD, intro, caption)
    assert [problem for problem in found if said in problem], found


@pytest.mark.parametrize(
    "up",
    [
        "Up: [L1 Context -- DFE](../overview.md).",
        "Up: top of dfe-infra.",
        "Up: L1 Context -- DFE.",
    ],
    ids=["link", "top_of_repo", "parent_title"],
)
def test_an_up_that_names_a_parent_passes(up):
    assert (
        _problems(
            GOOD,
            "DFE writes every event through one loader.",
            f"*Figure 2. L2 Services -- DFE.* {up}",
        )
        == []
    )


def test_an_intro_that_names_a_chart_as_a_thing_passes():
    intro = "One CI run builds the image and the chart from the contract."
    assert _problems(GOOD, intro, CAPTION) == []


@pytest.mark.parametrize(
    "intro",
    ["", "## Architecture", "| Step | Built on |"],
    ids=["none", "heading", "table"],
)
def test_a_diagram_needs_no_intro_sentence(intro):
    assert _problems(GOOD, intro, CAPTION) == []


def test_the_top_level_needs_no_up_link():
    top = GOOD.replace("L2 Services", "L0 Landscape")
    assert (
        _problems(
            top,
            "HyperI sells three products on one data plane.",
            "*Figure 1. L0 Landscape -- HyperI.*",
        )
        == []
    )


def test_a_page_gives_its_diagrams_and_one_finding_a_text_box(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corner = "\u250c\u2500\u2500\u2510"
    page = Path("page.md")
    lines = [
        "# Page",
        "",
        "````markdown",
        "```mermaid",
        "flowchart LR",
        "```",
        "````",
        "",
        "DFE writes every event through one loader.",
        "",
        "```mermaid",
        "flowchart LR",
        '    a["A"]',
        "```",
        "",
        "*Figure 1. L2 Services -- DFE.*",
        "",
        "```text",
        corner,
        "+-----+",
        corner,
        "```",
        "",
        "```text",
        "src/",
        "\u251c\u2500\u2500 a.py",
        "\u2514\u2500\u2500 b.py",
        "```",
    ]
    page.write_text("\n".join(lines), encoding="utf-8")
    blocks, problems = dc.page_blocks(page)
    assert [(block.name, block.intro, block.caption) for block in blocks] == [
        (
            "page.md:11",
            "DFE writes every event through one loader.",
            "*Figure 1. L2 Services -- DFE.*",
        )
    ]
    assert blocks[0].source == 'flowchart LR\n    a["A"]'
    assert problems == [
        "page.md:18 R1 a text diagram: draw it in Mermaid, or a numbered list when it has no branches"
    ]


@pytest.mark.parametrize(
    ("page", "names", "problems"),
    [
        ("```c++\nint x;\n```\n\n```mermaid\nflowchart LR\n```\n", ["page.md:5"], 0),
        ('```mermaid title="Flow"\nflowchart LR\n```\n', ["page.md:1"], 0),
        ("```{mermaid}\nflowchart LR\n```\n", ["page.md:1"], 0),
        ("~~~mermaid\nflowchart LR\n~~~\n", ["page.md:1"], 0),
        ("1. A step\n\n    ```mermaid\n    flowchart LR\n    ```\n", ["page.md:3"], 0),
        ("Intro.\n\n```mermaid\nflowchart LR\n", ["page.md:3"], 0),
        ("```console\n+----+------+\n| id | name |\n+----+------+\n```\n", [], 0),
        ("```sql\n+----+\n```\n\n```text\n+----+\n```\n", [], 1),
        ("```\n+----+\n| a  |\n+----+\n```\n", [], 1),
        ("```text\n\u256d\u2500\u2500\u256e\n\u2570\u2500\u2500\u256f\n```\n", [], 1),
        ("```text\n\u2554\u2550\u2557\n\u255a\u2550\u255d\n```\n", [], 1),
        ("```text\n.-----.\n| box |\n'-----'\n```\n", [], 1),
        (
            "```text\nsrc/\n\u251c\u2500\u2500 a.py\n\u2514\u2500\u2500 b.py\n```\n",
            [],
            0,
        ),
        ("```text\nclient -> stunnel -> openvpn\n```\n", [], 1),
        ("```\nreceiver --> topic --> loader\n```\n", [], 1),
        ("```text\nread \u2192 route \u2192 write\n```\n", [], 1),
        ("```text\nlrwxrwxrwx 1 root root 7 bin -> usr/bin\n```\n", [], 0),
        ("```text\nx->y\n```\n", [], 0),
    ],
    ids=[
        "info_string_with_symbols",
        "info_string_with_attributes",
        "braced_kind",
        "tilde_fence",
        "fence_in_a_list",
        "open_at_the_end_of_the_page",
        "terminal_output_is_not_a_diagram",
        "only_a_text_fence_is_scanned",
        "untagged_fence_is_scanned",
        "rounded_corners",
        "double_corners",
        "dotted_ascii_box",
        "a_directory_tree_is_no_diagram",
        "arrow_chain",
        "long_arrow_chain_untagged",
        "glyph_arrow_chain",
        "one_symlink_arrow_is_no_diagram",
        "one_arrow_is_no_diagram",
    ],
)
def test_a_fence_is_read_as_markdown_reads_it(
    tmp_path, monkeypatch, page, names, problems
):
    monkeypatch.chdir(tmp_path)
    path = Path("page.md")
    path.write_text(page, encoding="utf-8")
    blocks, found = dc.page_blocks(path)
    assert [block.name for block in blocks] == names
    assert all(block.source.strip() == "flowchart LR" for block in blocks)
    assert len(found) == problems


FENCE = "```mermaid\nflowchart LR\n```\n"


@pytest.mark.parametrize(
    ("page", "intro", "caption"),
    [
        pytest.param(
            f"Intro.\n\n<!-- gen:begin x -->\n{FENCE}<!-- gen:end x -->\n\n*Figure 1. T.*\n",
            "Intro.",
            "*Figure 1. T.*",
            id="a_generators_marker_is_neither",
        ),
        pytest.param(
            f"Every event reaches\nthe loader.\n\n{FENCE}\n_Figure 1. L2 Services -- DFE._\nUp: [L1](a.md).\n\nNext paragraph.\n",
            "Every event reaches the loader.",
            "_Figure 1. L2 Services -- DFE._ Up: [L1](a.md).",
            id="a_formatter_wrapped_both",
        ),
        pytest.param(
            f"## Heading\nIntro.\n\n{FENCE}\n*Figure 1. T.*\n| a | b |\n",
            "Intro.",
            "*Figure 1. T.*",
            id="a_heading_and_a_table_end_it",
        ),
        pytest.param(
            f"- item one\n- item two\n\n{FENCE}\n<!-- prettier-ignore -->\n*Figure 1. T.*\n\n*Figure 2. U.*\n",
            "- item two",
            "*Figure 1. T.*",
            id="a_list_item_and_a_comment",
        ),
    ],
)
def test_the_intro_and_caption_are_whole_paragraphs(tmp_path, page, intro, caption):
    path = tmp_path / "page.md"
    path.write_text(page, encoding="utf-8")
    blocks, _ = dc.page_blocks(path)
    assert [(block.intro, block.caption) for block in blocks] == [(intro, caption)]


def test_a_mermaid_file_is_one_diagram_with_no_wrapper(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("flow.mmd")
    path.write_text(GOOD, encoding="utf-8")
    blocks, problems = dc.page_blocks(path)
    assert problems == []
    assert [(block.name, block.intro, block.caption) for block in blocks] == [
        ("flow.mmd", None, None)
    ]


def test_a_diagram_inside_the_limits_has_no_layout_problems():
    assert dc.layout_problems(MEASURED) == []
    assert dc.layout_problems(MEASURED | {"backward": ["Write -> Read"]}) == []
    # 1240 px is scaled to the 860 px column, so its 620 px shows as 430.
    assert dc.layout_problems(MEASURED | {"width": 1240, "height": 620}) == []
    # A sequence, ER or class diagram is not held to the proportion.
    assert (
        dc.layout_problems(MEASURED | {"width": 389, "height": 300}, landscape=False)
        == []
    )


@pytest.mark.parametrize(
    ("measured", "said"),
    [
        (
            {"ok": False, "error": "Parse error on line 3"},
            "R10 does not parse: Parse error on line 3",
        ),
        ({"width": 1251}, "1251 px wide"),
        ({"height": 601, "width": 800}, "601 px tall on the page"),
        ({"width": 389, "height": 300}, "R2 not landscape"),
        ({"nodes": 13, "edges": 12}, "R3 13 nodes"),
        ({"groups": 5}, "5 subgraphs"),
        ({"edges": 9}, "9 arrows on 6 nodes"),
        ({"busiest": 6}, "6 arrows on `Loader`"),
        ({"crossings": ["A -> D  x  B -> C"]}, "R4 crossing: A -> D  x  B -> C"),
        ({"through": ["A -> C  through  B"]}, "R4 line through a box"),
        ({"overlaps": ['label "yes"  on box  B']}, "R4 overlap"),
        ({"skips": ["Read -> Write"]}, "skip arrow"),
        (
            {"backward": ["Write -> Read", "Route -> Read"]},
            "more than one arrow against the flow",
        ),
        (
            {"backward": ["Write -> Read"], "solid_back": ["Write -> Read"]},
            "a solid arrow against the flow",
        ),
        ({"orphans": ["Stray"]}, "an orphan box, no arrow and no subgraph: Stray"),
        (
            {"wrapped": ["schema-registry-checker (1 written, 3 shown)"]},
            "a label wraps past 2 lines or breaks a name mid-word: schema-registry-checker",
        ),
    ],
)
def test_a_layout_fault_is_named(measured, said):
    found = dc.layout_problems(MEASURED | measured)
    assert any(said in problem for problem in found), found


@pytest.mark.parametrize(
    ("source", "code", "verdict"),
    [
        (GOOD, 0, "ok    docs/flow.mmd"),
        (GOOD.replace("flowchart LR", "graph TD"), 1, "FAIL  docs/flow.mmd"),
    ],
    ids=["clean", "faulty"],
)
def test_the_source_pass_runs_without_a_browser(
    tmp_path, monkeypatch, capsys, source, code, verdict
):
    """The verdict names the page by the path as given, so two README.md pages stay apart."""
    monkeypatch.chdir(tmp_path)
    path = Path("docs") / "flow.mmd"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    assert dc.main([str(path), "--no-render"]) == code
    out = capsys.readouterr().out
    assert verdict in out
    assert "source only, not rendered" in out
