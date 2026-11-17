import pytest

from merrow import config


@pytest.fixture
def limits(monkeypatch, tmp_path):
    """merrow's shipped limits and ignore pattern, read from a clean directory."""
    monkeypatch.chdir(tmp_path)
    return config.limits(config.load())
