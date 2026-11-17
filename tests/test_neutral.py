"""merrow is general purpose: one company's names belong in its reference repo."""

import re
import shutil
from pathlib import Path

from merrow import proc

ROOT = Path(__file__).resolve().parents[1]
# A product or company name, and where each may appear.
NAMES = {
    re.compile(r"(?i)\bdfe\b"): frozenset(),
    re.compile(r"\bHyperI\b(?! Team)"): frozenset({".hyperi-ci.yaml"}),
    re.compile(r"\bhyperi-merrow\b"): frozenset({"README.md", "reference/README.md"}),
}
# Lock files hold hashes, and this file names what it looks for.
SKIPPED = re.compile(
    r"(^|/)(uv\.lock|package-lock\.json)$|\.(png|svg|zip|vssx)$|^tests/test_neutral\.py$"
)


def tracked() -> list[str]:
    git = shutil.which("git")
    assert git, "git is on PATH"
    listed = proc.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard"], ROOT
    )
    assert listed.returncode == 0, proc.tail(listed)
    return [path for path in listed.stdout.splitlines() if not SKIPPED.search(path)]


def test_no_company_or_product_name_outside_its_allowed_files():
    found = []
    for path in tracked():
        file = ROOT / path
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for pattern, allowed in NAMES.items():
            if path in allowed:
                continue
            found += [
                f"{path}:{text.count(chr(10), 0, hit.start()) + 1}: {hit[0]}"
                for hit in pattern.finditer(text)
            ]
    assert found == []


def test_the_check_catches_a_name_in_a_shipped_file():
    sample = "objects:\n  dfe.loader: {label: dfe-loader}\n# One look across every HyperI project\n"
    hits = [hit[0] for pattern in NAMES for hit in pattern.finditer(sample)]
    assert hits == ["dfe", "dfe", "HyperI"]
