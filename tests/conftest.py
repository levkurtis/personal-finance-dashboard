import pytest


@pytest.fixture(autouse=True)
def no_local_config(tmp_path, monkeypatch):
    """Tests never read the developer's real finance.local.toml."""
    monkeypatch.setenv("FINANCE_LOCAL_CONFIG", str(tmp_path / "no-local-config.toml"))


@pytest.fixture
def local_config(tmp_path, monkeypatch):
    """Write a local config for one test: local_config('toml text')."""

    def write(text: str):
        path = tmp_path / "finance.local.toml"
        path.write_text(text, encoding="utf-8")
        monkeypatch.setenv("FINANCE_LOCAL_CONFIG", str(path))
        return path

    return write
