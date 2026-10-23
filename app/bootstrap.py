"""Wiring: settings -> engine -> session factory -> queue + handler registry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .db import init_db, make_engine, make_session_factory
from .queue import TaskQueue
from .registry import HandlerRegistry, register_default_handlers


@dataclass
class Settings:
    database_url: str = "sqlite:///./jobs.db"
    worker_id: str = "worker"
    worker_poll_interval: float = 1.0
    backoff_base: float = 2.0
    backoff_max: float = 300.0
    default_max_attempts: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///./jobs.db"),
            worker_id=os.getenv("WORKER_ID", f"worker-{os.getpid()}"),
            worker_poll_interval=float(os.getenv("WORKER_POLL_INTERVAL", "1.0")),
            backoff_base=float(os.getenv("BACKOFF_BASE", "2.0")),
            backoff_max=float(os.getenv("BACKOFF_MAX", "300")),
            default_max_attempts=int(os.getenv("DEFAULT_MAX_ATTEMPTS", "3")),
        )


def build(settings: Optional[Settings] = None):
    """Return (settings, engine, session_factory, queue, registry)."""
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    registry = register_default_handlers(HandlerRegistry())
    queue = TaskQueue(
        session_factory,
        engine=engine,
        backoff_base=settings.backoff_base,
        backoff_max=settings.backoff_max,
        default_max_attempts=settings.default_max_attempts,
    )
    return settings, engine, session_factory, queue, registry
