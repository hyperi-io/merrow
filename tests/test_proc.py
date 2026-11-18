"""Running the tools merrow drives: exit codes and timeouts come back, never raise."""

import sys
import time

import pytest

from merrow import proc

# A tool that starts a helper which holds its output open, as playwright's CLI does.
STALLS = (
    "import subprocess, sys; print('downloading', flush=True); "
    "subprocess.run([sys.executable, '-c', 'import time; time.sleep(30)'])"
)


@pytest.mark.parametrize(
    ("code", "timeout", "returncode", "tail_has"),
    [
        ("print('ok')", None, 0, []),
        ("import sys; print('half'); sys.exit(3)", None, 3, ["half"]),
        (STALLS, 1, -1, ["downloading", "timed out after 1 s"]),
    ],
    ids=["ok", "exit-code", "timeout-kills-the-helper-too"],
)
def test_run_returns_every_outcome(code, timeout, returncode, tail_has):
    started = time.monotonic()
    result = proc.run([sys.executable, "-c", code], timeout=timeout)
    assert time.monotonic() - started < 20, "a helper left running holds the pipes"
    assert result.returncode == returncode
    for text in tail_has:
        assert text in proc.tail(result)
