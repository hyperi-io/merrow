import functools
import http.server
import threading

import pytest

from merrow import config


@pytest.fixture
def limits(monkeypatch, tmp_path):
    """merrow's shipped limits and ignore pattern, read from a clean directory."""
    monkeypatch.chdir(tmp_path)
    return config.limits(config.load())


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
