import pytest

from regressionforge.models import StepType, WorkflowStep, WorkflowVersion


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

