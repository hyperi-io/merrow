"""New releases: nvchecker checks each source, and changed downloads are re-pinned.

A source's `check:` config is an nvchecker entry, passed through as is, so any
of nvchecker's sources (regex on a page, GitHub commits or releases, npm, HTTP
headers) works without code. Its `url:` template takes the `{version}` and
`{revision}` nvchecker reports.

A publisher with a stable URL and no version signal at all (no ETag, no date,
no listing) uses `check: {source: content}`: merrow downloads it and the
content hash is the version.
"""

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import tomli_w
from scalo.logger import logger

from merrow import proc
from merrow.model import Limits, Source
from merrow.sources.fetch import download
from merrow.sources.lock import Pin

# merrow's own check type, beside nvchecker's: the download's hash is its version.
CONTENT_CHECK = "content"


class DetectError(RuntimeError):
    """nvchecker failed outright, or a source's URL template is unusable."""


@dataclass(frozen=True, slots=True)
class Change:
    """One source whose pin moved, or failed to.

    Attributes:
        source: The source id.
        old: The previous version, or None for a first pin.
        new: The detected version, or None when detection failed.
        error: Why the source wasn't re-pinned, when it wasn't.
    """

    source: str
    old: str | None
    new: str | None
    error: str | None = None


def detect(
    sources: Iterable[Source], tokens: Mapping[str, str], timeout: float
) -> dict[str, dict[str, str]]:
    """Return what nvchecker reports per source id: `version`, maybe `revision`.

    `tokens` maps an nvchecker key name (`github`) to the env var holding it.
    A source nvchecker can't check is missing from the result.

    Raises:
        DetectError: nvchecker itself failed to run.
    """
    entries = {
        source.id: dict(source.check)
        for source in sources
        if source.check and source.check.get("source") != CONTENT_CHECK
    }
    if not entries:
        return {}
    with tempfile.TemporaryDirectory(prefix="merrow-nvchecker-") as work:
        root = Path(work)
        settings: dict[str, object] = {"oldver": "old.json", "newver": "new.json"}
        keys = {
            name: os.environ[var] for name, var in tokens.items() if os.environ.get(var)
        }
        if keys:
            keyfile = root / "keys.toml"
            keyfile.write_bytes(tomli_w.dumps({"keys": keys}).encode("utf-8"))
            keyfile.chmod(0o600)
            settings["keyfile"] = "keys.toml"
        (root / "old.json").write_text('{"version": 2, "data": {}}', encoding="utf-8")
        config = root / "nvchecker.toml"
        config.write_bytes(
            tomli_w.dumps({"__config__": settings, **entries}).encode("utf-8")
        )
        argv = [
            sys.executable,
            "-m",
            "nvchecker",
            "-c",
            str(config),
            "--logger",
            "json",
        ]
        result = proc.run(argv, timeout=timeout)
        newver = root / "new.json"
        if result.returncode != 0 or not newver.is_file():
            raise DetectError(
                f"nvchecker exited {result.returncode}: {result.stderr[-500:]}"
            )
        data = json.loads(newver.read_text(encoding="utf-8"))["data"]
    for line in result.stdout.splitlines():
        event = json.loads(line) if line.startswith("{") else {}
        if event.get("level") in ("error", "warning"):
            logger.warning("nvchecker", **{k: str(v) for k, v in event.items()})
    return {name: {k: str(v) for k, v in found.items()} for name, found in data.items()}


def resolve_url(source: Source, found: Mapping[str, str]) -> str:
    """Return the source's download URL for what detection found.

    Raises:
        DetectError: The source has no `url`, or it names a field detection lacks.
    """
    if not source.url:
        raise DetectError(f"source {source.id!r} has a check but no url")
    try:
        return source.url.format(**found)
    except KeyError as missing:
        raise DetectError(
            f"source {source.id!r} url needs {missing}, detection gave {sorted(found)}"
        ) from None


def update(
    sources: Iterable[Source],
    pins: Mapping[str, Pin],
    found: Mapping[str, Mapping[str, str]],
    limits: Limits,
) -> tuple[dict[str, Pin], list[Change]]:
    """Return the new pins and what changed: a source whose URL moved is downloaded and re-pinned.

    A source that failed detection or download keeps its old pin and is listed with
    its error, so one bad vendor page never blocks the rest.
    """
    updated = dict(pins)
    changes = []
    for source in sources:
        if not source.check:
            continue
        old = pins.get(source.id)
        old_version = old.version if old else None
        by_content = source.check.get("source") == CONTENT_CHECK
        if not by_content and source.id not in found:
            changes.append(Change(source.id, old_version, None, "detection failed"))
            continue
        detected = {} if by_content else found[source.id]
        try:
            url = resolve_url(source, detected)
            if not by_content and old and old.url == url:
                continue
            data = download(url, limits)
        except Exception as error:  # noqa: BLE001 -- reported per source, never stops the rest
            changes.append(
                Change(source.id, old_version, detected.get("version"), str(error))
            )
            continue
        digest = hashlib.sha256(data).hexdigest()
        if old and old.sha256 == digest:
            continue
        version = digest[:12] if by_content else detected["version"]
        updated[source.id] = Pin(version, url, digest, len(data))
        changes.append(Change(source.id, old_version, version))
    return updated, changes
