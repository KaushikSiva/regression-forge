import pytest

from regressionforge.models import Deployment, StepType, WorkflowStep, WorkflowVersion


def test_workflow_hash_is_reproducible():
    step = WorkflowStep(id="one", type=StepType.NAVIGATE, name="Open", config={"path": "/"})
    first = WorkflowVersion(workflow_id="wf", version=1, outcome="test", steps=[step])
    second = WorkflowVersion(workflow_id="wf", version=2, outcome="test", steps=[step])
    assert first.content_hash == second.content_hash


def test_tampered_workflow_hash_is_rejected():
    with pytest.raises(ValueError):
        WorkflowVersion(
            workflow_id="wf",
            version=1,
            outcome="test",
            content_hash="not-the-real-hash",
            steps=[WorkflowStep(id="one", type=StepType.NAVIGATE, name="Open")],
        )


def test_deployment_carries_pull_request_context():
    deployment = Deployment(
        project_id="prj_forgecart",
        environment="pull-request",
        version="pr-12-deadbeef",
        commit_sha="deadbeef",
        storefront_url="http://forgecart-web",
        api_url="http://forgecart-api:8000",
        repository="owner/regressionforge-demo-store",
        repository_provider="github",
        pull_request_number=12,
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_files=["backend/forgecart/contracts/good.py"],
    )
    assert deployment.pull_request_number == 12
    assert deployment.changed_files == ["backend/forgecart/contracts/good.py"]
