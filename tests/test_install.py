"""install.sh fetches uv only as the pinned build and refuses anything else."""

import subprocess
from pathlib import Path

import pytest

INSTALL = Path(__file__).resolve().parent.parent / "install.sh"


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ('fetch() { echo tampered > "$2"; }', "failed its SHA256 check"),
        ("uv_target() { echo riscv64-unknown-linux-gnu; }", "no uv build for riscv64"),
    ],
    ids=["tampered-download", "unpinned-platform"],
)
def test_install_uv_refuses(tmp_path, override, says):
    bin_dir = tmp_path / "bin"
    script = f'source "{INSTALL}"; {override}; install_uv "{bin_dir}"'
    result = subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 1
    assert says in result.stderr
    assert not (bin_dir / "uv").exists()
