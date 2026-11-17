"""Verified downloads into the cache, keyed by the lock's SHA-256."""

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from scalo.http import HttpClient
from scalo.logger import logger

from merrow.model import Limits
from merrow.sources.lock import Pin


class DownloadError(RuntimeError):
    """A download failed, was too large, or didn't match its pin."""


def download(url: str, limits: Limits) -> bytes:
    """Return the body at `url`.

    SHORTCUT: the body is held in memory. Stream it once a source passes a few
    hundred MB, which `limits.download_bytes` bounds until then.

    Raises:
        DownloadError: The body is over `limits.download_bytes`.
    """
    # Publisher downloads redirect routinely (GitHub archives to codeload). No
    # credentials are sent, so following one leaks nothing.
    with HttpClient(
        timeout=limits.download_timeout_seconds, follow_redirects=True
    ) as client:
        response = client.get(url)
    size = len(response.content)
    if size > limits.download_bytes:
        raise DownloadError(f"{url} is {size} bytes, over {limits.download_bytes}")
    return response.content


def cache_path(cache_dir: Path, source: str, pin: Pin) -> Path:
    """Return where a pinned download lives in the cache."""
    name = PurePosixPath(urlparse(pin.url).path).name or "download"
    return cache_dir / "sources" / source / pin.sha256[:16] / name


def fetch(cache_dir: Path, source: str, pin: Pin, limits: Limits) -> Path:
    """Return the cached download for a pin, downloading it when missing.

    Raises:
        DownloadError: The download failed or its SHA-256 isn't the pinned one.
    """
    target = cache_path(cache_dir, source, pin)
    if target.is_file() and _sha256(target.read_bytes()) == pin.sha256:
        return target
    logger.info("downloading source", source=source, url=pin.url)
    data = download(pin.url, limits)
    digest = _sha256(data)
    if digest != pin.sha256:
        raise DownloadError(
            f"{source}: {pin.url} has SHA-256 {digest}, the lock pins {pin.sha256}"
        )
    write_atomic(target, data)
    return target


def write_atomic(target: Path, data: bytes) -> None:
    """Write `data` to `target` through a rename, so a reader never sees a partial file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(dir=target.parent, prefix=".partial-")
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    Path(staging).replace(target)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
