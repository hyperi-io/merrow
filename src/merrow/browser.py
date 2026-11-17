"""The browser every laid-out page runs in: render, post-render and lint."""

import functools
import sys
from typing import Any

from merrow import config, proc


class BrowserError(RuntimeError):
    """No browser could be installed or launched."""


@functools.cache
def _install(name: str, deps: bool, timeout: float) -> str:
    """Return "" once playwright has `name`, else its error. A no-op when installed."""
    argv = [sys.executable, "-m", "playwright", "install", name]
    result = proc.run([*argv, "--with-deps"] if deps else argv, timeout=timeout)
    return "" if result.returncode == 0 else proc.tail(result)


def ensure(settings: Any, deps: bool = False) -> None:
    """Install the browser build this playwright release pins, with its system libraries when `deps`.

    Raises:
        BrowserError: The install failed, for example offline or, with `deps`, without root.
    """
    timeout = config.limits(settings).install_timeout_seconds
    failed = _install(str(settings.get("browser")), deps, timeout)
    if failed:
        raise BrowserError(f"playwright install {settings.get('browser')}: {failed}")


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
        try:
            return driver.chromium.launch(channel="chrome")
        except Error as chrome:
            raise BrowserError(
                f"no browser to render with: {pinned}; Chrome: {chrome}"
            ) from chrome
