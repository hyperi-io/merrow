"""Verified downloads into the cache, keyed by the lock's SHA-256."""

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx
import stamina
from scalo.crypto import CryptoProfile, ssl_context
from scalo.logger import logger

from merrow import MerrowError
from merrow.model import Limits
from merrow.sources.lock import Pin


class DownloadError(MerrowError):
    """A download failed, was too large, or didn't match its pin."""


@stamina.retry(on=httpx.TransportError, attempts=3)
def download(url: str, limits: Limits) -> bytes:
    """Return the body at `url`, read in chunks and stopped past `limits.download_bytes`.

    Raises:
        DownloadError: The server refused it, or the body is over `limits.download_bytes`.
    """
    cap = limits.download_bytes
    # Publisher downloads redirect routinely (GitHub archives to codeload). No
    # credentials are sent, so following one leaks nothing.
    with (
        httpx.Client(
            verify=ssl_context(CryptoProfile.PROD),
            timeout=limits.download_timeout_seconds,
            follow_redirects=True,
        ) as client,
        client.stream("GET", url) as response,
    ):
        if response.is_error:
            raise DownloadError(f"{url}: HTTP {response.status_code}")
        declared = int(response.headers.get("content-length") or 0)
        if declared > cap:
            raise DownloadError(f"{url} is {declared} bytes, over {cap}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > cap:
                raise DownloadError(f"{url} is over {cap} bytes")
    return bytes(body)


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
