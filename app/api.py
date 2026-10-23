"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from .queue import TaskQueue
from .registry import HandlerRegistry
from .schemas import JobCreate, JobOut, MetricsOut


def create_app(queue: TaskQueue, registry: HandlerRegistry) -> FastAPI:
    app = FastAPI(
        title="Distributed Task Queue & Job Scheduler",
        version="1.0.0",
        description=(
            "A PostgreSQL-backed job queue with concurrent workers, priority "
            "queues, exponential-backoff retries and a dead-letter queue."
        ),
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/handlers")
    def handlers() -> dict:
        return {"handlers": registry.names()}

    @app.post("/jobs", response_model=JobOut, status_code=201)
    def create_job(body: JobCreate) -> JobOut:
        if body.type not in registry:
            raise HTTPException(status_code=422, detail=f"Unknown job type '{body.type}'")
        return queue.enqueue(
            type=body.type,
            payload=body.payload,
            priority=body.priority,
            max_attempts=body.max_attempts,
            delay_seconds=body.delay_seconds,
        )

    @app.get("/jobs", response_model=list[JobOut])
    def list_jobs(
        status: str | None = Query(None),
        type: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[JobOut]:
        return queue.list_jobs(status=status, type=type, limit=limit, offset=offset)

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str) -> JobOut:
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/jobs/{job_id}/retry", response_model=JobOut)
    def retry_job(job_id: str) -> JobOut:
        if queue.get(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return queue.retry(job_id)

    @app.get("/metrics", response_model=MetricsOut)
    def metrics() -> MetricsOut:
        return queue.metrics()

    return app
