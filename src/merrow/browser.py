"""The browser for the steps that need a laid-out page: lint's render pass and post-render."""

from typing import Any


def launch(driver: Any) -> Any:
    """Return a launched browser: the host's Chrome, else playwright's Chromium.

    Raises:
        SystemExit: Neither starts.
    """
    # Imported here so the steps that need no page run without playwright.
    from playwright.sync_api import Error

    try:
        return driver.chromium.launch(channel="chrome")
    except Error:
        try:
            return driver.chromium.launch()
        except Error as failure:
            raise SystemExit(
                f"no Chrome or Chromium to render with: {failure}"
            ) from failure
