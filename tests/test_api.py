from fastapi.testclient import TestClient

from app.api import create_app
from app.bootstrap import Settings, build


def make_client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    _settings, _engine, _session_factory, queue, registry = build(settings)
    return TestClient(create_app(queue, registry)), queue


def test_health(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_job(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/jobs", json={"type": "echo", "payload": {"hi": 1}})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    got = client.get(f"/jobs/{body['id']}")
    assert got.status_code == 200
    assert got.json()["payload"] == {"hi": 1}


def test_unknown_type_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/jobs", json={"type": "nope"}).status_code == 422


def test_get_missing_job_returns_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_metrics_endpoint(tmp_path):
    client, _ = make_client(tmp_path)
    client.post("/jobs", json={"type": "echo"})
    metrics = client.get("/metrics").json()
    assert metrics["total"] == 1
    assert metrics["by_status"]["queued"] == 1


def test_list_jobs_filter_by_status(tmp_path):
    client, _ = make_client(tmp_path)
    client.post("/jobs", json={"type": "echo"})
    assert len(client.get("/jobs", params={"status": "queued"}).json()) == 1
    assert client.get("/jobs", params={"status": "succeeded"}).json() == []


def test_retry_endpoint(tmp_path):
    client, queue = make_client(tmp_path)
    job_id = client.post("/jobs", json={"type": "echo", "max_attempts": 1}).json()["id"]
    queue.claim("w1")
    queue.fail(job_id, "boom")
    response = client.post(f"/jobs/{job_id}/retry")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
