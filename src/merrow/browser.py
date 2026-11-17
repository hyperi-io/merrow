"""The browser for the steps that need a laid-out page: lint's render pass and post-render."""

from pathlib import Path
from typing import Any


def launch(driver: Any, executable: Path | None = None) -> Any:
    """Return a launched browser: `executable`, else the host's Chrome, else playwright's Chromium.

    Raises:
        SystemExit: None of them starts.
    """
    # Imported here so the steps that need no page run without playwright.
    from playwright.sync_api import Error

    if executable is not None:
        try:
            return driver.chromium.launch(executable_path=str(executable))
        except Error:
            pass
    try:
        return driver.chromium.launch(channel="chrome")
    except Error:
        try:
            return driver.chromium.launch()
        except Error as failure:
            raise SystemExit(
                f"no Chrome or Chromium to render with: {failure}"
            ) from failure
