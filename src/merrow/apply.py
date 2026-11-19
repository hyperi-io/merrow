"""Hand-written Mermaid in a profile's look: its two managed regions.

An author writes the body, naming an object as `id:::aws-msk` (the object id
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
# Mermaid kinds that take the frontmatter alone: they can name no object.
_FRONT_ONLY = ("sequenceDiagram", "erDiagram", "classDiagram")


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _class_of(line: str) -> str:
    """Return the class a `classDef` line defines, or "" for any other line."""
    words = line.split()
    return words[1] if len(words) > 1 and words[0] == "classDef" else ""


def apply(source: str, profile: Profile, by_ref: Mapping[str, L1Object]) -> str:
    """Return one diagram with the profile's frontmatter and class block.

    `by_ref` is `objects.by_class_name` of the object library. A flowchart with
    class lines pasted in, no object and no class block keeps its shape: each
    class line is set in place.

    Raises:
        ValueError: An object styles as a class the profile doesn't define, or
            a class block marker has no partner.
    """
    _, body = split_front(source)
    flow = diagram_type(body)[0] in ("flowchart", "graph")
    kept, managed = [], False
    for line in body.splitlines():
        mark = line.strip()
        if mark == BEGIN and managed:
            raise ValueError(f"a second `{BEGIN}` before `{END}`")
        if mark == END and not managed:
            raise ValueError(f"`{END}` with no `{BEGIN}` above it")
        if mark in (BEGIN, END):
            managed = mark == BEGIN
        elif not managed:
            kept.append(line)
    if managed:
        raise ValueError(f"`{BEGIN}` has no `{END}`: every line under it would go")
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

    lines = {ln.split()[1]: ln for ln in profile.class_lines}
    pasted = BEGIN not in body and not styles and any(_class_of(ln) for ln in out)
    if flow and pasted:
        out = [
            _indent(ln) + lines.get(_class_of(ln), ln.strip()) if _class_of(ln) else ln
            for ln in out
        ]
    elif flow:
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


def managed(source: str, by_ref: Mapping[str, L1Object]) -> bool:
    """Return whether a diagram takes the profile.

    It does when it names an object, carries the class block or a frontmatter,
    or is a sequence, ER or class diagram, which can name no object.
    """
    names = {m["ref"] for ln in source.splitlines() if (m := _REF.match(ln.strip()))}
    front, body = split_front(source)
    front_only = diagram_type(body)[0] in _FRONT_ONLY
    fronted = front is not None
    return BEGIN in source or bool(names & set(by_ref)) or front_only or fronted


def applied(
    path: Path, profile: Profile, by_ref: Mapping[str, L1Object]
) -> tuple[str, str]:
    """Return a file's text and its text with the profile applied, writing nothing.

    The profile goes on a `.mmd` file, or on each managed fence in Markdown.
    A fence is managed once it names an object or carries the class block or
    a frontmatter. A sequence, ER or class diagram is always managed: it can
    name no object.

    Raises:
        ValueError: An object styles as a class the profile doesn't define, or
            a class block marker has no partner.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".md":
        return text, apply(text, profile, by_ref)

    def one(fence: re.Match[str]) -> str:
        body = fence.group(1)
        if not managed(body, by_ref):
            return fence.group(0)
        return fence.group(0).replace(body, apply(body, profile, by_ref), 1)

    return text, FENCE.sub(one, text)
