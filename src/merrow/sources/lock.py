"""The source lock: each source's pinned version, URL, SHA-256 and size.

The lock is YAML under a top-level `lock:` key, so the config cascade merges it
like every other layer: merrow's packaged lock first, then a reference repo's.
Only `merrow source update` writes one.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class Pin:
    """One locked download.

    Attributes:
        version: What detection reported, opaque to merrow.
        url: Where the bytes come from.
        sha256: Hex digest the download must match.
        bytes: Size of the download.
    """

    version: str
    url: str
    sha256: str
    bytes: int


def pins(settings_lock: Mapping[str, Mapping[str, object]] | None) -> dict[str, Pin]:
    """Return the merged `lock` config as pins, by source id."""
    return {
        source: Pin(
            version=str(entry["version"]),
            url=str(entry["url"]),
            sha256=str(entry["sha256"]),
            bytes=int(str(entry["bytes"])),
        )
        for source, entry in (settings_lock or {}).items()
    }


def read(path: Path) -> dict[str, Pin]:
    """Return the pins in one lock file, or none when it doesn't exist yet."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return pins(data.get("lock"))


def write(path: Path, locked: Mapping[str, Pin]) -> None:
    """Write the pins to `path`, sorted by source id."""
    body = {"lock": {source: asdict(locked[source]) for source in sorted(locked)}}
    header = "# Written by `merrow source update`. Edit the sources, not this file.\n"
    text = header + yaml.safe_dump(body, sort_keys=False)
    path.write_text(text, encoding="utf-8", newline="\n")
