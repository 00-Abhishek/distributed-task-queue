"""SQLAlchemy models and helpers for jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (portable across databases)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JobStatus:
    """Lifecycle states for a job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEAD = "dead"  # exhausted all retries -> dead-letter set

    ALL = (QUEUED, RUNNING, SUCCEEDED, DEAD)


class Job(Base):
    """A single unit of work stored in the queue."""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)

    status = Column(String(20), nullable=False, default=JobStatus.QUEUED, index=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    run_at = Column(DateTime, nullable=False, default=utcnow, index=True)

    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    last_error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)

    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Job {self.id} type={self.type!r} status={self.status!r} attempts={self.attempts}>"
