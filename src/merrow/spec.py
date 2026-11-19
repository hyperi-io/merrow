"""A diagram file: its title and a Graph, an L2 pattern with fills, or both.

The JSON Schema comes from these types, so it can't drift from what merrow reads.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Required, TypedDict

import yaml
from pydantic import ConfigDict, TypeAdapter, with_config

from merrow.graph import Edge, Graph, Group, Node
from merrow.patterns import Pattern, expand

_BOOL = "tag:yaml.org,2002:bool"


class _Loader(yaml.SafeLoader):
    """YAML 1.2 booleans: only true and false, so a label of `yes` or `on` stays text."""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag != _BOOL]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    _BOOL, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


@with_config(ConfigDict(extra="forbid"))
class Fill(TypedDict, total=False):
    """One slot entry when an object id alone won't do."""

    object: str
    label: str
    subtitle: str
    id: str


# merrow.yaml's object keys. `class` is a keyword, so the class form can't hold it.
ObjectEntry = with_config(ConfigDict(extra="forbid"))(
    TypedDict(
        "ObjectEntry",
        {
            "label": Required[str],
            "class": str,
            "subtitle": str,
            "icon": str,
            "shape": str,
            "group_style": str,
        },
        total=False,
    )
)


@with_config(ConfigDict(extra="forbid"))
@dataclass(frozen=True, slots=True)
class Spec:
    """One diagram.

    Attributes:
        title: The `accTitle`: `L<n> <Level name> -- <scope>`.
        description: The `accDescr`: the diagram's content in one or two sentences.
        pattern: An L2 pattern id, expanded from `fills`.
        fills: Each slot's entries: object ids, or `Fill` mappings.
        nodes: Nodes drawn as given, beside any the pattern makes.
        edges: Edges drawn as given.
        groups: Groups drawn as given.
        objects: One-off objects for this file, merrow.yaml's keys, over the library.
        profile: The profile it is drawn in. A `--profile` flag wins over it, and
            none takes the configured one.
        direction: LR, or TB for two rows, such as pairs: no arrow may leave a
            box an arrow enters.
    """

    title: str
    description: str
    pattern: str | None = None
    profile: str | None = None
    direction: Literal["LR", "TB"] = "LR"
    fills: dict[str, list[str | Fill]] = field(default_factory=dict)
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    objects: dict[str, ObjectEntry] = field(default_factory=dict)


_ADAPTER = TypeAdapter(Spec)


def schema() -> dict[str, Any]:
    """Return the diagram file's JSON Schema."""
    return _ADAPTER.json_schema()


def read(path: Path) -> Spec:
    """Return the diagram a YAML or JSON file describes.

    Raises:
        pydantic.ValidationError: A field is missing, mistyped or unknown.
        ValueError: The file isn't YAML (JSON is YAML), with a hint to quote.
    """
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 -- a SafeLoader subclass
    except yaml.YAMLError as error:
        hint = "quote a value that holds ': ', ' #' or '?', or starts with '-'"
        raise ValueError(f"{error}\n{hint}") from error
    return _ADAPTER.validate_python(data)


def graph(spec: Spec, patterns: dict[str, Pattern]) -> Graph:
    """Return the spec's Graph: its pattern expanded, then its own items added.

    Raises:
        ValueError: The pattern is unknown, or its fills don't fit it.
    """
    found = Graph()
    if spec.pattern:
        if spec.pattern not in patterns:
            raise ValueError(f"no pattern {spec.pattern}")
        found = expand(patterns[spec.pattern], spec.fills)
    found.nodes += spec.nodes
    found.edges += spec.edges
    found.groups += spec.groups
    return found
