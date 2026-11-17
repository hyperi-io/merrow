"""merrow settings: scalo's config cascade with the reference repos layered in."""

from importlib.resources import files
from pathlib import Path
from typing import Any

from scalo.config import get_config
from scalo.runtime import RuntimeEnvironment

from merrow.model import Limits, Source

ENV_PREFIX = "MERROW"
BASE_LAYERS = [
    Path(str(files("merrow") / "defaults.yaml")),
    Path(str(files("merrow") / "sources.yaml")),
    Path(str(files("merrow") / "sources.lock.yaml")),
    Path(str(files("merrow") / "profiles.yaml")),
    Path(str(files("merrow") / "patterns.yaml")),
    Path(str(files("merrow") / "objects.yaml")),
]


def reference_layers(settings: Any) -> list[Path]:
    """Return each listed reference repo's data file, in layer order.

    Raises:
        FileNotFoundError: A listed reference repo has no data file.
    """
    name = settings.get("reference_file")
    layers = []
    for repo in settings.get("references", []):
        layer = Path(repo).expanduser().resolve() / name
        if not layer.is_file():
            raise FileNotFoundError(f"reference repo {repo} has no {name}")
        layers.append(layer)
    return layers


def data_file(settings: Any, relative: str) -> Path:
    """Return a data file from the last reference repo that has it, else merrow's.

    Raises:
        FileNotFoundError: No reference repo and not merrow has it.
    """
    repos = [Path(r).expanduser().resolve() for r in settings.get("references", [])]
    for root in [*reversed(repos), Path(str(files("merrow")))]:
        if (root / relative).is_file():
            return root / relative
    raise FileNotFoundError(f"{relative} is in no reference repo and not in merrow")


def cache_dir(settings: Any) -> Path:
    """Return the download and tool cache: `cache_dir` if set, else scalo's."""
    configured = settings.get("cache_dir")
    if configured:
        return Path(configured).expanduser()
    mode = settings.get("runtime_mode")
    force = None if mode in (None, "", "auto") else str(mode)
    return (
        RuntimeEnvironment("merrow", force_mode=force)
        .detect_runtime()
        .effective_cache_dir
    )


def packs_dir(settings: Any) -> Path:
    """Return where built icon packs go: `packs_dir` if set, else under the cache."""
    configured = settings.get("packs_dir")
    if configured:
        return Path(configured).expanduser()
    return cache_dir(settings) / "packs"


def sources(settings: Any) -> dict[str, Source]:
    """Return every configured source, its format defaults filled in, by id."""
    formats = settings.get("formats") or {}
    return {
        source_id: Source.from_config(source_id, entry, formats)
        for source_id, entry in (settings.get("sources") or {}).items()
    }


def limits(settings: Any) -> Limits:
    """Return the size and time caps and the ignore pattern."""
    return Limits.from_config(settings.get("limits"), settings.get("ignore"))


def load() -> Any:
    """Return merrow's settings: base layer, then each reference repo, later wins.

    The reference list itself comes from the cascade, so the first pass reads
    only that and the second merges the repos' data files in.
    """
    base = [str(layer) for layer in BASE_LAYERS]
    first = get_config(additional_files=base, env_prefix=ENV_PREFIX)
    layers = [*BASE_LAYERS, *reference_layers(first)]
    return get_config(
        additional_files=[str(layer) for layer in layers], env_prefix=ENV_PREFIX
    )
