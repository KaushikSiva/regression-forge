from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class StepType(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_TEXT = "assert_text"
    ASSERT_HTTP = "assert_http"
    ASSERT_EMAIL = "assert_email"
    ASSERT_WEBHOOK = "assert_webhook"
    ASSERT_SIGNOZ_LOGS = "assert_signoz_logs"


class ResultStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    ERROR = "ERROR"


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class IntegrationState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: identifier("prj"))
    name: str
    repository_path: str
    repository_remote: str | None = None
    created_at: datetime = Field(default_factory=now)


class Deployment(BaseModel):
    id: str = Field(default_factory=lambda: identifier("dep"))
    project_id: str
    environment: str = "local"
    version: str
    commit_sha: str
    storefront_url: str
    api_url: str
    repository: str | None = None
    repository_provider: Literal["github", "gitlab", "local"] = "local"
    default_branch: str = "main"
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list, max_length=100)
    created_at: datetime = Field(default_factory=now)


class WorkflowStep(BaseModel):
    id: str
    type: StepType
    name: str
    required: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    visual_checkpoint: bool = False


class WorkflowVersion(BaseModel):
    id: str = Field(default_factory=lambda: identifier("wfv"))
    workflow_id: str
    version: int
    outcome: str
    steps: list[WorkflowStep]
    content_hash: str = ""
    approved: bool = False
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=now)
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def calculate_hash(self):
        canonical = json.dumps(
            [step.model_dump(mode="json") for step in self.steps], sort_keys=True, separators=(",", ":")
        )
        expected = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        if self.content_hash and self.content_hash != expected:
            raise ValueError("workflow content_hash does not match steps")
        self.content_hash = expected
        return self


class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: identifier("wf"))
    project_id: str
    name: str
    outcome: str
    current_version_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class EvidenceArtifact(BaseModel):
    id: str = Field(default_factory=lambda: identifier("ev"))
    run_id: str
    step_id: str | None = None
    kind: Literal["screenshot", "video", "trace", "network", "console", "http", "email", "webhook", "signoz", "glasskit", "source", "memory"]
    label: str
    path: str | None = None
    url: str | None = None
    mime_type: str = "application/json"
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)


class StepResult(BaseModel):
    id: str = Field(default_factory=lambda: identifier("sr"))
    run_id: str
    step_id: str
    step_name: str
    step_type: StepType
    required: bool
    status: ResultStatus = ResultStatus.PENDING
    started_at: datetime = Field(default_factory=now)
    completed_at: datetime | None = None
    duration_ms: float = 0
    summary: str = ""
    expected: Any = None
    actual: Any = None
    evidence_ids: list[str] = Field(default_factory=list)


class GateDecision(BaseModel):
    status: GateStatus
    reason: str
    passed_required: int
    failed_required: int
    review_required: int
    decided_at: datetime = Field(default_factory=now)
    policy: str = "required-steps-v1"


class Diagnosis(BaseModel):
    status: IntegrationState
    summary: str
    evidence_citations: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    investigation: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    provider: str = "deterministic-evidence-summarizer"


class MemoryMatch(BaseModel):
    observation_id: str
    title: str
    narrative: str
    created_at: str | None = None
    relevance: str = "historical"


class RegressionRun(BaseModel):
    id: str = Field(default_factory=lambda: identifier("run"))
    project_id: str
    deployment_id: str
    workflow_version_id: str
    status: ResultStatus = ResultStatus.PENDING
    gate: GateDecision | None = None
    trace_id: str = ""
    baseline_run_id: str | None = None
    step_results: list[StepResult] = Field(default_factory=list)
    evidence: list[EvidenceArtifact] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    memory_matches: list[MemoryMatch] = Field(default_factory=list)
    integration_status: dict[str, IntegrationState] = Field(default_factory=dict)
    console_errors: list[dict[str, Any]] = Field(default_factory=list)
    network_events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowDraftRequest(BaseModel):
    project_id: str
    outcome: str = Field(min_length=20, max_length=1000)


class WorkflowApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=2, max_length=80)


class RunRequest(BaseModel):
    deployment_id: str
    workflow_version_id: str | None = None


class DeploymentWebhookRequest(BaseModel):
    project_id: str
    environment: str
    version: str
    commit_sha: str
    storefront_url: str
    api_url: str
    repository: str | None = None
    repository_provider: Literal["github", "gitlab", "local"] = "local"
    default_branch: str = "main"
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list, max_length=100)


class CICertificationRequest(DeploymentWebhookRequest):
    workflow_version_id: str | None = None
