from regressionforge.gate import decide
from regressionforge.models import GateStatus, ResultStatus, StepResult, StepType


def result(status: ResultStatus, required: bool = True) -> StepResult:
    return StepResult(
        run_id="run_test",
        step_id="check",
        step_name="Check",
        step_type=StepType.ASSERT_HTTP,
        required=required,
        status=status,
    )


def test_pass_requires_every_required_check_to_pass():
    assert decide([result(ResultStatus.PASSED)]).status == GateStatus.PASS


def test_failure_cannot_be_overridden_by_review_or_optional_result():
    decision = decide([
        result(ResultStatus.FAILED),
        result(ResultStatus.NEEDS_REVIEW),
        result(ResultStatus.ERROR, required=False),
    ])
    assert decision.status == GateStatus.FAIL
    assert "cannot override" in decision.reason


def test_missing_observability_evidence_requires_review():
    assert decide([result(ResultStatus.PASSED), result(ResultStatus.NEEDS_REVIEW)]).status == GateStatus.NEEDS_REVIEW

