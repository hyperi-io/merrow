import dataclasses
import functools
import hashlib
import http.server
import json
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from merrow import config
from merrow.cli import app
from merrow.model import Limits, Source
from merrow.sources import detect, fetch, lock
from merrow.sources.lock import Pin

LIMITS = Limits(
    member_bytes=10**6,
    deck_bytes=10**6,
    download_bytes=10**6,
    group_name_chars=40,
    download_timeout_seconds=10,
    npm_timeout_seconds=10,
    detect_timeout_seconds=60,
)


@pytest.fixture
def site(tmp_path):
    """A real HTTP server over a directory, on a free local port."""
    root = tmp_path / "site"
    root.mkdir()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def publish(root: Path, name: str, data: bytes) -> str:
    (root / name).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_fetch_downloads_once_then_reuses_the_cache(site, tmp_path):
    root, base = site
    digest = publish(root, "pkg_1.zip", b"one")
    pin = Pin("1", f"{base}/pkg_1.zip", digest, 3)
    first = fetch.fetch(tmp_path / "cache", "demo", pin, LIMITS)
    (root / "pkg_1.zip").unlink()
    assert fetch.fetch(tmp_path / "cache", "demo", pin, LIMITS) == first
    assert first.read_bytes() == b"one"


@pytest.mark.parametrize(
    ("body", "limits", "message"),
    [
        (b"tampered", LIMITS, "the lock pins"),
        (b"x" * 50, dataclasses.replace(LIMITS, download_bytes=10), "over 10"),
    ],
    ids=["sha-mismatch", "too-large"],
)
def test_fetch_refuses_a_download_that_breaks_its_pin(
    site, tmp_path, body, limits, message
):
    root, base = site
    publish(root, "pkg.zip", body)
    pin = Pin("1", f"{base}/pkg.zip", hashlib.sha256(b"original").hexdigest(), 8)
    with pytest.raises(fetch.DownloadError, match=message):
        fetch.fetch(tmp_path / "cache", "demo", pin, limits)
    assert not list((tmp_path / "cache").rglob("pkg.zip"))


def regex_source(base: str, source_id: str = "demo", url: str = "{version}") -> Source:
    check = {
        "source": "regex",
        "url": f"{base}/index.html",
        "regex": r"href=\"([^\"]*pkg_\d+\.zip)\"",
    }
    return Source(source_id, "svg", "demo", url=f"{base}/{url}", check=check)


def test_update_repins_a_moved_source_and_reports_a_broken_one(site):
    root, base = site
    publish(root, "pkg_1.zip", b"one")
    new_digest = publish(root, "pkg_2.zip", b"two!")
    (root / "index.html").write_text('<a href="pkg_2.zip">latest</a>', encoding="utf-8")
    good = regex_source(base)
    broken = regex_source(base, "needs-revision", "{revision}")
    old = {"demo": Pin("pkg_1.zip", f"{base}/pkg_1.zip", "0" * 64, 3)}

    found = detect.detect([good, broken], {}, LIMITS.detect_timeout_seconds)
    pins, changes = detect.update([good, broken], old, found, LIMITS)

    assert pins["demo"] == Pin("pkg_2.zip", f"{base}/pkg_2.zip", new_digest, 4)
    by_source = {change.source: change for change in changes}
    assert by_source["demo"].old == "pkg_1.zip"
    assert by_source["demo"].error is None
    assert "needs 'revision'" in by_source["needs-revision"].error
    assert "needs-revision" not in pins


def test_update_leaves_an_unmoved_source_alone(site):
    root, base = site
    digest = publish(root, "pkg_1.zip", b"one")
    (root / "index.html").write_text('<a href="pkg_1.zip">x</a>', encoding="utf-8")
    source = regex_source(base)
    old = {"demo": Pin("pkg_1.zip", f"{base}/pkg_1.zip", digest, 3)}
    found = detect.detect([source], {}, LIMITS.detect_timeout_seconds)
    pins, changes = detect.update([source], old, found, LIMITS)
    assert pins == old
    assert changes == []


def test_lock_round_trips_sorted(tmp_path):
    path = tmp_path / "merrow.lock.yaml"
    pins = {
        "zeta": Pin("2", "https://z/2", "b" * 64, 2),
        "alpha": Pin("1", "https://a/1", "a" * 64, 1),
    }
    lock.write(path, pins)
    assert lock.read(path) == pins
    assert path.read_text(encoding="utf-8").index("alpha") < path.read_text(
        encoding="utf-8"
    ).index("zeta")


def test_source_update_cli_pins_sources_a_reference_repo_adds(
    site, tmp_path, monkeypatch
):
    root, base = site
    digest = publish(root, "pkg_7.zip", b"seven")
    (root / "index.html").write_text('<a href="pkg_7.zip">x</a>', encoding="utf-8")
    repo = tmp_path / "acme-diagrams"
    repo.mkdir()
    check = {
        "source": "regex",
        "url": f"{base}/index.html",
        "regex": r"href=\"([^\"]*pkg_\d+\.zip)\"",
    }
    layer = {
        "sources": {
            "acme-icons": {
                "format": "svg",
                "prefix": "acme",
                "check": check,
                "url": f"{base}/{{version}}",
                "names": [],
            }
        }
    }
    (repo / "merrow.yaml").write_text(json.dumps(layer), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERROW_REFERENCES", json.dumps([str(repo)]))
    lock_path = tmp_path / "acme.lock.yaml"

    sources = {
        s.id: s for s in config.sources(config.load()).values() if s.id == "acme-icons"
    }
    result = CliRunner().invoke(app, ["source", "update", "--lock", str(lock_path)])

    assert sources["acme-icons"].options["files"] == r"\.svg$"
    assert lock.read(lock_path)["acme-icons"].sha256 == digest
    assert '"source": "acme-icons"' in result.output


def test_a_content_check_repins_only_when_the_bytes_change(site):
    root, base = site
    publish(root, "fixed.zip", b"first")
    source = Source(
        "stable", "svg", "s", url=f"{base}/fixed.zip", check={"source": "content"}
    )
    assert detect.detect([source], {}, LIMITS.detect_timeout_seconds) == {}

    pins, changes = detect.update([source], {}, {}, LIMITS)
    first = pins["stable"]
    assert first.version == first.sha256[:12]
    assert [c.source for c in changes] == ["stable"]

    same, unchanged = detect.update([source], pins, {}, LIMITS)
    assert same == pins
    assert unchanged == []

    digest = publish(root, "fixed.zip", b"second release")
    moved, _ = detect.update([source], pins, {}, LIMITS)
    assert moved["stable"].sha256 == digest
    assert moved["stable"].url == first.url
