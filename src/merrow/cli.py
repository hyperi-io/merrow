"""merrow command line: `merrow <noun> <verb>`."""

import importlib
import json
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from scalo.cli import Argument, Option, Typer
from scalo.cli.version import version_option
from typer import BadParameter, Exit

from merrow import (
    MerrowError,
    apply,
    browser,
    bundle,
    config,
    destination,
    objects,
    patterns,
    profile,
    render,
    spec,
    write,
)
from merrow.lint import diagram_check, findings
from merrow.model import Limits
from merrow.sources import lock

app = Typer(help="Style, render and lint Mermaid diagrams.", no_args_is_help=True)
# The modules each extra brings, which a core install lacks.
EXTRAS = {
    "render": ("playwright.sync_api", "scalo.http", "httpx", "stamina"),
    "packs": ("nvchecker", "pypdfium2", "pydot", "scalo.http", "httpx", "stamina"),
}
config_app = Typer(help="The resolved configuration.", no_args_is_help=True)
tools_app = Typer(
    help="The pinned Mermaid bundle and browser render runs on.", no_args_is_help=True
)
source_app = Typer(
    help="Publisher sources: detect releases, pin, fetch.", no_args_is_help=True
)
diagram_app = Typer(help="Diagrams: render to SVG and lint.", no_args_is_help=True)
pack_app = Typer(help="Icon packs built from publisher sources.", no_args_is_help=True)
profile_app = Typer(help="Profiles: the look a diagram takes.", no_args_is_help=True)
skill_app = Typer(help="The agent skill merrow ships.", no_args_is_help=True)
graph_app = Typer(
    help="Diagram files: a Graph or an L2 pattern, drawn in a profile.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")
app.add_typer(tools_app, name="tools")
app.add_typer(source_app, name="source")
app.add_typer(pack_app, name="pack")
app.add_typer(diagram_app, name="diagram")
app.add_typer(profile_app, name="profile")
app.add_typer(graph_app, name="graph")
app.add_typer(skill_app, name="skill")


@app.callback()
def main(version: bool = version_option("merrow")) -> None:
    """Style, render and lint Mermaid diagrams."""


def _needs(extra: str, command: str) -> None:
    """Stop with the install line when an extra this command needs isn't installed.

    Raises:
        Exit: Code 2, a module of the extra is missing.
    """
    for module in EXTRAS[extra]:
        try:
            # The names come from the EXTRAS constant above, never from input.
            importlib.import_module(module)  # nosemgrep
        except ModuleNotFoundError:
            print(
                f"merrow: {command} needs merrow[{extra}]: "
                "uv tool install --python 3.14 'merrow[all]'",
                file=sys.stderr,
            )
            raise Exit(2) from None


@config_app.command("get")
def config_get() -> None:
    """Print the resolved settings as JSON, `objects` with every built pack's icons."""
    settings = config.load()
    shown = {key.lower(): value for key, value in settings.as_dict().items()}
    generated = {
        key: {
            field: value
            for field, value in asdict(found).items()
            if value and field != "id"
        }
        for key, found in objects.generated(settings).items()
    }
    shown["objects"] = generated | (shown.get("objects") or {})
    print(json.dumps(shown))


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
        help="Also install the browser's system libraries (Debian and Ubuntu, asks for sudo)",
    ),
) -> None:
    """Fetch the pinned Mermaid bundle and install the browser if missing, then print them."""
    _needs("render", "tools ensure")
    settings = config.load()
    browser.ensure(settings, deps=install_deps)
    print(
        json.dumps(
            {
                "mermaid": bundle.version(settings),
                "bundle": str(bundle.path(settings)),
                "browser": settings.get("browser"),
            }
        )
    )


@pack_app.command("build")
def pack_build(
    source_ids: list[str] = Argument(help="Source ids from the `sources` config"),
    from_path: Path | None = Option(
        None,
        "--from",
        help="A download to build from, with one source. Default: the locked download, fetched.",
    ),
) -> None:
    """Build each source into the packs dir and print a JSON line for each.

    Raises:
        BadParameter: An unknown source or format, or `--from` with several sources.
    """
    _needs("packs", "pack build")
    from merrow.convert import CONVERTERS
    from merrow.sources.fetch import write_atomic

    settings = config.load()
    sources = config.sources(settings)
    if from_path and len(source_ids) > 1:
        raise BadParameter("--from builds one source: name only that one")
    for source_id in source_ids:
        source = sources.get(source_id)
        if source is None:
            raise BadParameter(f"no source {source_id!r} in the sources config")
        if source.format not in CONVERTERS:
            known = ", ".join(sorted(CONVERTERS))
            raise BadParameter(
                f"source {source_id!r} has format {source.format!r}, not one of {known}"
            )
    limits = config.limits(settings)
    for source_id in source_ids:
        source = sources[source_id]
        download = from_path or _fetch_locked(settings, source_id, limits)
        built = CONVERTERS[source.format](download, source, limits)
        out = config.packs_dir(settings) / built.name
        data = json.dumps(built.data, separators=(",", ":")).encode("utf-8")
        write_atomic(out, data)
        report = {"pack": str(out), "bytes": out.stat().st_size, **built.report}
        print(json.dumps(report))


def _fetch_locked(settings: Any, source_id: str, limits: Limits) -> Path:
    pin = lock.pins(settings.get("lock")).get(source_id)
    if pin is None:
        raise BadParameter(
            f"source {source_id!r} has no lock entry: run `merrow source update`"
        )
    from merrow.sources import fetch

    return fetch.fetch(config.cache_dir(settings), source_id, pin, limits)


@source_app.command("update")
def source_update(
    lock_path: Path = Option(..., "--lock", help="The lock file to rewrite"),
) -> None:
    """Detect each source's newest release, re-pin what moved, rewrite the lock.

    Prints one JSON object per changed or failed source. Exits 1 when any failed.
    """
    _needs("packs", "source update")
    from merrow.sources import detect

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
    _needs("packs", "source fetch")
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
    where: str = Option(
        "", "--destination", help="Destination, default the configured one"
    ),
) -> None:
    """Render each diagram once per theme of the destination. Prints one JSON line per SVG.

    A diagram the profile manages takes that theme's look first, so a dark
    render isn't the light frontmatter on a dark page.
    """
    _needs("render", "diagram render")
    _one_output_each(files)
    settings = config.load()
    pages = destination.load(settings, where or None).themes
    items = [diagram for path in files for diagram in render.diagrams(path)]
    by_ref = objects.by_class_name(objects.library(settings))
    for theme in pages:
        shown = profile.load(settings, None, theme, pages)
        themed = [
            render.Diagram(d.name, apply.apply(d.source, shown, by_ref))
            if apply.managed(d.source, by_ref)
            else d
            for d in items
        ]
        for written in render.render(themed, out_dir, settings, [theme], pages):
            print(json.dumps(written))


type Loaded = dict[tuple[str | None, str | None], profile.Profile]


def _written(
    path: Path,
    settings: Any,
    name: str,
    loaded: Loaded,
    theme: str | None = None,
    pages: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[str, profile.Profile]:
    """Return a diagram file as Mermaid and the profile it's drawn in.

    The profile is `name`, else the file's own, else the configured one, and
    `loaded` caches each by name and theme. `pages` is a destination's themes.

    Raises:
        ValueError: The file isn't YAML or JSON, or its graph or objects can't be drawn.
    """
    found = spec.read(path)
    key = (name or found.profile, theme)
    if key not in loaded:
        loaded[key] = profile.load(settings, key[0], theme, pages)
    shown = loaded[key]
    graph = spec.graph(found, patterns.library(settings))
    library = objects.library(settings)
    library |= {
        key: objects.entry(key, fields) for key, fields in found.objects.items()
    }
    source = write.diagram(
        graph, shown, library, found.title, found.description, found.direction
    )
    return source, shown


@graph_app.command("schema")
def graph_schema() -> None:
    """Print the diagram file's JSON Schema."""
    print(json.dumps(spec.schema(), indent=1))


@graph_app.command("validate")
def graph_validate(
    files: list[Path] = Argument(help="Diagram files, YAML or JSON"),
    name: str = Option("", "--profile", help="Profile, default the configured one"),
    as_json: bool = Option(False, "--json", help="Print the results as JSON"),
) -> None:
    """Check each file draws and passes lint's source pass. Exits 1 on any problem."""
    settings = config.load()
    loaded: Loaded = {}
    names = frozenset(objects.by_class_name(objects.library(settings)))
    report = {}
    for path in files:
        try:
            source, shown = _written(path, settings, name, loaded)
        except ValueError as error:
            report[str(path)] = [str(error)]
            continue
        block = diagram_check.Block(path.name, source, None, None)
        found = diagram_check.source_problems(
            block, diagram_check.CLASS_LINES, shown, names
        )
        report[str(path)] = findings.unwaived(found, shown.waive)
    if as_json:
        print(json.dumps(report, indent=1))
    else:
        for path, problems in report.items():
            print(f"{'FAIL' if problems else 'ok  '}  {path}")
            print("".join(f"        {problem}\n" for problem in problems), end="")
    if any(report.values()):
        raise Exit(1)


@skill_app.command("install")
def skill_install(
    to: Path | None = Option(None, "--to", help="Skills dir, default `skill_dir`"),
) -> None:
    """Copy merrow's agent skill into a skills dir. Prints the installed SKILL.md."""
    source = Path(str(files("merrow") / "skill"))
    front = (source / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
    root = to or Path(str(config.load().get("skill_dir"))).expanduser()
    target = root / str(yaml.safe_load(front)["name"])
    shutil.copytree(source, target, dirs_exist_ok=True)
    print(target / "SKILL.md")


def _one_output_each(files: list[Path]) -> None:
    """Refuse two files that would write the same output name.

    Raises:
        BadParameter: Two files share a stem.
    """
    seen: dict[str, Path] = {}
    for path in files:
        if path.stem in seen:
            raise BadParameter(f"{seen[path.stem]} and {path} both write {path.stem}")
        seen[path.stem] = path


@graph_app.command("write")
def graph_write(
    files: list[Path] = Argument(help="Diagram files, YAML or JSON"),
    out_dir: Path = Option(..., "--out", help="Directory for the .mmd files"),
    name: str = Option("", "--profile", help="Profile, default the configured one"),
) -> None:
    """Write each file as Mermaid, with no browser and no SVG. Prints one JSON line per file."""
    _one_output_each(files)
    settings = config.load()
    out_dir.mkdir(parents=True, exist_ok=True)
    loaded: Loaded = {}
    for path in files:
        try:
            source = _written(path, settings, name, loaded)[0]
        except ValueError as error:
            raise BadParameter(f"{path}: {error}") from error
        target = out_dir / f"{path.stem}.mmd"
        target.write_text(source, encoding="utf-8", newline="\n")
        print(json.dumps({"diagram": path.stem, "mmd": str(target)}))


@graph_app.command("render")
def graph_render(
    files: list[Path] = Argument(help="Diagram files, YAML or JSON"),
    out_dir: Path = Option(..., "--out", help="Directory for the .mmd and SVGs"),
    name: str = Option("", "--profile", help="Profile, default the configured one"),
    where: str = Option(
        "", "--destination", help="Destination, default the configured one"
    ),
    page: bool = Option(
        False, "--page", help="Print the Markdown that puts each diagram on a page"
    ),
) -> None:
    """Write each file as Mermaid, then render it. Prints one JSON line per SVG.

    Each theme of the destination draws from the profile in that theme, and
    `<file>.mmd` is the profile with no theme, the same for every destination.
    `--page` adds a JSON line a diagram with its `page`: the fence, or the
    image lines where the destination's renderer can't draw it.
    """
    _needs("render", "graph render")
    _one_output_each(files)
    settings = config.load()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = destination.load(settings, where or None)
    pages = target.themes
    themes = list(pages)
    icon_refs = [re.compile(p) for p in settings.get("lint")["icon_refs"]]
    loaded: Loaded = {}
    for path in files:
        try:
            sources: dict[str | None, str] = {
                None: _written(path, settings, name, loaded)[0]
            }
            for theme in themes:
                sources[theme] = _written(path, settings, name, loaded, theme, pages)[0]
        except ValueError as error:
            raise BadParameter(f"{path}: {error}") from error
        (out_dir / f"{path.stem}.mmd").write_text(
            sources[None], encoding="utf-8", newline="\n"
        )
        for theme in themes:
            item = render.Diagram(path.stem, sources[theme])
            for written in render.render([item], out_dir, settings, [theme], pages):
                print(json.dumps(written))
        if page:
            has_icon = any(found.search(sources[None]) for found in icon_refs)
            block = target.page_block(path.stem, sources[None], has_icon)
            print(json.dumps({"diagram": path.stem, "page": block}))


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
    """Set each diagram's frontmatter and class block from the profile, in place.

    Prints `changed` or `unchanged` a file and exits 0. A missing file or
    profile, an object the profile can't style, or a class block marker with
    no partner exits 2 with the reason, and no file is written.
    """
    settings = config.load()
    shown = profile.load(settings, name or None)
    by_ref = objects.by_class_name(objects.library(settings))
    planned = {}
    for path in files:
        try:
            planned[path] = apply.applied(path, shown, by_ref)
        except ValueError as error:
            raise BadParameter(f"{path}: {error}") from error
    for path, (old, new) in planned.items():
        if new != old:
            path.write_text(new, encoding="utf-8", newline="\n")
        print(f"{'changed' if new != old else 'unchanged'}  {path}")


@diagram_app.command("lint")
def diagram_lint(
    files: list[Path] = Argument(
        help="`.mmd` files, or Markdown whose fences are checked"
    ),
    no_render: bool = Option(
        False, "--no-render", help="Source checks only, no browser"
    ),
    as_json: bool = Option(False, "--json", help="Print the results as JSON"),
    name: str = Option("", "--profile", help="Profile, default the configured one"),
    where: str = Option(
        "", "--destination", help="Destination, default the configured one"
    ),
) -> None:
    """Check diagrams against the standard and the built packs. Exits 1 on any failure."""
    if not no_render:
        _needs("render", "diagram lint (--no-render needs no extra)")
    argv = [str(path) for path in files]
    argv += ["--profile", name] if name else []
    argv += ["--destination", where] if where else []
    argv += ["--no-render"] if no_render else []
    argv += ["--json"] if as_json else []
    code = diagram_check.main(argv)
    if code:
        raise Exit(code)


def run() -> None:
    """Run the CLI, printing a bad file, profile, render, browser or download as one line."""
    try:
        app()
    except (OSError, profile.ProfileError, MerrowError) as error:
        print(f"merrow: {error}", file=sys.stderr)
        sys.exit(2)
