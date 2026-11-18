"""The worked examples that need no icon pack match what merrow writes from them."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from merrow.cli import app

EXAMPLES = Path(__file__).parent.parent / "docs" / "examples"


@pytest.mark.parametrize(
    ("diagram", "reference", "profile"),
    [
        ("pipeline/pipeline.yaml", None, "house"),
        ("c4-big-bank/context.yaml", "c4-big-bank/reference", "house"),
        ("c4-big-bank/containers.yaml", "c4-big-bank/reference", "house"),
        ("bpmn-order/order.yaml", None, "house"),
        ("bpmn-order/create-invoice.yaml", None, "house"),
        ("campus-network/campus.yaml", None, "house"),
    ],
    ids=[
        "pipeline",
        "c4_context",
        "c4_containers",
        "bpmn_order",
        "bpmn_create_invoice",
        "campus_network",
    ],
)
def test_a_worked_example_matches_what_merrow_writes(
    monkeypatch, tmp_path, diagram, reference, profile
):
    monkeypatch.chdir(tmp_path)
    if reference:
        references = json.dumps([str(EXAMPLES / reference)])
        monkeypatch.setenv("MERROW_REFERENCES", references)
    path = EXAMPLES / diagram
    result = CliRunner().invoke(
        app,
        ["graph", "write", "--profile", profile, str(path), "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    written = (tmp_path / f"{path.stem}.mmd").read_text(encoding="utf-8")
    committed = path.with_suffix(".mmd").read_text(encoding="utf-8")
    assert written == committed, "regenerate with make examples"
