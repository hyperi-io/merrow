import io
import json
import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from merrow import archive, config, naming
from merrow.cli import app
from merrow.convert import svg
from merrow.model import Source

NS = 'xmlns="http://www.w3.org/2000/svg"'
SODI = 'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"'


@pytest.mark.parametrize(
    ("source", "body_has", "body_lacks", "fields", "notes"),
    [
        (
            f'<svg {NS} viewBox="0 0 64 64"><title>t</title><path d="M0"/></svg>',
            ['<path d="M0" />'],
            ["title"],
            {"width": 64.0, "height": 64.0},
            [],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><style>.st1{{fill:#F90}}</style>'
            '<rect class="st1"/></svg>',
            ['fill="#F90"'],
            ["class=", "<style"],
            {},
            [],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><defs><linearGradient id="g"/></defs>'
            '<rect fill="url(#g)"/></svg>',
            ['id="k-g"', 'fill="url(#k-g)"'],
            ['id="g"'],
            {},
            [],
        ),
        (
            f'<svg {NS} {SODI} width="24px" height="16"><sodipodi:namedview/>'
            '<path sodipodi:type="x" d="M1"/></svg>',
            ['<path d="M1" />'],
            ["sodipodi"],
            {"width": 24.0, "height": 16.0},
            ["no-viewBox"],
        ),
        (
            f'<svg {NS} viewBox="2 3 8 8"><style>g > rect{{fill:red}}</style>'
            "<rect/></svg>",
            ["<rect />"],
            [],
            {"left": 2.0, "top": 3.0},
            ["complex-css"],
        ),
    ],
    ids=["metadata", "css-inlined", "ids-prefixed", "foreign-ns", "offset-complex-css"],
)
def test_clean_keeps_artwork_and_isolates_each_icon(
    source, body_has, body_lacks, fields, notes
):
    icon, found = svg.clean(source.encode(), "k")
    body = str(icon["body"])
    for text in body_has:
        assert text in body
    for text in body_lacks:
        assert text not in body
    for name, value in fields.items():
        assert icon[name] == value
    assert found == notes


def test_clean_rejects_malformed_xml():
    with pytest.raises(ET.ParseError):
        svg.clean(b"<svg><path></svg>", "k")


RULES = naming.rules(
    [
        {"match": "__MACOSX/", "key": None},
        {"match": r"/Arch_([^/]+)_64\.svg$", "key": r"\1"},
        {"match": r"/Res_([^/]+)_48_Dark\.svg$", "key": r"res-\1-dark"},
    ]
)


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("pkg_0731/Compute/64/Arch_Amazon-EC2_64.svg", "amazon-ec2"),
        ("pkg_0731/Res/Res_Amazon-S3_Bucket_48_Dark.svg", "res-amazon-s3-bucket-dark"),
        ("__MACOSX/pkg/Arch_Amazon-EC2_64.svg", None),
        ("pkg_0731/Compute/32/Arch_Amazon-EC2_32.svg", False),
    ],
    ids=["service", "dark-resource", "skipped", "unmatched"],
)
def test_names_come_from_the_sources_rules(path, key):
    assert naming.key_for(path, RULES) == key


def test_a_rule_without_match_is_refused():
    with pytest.raises(ValueError, match="without a match"):
        naming.rules([{"key": "x"}])


ICON = f'<svg {NS} viewBox="0 0 64 64"><path d="M0"/></svg>'.encode()


def write_archive(kind: str, root: Path) -> Path:
    members = {
        "pkg/64/Arch_Amazon-EC2_64.svg": ICON,
        "pkg/old/Arch_Amazon-EC2_64.svg": ICON,
        "pkg/64/Arch_Broken_64.svg": b"<svg",
        "pkg/64/Arch_Huge_64.svg": ICON + b" " * 200,
        "pkg/readme.txt": b"not an icon",
    }
    if kind == "zip":
        path = root / "icons.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        return path
    if kind == "tar":
        path = root / "icons.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return path
    for name, data in members.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root


def members(source, max_bytes=len(ICON) + 50):
    return archive.members(source, re.compile(r"\.svg$"), max_bytes)


@pytest.mark.parametrize("kind", ["zip", "tar", "dir"])
def test_pack_reads_every_container_and_reports_what_it_dropped(tmp_path, kind):
    source = write_archive(kind, tmp_path)
    pack, report = svg.pack(members(source), "aws", RULES)
    assert pack["prefix"] == "aws"
    icons = pack["icons"]
    assert isinstance(icons, dict)
    assert list(icons) == ["amazon-ec2"]
    assert report.icons == 1
    assert len(report.duplicates) == 1
    assert len(report.failed) == 1
    assert report.oversized == ["pkg/64/Arch_Huge_64.svg"]
    assert report.unmatched == 0


def test_build_refuses_a_file_that_is_no_container(tmp_path, limits):
    loose = tmp_path / "icon.svg"
    loose.write_bytes(ICON)
    source = Source("demo", "svg", "aws", options={"files": r"\.svg$", "names": []})
    with pytest.raises(ValueError, match="not a directory, zip or tarball"):
        svg.build(loose, source, limits)


def test_resource_forks_are_ignored_by_the_shipped_ignore_pattern(tmp_path, limits):
    path = tmp_path / "icons.zip"
    with zipfile.ZipFile(path, "w") as zipped:
        zipped.writestr("pkg/64/Arch_Amazon-EC2_64.svg", ICON)
        zipped.writestr("__MACOSX/pkg/64/._Arch_Amazon-EC2_64.svg", b"junk")
        zipped.writestr("pkg/64/._Arch_Other_64.svg", b"junk")
    source = Source(
        "demo",
        "svg",
        "aws",
        options={
            "files": r"\.svg$",
            "names": [{"match": r"/Arch_([^/]+)_64\.svg$", "key": r"\1"}],
        },
    )
    built = svg.build(path, source, limits)
    assert list(built.data["icons"]) == ["amazon-ec2"]
    assert built.report["failed"] == []


def test_pack_build_cli_writes_the_pack_where_config_says(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERROW_PACKS_DIR", str(tmp_path / "packs"))
    source = write_archive("zip", tmp_path)
    result = CliRunner().invoke(
        app, ["pack", "build", "aws-icons", "--from", str(source)]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output.strip().splitlines()[-1])
    written = json.loads(Path(report["pack"]).read_text(encoding="utf-8"))
    assert written["prefix"] == "aws"
    assert "amazon-ec2" in written["icons"]


def test_pack_build_cli_names_an_unknown_source(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["pack", "build", "nope", "--from", str(tmp_path)])
    assert result.exit_code == 2
    assert "no source 'nope'" in result.output


def test_aliases_point_at_real_icons_and_broken_ones_are_reported(tmp_path):
    source = write_archive("dir", tmp_path)
    aliases = {"ec2": "amazon-ec2", "ghost": "amazon-nothing"}
    pack, report = svg.pack(members(source, 10_000), "aws", RULES, aliases)
    assert pack["aliases"] == {"ec2": {"parent": "amazon-ec2"}}
    assert report.broken_aliases == ["ghost -> amazon-nothing"]


def test_every_shipped_alias_and_target_is_in_slug_form(limits):
    for source in config.sources(config.load()).values():
        for short, target in (source.options.get("aliases") or {}).items():
            assert short == naming.slug(short), short
            assert target == naming.slug(target), target
