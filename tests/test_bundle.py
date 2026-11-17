import base64
import hashlib
import io
import json
import tarfile

import pytest
from typer.testing import CliRunner

from merrow import bundle, config
from merrow.cli import app

FILE = "package/dist/mermaid.min.js"


def tarball(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return out.getvalue()


def integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


@pytest.fixture
def pinned(site, tmp_path, monkeypatch):
    """Publish a tarball on a local server and pin it in a lock merrow reads."""
    root, base = site
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MERROW_CACHE_DIR", str(tmp_path / "cache"))

    def pin(data: bytes, claimed: bytes | None = None) -> None:
        (root / "mermaid.tgz").write_bytes(data)
        entry = {
            "version": "9.9.9",
            "resolved": f"{base}/mermaid.tgz",
            "integrity": integrity(data if claimed is None else claimed),
        }
        lock = tmp_path / "package-lock.json"
        lock.write_text(
            json.dumps({"packages": {"node_modules/mermaid": entry}}), encoding="utf-8"
        )
        monkeypatch.setattr(bundle, "LOCKFILE", lock)

    return pin


def test_the_pinned_bundle_is_fetched_once_and_cached(pinned, site):
    pinned(tarball({FILE: b"mermaid()"}))
    settings = config.load()
    first = bundle.path(settings)
    assert first.read_bytes() == b"mermaid()"
    (site[0] / "mermaid.tgz").unlink()
    assert bundle.path(settings) == first, "a cached bundle needs no network"
    assert bundle.version(settings) == "9.9.9"


@pytest.mark.parametrize(
    ("data", "claimed", "said"),
    [
        (tarball({FILE: b"tampered"}), tarball({FILE: b"real"}), "integrity"),
        (tarball({"package/other.js": b"x"}), None, "has no package/dist"),
    ],
    ids=["integrity_mismatch", "no_bundle_file"],
)
def test_a_bad_tarball_is_refused(pinned, data, claimed, said):
    pinned(data, claimed)
    with pytest.raises(bundle.BundleError, match=said):
        bundle.path(config.load())


def test_tools_ensure_reports_the_version_the_shipped_lock_pins(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    lock = json.loads(bundle.LOCKFILE.read_text(encoding="utf-8"))
    pinned_version = lock["packages"]["node_modules/mermaid"]["version"]
    result = CliRunner().invoke(app, ["tools", "ensure"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output.strip().splitlines()[-1])
    assert report["mermaid"] == pinned_version
    assert report["bundle"].endswith("mermaid.min.js")
