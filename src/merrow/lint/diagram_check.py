# Project:   merrow
# File:      src/merrow/lint/diagram_check.py
# Purpose:   Check Mermaid diagrams against the diagrams standard, as source and as rendered
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Check Mermaid diagrams against ``style/diagrams.md``.

Nobody writing Mermaid can see the layout from the source, so each diagram gets
two passes. The source pass reads the text: type, direction, class lines, the
accessibility lines, the caption and the banned syntax. The render pass lays the
diagram out with Mermaid in a browser page and measures what a reader sees:
its size, and for a flowchart the node and arrow counts, crossed lines, lines
through boxes, overlapping labels, skip arrows, orphan boxes and labels that wrap
past 2 lines. A state diagram gets the same line checks, less the back-arrow
limit, and a sequence diagram's autonumber badges are checked against its labels.

    python -m merrow.lint.diagram_check FILE... [--no-render] [--png DIR] [--json]
                                            [--mermaid PATH]

FILE is a Markdown page or a ``.mmd`` file. A page has every ``mermaid`` fence
checked, apart from fences nested inside another fence, and its ``text`` and
untagged fences read for a text-box diagram. Exit 1 when a diagram fails.

Layout differs between Mermaid releases, so the bundle is the one merrow renders
with, pinned by its npm lock and downloaded into the cache. ``--mermaid`` takes a
local bundle, for a host with no network or a site on another version.
"""

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from merrow import bundle as pinned
from merrow import config
from merrow.browser import launch
from merrow.lint import icons
from merrow.objects import by_class_name, library
from merrow.profile import Profile, ProfileError, load

# The standard's Colour section, byte for byte. tests/test_diagram_check.py holds the two in step.
CLASS_LINES = frozenset(
    {
        "classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A",
        "classDef core fill:#DCEBF7,stroke:#0072B2,stroke-width:2px,color:#0B2A3F",
        "classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327",
        "classDef async fill:#F6E6EF,stroke:#A8517F,stroke-width:1px,color:#3D1529",
        "classDef decision fill:#FCF1D6,stroke:#9A6700,stroke-width:1px,color:#3D2A00",
        "classDef error fill:#FBE3D6,stroke:#C2410C,stroke-width:1px,color:#4A1A05",
        "classDef ext fill:#EEF0F2,stroke:#6B7280,stroke-width:1px,stroke-dasharray:4 3,color:#1F2937",
        "classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4",
    }
)

# The standard's limits. tests/test_diagram_check.py holds the two in step. Width,
# height and the column are the profile's.
MIN_RATIO = 1.3
MAX_NODES = 12
MAX_SUBGRAPHS = 4
EXTRA_ARROWS = 2
MAX_NODE_ARROWS = 5
MAX_COLOUR_CLASSES = 4
MAX_PARTICIPANTS = 6

TYPES = ("flowchart", "sequenceDiagram", "stateDiagram-v2", "erDiagram", "classDiagram")
LEVELS = ("L0 Landscape", "L1 Context", "L2 Services", "L3 Components", "L4 Detail")
UNCOLOURED = ("sequenceDiagram", "erDiagram", "classDiagram")
# The canvases a screenshot is taken on.
CANVASES = {"light": ("neutral", "#FFFFFF"), "dark": ("dark", "#1B1B1D")}

# A fence opener and the first word of its info string: ```mermaid, ~~~c++, ```{mermaid} title="x".
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})[ \t]*([^\s`]*)")
# Fences read for a text-box diagram. Terminal output goes in a `console` fence, which is not.
_SCANNED = frozenset({"", "text", "txt", "plain", "ascii"})
# An ASCII box top, and the box corners a directory tree never draws: light, rounded and double.
_BOX_ART = re.compile(
    r"[+.]-{3,}[+.]|\+-{2,}\+|[\u250c\u2510\u2518\u256d\u256e\u256f\u2570\u2554\u2557\u255a\u255d]"
)
# An arrow between two words. Two on one line is a flow drawn in text, where a symlink in `ls -l` has one.
_ARROW = re.compile(r"(?<=\S)\s*(?:-{1,2}>|=>|\u2192)\s*(?=\S)")
# What follows `Up:` in a caption: a link, the top of a repo, or the parent's title.
_UP = re.compile(r"Up: (?:\[|top of \S|L[0-4] )")
# A markdown link with an anchor: the file part (empty for this page) and the anchor.
_LINK_ANCHOR = re.compile(r"\]\(([^)#\s]*)#([^)\s]+)\)")
# One arrow in a flowchart line: its source id, the arrow and its target id.
_EDGE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*[\[\](){}>]*\s*(?:-->|-\.->|---|-\.-|==>)(?:\|[^|]*\|)?\s*([A-Za-z_]\w*)"
)
_COMMENT = re.compile(r"^\s*<!--.*-->\s*$")
# A line that opens its own markdown block, so a wrapped paragraph never runs into it.
_BLOCK = ("#", "|", "```", "~~~", "- ", "* ", "> ", "*Figure", "_Figure")
# An intro that announces the diagram instead of adding what it cannot show.
_ANNOUNCES = re.compile(
    r"\b(?:this|the following) (?:diagram|figure|chart)\b|\b(?:diagram|figure|chart) below\b|^below\b|^here is\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'"[^"]*"')
_TITLE = re.compile(r"accTitle:\s*(L[0-4] \w+) -- \S")
# Prettier rewrites `*...*` emphasis to `_..._`, so a caption takes either.
_CAPTION = re.compile(r"[*_]Figure \d+\. ")
_BANNED = (
    (re.compile(r"^%%\{"), "R9 an init directive"),
    (re.compile(r"^(style|linkStyle|click)\s"), "R9 `style`, `linkStyle` or `click`"),
)
# Read after quoted labels are emptied: a rounded box is `id(` with no `[` or `(` after it, a flag is `id>...]`.
_FLOW_BANNED = (
    (
        re.compile(r"^(?:class|end)\s*[\[\({]"),
        "a reserved word as a node id (`class`, `end`): it fails to parse",
    ),
    (re.compile(r"={2,}>?"), "a thick arrow"),
    (re.compile(r"<-[-.]*>"), "a double-headed arrow"),
    (
        re.compile(r"@\{|\(\(|\{\{|\[/|\[\\|\w\((?![\[(])|\w>[^\]\n]*\]"),
        "R6 an outline outside the five",
    ),
)
# An icon node `id@{ icon: ... }`, allowed where the profile draws icons. Any other
# `@{ ... }` form, `shape:` included, stays an R6 outline.
_ICON_NODE = re.compile(r"\w@\{\s*icon:[^}]*\}")
# A house flowchart's rounded `id("...")` label, read after quoted labels are emptied.
_ROUNDED = re.compile(r'\w\(""\)')
_SUBGRAPH = re.compile(r"^subgraph\s+([A-Za-z_]\w*)")
_STYLE = re.compile(r"^style\s+(\S+)\s+(.*)$")
# `id:::name` applies a class inline. Read after quoted labels are emptied.
_SHORTHAND = re.compile(r":::([A-Za-z_][\w-]*)")
_ENTITY = re.compile(r"&#?\w+;")
_FIGURE = re.compile(r"[*_]Figure (\d+)\.")
_SEQUENCE_COLOUR = re.compile(
    r"^(?:rect\b|box\s+(?:rgba?\(|hsla?\(|#|transparent\b|(?:aqua|black|blue|fuchsia|gray|grey|green|lime|maroon"
    r"|navy|olive|orange|pink|purple|red|silver|teal|white|yellow)\b))",
    re.IGNORECASE,
)
_PARTICIPANT = re.compile(r"^(?:participant|actor)\s+(\w+)")
_MESSAGE = re.compile(r"^(\w+)\s*(?:<<)?--?(?:>>|>|x|\))\s*[+-]?(\w+)\s*:")
_LANDSCAPE = ("flowchart", "graph", "stateDiagram-v2")


@dataclass(frozen=True, slots=True)
class Block:
    """One diagram and the page lines around it. ``intro`` and ``caption`` are None for a ``.mmd`` file."""

    name: str
    source: str
    intro: str | None = None
    caption: str | None = None


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the checker found on one diagram. ``measured`` is None when it was not rendered."""

    name: str
    problems: list[str]
    measured: dict | None

    def line(self) -> str:
        """Return the verdict line: ``ok`` or ``FAIL``, the name, and the rendered size and counts."""
        size = self.measured
        shape = ""
        if size and size["ok"]:
            shape = f"  {size['width']}x{size['height']} nodes={size['nodes']} arrows={size['edges']}"
        return f"{'FAIL' if self.problems else 'ok  '}  {self.name}{shape}"


def page_blocks(path: Path) -> tuple[list[Block], list[str]]:
    """Return the diagrams on ``path`` and the page-level problems: box art in a text fence.

    A fence closes on a line of its own character alone, at least as long as its
    opener, or at the end of the page.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix not in (".md", ".mdx"):
        return [Block(str(path), text)], []
    lines = text.splitlines()
    blocks: list[Block] = []
    problems: list[str] = []
    opener = ""
    kind = ""
    start = 0
    boxed = False
    for number, line in enumerate([*lines, None], 1):
        if not opener:
            fence = _FENCE.match(line) if line is not None else None
            if fence:
                opener, kind, start, boxed = (
                    fence.group(1),
                    fence.group(2).strip("{}.").lower(),
                    number,
                    False,
                )
            continue
        closer = line.strip() if line is not None else opener
        if set(closer) != {opener[0]} or len(closer) < len(opener):
            drawn = _BOX_ART.search(line or "") or len(_ARROW.findall(line or "")) > 1
            if kind in _SCANNED and not boxed and drawn:
                boxed = True
                problems.append(
                    f"{path}:{start} R1 a text diagram: draw it in Mermaid, or a numbered list when it has no branches"
                )
            continue
        if kind == "mermaid":
            # A generator's marker comment is not on the rendered page, so it is neither intro nor caption.
            before = _paragraph(lines[: start - 1][::-1])[::-1]
            after = _paragraph(lines[number:])
            blocks.append(
                Block(
                    f"{path}:{start}",
                    "\n".join(lines[start : number - 1]),
                    " ".join(before),
                    " ".join(after),
                )
            )
        opener = ""
    problems += [
        f"{block.name} {problem}"
        for block in blocks
        for problem in _title_anchors(path, block.caption)
    ]
    numbers = [
        int(found[1])
        for block in blocks
        if (found := _FIGURE.match(block.caption or ""))
    ]
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        problems.append(
            f"{path} R7 figures are numbered {numbers}: number a page's figures from 1"
        )
    return blocks, problems


def _paragraph(lines: list[str]) -> list[str]:
    """The stripped lines of the first paragraph in ``lines``, which a formatter may have wrapped.

    Blank lines and comments before it are skipped, and comments inside it. It
    ends at a blank line, or before a line that opens a block (a heading, list,
    table, quote, fence or another caption).
    """
    found: list[str] = []
    for text in lines:
        if _COMMENT.match(text):
            continue
        line = text.strip()
        if not line:
            if found:
                break
            continue
        if found and (line.startswith(_BLOCK) or found[-1].startswith("#")):
            break
        found.append(line)
    return found


def _h1_slug(text: str) -> str:
    """The anchor a renderer gives the page's first `# ` heading, or "" where it has none."""
    for line in text.splitlines():
        if line.startswith("# "):
            return re.sub(r"[^\w\- ]", "", line[2:].strip().lower()).replace(" ", "-")
    return ""


def _title_anchors(path: Path, caption: str | None) -> list[str]:
    """An Up or Down link to a page's H1 anchor: a docs site makes the H1 the page title, so the anchor does not exist."""
    found = []
    for target, anchor in _LINK_ANCHOR.findall(caption or ""):
        page = (path.parent / target) if target else path
        try:
            slug = _h1_slug(page.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if slug and anchor == slug:
            found.append(
                f"R8 a link to the page's H1 anchor `#{anchor}`: link the page itself"
            )
    return found


def diagram_type(source: str) -> tuple[str, str]:
    """Return the diagram's type keyword and the direction beside it, each empty when absent.

    Frontmatter is skipped, so a source with it reads as its body does.
    """
    for line in split_front(source)[1].splitlines():
        words = line.split()
        if words and not line.strip().startswith("%%"):
            return words[0], words[1] if len(words) > 1 else ""
    return "", ""


def split_front(source: str) -> tuple[str | None, str]:
    """Return the diagram's frontmatter, from its opening ``---`` to its closing one, and the source after it."""
    if not source.startswith("---\n"):
        return None, source
    end = source.find("\n---", 3)
    if end < 0 or source[end + 4 : end + 5] not in ("", "\n"):
        return source, ""
    return source[: end + 4], source[end + 5 :]


def _house_style_problems(
    lines: list[str], boundaries: frozenset[str]
) -> tuple[list[str], set[str]]:
    """Return a profile flowchart's boundary-line problems and the `style` lines that are its boundaries."""
    subgraphs = [match.group(1) for line in lines if (match := _SUBGRAPH.match(line))]
    allowed: set[str] = set()
    problems: list[str] = []
    styled: list[str] = []
    for line in lines:
        match = _STYLE.match(line)
        if match and match.group(2) in boundaries:
            styled.append(match.group(1))
            if match.group(1) in subgraphs:
                allowed.add(line)
            else:
                problems.append(
                    f"R9 a boundary line for `{match.group(1)}`, which is no subgraph: it draws a phantom node"
                )
    problems += [
        f"R9 subgraph `{name}` has no house boundary line"
        for name in subgraphs
        if name not in styled
    ]
    return problems, allowed


def source_problems(
    block: Block,
    class_lines: frozenset[str],
    profile: Profile,
    object_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Return what the diagram's text breaks in the standard, without rendering it.

    `object_names` are the L1 objects' class names, which a `:::` may apply
    with no class line of their own.

    A diagram with frontmatter is held to `profile`'s generated blocks instead
    of `class_lines`.
    """
    front, body = split_front(block.source)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    kind, direction = diagram_type(body)
    flow = kind in ("flowchart", "graph")
    house = front is not None
    if house and front != profile.fronts["flowchart" if flow else "other"]:
        return [
            f"R9 frontmatter that is not the {profile.name} block, byte for byte: `merrow profile show {profile.name}` prints it"
        ]
    problems: list[str] = []
    house_lines: set[str] = set()
    house_classes = frozenset(profile.class_lines)
    if house and flow:
        class_lines = house_classes
        found, house_lines = _house_style_problems(lines, profile.boundaries)
        problems += found
    if flow:
        pairs = {
            match.groups()
            for line in lines
            if (match := _EDGE.match(_QUOTED.sub("", line)))
        }
        problems += [
            f"R4 arrows both ways between `{a}` and `{b}` lie on top of each other: split one box into an intake and a return box"
            for a, b in sorted(pairs)
            if a < b and (b, a) in pairs
        ]
    if kind == "graph":
        problems.append("R2 `graph`: write `flowchart`")
    elif kind not in TYPES:
        problems.append(f"`{kind}` is not one of the five diagram types")
    if flow and direction not in ("LR", "TB"):
        problems.append(
            f"R2 direction `{direction}`: `flowchart LR`, or `TB` for the stacked forms"
        )
    two_rows = flow and not {a for a, _ in pairs} & {b for _, b in pairs}
    if flow and direction == "TB" and "direction LR" not in lines and not two_rows:
        problems.append(
            "R2 a vertical chain: `flowchart LR`, stage subgraphs with `direction LR`,"
            " or TB for two rows, where no arrow leaves a box an arrow enters"
        )
    if kind == "stateDiagram-v2" and "direction LR" not in lines:
        problems.append("R2 a state diagram needs `direction LR`")

    title = next((line for line in lines if line.startswith("accTitle:")), "")
    level = _TITLE.match(title)
    if not title:
        problems.append("R7 no `accTitle`")
    elif not level or level.group(1) not in LEVELS:
        problems.append("R8 `accTitle` is not `L<n> <Level name> -- <scope>`")
    if not any(line.startswith("accDescr:") for line in lines):
        problems.append("R7 no `accDescr`")

    bare = [
        _QUOTED.sub('""', line)
        for line in lines
        if not line.startswith(("accTitle:", "accDescr:")) and line not in house_lines
    ]
    if house and flow:
        bare = [_ROUNDED.sub('_[""]', line) for line in bare]
    if house and flow and profile.icon_node:
        bare = [_ICON_NODE.sub('_[""]', line) for line in bare]
    for pattern, what in _BANNED + (_FLOW_BANNED if flow else ()):
        if any(pattern.search(line) for line in bare):
            problems.append(f"{what} is not allowed")
    if any(_ENTITY.search(line) for line in lines):
        problems.append("an HTML entity, which shows literally: write the character")
    labels = [text for line in lines for text in _QUOTED.findall(line)]
    if any(profile.label_styling.search(text) for text in labels):
        problems.append(
            "R5 styling inside a label: colour and line come from the class lines"
        )

    defined = [line for line in lines if line.startswith("classDef ")]
    if defined and kind in UNCOLOURED:
        problems.append(f"R5 a `{kind}` takes no colour")
    problems += [
        f"R5 a class line differs from the standard: `{line}`"
        for line in defined
        if line not in class_lines
    ]
    names = {line.split()[1] for line in defined}
    if house and flow:
        missing = sorted(line.split()[1] for line in house_classes - set(defined))
        if missing:
            problems.append(
                f"R5 the house class lines are incomplete, missing: {', '.join(missing)}"
            )
    elif flow and "default" not in names:
        problems.append("R5 the `default` class line is missing")
    if kind == "stateDiagram-v2" and "default" in names:
        problems.append(
            "R5 a `stateDiagram-v2` takes no `default` class line: it fails to parse"
        )
    colours = names - {"default", "group"}
    if len(colours) > MAX_COLOUR_CLASSES and not (house and flow):
        problems.append(f"R5 {len(colours)} colour classes, limit {MAX_COLOUR_CLASSES}")
    if flow or kind == "stateDiagram-v2":
        applied = {
            words[2]
            for line in lines
            if (words := line.split())[0] == "class" and len(words) == 3
        }
        applied |= {name for line in bare for name in _SHORTHAND.findall(line)}
        problems += [
            f"R5 class `{name}` is applied and its class line is missing"
            for name in sorted(applied - names - object_names)
        ]
    if kind == "sequenceDiagram":
        if any(_SEQUENCE_COLOUR.match(line) for line in lines):
            problems.append(
                "R5 a coloured `box` or `rect`: write `box Title` with no colour"
            )
        people = {
            match.group(1) for line in lines if (match := _PARTICIPANT.match(line))
        }
        people |= {
            name
            for line in lines
            if (match := _MESSAGE.match(line))
            for name in match.groups()
        }
        if len(people) > MAX_PARTICIPANTS:
            problems.append(f"{len(people)} participants, limit {MAX_PARTICIPANTS}")

    if block.intro and _ANNOUNCES.search(block.intro):
        problems.append(
            "R7 the intro announces the diagram: say what the picture cannot show"
        )
    if block.caption is not None:
        if found := profile.caption_styling.search(block.caption):
            problems.append(
                f"R7 the caption names styling (`{found.group()}`), which goes stale when the profile changes"
            )
        if not _CAPTION.match(block.caption):
            problems.append("R7 no caption `*Figure N. <title>.*` under the diagram")
        elif level and level.group(1) != LEVELS[0] and not _UP.search(block.caption):
            problems.append(
                "R8 the caption's `Up:` names no parent: a link, `top of <repo>.` or the parent's title"
            )
    return problems


def layout_problems(
    result: dict, limits: Mapping[str, int], landscape: bool = True
) -> list[str]:
    """Return what the rendered diagram breaks in the standard, from the page's measurements.

    ``limits`` is the profile's ``column``, ``max_width`` and ``max_height``, and optionally ``nodes`` and ``subgraphs``.
    ``landscape`` is False for the types that are not held to the proportion: sequence, ER and class.
    """
    if not result["ok"]:
        return [f"R10 does not parse: {result['error']}"]
    problems: list[str] = []
    width, height = result["width"], result["height"]
    # A diagram wider than the column is scaled down to it, and its height with it.
    shown = round(height * min(1, limits["column"] / max(width, 1)))
    if width > limits["max_width"]:
        problems.append(f"{width} px wide, limit {limits['max_width']}")
    if shown > limits["max_height"]:
        problems.append(f"{shown} px tall on the page, limit {limits['max_height']}")
    if landscape and width < MIN_RATIO * height:
        problems.append(
            f"R2 not landscape: width is {width / max(height, 1):.2f} x height, minimum {MIN_RATIO}"
        )
    max_nodes = limits.get("nodes", MAX_NODES)
    max_groups = limits.get("subgraphs", MAX_SUBGRAPHS)
    if result["nodes"] > max_nodes:
        problems.append(f"R3 {result['nodes']} nodes, limit {max_nodes}")
    if result["groups"] > max_groups:
        problems.append(f"{result['groups']} subgraphs, limit {max_groups}")
    if result["edges"] > result["nodes"] + EXTRA_ARROWS:
        problems.append(
            f"{result['edges']} arrows on {result['nodes']} nodes, limit is nodes plus {EXTRA_ARROWS}"
        )
    if result["busiest"] > MAX_NODE_ARROWS:
        problems.append(
            f"{result['busiest']} arrows on `{result['busiest_name']}`, limit {MAX_NODE_ARROWS}"
        )
    problems += [f"R4 crossing: {line}" for line in result["crossings"]]
    problems += [f"R4 line through a box: {line}" for line in result["through"]]
    problems += [f"R4 overlap: {line}" for line in result["overlaps"]]
    problems += [
        f"skip arrow, it jumps a box between its ends: {line}"
        for line in result["skips"]
    ]
    if len(result["backward"]) > 1:
        problems.append(
            "more than one arrow against the flow: " + ", ".join(result["backward"])
        )
    elif result.get("solid_back"):
        problems.append(
            f"a solid arrow against the flow, the one feedback arrow is dotted: {result['solid_back'][0]}"
        )
    problems += [
        f"an orphan box, no arrow and no subgraph: {name}"
        for name in result.get("orphans", [])
    ]
    problems += [
        f"a label wraps past 2 lines or breaks a name mid-word: {name}"
        for name in result.get("wrapped", [])
    ]
    return problems


# Runs in the page. Geometry comes from the laid-out SVG, so transforms and curves are already applied.
_MEASURE = r"""
window.measure = async (src, cfg, id, dir) => {
  mermaid.initialize(Object.assign({startOnLoad: false}, cfg, {securityLevel: 'strict'}));
  let out;
  try { out = await mermaid.render(id, src); }
  catch (e) { return {ok: false, error: String(e).replace(/\s+/g, ' ').slice(0, 300)}; }
  const host = document.getElementById('o');
  host.innerHTML = out.svg;
  const svg = host.querySelector('svg'), vb = svg.viewBox.baseVal;
  const corner = (el, m, x, y) => { const p = svg.createSVGPoint(); p.x = x; p.y = y; return p.matrixTransform(m); };
  const box = el => {
    const b = el.getBBox(), m = el.getCTM();
    const c = [corner(el, m, b.x, b.y), corner(el, m, b.x + b.width, b.y),
               corner(el, m, b.x, b.y + b.height), corner(el, m, b.x + b.width, b.y + b.height)];
    return {x0: Math.min(...c.map(p => p.x)), y0: Math.min(...c.map(p => p.y)),
            x1: Math.max(...c.map(p => p.x)), y1: Math.max(...c.map(p => p.y))};
  };
  const text = el => {
    // Text nodes joined by a space, because a <br/> in a label leaves none.
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), parts = [];
    while (walk.nextNode()) parts.push(walk.currentNode.nodeValue.trim());
    return parts.filter(Boolean).join(' ').replace(/\s+/g, ' ').slice(0, 40).trim();
  };
  const inside = (p, b, pad) => p[0] > b.x0 - pad && p[0] < b.x1 + pad && p[1] > b.y0 - pad && p[1] < b.y1 + pad;
  const gap = (p, b) => Math.hypot(Math.max(b.x0 - p[0], 0, p[0] - b.x1), Math.max(b.y0 - p[1], 0, p[1] - b.y1));
  const overlap = (a, b, pad) => a.x0 < b.x1 - pad && b.x0 < a.x1 - pad && a.y0 < b.y1 - pad && b.y0 < a.y1 - pad;
  const meet = (a, b, c, d) => {
    const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(den) < 1e-9) return null;
    const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
    // Half-open, so a crossing on a sampled point belongs to one segment, never to none.
    return t >= 0 && t < 1 && u >= 0 && u < 1 ? [a[0] + t * r[0], a[1] + t * r[1]] : null;
  };
  // Rendered lines are the distinct tops of a label's line boxes. Written lines are its <br/> count plus one.
  const lines = el => {
    const label = el.querySelector('.nodeLabel');
    if (!label) return [0, 0];
    const walk = document.createTreeWalker(label, NodeFilter.SHOW_TEXT), tops = [];
    while (walk.nextNode()) {
      const range = document.createRange();
      range.selectNodeContents(walk.currentNode);
      for (const r of range.getClientRects()) if (r.width > 0 && !tops.some(t => Math.abs(t - r.top) < 4)) tops.push(r.top);
    }
    return [tops.length, label.querySelectorAll('br').length + 1];
  };
  const nodes = [...svg.querySelectorAll('g.node, g.icon-shape')].map(el => ({name: text(el), b: box(el), lines: lines(el)}));
  const groups = [...svg.querySelectorAll('g.cluster')].map(el => ({name: text(el) || '(group)', b: box(el), group: true}));
  const ends = nodes.concat(groups);
  const near = p => ends.reduce((best, n) => gap(p, n.b) + (n.group ? 6 : 0) < gap(p, best.b) + (best.group ? 6 : 0) ? n : best);
  const points = path => {
    const m = path.getCTM(), n = path.getTotalLength(), out = [];
    for (let d = 0; d <= n; d += 3) { const p = path.getPointAtLength(d).matrixTransform(m); out.push([p.x, p.y]); }
    const last = path.getPointAtLength(n).matrixTransform(m); out.push([last.x, last.y]);
    return out;
  };
  // A state diagram draws its transitions as `path.transition` between `g.node` states, so the flowchart checks read it too.
  const edges = ends.length ? [...svg.querySelectorAll('path.flowchart-link, path.transition')].map(el => {
    const p = points(el); return {p, from: near(p[0]), to: near(p[p.length - 1]), dotted: el.classList.contains('edge-pattern-dotted')};
  }).filter(e => e.p.length > 2) : [];
  const name = e => e.from.name + ' -> ' + e.to.name;
  const res = {ok: true, width: Math.round(vb.width), height: Math.round(vb.height), nodes: nodes.length,
               groups: groups.length, edges: edges.length, crossings: [], through: [], overlaps: [], backward: [],
               solid_back: [], skips: [], orphans: [], wrapped: []};
  // Past the 2-line cap, or an identifier with no space broken mid-word, often at a hyphen.
  res.wrapped = nodes.filter(n => n.lines[0] > 2 || (n.lines[0] > n.lines[1] && !n.name.includes(' ')))
    .map(n => n.name + ' (' + n.lines[1] + ' written, ' + n.lines[0] + ' shown)');
  // A `~~~` link pins a box on purpose, so it counts against orphans and nothing else.
  const pins = ends.length ? [...svg.querySelectorAll('path.edge-thickness-invisible')].map(el => points(el)) : [];
  const touched = new Set(edges.flatMap(e => [e.from, e.to]).concat(pins.flatMap(p => [near(p[0]), near(p[p.length - 1])])));
  const flowchart = (svg.getAttribute('aria-roledescription') || '').startsWith('flowchart');
  const state = (svg.getAttribute('aria-roledescription') || '').startsWith('stateDiagram');
  if (flowchart) res.orphans = nodes.filter(n => !touched.has(n) && !groups.some(g => inside([(n.b.x0 + n.b.x1) / 2, (n.b.y0 + n.b.y1) / 2], g.b, 0))).map(n => n.name);
  for (let i = 0; i < edges.length; i++) for (let j = i + 1; j < edges.length; j++) {
    const A = edges[i], B = edges[j];
    // Two arrows on one node meet at its border, which is no crossing.
    const shared = [A.from, A.to].filter(n => n === B.from || n === B.to);
    let hit = false;
    for (let a = 0; a < A.p.length - 1 && !hit; a++) for (let b = 0; b < B.p.length - 1 && !hit; b++) {
      const at = meet(A.p[a], A.p[a + 1], B.p[b], B.p[b + 1]);
      // 20 px, because two transitions into a state diagram's small end circle merge about 13 px out from it.
      hit = !!at && !shared.some(n => inside(at, n.b, 20));
    }
    if (hit) res.crossings.push(name(A) + '  x  ' + name(B));
  }
  for (const e of edges) for (const n of nodes) {
    if (n !== e.from && n !== e.to && e.p.some(p => inside(p, n.b, -3))) res.through.push(name(e) + '  through  ' + n.name);
  }
  // An autonumber badge is a 9 px circle drawn round its number at the message's start.
  const badge = el => { const b = box(el), x = (b.x0 + b.x1) / 2, y = (b.y0 + b.y1) / 2; return {x0: x - 9, y0: y - 9, x1: x + 9, y1: y + 9}; };
  const badges = [...svg.querySelectorAll('text.sequenceNumber')].map(el => ({name: 'badge ' + text(el), b: badge(el)}));
  const messages = [...svg.querySelectorAll('text.messageText')].filter(text).map(el => ({name: 'label "' + text(el) + '"', b: box(el)}));
  badges.forEach((one, i) => {
    for (const other of badges.slice(i + 1)) if (overlap(one.b, other.b, 1)) res.overlaps.push(one.name + '  on  ' + other.name);
    for (const m of messages) if (overlap(one.b, m.b, 1)) res.overlaps.push(one.name + '  on  ' + m.name);
  });
  const labels = [...svg.querySelectorAll('g.edgeLabel')].filter(text).map(el => ({name: 'label "' + text(el) + '"', b: box(el)}));
  labels.forEach((label, i) => {
    for (const other of labels.slice(i + 1)) if (overlap(label.b, other.b, 1)) res.overlaps.push(label.name + '  on  ' + other.name);
    for (const n of nodes) if (overlap(label.b, n.b, 2)) res.overlaps.push(label.name + '  on box  ' + n.name);
  });
  for (const e of edges) {
    const a = e.p[0], z = e.p[e.p.length - 1];
    // In a top-down chart a stage runs left to right, so back is up without moving right, or left along a row.
    const dx = z[0] - a[0], dy = z[1] - a[1];
    const back = dir === 'LR' || state ? dx < -20 : (dy < -20 && dx <= 20) || (dx < -20 && Math.abs(dy) <= 20);
    // A state machine loops by design, so its back transitions are neither counted nor skips.
    if (back && state) continue;
    if (back) res.backward.push(name(e));
    if (back && !e.dotted) res.solid_back.push(name(e));
    // A box whose whole column lies between the two ends is a column the arrow jumps. Inside a
    // left-to-right stage of a top-down chart the columns are the stage's own, so the box shares the row.
    const across = dir === 'LR' || Math.abs(dx) > Math.abs(dy);
    const lo = across ? e.from.b.x1 : e.from.b.y1, hi = across ? e.to.b.x0 : e.to.b.y0;
    const top = Math.min(e.from.b.y0, e.to.b.y0), bottom = Math.max(e.from.b.y1, e.to.b.y1);
    const row = n => dir === 'LR' || !across || (n.b.y0 < bottom && n.b.y1 > top);
    const jumped = n => (across ? n.b.x0 > lo && n.b.x1 < hi : n.b.y0 > lo && n.b.y1 < hi) && row(n);
    // The one dotted feedback arrow runs back across the columns by design.
    if (!(back && e.dotted) && nodes.some(n => n !== e.from && n !== e.to && jumped(n))) res.skips.push(name(e));
  }
  const counts = ends.map(n => edges.filter(e => e.from === n || e.to === n).length);
  res.busiest = Math.max(0, ...counts);
  res.busiest_name = res.busiest ? ends[counts.indexOf(res.busiest)].name : '';
  return res;
};
"""


def mermaid_version() -> str:
    """Return the Mermaid version merrow's npm lock pins."""
    return pinned.version(config.load())


def render(
    blocks: list[Block],
    library: Path,
    column: int,
    settings: Any,
    png: Path | None = None,
) -> list[dict]:
    """Lay each diagram out in a ``column`` px page and return its measurements, with screenshots under ``png``."""
    # Imported here so the source pass runs on a host without playwright.
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    with sync_playwright() as driver:
        browser = launch(driver, settings)
        page = browser.new_page(viewport={"width": column + 40, "height": 700})
        page.set_content(
            f'<!doctype html><div id="o" style="width:{column}px;padding:16px"></div>'
        )
        page.add_script_tag(path=str(library))
        page.add_script_tag(content=_MEASURE)
        for number, block in enumerate(blocks):
            direction = diagram_type(block.source)[1]
            for canvas, (theme, background) in (
                CANVASES.items() if png else [("light", CANVASES["light"])]
            ):
                page.evaluate(
                    "colour => { document.body.style.background = colour; }", background
                )
                call = [block.source, {"theme": theme}, f"d{number}{canvas}", direction]
                result = page.evaluate("args => window.measure(...args)", call)
                if png and result["ok"]:
                    png.mkdir(parents=True, exist_ok=True)
                    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", block.name)
                    page.locator("#o").screenshot(
                        path=str(png / f"{stem}-{canvas}.png")
                    )
            results.append(result)
        browser.close()
    return results


def _profile_of(
    block: Block, settings: Any, default: Profile, loaded: dict[str, Profile | None]
) -> Profile:
    """Return the profile whose frontmatter the diagram carries, else `default`.

    A profile that can't load here, such as one whose pack isn't built, is skipped.
    `loaded` caches each profile by name across a run.
    """
    front = split_front(block.source)[0]
    if front is None or front in default.fronts.values():
        return default
    for name in settings.get("profiles") or {}:
        if name not in loaded:
            try:
                loaded[name] = load(settings, name)
            except ProfileError, FileNotFoundError:
                loaded[name] = None
        candidate = loaded[name]
        if candidate and front in candidate.fronts.values():
            return candidate
    return default


def main(argv: list[str] | None = None) -> int:
    """Check every diagram in the files named, print one verdict a diagram, and return the exit code."""
    parser = argparse.ArgumentParser(
        description="Check Mermaid diagrams against the diagrams standard."
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--no-render", action="store_true", help="source pass only, no browser"
    )
    parser.add_argument(
        "--png",
        type=Path,
        help="save a light and a dark screenshot of each diagram here",
    )
    parser.add_argument(
        "--mermaid",
        type=Path,
        help="a local mermaid.min.js (default: the version merrow pins)",
    )
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument(
        "--profile", default="", help="profile, default the configured one"
    )
    args = parser.parse_args(argv)

    blocks: list[Block] = []
    page_level: list[str] = []
    for path in args.files:
        found, problems = page_blocks(path)
        blocks += found
        page_level += problems
    settings = config.load()
    default = load(settings, args.profile or None)
    loaded: dict[str, Profile | None] = {}
    chosen = (
        [default] * len(blocks)
        if args.profile
        else [_profile_of(block, settings, default, loaded) for block in blocks]
    )
    measured: list[dict | None] = [None] * len(blocks)
    how = "source only, not rendered"
    if not args.no_render:
        script = args.mermaid or pinned.path(settings)
        for name in dict.fromkeys(profile.name for profile in chosen):
            at = [i for i, profile in enumerate(chosen) if profile.name == name]
            column = chosen[at[0]].limits["column"]
            group = [blocks[i] for i in at]
            for i, result in zip(at, render(group, script, column, settings, args.png)):
                measured[i] = result
        how = (
            f"rendered with {args.mermaid.name}"
            if args.mermaid
            else f"rendered with Mermaid {mermaid_version()}"
        )

    patterns = [re.compile(p) for p in settings.get("lint")["icon_refs"]]
    known = icons.known_keys(config.pack_files(settings).values())
    object_names = frozenset(by_class_name(library(settings)))
    report: list[Verdict] = []
    for block, result, profile in zip(blocks, measured, chosen, strict=True):
        problems = source_problems(block, CLASS_LINES, profile, object_names)
        problems += [
            f"icon {key} is in no built pack: run `merrow pack build` for its source"
            for key in icons.unresolved(block.source, patterns, known)
        ]
        if result:
            found = layout_problems(
                result, profile.limits, diagram_type(block.source)[0] in _LANDSCAPE
            )
            waive = profile.layout_waive
            problems += [p for p in found if not (waive and waive.search(p))]
        report.append(Verdict(block.name, problems, result))
    if args.json:
        print(
            json.dumps(
                {
                    "how": how,
                    "page": page_level,
                    "diagrams": [asdict(entry) for entry in report],
                },
                indent=1,
            )
        )
    else:
        for line in page_level:
            print(f"FAIL  {line}")
        for entry in report:
            print(entry.line())
            for problem in entry.problems:
                print(f"        {problem}")
        failed = sum(bool(entry.problems) for entry in report)
        print(
            f"{len(report)} diagram(s), {failed} failing, {len(page_level)} page finding(s) ({how})"
        )
    return 1 if page_level or any(entry.problems for entry in report) else 0


if __name__ == "__main__":
    sys.exit(main())
