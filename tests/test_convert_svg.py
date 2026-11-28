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
        (
            f'<svg {NS} viewBox="0 0 8 8"><script>x()</script>'
            '<rect onload="x()" width="1"/><a href="javascript:x()"><rect/></a>'
            '<image href="data:image/png;base64,AA"/>'
            '<image href="data:image/svg+xml;base64,BB"/><foreignObject/></svg>',
            [
                '<rect width="1" />',
                "<g><rect /></g>",
                'href="data:image/png;base64,AA"',
            ],
            ["<script", "<a", "onload", "javascript", "svg+xml", "foreignObject"],
            {},
            ["script-dropped"],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><style>.c{{onclick:x();fill:#000}}</style>'
            '<rect class="c"/></svg>',
            ['fill="#000"'],
            ["onclick"],
            {},
            ["script-dropped"],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><a><set attributeName="href" '
            'to="javascript:alert(1)"/><circle r="1"/></a>'
            '<animate attributeName="href" to="javascript:x()"/></svg>',
            ['<g><circle r="1" /></g>'],
            ["<set", "<animate", "javascript", "<a"],
            {},
            ["script-dropped"],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><img src="http://127.0.0.1:9/b.png"/>'
            '<rect src="http://127.0.0.1:9/c.png" width="1"/></svg>',
            ['<rect width="1" />'],
            ["<img", "src=", "127.0.0.1"],
            {},
            ["script-dropped"],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><rect fill="url(http://127.0.0.1:9/a.svg#a)"/>'
            '<rect style="fill:url(//evil/x);stroke:#000;onclick:x()" width="2"/>'
            '<rect fill="url(\\68ttp://x)"/></svg>',
            ["stroke:#000", 'width="2"'],
            ["127.0.0.1", "evil", "fill:", "onclick", "http"],
            {},
            ["script-dropped"],
        ),
        (
            f'<svg {NS} viewBox="0 0 8 8"><style>/* note */ .a{{fill:red}}</style>'
            '<path class="a" data-x="1" aria-hidden="true"/><unknown><rect/></unknown>'
            "</svg>",
            ['<path fill="red" />'],
            ["data-x", "aria-hidden", "unknown", "<rect"],
            {},
            [],
        ),
        (
            f'<svg {NS} viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'class="x"><path d="M1"/></svg>',
            ['<g fill="none" stroke="currentColor"><path d="M1" /></g>'],
            ["class="],
            {},
            [],
        ),
    ],
    ids=[
        "metadata",
        "css-inlined",
        "ids-prefixed",
        "foreign-ns",
        "offset-complex-css",
        "script-dropped",
        "script-in-css-dropped",
        "smil-retargeting-dropped",
        "html-img-and-src-dropped",
        "remote-url-dropped",
        "allowlist-and-css-comment",
        "root-presentation-kept",
    ],
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


@pytest.mark.parametrize(
    ("root", "wrapper"),
    [
        ("", '<g fill="currentColor">'),
        (' fill="#F90"', '<g fill="#F90">'),
    ],
    ids=["fill_applied", "artwork_fill_wins"],
)
def test_a_source_fill_paints_a_monochrome_icon(root, wrapper):
    icon, _ = svg.clean(
        f'<svg {NS} viewBox="0 0 8 8"{root}><path/></svg>'.encode(), "k", "currentColor"
    )
    assert str(icon["body"]).startswith(wrapper)


def test_clean_rejects_malformed_xml():
    with pytest.raises(ET.ParseError):
        svg.clean(b"<svg><path></svg>", "k")


RULES = naming.rules(
    [
        {"match": "__MACOSX/", "key": None},
        {"match": r"/Arch_([^/]+)_64\.svg$", "key": r"\1", "title": r"\1"},
        {"match": r"/Res_([^/]+)_48_Dark\.svg$", "key": r"res-\1-dark"},
    ]
)


@pytest.mark.parametrize(
    ("path", "key", "title"),
    [
        ("pkg_0731/Compute/64/Arch_Amazon-EC2_64.svg", "amazon-ec2", "Amazon EC2"),
        (
            "pkg_0731/Res/Res_Amazon-S3_Bucket_48_Dark.svg",
            "res-amazon-s3-bucket-dark",
            None,
        ),
        ("__MACOSX/pkg/Arch_Amazon-EC2_64.svg", None, None),
        ("pkg_0731/Compute/32/Arch_Amazon-EC2_32.svg", False, None),
    ],
    ids=["service", "dark-resource", "skipped", "unmatched"],
)
def test_names_come_from_the_sources_rules(path, key, title):
    assert naming.key_for(path, RULES) == key
    assert naming.title_for(path, RULES) == title


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
@pytest.mark.parametrize(
    ("titles", "title"),
    [(None, "Amazon EC2"), ({"amazon-ec2": "EC2 instance"}, "EC2 instance")],
    ids=["rule_title", "configured_title_wins"],
)
def test_pack_reads_every_container_and_reports_what_it_dropped(
    tmp_path, kind, titles, title
):
    source = write_archive(kind, tmp_path)
    pack, report = svg.pack(members(source), "aws", RULES, titles=titles)
    assert pack["prefix"] == "aws"
    icons = pack["icons"]
    assert isinstance(icons, dict)
    assert list(icons) == ["amazon-ec2"]
    assert pack["titles"] == {"amazon-ec2": title}
    assert report.titled == 1
    assert report.icons == 1
    assert len(report.duplicates) == 1
    assert len(report.failed) == 1
    assert report.oversized == ["pkg/64/Arch_Huge_64.svg"]
    assert report.unmatched == 0


def test_a_single_file_download_is_one_member_and_a_missing_one_is_refused(
    tmp_path, limits
):
    loose = tmp_path / "icon.svg"
    loose.write_bytes(ICON)
    names = [{"match": r"^icon\.svg$", "key": "icon"}]
    source = Source("demo", "svg", "aws", options={"files": r"\.svg$", "names": names})
    assert list(svg.build(loose, source, limits).data["icons"]) == ["icon"]
    with pytest.raises(ValueError, match="not a file, directory, zip or tarball"):
        svg.build(tmp_path / "gone.svg", source, limits)


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


@pytest.mark.parametrize(
    ("args", "says"),
    [
        (["nope", "--from"], "no source 'nope'"),
        (["aws-icons", "nope"], "no source 'nope'"),
        (
            ["aws-icons", "aws-groups", "--from"],
            "builds one source: name only that one",
        ),
    ],
    ids=["unknown", "unknown-second-fetches-nothing", "from-with-two"],
)
def test_pack_build_cli_refuses_before_building(monkeypatch, tmp_path, args, says):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERROW_PACKS_DIR", str(tmp_path / "packs"))
    source = write_archive("zip", tmp_path)
    if args[-1] == "--from":
        args = [*args, str(source)]
    result = CliRunner().invoke(app, ["pack", "build", *args])
    assert result.exit_code == 2
    assert says in result.output
    assert not (tmp_path / "packs").exists()


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


@pytest.mark.parametrize(
    ("path", "key", "title"),
    [
        (
            "P/Arch_General-Icons/64/Arch_AWS-Marketplace_Light_64.svg",
            "aws-marketplace",
            "AWS Marketplace",
        ),
        (
            "P/Arch_General-Icons/64/Arch_AWS-Marketplace_Dark_64.svg",
            "aws-marketplace-dark",
            None,
        ),
        ("P/Arch_Compute/64/Arch_Amazon-EC2_64.svg", "amazon-ec2", "Amazon EC2"),
        (
            "P/Res_Compute/Res_Amazon-EC2_Instance_48.svg",
            "res-amazon-ec2-instance",
            "Amazon EC2 Instance",
        ),
        ("P/Arch_Compute/16/Arch_Amazon-EC2_16.svg", None, None),
        ("P/G/32/Arch_AWS-Marketplace_Light_32.svg", "aws-marketplace-32", None),
        ("P/G/32/Arch_AWS-Marketplace_Dark_32.svg", "aws-marketplace-dark-32", None),
        ("P/Arch_Compute/32/Arch_Amazon-EC2_32.svg", "amazon-ec2-32", None),
        (
            "P/Res_Compute/Res_Amazon-EC2_Instance_48_Light.svg",
            "res-amazon-ec2-instance",
            "Amazon EC2 Instance",
        ),
    ],
    ids=[
        "light",
        "dark",
        "service",
        "resource",
        "skipped_size",
        "light_32",
        "dark_32",
        "service_32",
        "resource_light",
    ],
)
def test_the_shipped_aws_rules_name_and_title_icons(path, key, title):
    rules = naming.rules(config.sources(config.load())["aws-icons"].options["names"])
    assert naming.key_for(path, rules) == key
    assert naming.title_for(path, rules) == title


@pytest.mark.parametrize(
    ("source", "path", "key", "title"),
    [
        ("carbon-icons", "package/svg/32/router.svg", "router", "Router"),
        ("carbon-icons", "package/svg/32/ibm-cloud.svg", None, None),
        ("carbon-icons", "package/svg/32/logo-github.svg", None, None),
        ("carbon-icons", "package/svg/16/router.svg", None, None),
        ("hashicorp-icons", "package/svg/vault-24.svg", "vault", "Vault"),
        ("hashicorp-icons", "package/svg/vault-16.svg", None, None),
        ("tabler-icons", "package/icons/outline/server-2.svg", "server-2", "Server 2"),
        ("tabler-icons", "package/icons/outline/brand-github.svg", None, None),
        ("tabler-icons", "package/icons/filled/server.svg", None, None),
        (
            "redhat-icons",
            "r-2.3.1/src/standard/data-center.svg",
            "data-center",
            "Data center",
        ),
        ("redhat-icons", "r-2.3.1/src/social/github.svg", None, None),
        ("shownet-icons", "s-HEAD/svg/L3-box.svg", "l3-box", "L3 box"),
    ],
    ids=[
        "carbon",
        "carbon_ibm_mark",
        "carbon_logo",
        "carbon_16",
        "hashicorp",
        "hashicorp_16",
        "tabler",
        "tabler_brand",
        "tabler_filled",
        "redhat",
        "redhat_social",
        "shownet",
    ],
)
def test_the_open_sources_name_and_title_icons(source, path, key, title):
    rules = naming.rules(config.sources(config.load())[source].options["names"])
    assert naming.key_for(path, rules) == key
    assert naming.title_for(path, rules) == title


@pytest.mark.parametrize(
    "bad",
    [
        f'<svg {NS}><path d="M0"/></svg>',
        f'<svg {NS} viewBox="0 0 10"><path d="M0"/></svg>',
        f'<svg {NS} viewBox="0 0 8 8">' + "<g>" * 3000 + "</g>" * 3000 + "</svg>",
    ],
    ids=["no-size", "short-viewBox", "nested-too-deep"],
)
def test_a_bad_icon_is_reported_and_the_pack_goes_on(bad):
    members = [archive.Member("bad.svg", bad.encode()), archive.Member("ok.svg", ICON)]
    rules = naming.rules([{"match": r"(\w+)\.svg$", "key": r"\1"}])
    built, report = svg.pack(members, "p", rules, size=24)
    assert isinstance(built["icons"], dict)
    assert list(built["icons"]) == ["ok"]
    assert [f.split(":")[0] for f in report.failed] == ["bad.svg"]
