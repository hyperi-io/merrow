"""The shapes every part of merrow shares: a source, the limits, a build result.

A source is pure config: where its download comes from, how a new release is
detected, which converter reads it and that converter's options. A converter is
one function per format with the `Converter` signature, registered by format
name, so a new publisher in a known format needs config and no code.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Source:
    """One publisher source, from the `sources` config.

    Attributes:
        id: The key under `sources`.
        format: The converter that reads it, such as `svg` or `pptx`.
        prefix: The icon pack prefix diagrams use, such as `aws`.
        url: Download URL template. `{version}` and `{revision}` come from detection.
        check: The nvchecker entry that detects a new release, passed through as is.
        options: Everything else in the entry, for the converter to read.
    """

    id: str
    format: str
    prefix: str
    url: str | None = None
    check: Mapping[str, Any] | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(
        cls,
        source_id: str,
        entry: Mapping[str, Any],
        format_defaults: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> Source:
        """Return the source a `sources` config entry describes.

        The entry's format defaults (`formats.<format>`) fill any option the
        entry doesn't set.

        Raises:
            ValueError: The entry has no `format` or `prefix`.
        """
        defaults = (format_defaults or {}).get(str(entry.get("format")), {})
        entry = {**defaults, **entry}
        missing = [name for name in ("format", "prefix") if not entry.get(name)]
        if missing:
            raise ValueError(f"source {source_id!r} has no {', '.join(missing)}")
        known = {"format", "prefix", "url", "check"}
        return cls(
            id=source_id,
            format=str(entry["format"]),
            prefix=str(entry["prefix"]),
            url=entry.get("url"),
            check=entry.get("check"),
            options={k: v for k, v in entry.items() if k not in known},
        )


@dataclass(frozen=True, slots=True)
class Limits:
    """Size and time caps, and the paths every download ignores, from config."""

    member_bytes: int
    deck_bytes: int
    download_bytes: int
    group_name_chars: int
    download_timeout_seconds: float
    install_timeout_seconds: float
    detect_timeout_seconds: float
    ignore: re.Pattern[str] | None = None

    @classmethod
    def from_config(cls, limits: Mapping[str, Any], ignore: str | None) -> Limits:
        """Return the limits a `limits` config mapping and `ignore` regex set."""
        return cls(
            ignore=re.compile(ignore) if ignore else None,
            member_bytes=int(limits["member_bytes"]),
            deck_bytes=int(limits["deck_bytes"]),
            download_bytes=int(limits["download_bytes"]),
            group_name_chars=int(limits["group_name_chars"]),
            download_timeout_seconds=float(limits["download_timeout_seconds"]),
            install_timeout_seconds=float(limits["install_timeout_seconds"]),
            detect_timeout_seconds=float(limits["detect_timeout_seconds"]),
        )


@dataclass(frozen=True, slots=True)
class Built:
    """What a converter made from one download.

    Attributes:
        name: The file name under the packs dir, such as `aws.json`.
        data: The JSON to write there.
        report: What was dropped or skipped and why, for review.
    """

    name: str
    data: Mapping[str, Any]
    report: Mapping[str, Any]


type Converter = Callable[[Path, Source, Limits], Built]


def tally(counts: dict[str, int], key: str) -> None:
    """Count one more `key`. Reports use plain dicts, which `asdict` copies intact."""
    counts[key] = counts.get(key, 0) + 1
