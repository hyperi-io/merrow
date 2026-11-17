"""Install the pinned npm tools behind render: mermaid-cli and its browser.

package.json and package-lock.json ship in the wheel and Renovate keeps them
current. `npm ci` checks every tarball's sha512 against the lock, and the
install directory is keyed by both files, so a bump installs fresh.
"""

import functools
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock
from scalo.logger import logger

from merrow import config, proc

NODE_DIR = Path(__file__).parent / "node"
MANIFEST = NODE_DIR / "package.json"
LOCKFILE = NODE_DIR / "package-lock.json"

# Written last, so a directory without it is a partial install.
_DONE = ".merrow-installed"


class NodeToolsError(RuntimeError):
    """The pinned npm tools could not be installed or found."""


def _require(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise NodeToolsError(
            f"{name} is not on PATH: install Node.js 22.13 or later, then rerun"
        )
    return path


def _run(argv: list[str], cwd: Path, timeout: float) -> None:
    result = proc.run(argv, cwd, timeout)
    if result.returncode != 0:
        step = " ".join(argv[1:3])
        raise NodeToolsError(f"{step} exited {result.returncode}: {proc.tail(result)}")


def install_dir(cache_dir: Path) -> Path:
    """Return the install directory for this exact manifest and lock pair."""
    key = hashlib.sha256(MANIFEST.read_bytes() + LOCKFILE.read_bytes())
    return cache_dir / "node-tools" / key.hexdigest()[:16]


def _bin(root: Path, package: str) -> Path:
    """Return the script a package's `bin` names, run with node on every OS."""
    package_dir = root / "node_modules" / package
    meta = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    bin_field = meta["bin"]
    if isinstance(bin_field, str):
        return package_dir / bin_field
    return package_dir / next(iter(bin_field.values()))


@functools.cache
def install(cache_dir: Path, browser: str, timeout: float) -> Path:
    """Return the installed tree, running `npm ci` and the browser install once.

    `browser` is puppeteer's name for the build it fetches, such as
    `chrome-headless-shell`.

    Raises:
        NodeToolsError: node or npm is missing, or an install step failed.
    """
    node = _require("node")
    npm = _require("npm")
    final = install_dir(cache_dir)
    if (final / _DONE).is_file():
        return final

    final.parent.mkdir(parents=True, exist_ok=True)
    # One install at a time per tree: concurrent puppeteer browser installs into
    # its shared cache corrupt each other.
    with FileLock(final.parent / f"{final.name}.lock"):
        if (final / _DONE).is_file():
            return final
        # Stage then rename, so a crash never leaves a tree that looks finished.
        staging = Path(tempfile.mkdtemp(prefix=f"{final.name}.", dir=final.parent))
        try:
            shutil.copyfile(MANIFEST, staging / "package.json")
            shutil.copyfile(LOCKFILE, staging / "package-lock.json")
            logger.info("installing pinned node tools", lock=str(LOCKFILE))
            npm_ci = [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
            _run(npm_ci, staging, timeout)
            # Install scripts stay off, so puppeteer's CLI fetches the browser
            # build its release pins, into puppeteer's default cache.
            puppeteer = str(_bin(staging, "puppeteer"))
            _run([node, puppeteer, "browsers", "install", browser], staging, timeout)
            (staging / _DONE).write_text("", encoding="utf-8", newline="\n")
            shutil.rmtree(final, ignore_errors=True)
            staging.rename(final)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return final


def installed(settings: Any) -> Path:
    """Return the installed tree for the settings' cache, browser and timeout.

    Raises:
        NodeToolsError: node or npm is missing, or an install step failed.
    """
    timeout = config.limits(settings).npm_timeout_seconds
    return install(config.cache_dir(settings), settings.get("browser"), timeout)


def mmdc(settings: Any) -> list[str]:
    """Return the argv prefix that runs the pinned mermaid-cli.

    Raises:
        NodeToolsError: node or npm is missing, or an install step failed.
    """
    return [_require("node"), str(_bin(installed(settings), "@mermaid-js/mermaid-cli"))]
