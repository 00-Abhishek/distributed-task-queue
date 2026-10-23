# Distributed Task Queue & Job Scheduler

A small, production-shaped **background job queue** built with FastAPI, SQLAlchemy and PostgreSQL.

A producer (HTTP API) enqueues jobs; one or more **worker processes** claim and execute them
concurrently. Workers coordinate through PostgreSQL row-level locking
(`SELECT ... FOR UPDATE SKIP LOCKED`), so **two workers never run the same job** — without a
central broker such as Redis or RabbitMQ.

## Features

- **Concurrent workers, no double-processing** — atomic claims via `FOR UPDATE SKIP LOCKED`.
- **Priority queues** — higher-priority jobs are claimed first.
- **Delayed / scheduled jobs** — `delay_seconds` (or a future `run_at`) before a job is runnable.
- **Retries with exponential backoff** — configurable base and cap.
- **Dead-letter set** — jobs that exhaust their attempts are marked `dead` and can be retried.
- **Observability** — a `/metrics` endpoint with counts per status and average processing time.
- **Docker Compose** — Postgres + API + two workers in one command.

## Architecture

```
                 POST /jobs
   client  ─────────────────▶  FastAPI  ──┐
                                          │  INSERT (status=queued)
                                          ▼
                                    ┌───────────┐
                                    │ PostgreSQL │
                                    └───────────┘
                                          ▲
        claim: SELECT ... FOR UPDATE SKIP LOCKED, status=queued, run_at<=now
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
               worker #1             worker #2             worker #N
                    │                     │                     │
             run handler → complete()   ...            run handler → complete()
                              │
                       on error → fail() → requeue with backoff, or → dead
```

## Job lifecycle

```
queued ──claim──▶ running ──complete──▶ succeeded
   ▲                  │
   │                  └──fail──▶ queued (backoff)  ── attempts exhausted ──▶ dead
   └──────────────────────── retry() ───────────────────────────────────────┘
```

## Quick start (Docker)

```bash
docker compose up --build
```

- API docs: <http://localhost:8000/docs>
- Postgres: `localhost:5432` (db/user/password: `jobs` / `queue` / `queue`)

Enqueue a job and watch a worker pick it up:

```bash
curl -s -X POST localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"type": "add", "payload": {"a": 2, "b": 3}}'

curl -s localhost:8000/metrics
```

## Run locally without Docker

The queue falls back to SQLite for local development and tests:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# terminal 1 — API
uvicorn app.main:app --reload

# terminal 2 — worker
python -m app.worker
```

## API

| Method | Path                  | Description                          |
| ------ | --------------------- | ------------------------------------ |
| GET    | `/health`             | Liveness check                       |
| GET    | `/handlers`           | Registered job types                 |
| POST   | `/jobs`               | Enqueue a job                        |
| GET    | `/jobs`               | List jobs (filter by `status`, `type`) |
| GET    | `/jobs/{id}`          | Fetch one job                        |
| POST   | `/jobs/{id}/retry`    | Requeue a job (e.g. from the dead set) |
| GET    | `/metrics`            | Counts per status + avg processing time |

Enqueue body:

```json
{
  "type": "add",
  "payload": {"a": 2, "b": 3},
  "priority": 0,
  "max_attempts": 3,
  "delay_seconds": 0
}
```

## Built-in handlers

| Type    | Payload                     | Result                  |
| ------- | --------------------------- | ----------------------- |
| `echo`  | anything                    | `{"echo": <payload>}`   |
| `add`   | `{"a": int, "b": int}`      | `{"sum": int}`          |
| `sleep` | `{"seconds": float}`        | `{"slept": float}`      |

Add your own in `app/registry.py`:

```python
@registry.register("send_email")
def send_email(payload: dict) -> dict:
    ...
    return {"sent": True}
```

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable                | Default                  | Purpose                       |
| ----------------------- | ------------------------ | ----------------------------- |
| `DATABASE_URL`          | `sqlite:///./jobs.db`    | SQLAlchemy connection string  |
| `WORKER_ID`             | `worker-<pid>`           | Identifier recorded on claims |
| `WORKER_POLL_INTERVAL`  | `1.0`                    | Idle sleep between polls (s)  |
| `BACKOFF_BASE`          | `2.0`                    | Exponential backoff base      |
| `BACKOFF_MAX`           | `300`                    | Backoff cap (s)               |
| `DEFAULT_MAX_ATTEMPTS`  | `3`                      | Attempts before dead-letter   |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite runs against SQLite and covers enqueue/claim/complete, priority ordering,
delayed jobs, exponential backoff, the dead-letter transition, manual retry, metrics,
the worker loop, and the HTTP API.

## Design notes

- **Why `SKIP LOCKED`?** It lets many workers pull from one table concurrently without
  contending on the same row — the standard "queue on top of a relational database" pattern.
  It is used automatically when the backend is PostgreSQL.
- **Idempotency is the handler's job.** A worker that crashes mid-job leaves the row in
  `running`; a production deployment would add a visibility timeout that requeues stale
  `running` jobs (see *Next steps*).
- **AI is not required here** — the core is plain SQL and Python.

## Next steps

- Visibility timeout / heartbeat to recover jobs from crashed workers.
- `SELECT ... FOR UPDATE SKIP LOCKED` benchmark under load.
- Scheduled (cron-style) recurring jobs.
- Prometheus metrics and structured logging.

## License

MIT — see [LICENSE](LICENSE).
