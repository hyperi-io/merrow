"""Hand-written Mermaid in a profile's look: its two managed regions (DESIGN D5).

An author writes the body, naming an object as `id:::dfe-loader` (the object id
with dots as hyphens). apply sets the frontmatter, expands a bare object node
into the profile's label form, and rewrites the class block between the
markers. Each `:::` stays, so re-running is a no-op and picks up object edits.
"""

import re
from collections.abc import Mapping
from pathlib import Path

from merrow.graph import Node
from merrow.lint.diagram_check import diagram_type, split_front
from merrow.objects import L1Object
from merrow.profile import Profile
from merrow.render import FENCE
from merrow.write import misfits, profile_label

BEGIN = "%% merrow:begin"
END = "%% merrow:end"
_REF = re.compile(r"^(?P<id>[A-Za-z_]\w*)(?P<label>[\[(].*[\])])?:::(?P<ref>[\w-]+)$")
_SUBGRAPH = re.compile(r"^subgraph\s+([A-Za-z_]\w*)")


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def apply(source: str, profile: Profile, by_ref: Mapping[str, L1Object]) -> str:
    """Return one diagram with the profile's frontmatter and class block.

    `by_ref` is `objects.by_class_name` of the object library.

    Raises:
        ValueError: An object styles as a class the profile doesn't define.
    """
    _, body = split_front(source)
    flow = diagram_type(body)[0] in ("flowchart", "graph")
    kept, managed = [], False
    for line in body.splitlines():
        if line.strip() in (BEGIN, END):
            managed = line.strip() == BEGIN
        elif not managed:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()

    styles: dict[str, list[str]] = {}
    subgraphs, out = [], []
    for line in kept:
        match = _REF.match(line.strip())
        known = by_ref.get(match["ref"]) if match else None
        if match and known is not None:
            if problems := misfits(profile, known):
                raise ValueError("; ".join(problems))
            node = Node(match["id"], known.label, known.subtitle)
            label = match["label"] or profile_label(profile, node, known.shape)
            line = f"{_indent(line)}{match['id']}{label}:::{match['ref']}"
            styles.setdefault(known.style, []).append(match["id"])
        if found := _SUBGRAPH.match(line.strip()):
            subgraphs.append(found.group(1))
        out.append(line)

    if flow:
        indent = next((_indent(ln) for ln in out[1:] if ln.strip()), "    ")
        order = [ln.split()[1] for ln in profile.class_lines]
        block = [
            f"class {','.join(styles[name])} {name}"
            for name in sorted(styles, key=order.index)
        ]
        block += [*profile.class_lines]
        block += [f"style {name} {profile.boundary}" for name in subgraphs]
        out += [f"{indent}{BEGIN}", *(indent + ln for ln in block), f"{indent}{END}"]
    front = profile.fronts["flowchart" if flow else "other"]
    return f"{front}\n" + "\n".join(out) + "\n"


def apply_file(path: Path, profile: Profile, by_ref: Mapping[str, L1Object]) -> bool:
    """Apply the profile to a `.mmd` file, or to each managed fence in Markdown.

    A fence is managed once it names an object or carries the class block.
    Returns whether the file changed.

    Raises:
        ValueError: An object styles as a class the profile doesn't define.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".md":
        new = apply(text, profile, by_ref)
    else:

        def one(fence: re.Match[str]) -> str:
            body = fence.group(1)
            names = {
                m["ref"] for ln in body.splitlines() if (m := _REF.match(ln.strip()))
            }
            if BEGIN not in body and not names & set(by_ref):
                return fence.group(0)
            return fence.group(0).replace(body, apply(body, profile, by_ref), 1)

        new = FENCE.sub(one, text)
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
    return new != text
