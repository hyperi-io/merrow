"""The browser every laid-out page runs in: render, post-render and lint."""

import functools
import subprocess
import sys
from typing import Any

from scalo.logger import logger

from merrow import MerrowError, config, proc


class BrowserError(MerrowError):
    """No browser could be installed or launched."""


@functools.cache
def _install(name: str, timeout: float) -> str:
    """Return "" once playwright has `name`, else its error. A no-op when installed."""
    result = proc.run(
        [sys.executable, "-m", "playwright", "install", name], timeout=timeout
    )
    return "" if result.returncode == 0 else proc.tail(result)


def _system_libraries(name: str, timeout: float) -> str:
    """Return "" once apt has the libraries `name` needs, else why not.

    Runs on the terminal, so the sudo playwright starts can ask for a password.
    """
    argv = [sys.executable, "-m", "playwright", "install-deps", name]
    try:
        code = subprocess.run(argv, timeout=timeout, check=False).returncode  # noqa: S603
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout:g} s"
    return "" if code == 0 else f"exit {code}"


def ensure(settings: Any, deps: bool = False) -> None:
    """Install the browser build this playwright release pins, with its system libraries when `deps`.

    Raises:
        BrowserError: The install failed, for example offline or, with `deps`, without sudo.
    """
    timeout = config.limits(settings).install_timeout_seconds
    name = str(settings.get("browser"))
    failed = _install(name, timeout)
    if not failed and deps:
        failed = _system_libraries(name, timeout)
    if failed:
        raise BrowserError(f"playwright install {name}: {failed}")


def launch(driver: Any, settings: Any) -> Any:
    """Return a launched browser: playwright's pinned build, else the host's Chrome.

    The pinned build lays text out the same on every host, so it comes first.

    Raises:
        BrowserError: Neither starts.
    """
    # Imported here so the steps that need no page run without playwright.
    from playwright.sync_api import Error

    try:
        ensure(settings)
        return driver.chromium.launch()
    except (BrowserError, Error) as pinned:
        logger.warning(
            "pinned browser failed, using the host's Chrome", error=str(pinned)
        )
        try:
            return driver.chromium.launch(channel="chrome")
        except Error as chrome:
            raise BrowserError(
                f"no browser to render with: {pinned}; Chrome: {chrome}"
            ) from chrome


def offline(page: Any) -> None:
    """Abort every request `page` makes, so diagram content can't reach the network or local services."""
    page.route("**/*", lambda route: route.abort())
