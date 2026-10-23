from datetime import timedelta

from app.models import Job, JobStatus, utcnow
from app.worker import Worker


def _force_runnable(queue, job_id):
    """Move a job's run_at into the past so the next claim picks it up."""
    session = queue._session()
    try:
        job = session.get(Job, job_id)
        job.run_at = utcnow() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()


def test_enqueue_creates_queued_job(env):
    queue, _ = env
    job = queue.enqueue("echo", {"x": 1})
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.payload == {"x": 1}


def test_claim_marks_running_and_counts_attempt(env):
    queue, _ = env
    job = queue.enqueue("echo", {})
    claimed = queue.claim("w1")
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempts == 1
    assert claimed.locked_by == "w1"


def test_claim_returns_none_when_empty(env):
    queue, _ = env
    assert queue.claim("w1") is None


def test_claim_does_not_double_claim(env):
    queue, _ = env
    queue.enqueue("echo", {})
    assert queue.claim("w1") is not None
    assert queue.claim("w2") is None  # the only job is already running


def test_complete_sets_succeeded(env):
    queue, _ = env
    job = queue.enqueue("echo", {})
    queue.claim("w1")
    done = queue.complete(job.id, {"ok": True})
    assert done.status == JobStatus.SUCCEEDED
    assert done.result == {"ok": True}
    assert done.finished_at is not None


def test_fail_requeues_with_backoff(env):
    queue, _ = env
    job = queue.enqueue("echo", {}, max_attempts=3)
    queue.claim("w1")
    failed = queue.fail(job.id, "boom")
    assert failed.status == JobStatus.QUEUED
    assert failed.attempts == 1
    assert failed.last_error == "boom"
    # retry is scheduled in the future, so it is not immediately claimable
    assert failed.run_at > failed.started_at
    assert queue.claim("w1") is None


def test_fail_moves_to_dead_after_max_attempts(env):
    queue, _ = env
    job = queue.enqueue("echo", {}, max_attempts=2)
    queue.claim("w1")
    queue.fail(job.id, "boom")  # attempt 1 -> requeued with backoff
    _force_runnable(queue, job.id)
    queue.claim("w1")
    queue.fail(job.id, "boom")  # attempt 2 -> dead
    dead = queue.get(job.id)
    assert dead.status == JobStatus.DEAD
    assert dead.attempts == 2


def test_backoff_is_exponential_and_capped(make_env):
    queue, _ = make_env(backoff_base=2.0, backoff_max=5.0)
    assert queue.backoff_seconds(1) == 1.0
    assert queue.backoff_seconds(2) == 2.0
    assert queue.backoff_seconds(3) == 4.0
    assert queue.backoff_seconds(10) == 5.0  # capped


def test_higher_priority_claimed_first(env):
    queue, _ = env
    queue.enqueue("echo", {"n": "low"}, priority=1)
    high = queue.enqueue("echo", {"n": "high"}, priority=10)
    claimed = queue.claim("w1")
    assert claimed.id == high.id


def test_delayed_job_not_claimable_early(env):
    queue, _ = env
    queue.enqueue("echo", {}, delay_seconds=60)
    assert queue.claim("w1") is None


def test_retry_requeues_dead_job(make_env):
    queue, _ = make_env(backoff_base=0.0)
    job = queue.enqueue("echo", {}, max_attempts=1)
    queue.claim("w1")
    queue.fail(job.id, "boom")
    assert queue.get(job.id).status == JobStatus.DEAD
    requeued = queue.retry(job.id)
    assert requeued.status == JobStatus.QUEUED
    assert requeued.attempts == 0
    assert requeued.last_error is None


def test_metrics_counts(env):
    queue, _ = env
    queue.enqueue("echo", {})
    queue.enqueue("echo", {})
    queue.claim("w1")
    metrics = queue.metrics()
    assert metrics["total"] == 2
    assert metrics["by_status"]["running"] == 1
    assert metrics["by_status"]["queued"] == 1


def test_worker_executes_job(env):
    queue, registry = env
    job = queue.enqueue("add", {"a": 2, "b": 3})
    worker = Worker(queue, registry, "w1")
    assert worker.run_once() is True
    done = queue.get(job.id)
    assert done.status == JobStatus.SUCCEEDED
    assert done.result == {"sum": 5}


def test_worker_marks_failed_job_dead(make_env):
    queue, registry = make_env(backoff_base=0.0)

    @registry.register("always_fails")
    def _always_fails(payload):
        raise ValueError("nope")

    job = queue.enqueue("always_fails", {}, max_attempts=1)
    Worker(queue, registry, "w1").run_once()
    dead = queue.get(job.id)
    assert dead.status == JobStatus.DEAD
    assert "nope" in dead.last_error


def test_worker_fails_unknown_type(make_env):
    queue, registry = make_env(backoff_base=0.0)
    job = queue.enqueue("does-not-exist", {}, max_attempts=1)
    Worker(queue, registry, "w1").run_once()
    assert queue.get(job.id).status == JobStatus.DEAD
