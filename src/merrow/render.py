"""Mermaid to SVG, once per configured theme, with every built icon pack registered.

Packs are read from the packs dir as local files, so a render never fetches
anything. A Markdown file renders each of its `mermaid` fences.
"""

import json
import re
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from merrow import config, node, proc

_FENCE = re.compile(r"^```mermaid[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


class RenderError(RuntimeError):
    """mermaid-cli failed on a diagram."""


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
    for number, fence in enumerate(_FENCE.finditer(text), 1):
        yield Diagram(f"{path.stem}-{number}", fence.group(1))


def icon_pack_args(packs_dir: Path) -> list[str]:
    """Return mermaid-cli's arguments registering every Iconify pack in the dir."""
    pairs = []
    for pack in sorted(packs_dir.glob("*.json")):
        data = json.loads(pack.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "icons" in data and "prefix" in data:
            pairs.append(f"{data['prefix']}#{pack.resolve().as_uri()}")
    return ["--iconPacksNamesAndUrls", *pairs] if pairs else []


def render(items: list[Diagram], out_dir: Path, settings: Any) -> list[dict[str, str]]:
    """Render each diagram once per theme into `out_dir` and return what was written.

    Raises:
        RenderError: mermaid-cli failed on a diagram.
    """
    options: Mapping[str, Any] = settings.get("render")
    argv = node.mmdc(settings)
    packs = icon_pack_args(config.packs_dir(settings))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with tempfile.TemporaryDirectory(prefix="merrow-render-") as work:
        puppeteer_config = Path(work) / "puppeteer.json"
        puppeteer_config.write_text(
            json.dumps(options.get("puppeteer") or {}), encoding="utf-8"
        )
        mermaid_config = Path(work) / "mermaid.json"
        mermaid_config.write_text(
            json.dumps(options["mermaid_config"]), encoding="utf-8"
        )
        for item in items:
            source = Path(work) / f"{item.name}.mmd"
            source.write_text(item.source, encoding="utf-8")
            for theme, look in options["themes"].items():
                target = out_dir / f"{item.name}-{theme}.svg"
                command = [
                    *argv,
                    "--quiet",
                    "--input",
                    str(source),
                    "--output",
                    str(target),
                    "--theme",
                    look["mermaid"],
                    "--backgroundColor",
                    look["background"],
                    "--configFile",
                    str(mermaid_config),
                    "--puppeteerConfigFile",
                    str(puppeteer_config),
                    *packs,
                ]
                result = proc.run(command)
                if result.returncode != 0:
                    raise RenderError(f"{item.name} ({theme}): {proc.tail(result, 20)}")
                written.append(
                    {"diagram": item.name, "theme": theme, "svg": str(target)}
                )
    return written
