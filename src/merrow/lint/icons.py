"""Every icon a diagram names must exist in a built pack, as an icon or an alias."""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


def known_keys(packs_dir: Path) -> set[str]:
    """Return every `prefix:name` the Iconify packs in the dir define, aliases included."""
    keys = set()
    for pack in packs_dir.glob("*.json"):
        data = json.loads(pack.read_text(encoding="utf-8"))
        if not (isinstance(data, Mapping) and "icons" in data and "prefix" in data):
            continue
        for name in [*data["icons"], *data.get("aliases", {})]:
            keys.add(f"{data['prefix']}:{name}")
    return keys


def unresolved(
    source: str, patterns: Sequence[re.Pattern[str]], known: Iterable[str]
) -> list[str]:
    """Return each icon key the diagram names that no pack defines, in order, once."""
    available = set(known)
    missing: list[str] = []
    for pattern in patterns:
        for found in pattern.finditer(source):
            key = found.group(1)
            if key not in available and key not in missing:
                missing.append(key)
    return missing
