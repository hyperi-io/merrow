"""Profiles: DTCG tokens and templates in, the blocks a diagram carries out."""

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from merrow import config

# A DTCG alias: a dotted token path in braces. A CSS rule's braces never hold one.
_ALIAS = re.compile(r"\{([A-Za-z][\w-]*(?:\.[\w-]+)+)\}")
_MAX_DEPTH = 8


class ProfileError(ValueError):
    """A profile names a profile, token or field that isn't defined."""


@dataclass(frozen=True, slots=True)
class Profile:
    """What a profile generates.

    Attributes:
        name: The profile's key under `profiles`.
        fronts: Frontmatter by diagram family, `flowchart` or `other`.
        class_lines: One `classDef` line a class, in the configured order.
        boundary: The style a subgraph boundary line carries.
        node_label: A node's label, `subtitle` and `plain`, its `{node.*}` and
            `{shape.*}` fields left for the writer.
        shapes: Each shape's opening and closing brackets.
        default_shape: The shape of a node whose object names none.
        max_ranks: The longest chain drawn left to right before pattern B.
        stage_title: A pattern B stage's title, `{n}` its number.
        limits: Rendered `column`, `max_width` and `max_height`, in px.
        label_styling: Styling lint fails inside a quoted label.
        caption_styling: Styling lint fails when a caption names it.
    """

    name: str
    fronts: Mapping[str, str]
    class_lines: tuple[str, ...]
    boundary: str
    node_label: Mapping[str, str]
    shapes: Mapping[str, tuple[str, str]]
    default_shape: str
    max_ranks: int
    stage_title: str
    limits: Mapping[str, int]
    label_styling: re.Pattern[str]
    caption_styling: re.Pattern[str]

    @property
    def classes(self) -> frozenset[str]:
        """Return the class names the profile defines."""
        return frozenset(line.split()[1] for line in self.class_lines)


def tokens(tree: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield each DTCG token as its dotted path and value, aliases unresolved.

    A list value, such as a font family, is joined with commas.
    """
    for key, value in tree.items():
        if key.startswith("$") or not isinstance(value, Mapping):
            continue
        if "$value" in value:
            raw = value["$value"]
            yield prefix + key, ", ".join(raw) if isinstance(raw, list) else str(raw)
        else:
            yield from tokens(value, f"{prefix}{key}.")


def fill(text: str, scope: Mapping[str, str]) -> str:
    """Replace each alias in `text` once, leaving what the values hold alone.

    Raises:
        ProfileError: An alias names nothing in `scope`.
    """

    def value(match: re.Match[str]) -> str:
        if match.group(1) not in scope:
            raise ProfileError(f"no token {match.group(1)}")
        return scope[match.group(1)]

    return _ALIAS.sub(value, text)


def resolve(text: str, scope: Mapping[str, str]) -> str:
    """Replace every alias in `text`, following aliases to aliases.

    Raises:
        ProfileError: An alias names nothing, or aliases loop.
    """
    for _ in range(_MAX_DEPTH):
        if not _ALIAS.search(text):
            return text
        text = fill(text, scope)
    raise ProfileError(f"aliases nest deeper than {_MAX_DEPTH}: {text}")


def _expand(template: str, scope: Mapping[str, str]) -> str:
    """Resolve a template, a multi-line value taking its placeholder's indent."""
    out = []
    for line in template.splitlines():
        whole = _ALIAS.fullmatch(line.strip())
        lines = scope.get(whole.group(1), "") if whole else ""
        if "\n" in lines:
            indent = line[: len(line) - len(line.lstrip())]
            out += [indent + part for part in lines.splitlines()]
        else:
            out.append(resolve(line, scope))
    return "\n".join(out)


def _properties(
    fields: Mapping[str, Any], order: Sequence[str], scope: Mapping[str, str]
) -> str:
    return ",".join(
        f"{p}:{resolve(str(fields[p]), scope)}" for p in order if p in fields
    )


def load(settings: Any, name: str | None = None) -> Profile:
    """Return the named profile, else the configured one, generated from its tokens.

    Raises:
        ProfileError: The profile, or a token it names, isn't defined.
        FileNotFoundError: A token file is in no reference repo and not in merrow.
    """
    name = name or str(settings.get("profile"))
    entry = (settings.get("profiles") or {}).get(name)
    if not entry:
        raise ProfileError(f"no profile {name}")
    scope: dict[str, str] = {}
    for relative in entry["tokens"]:
        path = config.data_file(settings, relative)
        scope.update(tokens(json.loads(path.read_text(encoding="utf-8"))))
    order = list(entry["class_properties"])
    defaults = entry.get("class_defaults") or {}
    class_lines, icon_lines = [], []
    for class_name, own in entry["classes"].items():
        fields = {**defaults, **own}
        class_lines.append(f"classDef {class_name} {_properties(fields, order, scope)}")
        if "icon" in fields:
            icon = resolve(str(fields["icon"]), scope)
            each = {**scope, "class.name": class_name, "class.icon": icon}
            icon_lines.append(resolve(entry["icon_css"], each))
    scope["profile.icon_css"] = "\n".join(icon_lines)
    return Profile(
        name,
        {family: _expand(text, scope) for family, text in entry["front"].items()},
        tuple(class_lines),
        _properties(entry["boundary"], order, scope),
        dict(entry["node_label"]),
        {
            shape: (str(pair[0]), str(pair[1]))
            for shape, pair in entry["shapes"].items()
        },
        str(entry["default_shape"]),
        int(entry["layout"]["max_ranks"]),
        str(entry["layout"]["stage_title"]),
        {key: int(value) for key, value in entry["limits"].items()},
        re.compile(str(entry["lint"]["label_styling"])),
        re.compile(str(entry["lint"]["caption_styling"])),
    )
