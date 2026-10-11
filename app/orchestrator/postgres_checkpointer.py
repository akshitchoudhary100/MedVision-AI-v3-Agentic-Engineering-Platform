"""PostgreSQL-backed LangGraph checkpointer factory.

The returned context manager owns the database connection. Compile and invoke the
graph inside the context; for a later resume, open a new context and reuse the
same configurable.thread_id.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

DEFAULT_DATABASE_URL_ENV = "LANGGRAPH_DATABASE_URL"


def _database_url(database_url: str | None = None) -> str:
    url = database_url or os.getenv(DEFAULT_DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(
            f"{DEFAULT_DATABASE_URL_ENV} is not set. Configure it in your "
            ".env file or pass database_url explicitly."
        )
    return url


@contextmanager
def postgres_checkpointer(
    database_url: str | None = None,
    *,
    setup: bool = True,
) -> Iterator[object]:
    """Yield a synchronous PostgresSaver and close its connection afterwards.

    `setup()` creates/updates LangGraph's checkpoint tables. It is safe to call
    during application startup; production deployments may run it as a controlled
    migration step instead.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL checkpoint support is missing. Install "
            "'langgraph-checkpoint-postgres' and its psycopg dependency."
        ) from exc

    with PostgresSaver.from_conn_string(_database_url(database_url)) as saver:
        if setup:
            saver.setup()
        yield saver
