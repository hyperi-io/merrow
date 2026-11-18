"""Mermaid to SVG in a browser page, once per configured theme, with every built icon pack registered.

Packs are read from the packs dir as local files, so a render never fetches
anything. A Markdown file renders each of its `mermaid` fences.
"""

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from merrow import browser, bundle, config, post

FENCE = re.compile(r"^```mermaid[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)

# Runs in the page with [source, id, Mermaid config, background colour]. Mermaid's
# HTML labels are not valid XML, so the SVG is parsed as HTML and written as XML.
# Strict comes last because that parse runs whatever a label carries.
_RENDER = """async ([source, id, options, background]) => {
  mermaid.initialize({startOnLoad: false, ...options, securityLevel: 'strict'});
  const { svg } = await mermaid.render(id, source);
  const host = document.createElement('div');
  host.innerHTML = svg;
  const root = host.querySelector('svg');
  root.style.backgroundColor = background;
  return new XMLSerializer().serializeToString(root);
}"""
_PACKS = (
    "packs => mermaid.registerIconPacks(packs.map(p => ({name: p.prefix, icons: p})))"
)


class RenderError(RuntimeError):
    """Mermaid failed on a diagram."""


@dataclass(frozen=True, slots=True)
class Diagram:
    """One diagram to render.

    Attributes:
        name: Output stem: the file stem, plus `-<n>` for a Markdown fence.
        source: The Mermaid text.
    """

    name: str
    source: str


def diagrams(path: Path) -> Iterator[Diagram]:
    """Yield the diagrams in a `.mmd` file, or each `mermaid` fence in Markdown."""
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".md":
        yield Diagram(path.stem, text)
        return
    for number, fence in enumerate(FENCE.finditer(text), 1):
        yield Diagram(f"{path.stem}-{number}", fence.group(1))


def icon_packs(packs_dir: Path) -> list[dict[str, Any]]:
    """Return every Iconify pack in the dir, to register with Mermaid."""
    found = []
    for pack in sorted(packs_dir.glob("*.json")):
        data = json.loads(pack.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "icons" in data and "prefix" in data:
            found.append(data)
    return found


def render(
    items: list[Diagram],
    out_dir: Path,
    settings: Any,
    themes: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Render each diagram once per theme into `out_dir` and return what was written.

    `themes` limits it to those configured themes.

    Raises:
        RenderError: Mermaid failed on a diagram.
    """
    # Imported here so the steps that need no page run without playwright.
    from playwright.sync_api import Error, sync_playwright

    options: Mapping[str, Any] = settings.get("render")
    packs_dir = config.packs_dir(settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as driver:
        shown = browser.launch(driver, settings)
        try:
            page = shown.new_page()
            page.set_content("<!doctype html><body></body>")
            page.add_script_tag(path=str(bundle.path(settings)))
            page.evaluate(_PACKS, icon_packs(packs_dir))
            for number, item in enumerate(items):
                groups = post.marks(item.source)
                for theme, look in options["themes"].items():
                    if themes is not None and theme not in themes:
                        continue
                    suffix = str(look.get("icon_suffix", ""))
                    text = post.themed(item.source, suffix, packs_dir)
                    mermaid = {**options["mermaid_config"], "theme": look["mermaid"]}
                    call = [text, f"d{number}{theme}", mermaid, look["background"]]
                    try:
                        svg = page.evaluate(_RENDER, call)
                    except Error as failure:
                        raise RenderError(
                            f"{item.name} ({theme}): {failure.message}"
                        ) from failure
                    if groups:
                        svg = post.group_icons(page, svg, groups, packs_dir, suffix)
                    target = out_dir / f"{item.name}-{theme}.svg"
                    target.write_text(svg, encoding="utf-8", newline="\n")
                    written.append(
                        {"diagram": item.name, "theme": theme, "svg": str(target)}
                    )
        finally:
            shown.close()
    return written
