"""Core queue logic: enqueue, claim, complete, retry, dead-letter, metrics."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select

from .models import Job, JobStatus, utcnow


class TaskQueue:
    """A PostgreSQL-backed task queue.

    Workers claim jobs with ``SELECT ... FOR UPDATE SKIP LOCKED`` so two workers
    never process the same job. On non-PostgreSQL backends (used for local
    development and the test suite) a plain claim is used; SQLite serialises
    writers, so a single-writer setup is safe.
    """

    def __init__(
        self,
        session_factory,
        engine=None,
        backoff_base: float = 2.0,
        backoff_max: float = 300.0,
        default_max_attempts: int = 3,
    ) -> None:
        self.session_factory = session_factory
        self.engine = engine if engine is not None else session_factory.kw.get("bind")
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.default_max_attempts = default_max_attempts

    # -- helpers ---------------------------------------------------------
    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def _session(self):
        return self.session_factory()

    def backoff_seconds(self, attempts: int) -> float:
        """Exponential backoff for the given attempt count, capped."""
        exponent = max(0, attempts - 1)
        return min(self.backoff_base ** exponent, self.backoff_max)

    # -- producer --------------------------------------------------------
    def enqueue(
        self,
        type: str,
        payload: Optional[dict] = None,
        priority: int = 0,
        max_attempts: Optional[int] = None,
        delay_seconds: float = 0,
    ) -> Job:
        now = utcnow()
        job = Job(
            type=type,
            payload=payload or {},
            status=JobStatus.QUEUED,
            priority=priority,
            run_at=now + timedelta(seconds=delay_seconds),
            attempts=0,
            max_attempts=max_attempts if max_attempts is not None else self.default_max_attempts,
            created_at=now,
            updated_at=now,
        )
        session = self._session()
        try:
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    # -- worker ----------------------------------------------------------
    def claim(self, worker_id: str) -> Optional[Job]:
        """Atomically take the next runnable job, or return None."""
        now = utcnow()
        session = self._session()
        try:
            stmt = (
                select(Job)
                .where(Job.status == JobStatus.QUEUED, Job.run_at <= now)
                .order_by(Job.priority.desc(), Job.run_at.asc(), Job.created_at.asc())
                .limit(1)
            )
            if self.dialect == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)

            job = session.execute(stmt).scalar_one_or_none()
            if job is None:
                session.rollback()
                return None

            job.status = JobStatus.RUNNING
            job.locked_by = worker_id
            job.locked_at = now
            job.started_at = now
            job.attempts += 1
            job.updated_at = now
            session.commit()
            session.refresh(job)
            return job
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete(self, job_id: str, result=None) -> Optional[Job]:
        now = utcnow()
        session = self._session()
        try:
            job = session.get(Job, job_id)
            if job is None:
                return None
            job.status = JobStatus.SUCCEEDED
            job.result = result
            job.finished_at = now
            job.updated_at = now
            job.locked_by = None
            job.locked_at = None
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def fail(self, job_id: str, error: str) -> Optional[Job]:
        """Record a failure: requeue with backoff, or move to the dead-letter set."""
        now = utcnow()
        session = self._session()
        try:
            job = session.get(Job, job_id)
            if job is None:
                return None
            job.last_error = str(error)[:2000]
            job.locked_by = None
            job.locked_at = None
            job.updated_at = now
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.DEAD
                job.finished_at = now
            else:
                job.status = JobStatus.QUEUED
                job.run_at = now + timedelta(seconds=self.backoff_seconds(job.attempts))
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    # -- admin -----------------------------------------------------------
    def retry(self, job_id: str) -> Optional[Job]:
        """Requeue a job (typically a dead-letter job), resetting its attempts."""
        now = utcnow()
        session = self._session()
        try:
            job = session.get(Job, job_id)
            if job is None:
                return None
            job.status = JobStatus.QUEUED
            job.attempts = 0
            job.run_at = now
            job.last_error = None
            job.locked_by = None
            job.locked_at = None
            job.finished_at = None
            job.updated_at = now
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def get(self, job_id: str) -> Optional[Job]:
        session = self._session()
        try:
            return session.get(Job, job_id)
        finally:
            session.close()

    def list_jobs(self, status=None, type=None, limit: int = 50, offset: int = 0):
        session = self._session()
        try:
            stmt = select(Job)
            if status:
                stmt = stmt.where(Job.status == status)
            if type:
                stmt = stmt.where(Job.type == type)
            stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()

    def metrics(self) -> dict:
        session = self._session()
        try:
            rows = session.execute(
                select(Job.status, func.count(Job.id)).group_by(Job.status)
            ).all()
            counts = {status: count for status, count in rows}
            durations = session.execute(
                select(Job.started_at, Job.finished_at).where(Job.status == JobStatus.SUCCEEDED)
            ).all()
            secs = [
                (finished - started).total_seconds()
                for started, finished in durations
                if started is not None and finished is not None
            ]
            by_status = {s: int(counts.get(s, 0)) for s in JobStatus.ALL}
            return {
                "total": int(sum(counts.values())),
                "by_status": by_status,
                "avg_processing_seconds": round(sum(secs) / len(secs), 4) if secs else 0.0,
            }
        finally:
            session.close()
