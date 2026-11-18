"""Run a tool merrow drives (playwright's browser install, nvchecker) and capture its text."""

import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


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
            stdout, stderr = process.communicate()
            said = [stdout, stderr, f"timed out after {timeout:g} s"]
            return subprocess.CompletedProcess(
                list(argv), -1, stdout, "\n".join(filter(None, said))
            )
        except BaseException:
            _stop(process)
            raise
    return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)


def _stop(process: subprocess.Popen[str]) -> None:
    """Kill the tool and every process it started.

    SHORTCUT: Windows kills the tool only. Upgrade if a Windows install outlives its timeout.
    """
    if sys.platform == "win32":
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)


def tail(result: subprocess.CompletedProcess[str], lines: int = 5) -> str:
    """Return the last lines of a failed run's stderr, or stdout when stderr is empty."""
    text = (result.stderr or result.stdout).strip()
    return " | ".join(text.splitlines()[-lines:])
