import json
import shutil

import pytest
from typer.testing import CliRunner

from merrow.cli import app
from merrow.node import MANIFEST


@pytest.mark.skipif(shutil.which("npm") is None, reason="needs node and npm")
def test_tools_ensure_installs_the_pinned_mermaid_cli():
    pinned = json.loads(MANIFEST.read_text(encoding="utf-8"))["dependencies"]
    result = CliRunner().invoke(app, ["tools", "ensure"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output.strip().splitlines()[-1])
    assert report["version"] == pinned["@mermaid-js/mermaid-cli"]


def test_tools_ensure_without_node_names_the_fix(monkeypatch):
    monkeypatch.setenv("PATH", "")
    result = CliRunner().invoke(app, ["tools", "ensure"])
    assert result.exit_code != 0
    assert "Node.js" in str(result.exception)
