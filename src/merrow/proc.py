"""Run a tool merrow drives (playwright's browser install, nvchecker) and capture its text."""

import subprocess
from collections.abc import Sequence
from pathlib import Path


def run(
    argv: Sequence[str], cwd: Path | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Return the finished process, its output decoded as UTF-8. Never raises on exit code."""
    return subprocess.run(  # noqa: S603 -- argv is built by merrow, never a shell
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def tail(result: subprocess.CompletedProcess[str], lines: int = 5) -> str:
    """Return the last lines of a failed run's stderr, or stdout when stderr is empty."""
    text = (result.stderr or result.stdout).strip()
    return " | ".join(text.splitlines()[-lines:])
