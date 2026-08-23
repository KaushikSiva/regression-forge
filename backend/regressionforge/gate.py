from __future__ import annotations

from .models import GateDecision, GateStatus, ResultStatus, StepResult


def decide(results: list[StepResult]) -> GateDecision:
    required = [result for result in results if result.required]
    failed = [result for result in required if result.status in {ResultStatus.FAILED, ResultStatus.ERROR}]
    review = [result for result in required if result.status == ResultStatus.NEEDS_REVIEW]
    passed = [result for result in required if result.status == ResultStatus.PASSED]
    if failed:
        return GateDecision(
            status=GateStatus.FAIL,
            reason=f"{len(failed)} required check{'s' if len(failed) != 1 else ''} failed. Agent analysis cannot override deterministic evidence.",
            passed_required=len(passed),
            failed_required=len(failed),
            review_required=len(review),
        )
    if review:
        return GateDecision(
            status=GateStatus.NEEDS_REVIEW,
            reason=f"{len(review)} required observability check{'s are' if len(review) != 1 else ' is'} unavailable.",
            passed_required=len(passed),
            failed_required=0,
            review_required=len(review),
        )
    return GateDecision(
        status=GateStatus.PASS,
        reason="Every required check produced matching evidence.",
        passed_required=len(passed),
        failed_required=0,
        review_required=0,
    )

