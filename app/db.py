"""Engine and session helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def make_engine(database_url: str, echo: bool = False):
    """Create a SQLAlchemy engine, tuned for the given backend."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        # The engine is shared across threads (FastAPI / TestClient).
        connect_args["check_same_thread"] = False
    return create_engine(database_url, echo=echo, future=True, connect_args=connect_args)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine) -> None:
    """Create tables if they do not already exist."""
    Base.metadata.create_all(engine)
