import json
import re

import pytest

from merrow import config
from merrow.lint import icons


@pytest.fixture
def packs(tmp_path):
    pack = {
        "prefix": "aws",
        "icons": {"amazon-ec2": {}},
        "aliases": {"ec2": {"parent": "amazon-ec2"}},
    }
    (tmp_path / "aws.json").write_text(json.dumps(pack), encoding="utf-8")
    (tmp_path / "aws-groups.json").write_text(
        json.dumps({"light": []}), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    ("source", "missing"),
    [
        ("architecture-beta\n  service a(aws:amazon-ec2)[A]\n", []),
        ("architecture-beta\n  service a(aws:ec2)[A]\n", []),
        (
            "architecture-beta\n  group g(aws:vpc)[G]\n  service a(aws:ec2)[A] in g\n",
            ["aws:vpc"],
        ),
        ('flowchart LR\n  a@{ icon: "k8s:pod", label: "Pod" }\n', ["k8s:pod"]),
        (
            "architecture-beta\n  service a(aws:nope)[A]\n  service b(aws:nope)[B]\n",
            ["aws:nope"],
        ),
        ("flowchart LR\n  a --> b\n", []),
    ],
    ids=["icon", "alias", "group", "icon-shape", "reported-once", "no-icons"],
)
def test_every_named_icon_must_resolve(packs, monkeypatch, tmp_path, source, missing):
    monkeypatch.chdir(tmp_path)
    patterns = [re.compile(p) for p in config.load().get("lint")["icon_refs"]]
    assert (
        icons.unresolved(source, patterns, icons.known_keys(packs.glob("*.json")))
        == missing
    )
