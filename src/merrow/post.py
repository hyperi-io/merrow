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

from merrow.browser import launch
from merrow.write import GROUP_ICON

_MARK = re.compile(rf"^\s*{re.escape(GROUP_ICON)}\s+(\S+)\s+(\S+)\s*$", re.MULTILINE)

# Runs in the page with [svg text, {group id: icon}]. Each icon draws at its own artwork size.
_PLACE = """([text, groups]) => {
  const svg = new DOMParser().parseFromString(text, 'image/svg+xml').documentElement;
  document.body.appendChild(svg);
  for (const cluster of svg.querySelectorAll('g.cluster')) {
    const id = Object.keys(groups).find(k => cluster.id === k || cluster.id.endsWith('-' + k));
    const rect = cluster.querySelector('rect');
    if (!id || !rect) continue;
    const icon = groups[id];
    const x = +rect.getAttribute('x'), y = +rect.getAttribute('y');
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    box.setAttribute('x', x); box.setAttribute('y', y);
    box.setAttribute('width', icon.width); box.setAttribute('height', icon.height);
    box.setAttribute('viewBox', `${icon.left} ${icon.top} ${icon.width} ${icon.height}`);
    box.innerHTML = icon.body;
    cluster.parentNode.insertBefore(box, cluster.nextSibling);
    const label = cluster.querySelector('.cluster-label');
    if (label) {
      const bb = label.getBBox();
      label.setAttribute('transform', `translate(${x + icon.width + 8}, ${y + (icon.height - bb.height) / 2})`);
    }
  }
  return new XMLSerializer().serializeToString(svg);
}"""


def marks(source: str) -> dict[str, str]:
    """Return each marked group's Mermaid id and its icon key."""
    return dict(_MARK.findall(source))


def _icons(
    packs_dir: Path, keys: Sequence[str], suffix: str
) -> dict[str, dict[str, Any]]:
    """Return each icon's body and box by key, its `suffix` variant where one exists."""
    found = {}
    for key in keys:
        prefix, name = key.split(":", 1)
        pack = json.loads((packs_dir / f"{prefix}.json").read_text(encoding="utf-8"))
        icons = pack["icons"]
        name = pack.get("aliases", {}).get(name, {}).get("parent", name)
        name = f"{name}{suffix}" if suffix and f"{name}{suffix}" in icons else name
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
    jobs: Sequence[tuple[Path, Mapping[str, str], str]],
    packs_dir: Path,
    executable: Path | None = None,
) -> None:
    """Place group icons in each rendered SVG, in place, in the `executable` browser.

    A job is the SVG, its marks and the icon name suffix for its theme.

    Raises:
        KeyError: A marked icon isn't in its pack.
        FileNotFoundError: A marked icon's pack isn't built.
    """
    if not jobs:
        return
    # Imported here so nothing else pays for playwright at import.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        browser = launch(driver, executable)
        try:
            page = browser.new_page()
            for svg, groups, suffix in jobs:
                icons = _icons(packs_dir, sorted(set(groups.values())), suffix)
                by_group = {gid: icons[key] for gid, key in groups.items()}
                page.set_content("<!doctype html><body></body>")
                text = svg.read_text(encoding="utf-8")
                placed = page.evaluate(_PLACE, [text, by_group])
                svg.write_text(placed, encoding="utf-8", newline="\n")
        finally:
            browser.close()


_ICON_REF = re.compile(r'(icon:\s*")([a-z0-9-]+):([a-z0-9-]+)(")')


def themed(source: str, suffix: str, packs_dir: Path) -> str:
    """Return the source with each node icon swapped for its `suffix` variant, where one exists."""
    if not suffix:
        return source
    names: dict[str, set[str]] = {}

    def swap(match: re.Match[str]) -> str:
        prefix, name = match.group(2), match.group(3)
        if prefix not in names:
            pack = packs_dir / f"{prefix}.json"
            names[prefix] = (
                set(json.loads(pack.read_text(encoding="utf-8"))["icons"])
                if pack.is_file()
                else set()
            )
        if f"{name}{suffix}" in names[prefix]:
            name = f"{name}{suffix}"
        return f"{match.group(1)}{prefix}:{name}{match.group(4)}"

    return _ICON_REF.sub(swap, source)
