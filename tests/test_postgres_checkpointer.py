import pytest

from app.orchestrator.postgres_checkpointer import _database_url


def test_database_url_uses_explicit_value():
    assert _database_url("postgresql://user:pass@localhost/db") == (
        "postgresql://user:pass@localhost/db"
    )


def test_database_url_reads_environment(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_DATABASE_URL", "postgresql://localhost/medvision")
    assert _database_url() == "postgresql://localhost/medvision"


def test_database_url_fails_clearly_when_missing(monkeypatch):
    monkeypatch.delenv("LANGGRAPH_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="LANGGRAPH_DATABASE_URL is not set"):
        _database_url()
