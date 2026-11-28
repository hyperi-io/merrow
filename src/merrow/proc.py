"""Run a tool merrow drives (playwright's browser install, nvchecker) and capture its text."""

import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

# How long a killed tool gets to close its pipes before its output is dropped.
_DRAIN_SECONDS = 5.0


def run(
    argv: Sequence[str], cwd: Path | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Return the finished process, its output decoded as UTF-8.

    Never raises on exit code. A timeout kills the tool and what it started,
    and returns code -1 with what it printed and the timeout at the end of stderr.
    """
    with subprocess.Popen(  # noqa: S603 -- argv is built by merrow, never a shell
        list(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=sys.platform != "win32",
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(process)
            try:
                stdout, stderr = process.communicate(timeout=_DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                # A grandchild that survived the kill still holds the pipes.
                stdout, stderr = "", ""
            said = [stdout, stderr, f"timed out after {timeout:g} s"]
            return subprocess.CompletedProcess(
                list(argv), -1, stdout, "\n".join(filter(None, said))
            )
        except BaseException:
            _stop(process)
            raise
    return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)


def _stop(process: subprocess.Popen[str]) -> None:
    """Kill the tool and every process it started."""
    if sys.platform == "win32":
        # taskkill ships with Windows, and the argv is fixed.
        subprocess.run(  # noqa: S603
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],  # noqa: S607
            capture_output=True,
            check=False,
        )
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)


def tail(result: subprocess.CompletedProcess[str], lines: int = 5) -> str:
    """Return the last lines of a failed run's stderr, or stdout when stderr is empty."""
    text = (result.stderr or result.stdout).strip()
    return " | ".join(text.splitlines()[-lines:])
