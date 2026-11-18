"""Vendor SVG icon sets to an Iconify JSON pack for Mermaid's `registerIconPacks`.

Per icon: drop editor metadata, foreign namespaces and anything that runs script
(scripts, `on*` handlers, links off the icon), inline simple CSS class
rules (a pack puts many icons on one page, so a shared `.st1` would recolour its
neighbours), and prefix every id so gradients and clip paths can't collide. The
artwork is never changed. Which file becomes which icon key is the source's
`names` rules, never code.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

from merrow import archive, naming
from merrow.model import Built, Limits, Source, tally

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
_DROP_TAGS = {"title", "desc", "metadata", "style"}
# Render pastes group icons into the page without Mermaid's sanitiser.
_UNSAFE_TAGS = {"script", "foreignObject"}
_SAFE_HREF = re.compile(r"#|data:image/(png|jpeg|gif|webp)[;,]")
# What a root <svg> sets for every shape in it, kept on a wrapping <g>.
_INHERITED = {
    "fill",
    "fill-rule",
    "clip-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "opacity",
    "color",
}


@dataclass(slots=True)
class Report:
    """What one conversion did, for the CLI and for review."""

    icons: int = 0
    unmatched: int = 0
    skipped: int = 0
    duplicates: list[str] = field(default_factory=list)
    oversized: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    broken_aliases: list[str] = field(default_factory=list)
    titled: int = 0
    notes: dict[str, int] = field(default_factory=dict)


def _css_rules(text: str) -> tuple[dict[str, dict[str, str]], bool]:
    """Return `.class` rules from a `<style>` body, and whether any selector was more complex."""
    rules: dict[str, dict[str, str]] = {}
    complex_selector = False
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
        pairs = [part.split(":", 1) for part in body.split(";") if ":" in part]
        declarations = {name.strip(): value.strip() for name, value in pairs}
        for selector in (s.strip() for s in selectors.split(",")):
            if re.fullmatch(r"\.[\w-]+", selector):
                rules.setdefault(selector[1:], {}).update(declarations)
            elif selector:
                complex_selector = True
    return rules, complex_selector


def _local_name(tag: object) -> tuple[str, str]:
    """Return an element tag's namespace and local name."""
    if not isinstance(tag, str):
        return "", ""
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


def clean(
    svg: bytes, key: str, fill: str | None = None
) -> tuple[dict[str, object], list[str]]:
    """Return one icon's Iconify entry and the notes worth reviewing.

    `fill` paints a monochrome set that sets none, such as `currentColor`, so
    the icon takes the theme's colour. A fill the artwork sets wins.

    Raises:
        xml.etree.ElementTree.ParseError: The file isn't well-formed XML.
    """
    notes = []
    root = ET.fromstring(svg)  # noqa: S314 -- expat refuses entity expansion attacks
    css: dict[str, dict[str, str]] = {}
    for style in root.iter(f"{{{SVG}}}style"):
        rules, complex_selector = _css_rules(style.text or "")
        css.update(rules)
        if complex_selector:
            notes.append("complex-css")

    unsafe = False
    for parent in list(root.iter()):
        for child in list(parent):
            namespace, local = _local_name(child.tag)
            unsafe = unsafe or local in _UNSAFE_TAGS
            if local in _DROP_TAGS | _UNSAFE_TAGS or (namespace and namespace != SVG):
                parent.remove(child)
    for element in root.iter():
        # Inlined first, so a CSS declaration passes the same checks as an attribute.
        for name in (element.attrib.pop("class", None) or "").split():
            for prop, value in css.get(name, {}).items():
                element.set(prop, value)
        for attribute, value in list(element.attrib.items()):
            local = _local_name(attribute)[1]
            runs = local.lower().startswith("on") or (
                local == "href" and not _SAFE_HREF.match(value.strip())
            )
            unsafe = unsafe or runs
            foreign = attribute.startswith("{") and not attribute.startswith(
                f"{{{XLINK}}}"
            )
            if runs or foreign:
                del element.attrib[attribute]

    if unsafe:
        notes.append("script-dropped")

    ids = {element.get("id") for element in root.iter() if element.get("id")}

    def prefixed(found: re.Match[str]) -> str:
        target = found.group(1)
        return f"#{key}-{target}" if target in ids else f"#{target}"

    for element in root.iter():
        if element.get("id"):
            element.set("id", f"{key}-{element.get('id')}")
        for attribute, value in list(element.attrib.items()):
            is_href = attribute in ("href", f"{{{XLINK}}}href") and value.startswith(
                "#"
            )
            if "url(#" in value or is_href:
                element.set(attribute, re.sub(r"#([^)\s\"']+)", prefixed, value))

    view_box = root.get("viewBox")
    if view_box:
        left, top, width, height = (
            float(v) for v in view_box.replace(",", " ").split()
        )
    else:
        left = top = 0.0
        width, height = (
            float(re.sub(r"[^\d.]", "", root.get(side, "0")) or 0)
            for side in ("width", "height")
        )
        notes.append("no-viewBox")

    body = "".join(ET.tostring(child, encoding="unicode") for child in root)
    body = re.sub(r"\s+xmlns(:\w+)?=\"[^\"]+\"", "", body)
    body = re.sub(r">\s+<", "><", body).strip()
    inherited = {k: v for k, v in root.attrib.items() if k in _INHERITED}
    if fill and "fill" not in inherited:
        inherited["fill"] = fill
    if inherited:
        shared = " ".join(f"{k}={quoteattr(v)}" for k, v in sorted(inherited.items()))
        body = f"<g {shared}>{body}</g>"
    icon: dict[str, object] = {"body": body, "width": width, "height": height}
    if left or top:
        icon["left"], icon["top"] = left, top
    return icon, notes


def pack(
    members: Iterable[archive.Member],
    prefix: str,
    rules: Sequence[naming.NameRule],
    aliases: Mapping[str, str] | None = None,
    titles: Mapping[str, str] | None = None,
    fill: str | None = None,
    info: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], Report]:
    """Return the Iconify pack for a download's files and what was dropped.

    `aliases` maps a short name to an icon key. One whose key isn't in the pack
    is left out and listed in the report, never written. A rule's `title` goes
    into the pack's `titles`, by key, and an entry in `titles` wins over it.
    `info` is Iconify's pack info, the licence and author with it.
    """
    icons: dict[str, object] = {}
    titles_found: dict[str, str] = {}
    report = Report()
    for member in members:
        key = naming.key_for(member.path, rules)
        if key is False:
            report.unmatched += 1
            continue
        if key is None or not isinstance(key, str):
            report.skipped += 1
            continue
        if key in icons:
            report.duplicates.append(member.path)
            continue
        if member.data is None:
            report.oversized.append(member.path)
            continue
        try:
            icons[key], notes = clean(member.data, key, fill)
        except ET.ParseError as error:
            report.failed.append(f"{member.path}: {error}")
            continue
        for note in notes:
            tally(report.notes, note)
        if title := (titles or {}).get(key) or naming.title_for(member.path, rules):
            titles_found[key] = title
    report.icons = len(icons)
    report.titled = len(titles_found)
    built: dict[str, object] = {
        "prefix": prefix,
        "icons": icons,
        "titles": titles_found,
    }
    if info:
        built["info"] = dict(info)
    resolved = {}
    for short, target in (aliases or {}).items():
        if target in icons:
            resolved[short] = {"parent": target}
        else:
            report.broken_aliases.append(f"{short} -> {target}")
    if resolved:
        built["aliases"] = resolved
    return built, report


def build(download: Path, source: Source, limits: Limits) -> Built:
    """Build a source's Iconify pack, `<prefix>.json`.

    Raises:
        ValueError: The download is not a directory, zip or tarball.
    """
    files = re.compile(source.options["files"])
    members = archive.members(download, files, limits.member_bytes, limits.ignore)
    rules = naming.rules(source.options["names"])
    options = source.options
    built, report = pack(
        members,
        source.prefix,
        rules,
        options.get("aliases"),
        options.get("titles"),
        options.get("fill"),
        options.get("info"),
    )
    return Built(f"{source.prefix}.json", built, asdict(report))
