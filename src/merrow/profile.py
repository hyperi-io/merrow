"""Profiles: DTCG tokens and templates in, the blocks a diagram carries out."""

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from merrow import config

# A DTCG alias: a dotted token path in braces. A CSS rule's braces never hold one.
_ALIAS = re.compile(r"\{([A-Za-z][\w-]*(?:\.[\w-]+)+)\}")
_MAX_DEPTH = 8
# An icon's first fill colour: an AWS service icon's category colour.
_FILL = re.compile(r'fill="(#[0-9A-Fa-f]{6})"')


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
        default_class: The class of a node with no object.
        max_ranks: The longest chain drawn left to right before pattern B.
        stage_title: A pattern B stage's title, `{n}` its number.
        limits: Rendered `column`, `max_width` and `max_height`, in px.
        label_styling: Styling lint fails inside a quoted label.
        caption_styling: Styling lint fails when a caption names it.
        layout_waive: Render findings lint drops for this profile.
        icon_node: How a node whose object has an icon is drawn, its `{node.*}`
            fields left for the writer. None draws every node as a box.
        group_boundaries: A group's style by the `group_style` its object names.
        group_icons: Put each group's icon in its corner after render.
        icon_sizes: Each built icon's artwork height by `prefix:name`, from the
            packs the profile names.
        icon_fills: Each built icon's first fill colour by `prefix:name`.
        service_group: The `group_style` that takes its icon's colour, if any.
        row_groups: Lay a group with no arrow between its members left to right.
        stack_after: Stack a boundary diagram whose inside runs past this many
            columns, 0 for never.
    """

    name: str
    fronts: Mapping[str, str]
    class_lines: tuple[str, ...]
    boundary: str
    node_label: Mapping[str, str]
    shapes: Mapping[str, tuple[str, str]]
    default_shape: str
    default_class: str
    max_ranks: int
    stage_title: str
    limits: Mapping[str, int]
    label_styling: re.Pattern[str]
    caption_styling: re.Pattern[str]
    icon_node: str | None = None
    layout_waive: re.Pattern[str] | None = None
    group_boundaries: Mapping[str, str] = field(default_factory=dict)
    group_icons: bool = False
    icon_sizes: Mapping[str, int] = field(default_factory=dict)
    icon_fills: Mapping[str, str] = field(default_factory=dict)
    service_group: str = ""
    row_groups: bool = False
    stack_after: int = 0

    @property
    def classes(self) -> frozenset[str]:
        """Return the class names the profile defines."""
        return frozenset(line.split()[1] for line in self.class_lines)

    @property
    def boundaries(self) -> frozenset[str]:
        """Return every style a subgraph boundary line may carry."""
        return frozenset({self.boundary, *self.group_boundaries.values()})


def tokens(
    tree: Mapping[str, Any], prefix: str = "", kind: str | None = None
) -> Iterator[tuple[str, str]]:
    """Yield each DTCG token as its dotted path and value, aliases unresolved.

    A list value, such as a font family, is joined with commas. A `kind`
    yields only the tokens of that `$type`.
    """
    for key, value in tree.items():
        if key.startswith("$") or not isinstance(value, Mapping):
            continue
        if "$value" in value:
            if kind is not None and value.get("$type") != kind:
                continue
            raw = value["$value"]
            yield prefix + key, ", ".join(raw) if isinstance(raw, list) else str(raw)
        else:
            yield from tokens(value, f"{prefix}{key}.", kind)


def _font(settings: Any) -> str:
    """Return the forced font stack, commas between faces, or "" for none."""
    forced = settings.get("font") or ""
    return ", ".join(forced) if isinstance(forced, list) else str(forced)


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


def _partial(text: str, scope: Mapping[str, str]) -> str:
    """Resolve the tokens `scope` holds, leaving other aliases for the writer."""
    for _ in range(_MAX_DEPTH):
        done = _ALIAS.sub(lambda m: scope.get(m.group(1), m.group(0)), text)
        if done == text:
            return text
        text = done
    raise ProfileError(f"aliases nest deeper than {_MAX_DEPTH}: {text}")


def _icon_facts(settings: Any, packs: Sequence[str]) -> dict[str, tuple[int, str]]:
    """Return each icon's height and first fill colour in the named packs, every pack for `all`.

    Aliases are included. An icon with no fill colour has an empty one.

    Raises:
        FileNotFoundError: A pack isn't built.
    """
    files = config.pack_files(settings)
    found = {}
    for name in files if packs == "all" else packs:
        path = files.get(name)
        if path is None:
            missing = config.packs_dir(settings) / f"{name}.json"
            raise FileNotFoundError(
                f"{missing} is missing: run `merrow pack build` for it"
            )
        pack = json.loads(path.read_text(encoding="utf-8"))
        if "icons" not in pack:
            continue
        default = pack.get("height", 16)
        facts = {}
        for key, icon in pack["icons"].items():
            colour = _FILL.search(icon["body"])
            facts[key] = (int(icon.get("height", default)), colour[1] if colour else "")
        for alias, target in (pack.get("aliases") or {}).items():
            if target.get("parent") in facts:
                facts[alias] = facts[target["parent"]]
        found |= {f"{pack['prefix']}:{key}": fact for key, fact in facts.items()}
    return found


def _group_boundaries(
    settings: Any,
    styles: Mapping[str, Any],
    order: Sequence[str],
    scope: Mapping[str, str],
    fills: frozenset[str],
) -> dict[str, str]:
    """Return each group style in a built pack by its key, as boundary properties.

    A `service` style adds one style a service colour, keyed `<service>:<colour>`:
    AWS's custom group for one service takes that service's category colour.

    Raises:
        FileNotFoundError: The pack isn't built.
    """
    path = config.pack_files(settings).get(styles["pack"])
    if path is None:
        missing = config.packs_dir(settings) / f"{styles['pack']}.json"
        raise FileNotFoundError(
            f"{missing} is missing: run `merrow pack build {styles['pack']}`"
        )
    found = {}
    for group in json.loads(path.read_text(encoding="utf-8"))[styles["theme"]]:
        fields = {
            "fill": "none",
            "stroke": group["stroke"],
            "stroke-width": styles["stroke_width"],
            "color": group["label_colour"],
        }
        if dash := styles["dash"].get(group["dash"]):
            fields["stroke-dasharray"] = dash
        found[group["key"]] = _properties(fields, order, scope)
    if service := styles.get("service"):
        for colour in sorted(fills - {""}):
            fields = {"fill": "none", "stroke": colour}
            fields |= {
                "stroke-width": styles["stroke_width"],
                "color": styles["service_label"],
            }
            found[f"{service}:{colour}"] = _properties(fields, order, scope)
    return found


def _properties(
    fields: Mapping[str, Any], order: Sequence[str], scope: Mapping[str, str]
) -> str:
    return ",".join(
        f"{p}:{resolve(str(fields[p]), scope)}" for p in order if p in fields
    )


def _merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    """Return `base` with `over`'s entries on top, a mapping entry key by key."""
    merged = {key: value for key, value in base.items() if key not in over}
    for key, value in over.items():
        below = base.get(key)
        both = isinstance(value, Mapping) and isinstance(below, Mapping)
        merged[key] = {**below, **value} if both else value
    return merged


def _entry(
    profiles: Mapping[str, Any], name: str, seen: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Return a profile's entry over the profile it `extends`, if any.

    Raises:
        ProfileError: The profile, or one it extends, isn't defined, or they loop.
    """
    entry = profiles.get(name)
    if not entry:
        raise ProfileError(f"no profile {name}")
    parent = entry.get("extends")
    if not parent:
        return dict(entry)
    if parent in (*seen, name):
        chain = " -> ".join((*seen, name, parent))
        raise ProfileError(f"profiles extend in a loop: {chain}")
    return _merge(_entry(profiles, parent, (*seen, name)), entry)


def load(settings: Any, name: str | None = None, theme: str | None = None) -> Profile:
    """Return the named profile, else the configured one, generated from its tokens.

    A profile that `extends` another overrides that one's entries, and a
    `theme` the profile lists under `themes` overrides its own, a mapping entry
    key by key. A `font` setting replaces every fontFamily token.

    Raises:
        ProfileError: The profile, or a token it names, isn't defined.
        FileNotFoundError: A token file is in no reference repo and not in merrow.
    """
    name = name or str(settings.get("profile"))
    entry = _entry(settings.get("profiles") or {}, name)
    entry = _merge(entry, (entry.get("themes") or {}).get(theme) or {})
    scope: dict[str, str] = {}
    font = _font(settings)
    for relative in entry["tokens"]:
        path = config.data_file(settings, relative)
        tree = json.loads(path.read_text(encoding="utf-8"))
        scope.update(tokens(tree))
        if font:
            scope.update({key: font for key, _ in tokens(tree, kind="fontFamily")})
    order = list(entry["class_properties"])
    defaults = entry.get("class_defaults") or {}
    class_lines, icon_lines = [], []
    for class_name, own in entry["classes"].items():
        fields = {**defaults, **own}
        class_lines.append(f"classDef {class_name} {_properties(fields, order, scope)}")
        if "icon" in fields and entry.get("icon_css"):
            icon = resolve(str(fields["icon"]), scope)
            each = {**scope, "class.name": class_name, "class.icon": icon}
            icon_lines.append(resolve(entry["icon_css"], each))
    scope["profile.icon_css"] = "\n".join(icon_lines)
    facts = _icon_facts(settings, entry.get("icon_packs") or [])
    fills = frozenset(fill for _, fill in facts.values())
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
        str(entry["default_class"]),
        int(entry["layout"]["max_ranks"]),
        str(entry["layout"]["stage_title"]),
        {key: int(value) for key, value in entry["limits"].items()},
        re.compile(str(entry["lint"]["label_styling"])),
        re.compile(str(entry["lint"]["caption_styling"])),
        _partial(str(entry["icon_node"]), scope) if entry.get("icon_node") else None,
        re.compile(str(entry["lint"]["layout_waive"]))
        if entry["lint"].get("layout_waive")
        else None,
        _group_boundaries(settings, entry["group_styles"], order, scope, fills)
        if entry.get("group_styles")
        else {},
        bool(entry.get("group_icons")),
        {key: size for key, (size, _) in facts.items()},
        {key: fill for key, (_, fill) in facts.items()},
        str((entry.get("group_styles") or {}).get("service", "")),
        bool(entry["layout"].get("row_groups")),
        int(entry["layout"].get("stack_after", 0)),
    )
