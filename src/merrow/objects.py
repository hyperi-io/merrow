"""L1 objects: a thing drawn the same way everywhere, defined once in config."""

import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from scalo.logger import logger

from merrow import config
from merrow.graph import Graph


@dataclass(frozen=True, slots=True)
class L1Object:
    """One `objects` entry.

    Attributes:
        id: Its key, such as `aws.msk` or `aws.eks`.
        style: The profile class it is drawn with, such as `load` or `ext`.
        label: The name a node takes when it gives none.
        subtitle: The second line a node takes when it gives none.
        icon: An Iconify key, `prefix:name`, for profiles that draw icons.
        shape: A profile shape such as `cylinder`. None takes the profile's default.
        group_style: A profile group style such as `region`, for a group object.
    """

    id: str
    style: str
    label: str
    subtitle: str | None = None
    icon: str | None = None
    shape: str | None = None
    group_style: str | None = None


@functools.cache
def _titles(path: Path, _mtime: float) -> dict[str, str] | None:
    """Return a built pack's titles by icon key, None for a pack with none.

    `_mtime` keys the cache: a library load reads every pack, several MB.
    """
    return json.loads(path.read_text(encoding="utf-8")).get("titles")


def generated(settings: Any) -> dict[str, L1Object]:
    """Return one object per titled icon in each `generated_objects` pack that is built.

    A pack not built yet gives none: `merrow pack build` makes it. A pack built
    before packs held titles gives none either, and a warning to rebuild it.
    """
    files = config.pack_files(settings)
    found = {}
    for entry in settings.get("generated_objects") or []:
        path = files.get(entry["pack"])
        if path is None:
            continue
        titles = _titles(path, path.stat().st_mtime)
        if titles is None:
            logger.warning("pack has no titles, rebuild it", pack=str(path))
        prefix = str(entry["id_prefix"])
        for key, title in (titles or {}).items():
            icon = f"{entry['pack']}:{key}"
            found[prefix + key] = L1Object(prefix + key, "", title, icon=icon)
    return found


def library(settings: Any) -> dict[str, L1Object]:
    """Return every object by id: the generated ones, then the configured ones over them.

    Raises:
        ValueError: An entry has no `label`.
    """
    found = generated(settings)
    for object_id, fields in (settings.get("objects") or {}).items():
        found[object_id] = entry(object_id, fields)
    return found


def entry(object_id: str, fields: Mapping[str, Any]) -> L1Object:
    """Return one object from an `objects:` entry, in merrow.yaml or a diagram file.

    Raises:
        ValueError: The entry has no `label`.
    """
    if "label" not in fields:
        raise ValueError(f"object {object_id} has no label")
    return L1Object(
        object_id,
        str(fields.get("class", "")),
        str(fields["label"]),
        fields.get("subtitle"),
        fields.get("icon"),
        fields.get("shape"),
        fields.get("group_style"),
    )


def bind(graph: Graph, objects: Mapping[str, L1Object]) -> tuple[Graph, list[str]]:
    """Return the graph with each missing node and group label from its object.

    The second value lists what can't be drawn: an unknown object, or a node
    with neither a label nor an object.
    """
    problems = []
    nodes = []
    for node in graph.nodes:
        known = objects.get(node.object) if node.object else None
        if node.object and known is None:
            problems.append(f"node {node.id!r} names unknown object {node.object!r}")
        if known is not None:
            node = replace(
                node,
                label=node.label or known.label,
                subtitle=node.subtitle or known.subtitle,
            )
        if not node.label:
            problems.append(f"node {node.id!r} has no label and no object")
        nodes.append(node)
    groups = []
    for group in graph.groups:
        known = objects.get(group.object) if group.object else None
        if group.object and known is None:
            problems.append(f"group {group.id!r} names unknown object {group.object!r}")
        groups.append(
            replace(group, label=group.label or known.label) if known else group
        )
    return Graph(nodes, list(graph.edges), groups), problems


def by_class_name(library: Mapping[str, L1Object]) -> dict[str, L1Object]:
    """Return each object by the class name a diagram gives it: dots as hyphens.

    Raises:
        ValueError: Two objects read as the same name.
    """
    found: dict[str, L1Object] = {}
    for known in library.values():
        name = known.id.replace(".", "-")
        if name in found:
            raise ValueError(f"{found[name].id} and {known.id} both read as :::{name}")
        found[name] = known
    return found
