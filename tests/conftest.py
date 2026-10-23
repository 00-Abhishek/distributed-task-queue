import pytest

from app.bootstrap import Settings, build


@pytest.fixture
def make_env(tmp_path):
    """Factory for a queue + registry backed by a throwaway SQLite database."""
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        db_path = tmp_path / f"test-{counter['n']}.db"
        settings = Settings(database_url=f"sqlite:///{db_path}", **overrides)
        _settings, _engine, _session_factory, queue, registry = build(settings)
        return queue, registry

    return _make


@pytest.fixture
def env(make_env):
    return make_env()
