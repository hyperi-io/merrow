"""merrow command line: `merrow <noun> <verb>`."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scalo.cli import Argument, Option, Typer
from scalo.cli.version import version_option
from typer import BadParameter, Exit

from merrow import apply, config, node, objects, proc, profile, render
from merrow.convert import CONVERTERS
from merrow.lint import diagram_check
from merrow.model import Limits
from merrow.sources import detect, fetch, lock

app = Typer(help="Style, render and lint Mermaid diagrams.", no_args_is_help=True)
config_app = Typer(help="The resolved configuration.", no_args_is_help=True)
tools_app = Typer(help="The pinned npm tools render runs on.", no_args_is_help=True)
source_app = Typer(
    help="Vendor sources: detect releases, pin, fetch.", no_args_is_help=True
)
diagram_app = Typer(help="Diagrams: render to SVG and lint.", no_args_is_help=True)
pack_app = Typer(help="Icon packs built from vendor sources.", no_args_is_help=True)
profile_app = Typer(help="Profiles: the look a diagram takes.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(tools_app, name="tools")
app.add_typer(source_app, name="source")
app.add_typer(pack_app, name="pack")
app.add_typer(diagram_app, name="diagram")
app.add_typer(profile_app, name="profile")


@app.callback()
def main(version: bool = version_option("merrow")) -> None:
    """Style, render and lint Mermaid diagrams."""


@config_app.command("get")
def config_get() -> None:
    """Print the resolved settings, every layer merged, as JSON on stdout."""
    settings = config.load().as_dict()
    print(json.dumps({key.lower(): value for key, value in settings.items()}))


@profile_app.command("show")
def profile_show(
    name: str = Argument("", help="Profile name, default the configured one"),
    family: str = Option(
        "flowchart", help="Diagram family: flowchart, or other for the rest"
    ),
) -> None:
    """Print a profile's frontmatter, class lines and subgraph boundary style."""
    shown = profile.load(config.load(), name or None)
    if family not in shown.fronts:
        raise BadParameter(f"{family}: one of {', '.join(shown.fronts)}")
    print(shown.fronts[family])
    if family == "flowchart":
        print(
            "\n".join(
                ["", *shown.class_lines, "", f"style <subgraph> {shown.boundary}"]
            )
        )


@tools_app.command("ensure")
def tools_ensure(
    install_deps: bool = Option(
        False,
        "--install-deps",
        help="Also install the browser's system libraries (Linux, needs root)",
    ),
) -> None:
    """Install the pinned mermaid-cli and browser if missing, then print them."""
    settings = config.load()
    if install_deps:
        node.install_browser_deps(settings)
    argv = node.mmdc(settings)
    result = proc.run([*argv, "--version"])
    if result.returncode != 0:
        raise node.NodeToolsError(f"mmdc --version failed: {proc.tail(result)}")
    version = result.stdout.strip()
    print(
        json.dumps(
            {
                "mmdc": argv[-1],
                "version": version,
                "cache_dir": str(config.cache_dir(settings)),
            }
        )
    )


@pack_app.command("build")
def pack_build(
    source_id: str = Argument(help="A source id from the `sources` config"),
    from_path: Path | None = Option(
        None,
        "--from",
        help="A download to build from. Default: the locked download, fetched.",
    ),
) -> None:
    """Build one source into the packs dir and print what was built as JSON."""
    settings = config.load()
    source = config.sources(settings).get(source_id)
    if source is None:
        raise BadParameter(f"no source {source_id!r} in the sources config")
    converter = CONVERTERS.get(source.format)
    if converter is None:
        known = ", ".join(sorted(CONVERTERS))
        raise BadParameter(
            f"source {source_id!r} has format {source.format!r}, not one of {known}"
        )
    limits = config.limits(settings)
    download = from_path or _fetch_locked(settings, source_id, limits)
    built = converter(download, source, limits)
    out = config.packs_dir(settings) / built.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built.data, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"pack": str(out), "bytes": out.stat().st_size, **built.report}))


def _fetch_locked(settings: Any, source_id: str, limits: Limits) -> Path:
    pin = lock.pins(settings.get("lock")).get(source_id)
    if pin is None:
        raise BadParameter(
            f"source {source_id!r} has no lock entry: run `merrow source update`"
        )
    return fetch.fetch(config.cache_dir(settings), source_id, pin, limits)


@source_app.command("update")
def source_update(
    lock_path: Path = Option(..., "--lock", help="The lock file to rewrite"),
) -> None:
    """Detect each source's newest release, re-pin what moved, rewrite the lock.

    Prints one JSON object per changed or failed source. Exits 1 when any failed.
    """
    settings = config.load()
    limits = config.limits(settings)
    sources = list(config.sources(settings).values())
    found = detect.detect(
        sources, settings.get("tokens") or {}, limits.detect_timeout_seconds
    )
    pins, changes = detect.update(sources, lock.read(lock_path), found, limits)
    lock.write(lock_path, pins)
    for change in changes:
        print(json.dumps(asdict(change)))
    if any(change.error for change in changes):
        raise Exit(1)


@source_app.command("fetch")
def source_fetch(
    source_ids: list[str] | None = Argument(
        None, help="Source ids. Default: every locked one"
    ),
) -> None:
    """Download each locked source into the cache, checked against its SHA-256."""
    settings = config.load()
    pins = lock.pins(settings.get("lock"))
    limits = config.limits(settings)
    for source_id in source_ids or sorted(pins):
        path = _fetch_locked(settings, source_id, limits)
        print(json.dumps({"source": source_id, "path": str(path)}))


@diagram_app.command("render")
def diagram_render(
    files: list[Path] = Argument(
        help="`.mmd` files, or Markdown whose mermaid fences render"
    ),
    out_dir: Path = Option(..., "--out", help="Directory for the SVGs"),
) -> None:
    """Render each diagram once per configured theme. Prints one JSON line per SVG."""
    settings = config.load()
    items = [diagram for path in files for diagram in render.diagrams(path)]
    for written in render.render(items, out_dir, settings):
        print(json.dumps(written))


@source_app.command("list")
def source_list(
    quiet: bool = Option(
        False, "--quiet", "-q", help="Print bare source ids, one per line"
    ),
) -> None:
    """List every configured source with its format, prefix and pinned version."""
    settings = config.load()
    pins = lock.pins(settings.get("lock"))
    for source in config.sources(settings).values():
        if quiet:
            print(source.id)
            continue
        pin = pins.get(source.id)
        locked = pin.version if pin else None
        print(
            json.dumps(
                {
                    "id": source.id,
                    "format": source.format,
                    "prefix": source.prefix,
                    "locked": locked,
                }
            )
        )


@diagram_app.command("apply")
def diagram_apply(
    files: list[Path] = Argument(help="`.mmd` files, or Markdown with mermaid fences"),
    name: str = Option("", "--profile", help="Profile, default the configured one"),
) -> None:
    """Set each diagram's frontmatter and class block from the profile, in place."""
    settings = config.load()
    shown = profile.load(settings, name or None)
    by_ref = objects.by_class_name(objects.library(settings))
    for path in files:
        try:
            changed = apply.apply_file(path, shown, by_ref)
        except ValueError as error:
            raise BadParameter(f"{path}: {error}") from error
        print(f"{'changed' if changed else 'unchanged'}  {path}")


@diagram_app.command("lint")
def diagram_lint(
    files: list[Path] = Argument(
        help="`.mmd` files, or Markdown whose fences are checked"
    ),
    no_render: bool = Option(
        False, "--no-render", help="Source checks only, no browser"
    ),
    as_json: bool = Option(False, "--json", help="Print the results as JSON"),
) -> None:
    """Check diagrams against the standard and the built packs. Exits 1 on any failure."""
    argv = [str(path) for path in files]
    argv += ["--no-render"] if no_render else []
    argv += ["--json"] if as_json else []
    code = diagram_check.main(argv)
    if code:
        raise Exit(code)
