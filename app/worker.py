"""Worker process: claims jobs and executes them.

Run one or more workers with::

    python -m app.worker
"""

from __future__ import annotations

import logging
import signal
import time

from .bootstrap import build

logger = logging.getLogger("task-queue.worker")


class Worker:
    def __init__(self, queue, registry, worker_id: str, poll_interval: float = 1.0) -> None:
        self.queue = queue
        self.registry = registry
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self._stopping = False

    def stop(self, *_) -> None:
        self._stopping = True

    def run_once(self) -> bool:
        """Claim and run a single job. Returns True if a job was processed."""
        job = self.queue.claim(self.worker_id)
        if job is None:
            return False

        handler = self.registry.get(job.type)
        if handler is None:
            self.queue.fail(job.id, f"No handler registered for type '{job.type}'")
            logger.warning("no handler for type=%s (job %s)", job.type, job.id)
            return True

        try:
            result = handler(job.payload or {})
        except Exception as exc:  # noqa: BLE001 - record any handler failure
            self.queue.fail(job.id, repr(exc))
            logger.warning("job %s failed (attempt %s): %s", job.id, job.attempts, exc)
        else:
            self.queue.complete(job.id, result)
            logger.info("job %s (%s) succeeded", job.id, job.type)
        return True

    def run_forever(self) -> None:
        while not self._stopping:
            try:
                worked = self.run_once()
            except Exception:  # noqa: BLE001 - keep the worker alive
                logger.exception("worker loop error")
                worked = False
            if not worked:
                time.sleep(self.poll_interval)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings, engine, session_factory, queue, registry = build()
    worker = Worker(queue, registry, settings.worker_id, settings.worker_poll_interval)

    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)

    logger.info("worker %s started (dialect=%s)", settings.worker_id, queue.dialect)
    worker.run_forever()
    logger.info("worker %s stopped", settings.worker_id)


if __name__ == "__main__":
    main()
