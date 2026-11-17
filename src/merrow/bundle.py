"""The Mermaid bundle render and lint run in a browser page.

npm/package-lock.json pins it and Renovate keeps it current. merrow downloads
the tarball the lock names, checks it against the lock's sha512 integrity, and
caches the bundle file from it, so no Node.js install is needed.
"""

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

from merrow import config
from merrow.sources.fetch import download, write_atomic

LOCKFILE = Path(__file__).parent / "npm" / "package-lock.json"


class BundleError(RuntimeError):
    """The pinned bundle could not be fetched, or didn't match the lock."""


def _pin(package: str) -> dict[str, str]:
    """Return the lock's `version`, `resolved` and `integrity` for a package."""
    lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    return lock["packages"][f"node_modules/{package}"]


def version(settings: Any) -> str:
    """Return the Mermaid version the lock pins."""
    return _pin(settings.get("render")["bundle"]["package"])["version"]


def _integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


def path(settings: Any) -> Path:
    """Return the cached bundle file, downloading the pinned tarball when missing.

    Raises:
        BundleError: The tarball doesn't match the lock, or lacks the bundle file.
    """
    wanted = settings.get("render")["bundle"]
    pin = _pin(wanted["package"])
    member = str(wanted["file"])
    target = (
        config.cache_dir(settings)
        / "bundle"
        / f"{wanted['package']}-{pin['version']}"
        / Path(member).name
    )
    if target.is_file():
        return target
    data = download(pin["resolved"], config.limits(settings))
    if _integrity(data) != pin["integrity"]:
        raise BundleError(f"{pin['resolved']} doesn't match the lock's integrity")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        try:
            handle = archive.extractfile(member)
        except KeyError as missing:
            raise BundleError(f"{pin['resolved']} has no {member}") from missing
        if handle is None:
            raise BundleError(f"{pin['resolved']}: {member} is not a file")
        write_atomic(target, handle.read())
    return target
