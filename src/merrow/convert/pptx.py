"""Group-box styles from a publisher PPTX deck, such as AWS's Groups slide.

Each group on the slide is a `p:grpSp` (or a lone `p:sp`) holding the box
rectangle (line colour, dash, weight, fill), its text label and a `p:pic` corner
icon. Which deck in the download and which slide are the source's config: a
regex per theme on the deck's path and a regex on the slide's text.
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping
from pathlib import Path

from merrow import archive
from merrow.convert import opc
from merrow.model import Built, Limits, Source
from merrow.naming import slug

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
}
_EMBED = f"{{{NS['r']}}}embed"
_EMU_PER_POINT = 12700
# Theme slots a shape may name by alias.
_ALIASES = {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2"}


def _related(deck: zipfile.ZipFile, part: str, kind: str) -> str:
    """Return the first part related to `part` whose name has `kind` in it.

    Raises:
        LookupError: The part has no such relationship.
    """
    found = (t for t in opc.relationships(deck, part).values() if f"/{kind}" in t)
    if (target := next(found, None)) is None:
        raise LookupError(f"{part} has no relationship to {kind.rstrip('/')}")
    return target


def theme_colours(
    deck: zipfile.ZipFile, slide: str, max_part: int = opc.MAX_PART_BYTES
) -> dict[str, str]:
    """Return the colour scheme of the theme the slide's master uses."""
    layout = _related(deck, slide, "slideLayouts/")
    master = _related(deck, layout, "slideMasters/")
    theme = _related(deck, master, "theme/")
    colours = {}
    scheme = opc.xml(deck, theme, max_part).find(".//a:clrScheme", NS)
    for slot in scheme if scheme is not None else []:
        rgb = slot.find("a:srgbClr", NS)
        system = slot.find("a:sysClr", NS)
        value = rgb.get("val") if rgb is not None else None
        if value is None and system is not None:
            value = system.get("lastClr")
        colours[slot.tag.split("}")[1]] = value or ""
    for alias, slot in _ALIASES.items():
        colours[alias] = colours.get(slot, "")
    return colours


_HEX = re.compile(r"[0-9A-Fa-f]{6}")


def _hex(value: str | None) -> str | None:
    return f"#{value}" if value and _HEX.fullmatch(value) else None


def _colour(element: ET.Element | None, theme: Mapping[str, str]) -> str | None:
    """Return an element's solid fill as `#RRGGBB`, `none`, or None when unset.

    A theme slot's `lumMod`, `lumOff` and `alpha` adjustments are not applied.
    """
    if element is None:
        return None
    if element.find("a:noFill", NS) is not None:
        return "none"
    fill = element.find("a:solidFill", NS)
    if fill is None:
        return None
    rgb = fill.find("a:srgbClr", NS)
    if rgb is not None:
        return _hex(rgb.get("val"))
    scheme = fill.find("a:schemeClr", NS)
    if scheme is not None:
        return _hex(theme.get(scheme.get("val", "")))
    return None


def _text(shape: ET.Element) -> str:
    return "".join(t.text or "" for t in shape.iter(f"{{{NS['a']}}}t")).strip()


def group_style(
    shape: ET.Element, theme: Mapping[str, str], rels: Mapping[str, str]
) -> dict[str, object] | None:
    """Return one group's style, or None when the shape is not a group box."""
    if shape.tag.endswith("}sp"):
        shapes, pictures = [shape], []
    else:
        shapes = shape.findall("p:sp", NS)
        pictures = shape.findall(".//p:pic", NS)
        if not pictures:
            return None
    box = label = None
    for candidate in shapes:
        properties = candidate.find("p:spPr", NS)
        line = properties.find("a:ln", NS) if properties is not None else None
        if _colour(line, theme) not in (None, "none"):
            box = candidate
        if _text(candidate):
            label = candidate
    if box is None:
        return None
    properties = box.find("p:spPr", NS)
    line = properties.find("a:ln", NS) if properties is not None else None
    if properties is None or line is None:
        return None
    dash = line.find("a:prstDash", NS)
    run = (label if label is not None else box).find(".//a:rPr", NS)
    paragraph = box.find(".//a:pPr", NS)
    blip = None
    if pictures:
        blip = pictures[0].find(".//asvg:svgBlip", NS)
        if blip is None:
            blip = pictures[0].find(".//a:blip", NS)
    weight = line.get("w")
    name = _text(label if label is not None else box)
    return {
        "name": name,
        "key": slug(name),
        "label_align": (paragraph.get("algn") if paragraph is not None else None)
        or "l",
        "stroke": _colour(line, theme),
        "stroke_width_pt": round(int(weight) / _EMU_PER_POINT, 2) if weight else None,
        "dash": dash.get("val") if dash is not None else "solid",
        "fill": _colour(properties, theme) or "none",
        "label_colour": _colour(run, theme) if run is not None else None,
        "icon_media": rels.get(blip.get(_EMBED, "")) if blip is not None else None,
    }


def find_slide(
    deck: zipfile.ZipFile, title: re.Pattern[str], max_part: int = opc.MAX_PART_BYTES
) -> str:
    """Return the first slide holding a text run that matches `title`.

    Raises:
        LookupError: No slide matches.
    """
    slides = [
        n for n in deck.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
    ]
    for name in sorted(slides, key=lambda n: int(re.sub(r"\D", "", n))):
        runs = opc.xml(deck, name, max_part).iter(f"{{{NS['a']}}}t")
        if any(title.search(run.text or "") for run in runs):
            return name
    raise LookupError(f"no slide has a text run matching {title.pattern!r}")


def deck_groups(
    deck: zipfile.ZipFile,
    title: re.Pattern[str],
    max_name: int,
    max_part: int = opc.MAX_PART_BYTES,
) -> list[dict[str, object]]:
    """Return every distinct group style on the deck's matching slide."""
    slide = find_slide(deck, title, max_part)
    theme = theme_colours(deck, slide, max_part)
    rels = opc.relationships(deck, slide)
    root = opc.xml(deck, slide, max_part)
    candidates = [*root.iter(f"{{{NS['p']}}}grpSp"), *root.iter(f"{{{NS['p']}}}sp")]
    styles, seen = [], set()
    for shape in candidates:
        style = group_style(shape, theme, rels)
        if not style or not style["name"] or len(str(style["name"])) > max_name:
            continue
        identity = (style["name"], style["stroke"], style["dash"])
        if identity not in seen:
            seen.add(identity)
            styles.append(style)
    return styles


def build(download: Path, source: Source, limits: Limits) -> Built:
    """Build a source's group styles per theme, `<prefix>-groups.json`.

    `decks` maps a theme (light, dark) to a regex on the deck's path inside the
    download. A download that is itself a deck needs a single theme.

    Raises:
        LookupError: A deck or the titled slide is missing.
        ValueError: A deck or one of its parts is over the size cap.
    """
    title = re.compile(source.options["slide_title"])
    decks: dict[str, str] = source.options["decks"]
    themes: dict[str, list[dict[str, object]]] = {}
    if zipfile.is_zipfile(download) and len(decks) == 1:
        with zipfile.ZipFile(download) as deck:
            if "ppt/presentation.xml" in deck.namelist():
                theme = next(iter(decks))
                themes[theme] = deck_groups(
                    deck, title, limits.group_name_chars, limits.member_bytes
                )
                return Built(f"{source.prefix}-groups.json", themes, _counts(themes))
    for theme, pattern in decks.items():
        found = next(
            archive.members(
                download, re.compile(pattern), limits.deck_bytes, limits.ignore
            ),
            None,
        )
        if found is None:
            raise LookupError(f"no deck in {download.name} matches {pattern!r}")
        if found.data is None:
            raise ValueError(f"{found.path} is over {limits.deck_bytes} bytes")
        with zipfile.ZipFile(io.BytesIO(found.data)) as deck:
            themes[theme] = deck_groups(
                deck, title, limits.group_name_chars, limits.member_bytes
            )
    return Built(f"{source.prefix}-groups.json", themes, _counts(themes))


def _counts(themes: Mapping[str, list[dict[str, object]]]) -> dict[str, int]:
    return {theme: len(styles) for theme, styles in themes.items()}
