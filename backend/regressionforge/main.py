from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import (
    CICertificationRequest,
    Deployment,
    DeploymentWebhookRequest,
    Project,
    RegressionRun,
    RunRequest,
    Workflow,
    WorkflowApprovalRequest,
    WorkflowDraftRequest,
    WorkflowVersion,
    now,
)
from .runner import RunBroker, Runner
from .security import valid_bearer_token
from .storage import Store
from .workflows import DEFAULT_OUTCOME, purchase_workflow


app = FastAPI(
    title="RegressionForge",
    version="1.0.0",
    description="Evidence-backed post-deployment regression certification",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/artifacts", StaticFiles(directory=settings.artifacts_dir), name="artifacts")
store = Store(settings.data_dir / "regressionforge.db")
broker = RunBroker(store)
runner = Runner(store, broker, settings)
running_tasks: set[asyncio.Task] = set()


def seed() -> None:
    if store.projects():
        return
    project = Project(
        id="prj_forgecart",
        name="ForgeCart",
        repository_path=str(settings.repo_path),
        repository_remote=settings.greptile_repo or None,
    )
    store.save("project", project)
    workflow = Workflow(
        id="wf_purchase",
        project_id=project.id,
        name="Customer purchase certification",
        outcome=DEFAULT_OUTCOME,
    )
    version = purchase_workflow(workflow.id)
    version.id = "wfv_purchase_v1"
    version.approved = True
    version.approved_by = "Demo operator"
    version.approved_at = now()
    workflow.current_version_id = version.id
    store.save("workflow", workflow)
    store.save("workflow_version", version)
    for release, sha in (("good", "2f31a0d"), ("broken", "8cb0d91"), ("fixed", "d4a821e")):
        deployment = Deployment(
            id=f"dep_forgecart_{release}",
            project_id=project.id,
            environment="local",
            version=f"forgecart-{release}",
            commit_sha=sha,
            storefront_url=settings.storefront_url,
            api_url=settings.store_api_url,
        )
        store.save("deployment", deployment)


seed()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "regressionforge",
        "projects": len(store.projects()),
        "runs": len(store.runs()),
    }


@app.get("/api/overview")
def overview() -> dict:
    runs = store.runs()
    return {
        "projects": store.projects(),
        "deployments": store.deployments(),
        "workflows": store.workflows(),
        "workflow_versions": store.versions(),
        "runs": runs,
        "latest_run": runs[0] if runs else None,
    }


@app.post("/api/workflows/draft", status_code=status.HTTP_201_CREATED)
def draft_workflow(request: WorkflowDraftRequest) -> dict:
    project = store.get("project", request.project_id, Project)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workflow = Workflow(
        project_id=project.id,
        name=f"{project.name} outcome certification",
        outcome=request.outcome,
    )
    store.save("workflow", workflow)
    version = purchase_workflow(workflow.id, request.outcome)
    store.save("workflow_version", version)
    return {
        "workflow": workflow,
        "version": version,
        "review_required": True,
        "execution_policy": "Declarative approved step types only; generated code is never executed.",
    }


@app.post("/api/workflows/{item_id}/approve")
def approve_workflow(item_id: str, request: WorkflowApprovalRequest) -> WorkflowVersion:
    version = store.get("workflow_version", item_id, WorkflowVersion)
    if not version:
        workflow = store.get("workflow", item_id, Workflow)
        candidates = [item for item in store.versions() if workflow and item.workflow_id == workflow.id]
        version = sorted(candidates, key=lambda item: item.version, reverse=True)[0] if candidates else None
    if not version:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    version.approved = True
    version.approved_by = request.approved_by
    version.approved_at = now()
    store.save("workflow_version", version)
    workflow = store.get("workflow", version.workflow_id, Workflow)
    if workflow:
        workflow.current_version_id = version.id
        store.save("workflow", workflow)
    return version


@app.get("/api/workflows")
def workflows() -> dict:
    return {"workflows": store.workflows(), "versions": store.versions()}


@app.post("/api/deployments/webhook", status_code=status.HTTP_201_CREATED)
def deployment_webhook(request: DeploymentWebhookRequest) -> Deployment:
    if not store.get("project", request.project_id, Project):
        raise HTTPException(status_code=404, detail="Project not found")
    deployment = Deployment(**request.model_dump())
    store.save("deployment", deployment)
    return deployment


def approved_version_for(deployment: Deployment, requested_id: str | None) -> WorkflowVersion | None:
    if requested_id:
        version = store.get("workflow_version", requested_id, WorkflowVersion)
        workflow = store.get("workflow", version.workflow_id, Workflow) if version else None
        return (
            version
            if version and version.approved and workflow and workflow.project_id == deployment.project_id
            else None
        )
    workflow = next((item for item in store.workflows() if item.project_id == deployment.project_id), None)
    if not workflow or not workflow.current_version_id:
        return None
    version = store.get("workflow_version", workflow.current_version_id, WorkflowVersion)
    return version if version and version.approved else None


def queue_run(deployment: Deployment, version: WorkflowVersion) -> RegressionRun:
    run = RegressionRun(
        project_id=deployment.project_id,
        deployment_id=deployment.id,
        workflow_version_id=version.id,
    )
    store.save("run", run)
    task = asyncio.create_task(runner.execute(run.id), name=f"regression-run-{run.id}")
    running_tasks.add(task)
    task.add_done_callback(running_tasks.discard)
    return run


@app.post("/api/ci/certifications", status_code=status.HTTP_202_ACCEPTED)
async def ci_certification(
    request: CICertificationRequest,
    response: Response,
    authorization: str = Header(default=""),
) -> dict:
    if not settings.ci_webhook_token:
        raise HTTPException(status_code=503, detail="CI certification endpoint is not configured")
    if not valid_bearer_token(authorization, settings.ci_webhook_token):
        raise HTTPException(status_code=401, detail="Invalid CI bearer token")
    if not store.get("project", request.project_id, Project):
        raise HTTPException(status_code=404, detail="Project not found")
    deployment = Deployment(**request.model_dump(exclude={"workflow_version_id"}))
    version = approved_version_for(deployment, request.workflow_version_id)
    if not version:
        raise HTTPException(status_code=409, detail="An approved workflow version is required")
    store.save("deployment", deployment)
    run = queue_run(deployment, version)
    response.headers["Location"] = f"/api/runs/{run.id}"
    return {
        "deployment_id": deployment.id,
        "run_id": run.id,
        "status": run.status,
        "run_url": f"/api/runs/{run.id}",
        "events_url": f"/api/runs/{run.id}/events",
        "evidence_room_url": f"{settings.evidence_room_url.rstrip('/')}?run={run.id}",
    }


@app.post("/api/webhooks/fulfillment", status_code=status.HTTP_202_ACCEPTED)
async def fulfillment_webhook(
    request: Request,
    x_regressionforge_run_id: str = Header(default="untracked"),
    x_deployment_version: str = Header(default="unknown"),
) -> dict:
    body = await request.json()
    webhook_id = store.webhook(x_regressionforge_run_id, x_deployment_version, body)
    return {"accepted": True, "webhook_id": webhook_id, "run_id": x_regressionforge_run_id}


@app.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(request: RunRequest, response: Response) -> dict:
    deployment = store.get("deployment", request.deployment_id, Deployment)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    version = approved_version_for(deployment, request.workflow_version_id)
    if not version:
        raise HTTPException(status_code=409, detail="An approved workflow version is required")
    run = queue_run(deployment, version)
    response.headers["Location"] = f"/api/runs/{run.id}"
    return {
        "run_id": run.id,
        "status": run.status,
        "events_url": f"/api/runs/{run.id}/events",
        "run_url": f"/api/runs/{run.id}",
    }


@app.get("/api/runs")
def runs() -> list[RegressionRun]:
    return store.runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> RegressionRun:
    run = store.get("run", run_id, RegressionRun)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/evidence")
def run_evidence(run_id: str) -> dict:
    run = get_run(run_id)
    baseline = store.get("run", run.baseline_run_id, RegressionRun) if run.baseline_run_id else None
    return {
        "run_id": run.id,
        "trace_id": run.trace_id,
        "artifacts": run.evidence,
        "baseline_run_id": run.baseline_run_id,
        "baseline_artifacts": baseline.evidence if baseline else [],
    }


@app.get("/api/runs/{run_id}/diagnosis")
def run_diagnosis(run_id: str) -> dict:
    run = get_run(run_id)
    return {
        "run_id": run.id,
        "diagnosis": run.diagnosis,
        "memory_matches": run.memory_matches,
        "integration_status": run.integration_status,
    }


@app.get("/api/runs/{run_id}/events")
async def run_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    if not store.get("run", run_id, RegressionRun):
        raise HTTPException(status_code=404, detail="Run not found")
    cursor = max(after, int(last_event_id or 0))

    async def stream():
        nonlocal cursor
        idle_after_complete = 0
        while True:
            events = store.events(run_id, cursor)
            for event in events:
                cursor = event["sequence"]
                yield f"id: {cursor}\nevent: {event['event']}\ndata: {json_dumps(event['data'])}\n\n"
            current = store.get("run", run_id, RegressionRun)
            if current and current.completed_at and not events:
                idle_after_complete += 1
                if idle_after_complete >= 2:
                    break
            yield ": heartbeat\n\n"
            await broker.wait(run_id, timeout=5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, default=str, separators=(",", ":"))


@app.post("/api/demo/deploy/{release}")
def demo_deploy(release: str) -> dict:
    if release not in {"good", "broken", "fixed"}:
        raise HTTPException(status_code=404, detail="Unknown allowlisted release")
    if not settings.enable_demo_deployments:
        raise HTTPException(
            status_code=409,
            detail="Demo deployment API is disabled. Use make deploy-good|deploy-broken|deploy-fixed.",
        )
    script = Path(__file__).resolve().parents[2] / "scripts" / "deploy.py"
    completed = subprocess.run(
        ["python3", str(script), release, "--compose"],
        cwd=script.parent.parent,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode:
        raise HTTPException(status_code=502, detail=completed.stderr[-1200:] or "Deployment failed")
    return {"status": "deployed", "release": release, "output": completed.stdout[-1200:]}
