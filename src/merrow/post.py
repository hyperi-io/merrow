"""After render: put each group's icon flush in its top-left corner, title beside it.

A writer marks which group takes which icon with `%% merrow:group-icon <id>
<prefix:name>` lines. The rendered SVG is changed in a browser page, because
the label size is known only once laid out, and written back as XML.
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from merrow import MerrowError
from merrow.write import GROUP_ICON

_MARK = re.compile(rf"^\s*{re.escape(GROUP_ICON)}\s+(\S+)\s+(\S+)\s*$", re.MULTILINE)

# Runs in the page with [svg text, {group id: icon}]. Each icon draws at its own artwork size.
# A pack built by an older merrow may hold active content, so each body is stripped again here.
_PLACE = """([text, groups]) => {
  const svg = new DOMParser().parseFromString(text, 'image/svg+xml').documentElement;
  document.body.appendChild(svg);
  const keys = Object.keys(groups);
  const raster = /^data:image\\/(png|jpeg|gif|webp|bmp);base64,/i;
  const strip = box => {
    box.querySelectorAll('script,foreignObject,set,animate,animateMotion,animateTransform,iframe,img').forEach(el => el.remove());
    for (const el of box.querySelectorAll('*')) {
      for (const {name, value} of [...el.attributes]) {
        const v = value.trim();
        const link = /(^|:)href$/i.test(name) && !v.startsWith('#') && !(el.localName === 'image' && raster.test(v));
        if (/^on/i.test(name) || name === 'src' || link || /url\\(\\s*['"]?(?!#)/i.test(v)) el.removeAttribute(name);
      }
    }
  };
  for (const cluster of svg.querySelectorAll('g.cluster')) {
    const id = keys.find(k => cluster.id === k) || keys.find(k => cluster.id.endsWith('-' + k));
    const rect = cluster.querySelector('rect');
    if (!id || !rect) continue;
    const icon = groups[id];
    const x = +rect.getAttribute('x'), y = +rect.getAttribute('y');
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    box.setAttribute('x', x); box.setAttribute('y', y);
    box.setAttribute('width', icon.width); box.setAttribute('height', icon.height);
    box.setAttribute('viewBox', `${icon.left} ${icon.top} ${icon.width} ${icon.height}`);
    box.innerHTML = icon.body;
    strip(box);
    cluster.parentNode.insertBefore(box, cluster.nextSibling);
    const label = cluster.querySelector('.cluster-label');
    if (label) {
      const bb = label.getBBox();
      label.setAttribute('transform', `translate(${x + icon.width + 8}, ${y + (icon.height - bb.height) / 2})`);
    }
  }
  const out = new XMLSerializer().serializeToString(svg);
  svg.remove();
  return out;
}"""


def marks(source: str) -> dict[str, str]:
    """Return each marked group's Mermaid id and its icon key."""
    return dict(_MARK.findall(source))


def _icons(
    packs: Mapping[str, Path], keys: Sequence[str], suffix: str
) -> dict[str, dict[str, Any]]:
    """Return each icon's body and box by key, its `suffix` variant where one exists.

    Raises:
        MerrowError: A key has no `prefix:` part, its pack isn't built, or the pack lacks it.
    """
    found = {}
    for key in keys:
        prefix, colon, name = key.partition(":")
        if not colon:
            raise MerrowError(f"group icon {key!r} has no pack prefix, as in aws:s3")
        if prefix not in packs:
            raise MerrowError(
                f"group icon {key}: no {prefix} pack, run merrow pack build {prefix}"
            )
        pack = json.loads(packs[prefix].read_text(encoding="utf-8"))
        icons = pack["icons"]
        name = pack.get("aliases", {}).get(name, {}).get("parent", name)
        name = f"{name}{suffix}" if suffix and f"{name}{suffix}" in icons else name
        if name not in icons:
            raise MerrowError(f"group icon {key}: the {prefix} pack has no {name}")
        icon = icons[name]
        found[key] = {
            "body": icon["body"],
            "left": icon.get("left", pack.get("left", 0)),
            "top": icon.get("top", pack.get("top", 0)),
            "width": icon.get("width", pack.get("width", 16)),
            "height": icon.get("height", pack.get("height", 16)),
        }
    return found


def group_icons(
    page: Any,
    svg: str,
    groups: Mapping[str, str],
    packs: Mapping[str, Path],
    suffix: str,
) -> str:
    """Return a rendered SVG with each marked group's icon placed, laid out in `page`.

    `suffix` picks each icon's variant for the theme, where one exists.

    Raises:
        MerrowError: A marked icon, or its pack, isn't there.
    """
    icons = _icons(packs, sorted(set(groups.values())), suffix)
    by_group = {gid: icons[key] for gid, key in groups.items()}
    return page.evaluate(_PLACE, [svg, by_group])


_ICON_REF = re.compile(r'(icon:\s*")([a-z0-9-]+):([a-z0-9-]+)(")')


def themed(source: str, suffix: str, packs: Mapping[str, Path]) -> str:
    """Return the source with each node icon swapped for its `suffix` variant, where one exists."""
    if not suffix:
        return source
    names: dict[str, set[str]] = {}

    def swap(match: re.Match[str]) -> str:
        prefix, name = match.group(2), match.group(3)
        if prefix not in names:
            pack = packs.get(prefix)
            names[prefix] = (
                set(json.loads(pack.read_text(encoding="utf-8"))["icons"])
                if pack is not None
                else set()
            )
        if f"{name}{suffix}" in names[prefix]:
            name = f"{name}{suffix}"
        return f"{match.group(1)}{prefix}:{name}{match.group(4)}"

    return _ICON_REF.sub(swap, source)
