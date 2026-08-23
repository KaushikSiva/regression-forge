from __future__ import annotations

from fastapi.testclient import TestClient

from regressionforge import main
from regressionforge.models import RegressionRun
from regressionforge.storage import Store


def test_ci_certification_requires_token_and_queues_run(monkeypatch, tmp_path):
    test_store = Store(tmp_path / "ci.db")
    monkeypatch.setattr(main, "store", test_store)
    main.seed()
    original_token = main.settings.ci_webhook_token
    object.__setattr__(main.settings, "ci_webhook_token", "ci-test-secret")

    def fake_queue(deployment, version):
        return RegressionRun(
            id="run_ci_api",
            project_id=deployment.project_id,
            deployment_id=deployment.id,
            workflow_version_id=version.id,
        )

    monkeypatch.setattr(main, "queue_run", fake_queue)
    client = TestClient(main.app)
    payload = {
        "project_id": "prj_forgecart",
        "environment": "pull-request",
        "version": "pr-42-deadbeef",
        "commit_sha": "deadbeef",
        "storefront_url": "http://forgecart-web",
        "api_url": "http://forgecart-api:8000",
        "repository": "owner/regressionforge-demo-store",
        "repository_provider": "github",
        "pull_request_number": 42,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "changed_files": ["backend/forgecart/contracts/good.py"],
    }
    try:
        unauthorized = client.post("/api/ci/certifications", json=payload)
        accepted = client.post(
            "/api/ci/certifications",
            json=payload,
            headers={"authorization": "Bearer ci-test-secret"},
        )
    finally:
        object.__setattr__(main.settings, "ci_webhook_token", original_token)

    assert unauthorized.status_code == 401
    assert accepted.status_code == 202
    assert accepted.json()["run_id"] == "run_ci_api"
    deployment = test_store.get("deployment", accepted.json()["deployment_id"], main.Deployment)
    assert deployment is not None
    assert deployment.pull_request_number == 42
