from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any, Awaitable, Callable

import httpx

from .artifacts import ArtifactWriter
from .config import Settings
from .gate import decide
from .glasskit import GlassKitEvaluator
from .integrations import ClaudeMemClient, CodexDiagnoser, GreptileClient, SignozClient
from .models import (
    Deployment,
    EvidenceArtifact,
    GateStatus,
    IntegrationState,
    RegressionRun,
    ResultStatus,
    StepResult,
    StepType,
    WorkflowStep,
    WorkflowVersion,
    now,
)
from .redaction import redact
from .storage import Store
from .telemetry import Telemetry


class StepFailure(AssertionError):
    def __init__(self, summary: str, expected: Any = None, actual: Any = None):
        super().__init__(summary)
        self.summary = summary
        self.expected = expected
        self.actual = actual


class EvidenceUnavailable(RuntimeError):
    pass


EVIDENCE_SCREENSHOT_STEPS = {
    "submit-checkout": "HTTP EXCHANGE",
    "order-confirmed": "BROWSER ASSERTION",
    "order-api": "PUBLIC API RESPONSE",
    "fulfillment-webhook": "FULFILLMENT WEBHOOK",
    "signoz-errors": "SIGNOZ / CORRELATED LOGS",
}


EVIDENCE_SCREEN_SCRIPT = """
(payload) => {
  document.getElementById("regressionforge-evidence-screen")?.remove();
  const screen = document.createElement("section");
  screen.id = "regressionforge-evidence-screen";
  Object.assign(screen.style, {
    position: "fixed", inset: "0", zIndex: "2147483647", overflow: "hidden",
    padding: "46px 54px", background: "#0b0e0c", color: "#e8ece5",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
  });
  const top = document.createElement("div");
  Object.assign(top.style, { display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: "25px", borderBottom: "1px solid #293029" });
  const brand = document.createElement("span");
  brand.textContent = "REGRESSIONFORGE / EVIDENCE";
  Object.assign(brand.style, { color: "#879087", fontSize: "11px", letterSpacing: ".16em" });
  const status = document.createElement("strong");
  status.textContent = payload.status;
  Object.assign(status.style, { color: payload.color, fontSize: "12px", letterSpacing: ".14em" });
  top.append(brand, status);

  const kind = document.createElement("p");
  kind.textContent = payload.kind;
  Object.assign(kind.style, { margin: "42px 0 12px", color: payload.color, fontSize: "11px", letterSpacing: ".14em" });
  const title = document.createElement("h1");
  title.textContent = payload.name;
  Object.assign(title.style, { margin: "0", maxWidth: "980px", color: "#f5f7f2", fontFamily: "system-ui, sans-serif", fontSize: "48px", fontWeight: "500", lineHeight: "1.05", letterSpacing: "-.04em" });
  const summary = document.createElement("p");
  summary.textContent = payload.summary;
  Object.assign(summary.style, { margin: "18px 0 34px", color: "#aab2a9", fontFamily: "system-ui, sans-serif", fontSize: "16px", lineHeight: "1.5" });

  const evidence = document.createElement("pre");
  evidence.textContent = payload.evidence;
  Object.assign(evidence.style, {
    margin: "0", height: "470px", overflow: "hidden", padding: "26px 30px",
    borderTop: `1px solid ${payload.color}`, borderBottom: "1px solid #293029",
    background: "#101411", color: "#c9d0c7", whiteSpace: "pre-wrap",
    wordBreak: "break-word", fontSize: "12px", lineHeight: "1.6"
  });
  const footer = document.createElement("div");
  Object.assign(footer.style, { display: "flex", justifyContent: "space-between", marginTop: "24px", color: "#697269", fontSize: "10px", letterSpacing: ".08em" });
  const correlation = document.createElement("span");
  correlation.textContent = `RUN ${payload.runId}  /  ${payload.stepType}`;
  const source = document.createElement("span");
  source.textContent = payload.source;
  footer.append(correlation, source);
  screen.append(top, kind, title, summary, evidence, footer);
  document.body.append(screen);
}
"""


class RunBroker:
    def __init__(self, store: Store):
        self.store = store
        self._signals: dict[str, asyncio.Condition] = {}

    async def publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.store.event(run_id, {"event": event_type, "data": redact(data)})
        condition = self._signals.setdefault(run_id, asyncio.Condition())
        async with condition:
            condition.notify_all()

    async def wait(self, run_id: str, timeout: float = 10) -> None:
        condition = self._signals.setdefault(run_id, asyncio.Condition())
        async with condition:
            try:
                await asyncio.wait_for(condition.wait(), timeout=timeout)
            except TimeoutError:
                pass


class Runner:
    def __init__(self, store: Store, broker: RunBroker, settings: Settings):
        self.store = store
        self.broker = broker
        self.settings = settings
        self.telemetry = Telemetry(settings.data_dir / "telemetry.jsonl", settings.otlp_endpoint)
        self.greptile = GreptileClient(settings)
        self.memory = ClaudeMemClient(settings)
        self.codex = CodexDiagnoser(settings)
        self.signoz = SignozClient(settings)
        self.glasskit = GlassKitEvaluator(settings)

    async def execute(self, run_id: str) -> None:
        run = self.store.get("run", run_id, RegressionRun)
        if not run:
            return
        deployment = self.store.get("deployment", run.deployment_id, Deployment)
        version = self.store.get("workflow_version", run.workflow_version_id, WorkflowVersion)
        if not deployment or not version:
            run.status = ResultStatus.ERROR
            run.completed_at = now()
            self.store.save("run", run)
            await self.broker.publish(run.id, "run.failed", {"reason": "Deployment or workflow not found"})
            return

        writer = ArtifactWriter(self.settings.artifacts_dir, self.settings.public_api_url, run.id)
        run.status = ResultStatus.RUNNING
        run.started_at = now()
        baseline = self.store.latest_passing_run(run.workflow_version_id, run.id)
        run.baseline_run_id = baseline.id if baseline else None
        self.store.save("run", run)
        await self.broker.publish(run.id, "run.started", {"run_id": run.id})

        with self.telemetry.span(
            "regressionforge.run",
            {
                "regression.run_id": run.id,
                "deployment.version": deployment.version,
                "workflow.version": version.content_hash,
            },
        ):
            run.trace_id = self.telemetry.trace_id()
            with self.telemetry.span("memory.recall", {"regression.run_id": run.id}):
                matches, memory_state = await self.memory.recall(
                    f"ForgeCart checkout {deployment.version} {version.outcome}"
                )
                run.memory_matches = matches
                run.integration_status["claude_mem_recall"] = memory_state
                if matches:
                    memory_artifact = writer.json(
                        kind="memory",
                        label="Claude-Mem recalled observations",
                        filename="memory-recall.json",
                        data=[match.model_dump(mode="json") for match in matches],
                    )
                    run.evidence.append(memory_artifact)
            await self.broker.publish(
                run.id,
                "memory.recalled",
                {"count": len(matches), "status": memory_state, "observation_ids": [m.observation_id for m in matches]},
            )

            await self._run_steps(run, version, deployment, writer)
            run.gate = decide(run.step_results)
            await self.broker.publish(run.id, "gate.decided", run.gate.model_dump(mode="json"))

            failed_text = " ".join(
                f"{result.step_name} {result.summary}" for result in run.step_results if result.status in {ResultStatus.FAILED, ResultStatus.ERROR}
            ) or "checkout order email webhook observability"
            with self.telemetry.span("greptile.context", {"regression.run_id": run.id}):
                source_context, greptile_state = await self.greptile.repository_context(failed_text[:200])
                run.integration_status["greptile"] = greptile_state
                if source_context:
                    source_artifact = writer.json(
                        kind="source",
                        label="Greptile knowledge-base context",
                        filename="greptile-context.json",
                        data=source_context,
                    )
                    run.evidence.append(source_artifact)

            changed_files = await self._changed_files(deployment)
            with self.telemetry.span("codex.diagnose", {"regression.run_id": run.id}):
                run.diagnosis = await self.codex.diagnose(run, source_context, changed_files)
                run.integration_status["codex"] = run.diagnosis.status

            run.status = {
                GateStatus.PASS: ResultStatus.PASSED,
                GateStatus.FAIL: ResultStatus.FAILED,
                GateStatus.NEEDS_REVIEW: ResultStatus.NEEDS_REVIEW,
            }[run.gate.status]
            run.completed_at = now()
            self.store.save("run", run)

            with self.telemetry.span("memory.save", {"regression.run_id": run.id}):
                memory_save_state = await self.memory.save(run)
                run.integration_status["claude_mem_save"] = memory_save_state

            self.store.save("run", run)
            await self.broker.publish(
                run.id,
                "run.completed",
                {"status": run.status, "gate": run.gate.model_dump(mode="json")},
            )

    async def _run_steps(
        self,
        run: RegressionRun,
        version: WorkflowVersion,
        deployment: Deployment,
        writer: ArtifactWriter,
    ) -> None:
        page = None
        browser = None
        context = None
        playwright = None
        browser_error = ""
        video_path: Path | None = None
        video_dir = writer.run_dir / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.async_api import async_playwright

            with self.telemetry.span("browser.launch", {"regression.run_id": run.id}):
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 920},
                    record_video_dir=str(video_dir),
                    record_video_size={"width": 1440, "height": 920},
                    extra_http_headers={
                        "x-regressionforge-run-id": run.id,
                        "x-deployment-version": deployment.version,
                    },
                )
                await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                page = await context.new_page()
                page.set_default_timeout(6000)
                page.on(
                    "console",
                    lambda message: run.console_errors.append(
                        redact({"type": message.type, "text": message.text})
                    ) if message.type in {"error", "warning"} else None,
                )
                page.on(
                    "pageerror",
                    lambda error: run.console_errors.append(redact({"type": "pageerror", "text": str(error)})),
                )
        except Exception as exc:
            browser_error = f"Browser launch failed: {exc}"

        browser_types = {
            StepType.NAVIGATE,
            StepType.CLICK,
            StepType.FILL,
            StepType.ASSERT_VISIBLE,
            StepType.ASSERT_TEXT,
        }
        for step in version.steps:
            result = StepResult(
                run_id=run.id,
                step_id=step.id,
                step_name=step.name,
                step_type=step.type,
                required=step.required,
                status=ResultStatus.RUNNING,
            )
            run.step_results.append(result)
            self.store.save("run", run)
            await self.broker.publish(
                run.id, "step.started", {"step_id": step.id, "name": step.name, "type": step.type}
            )
            started = time.perf_counter()
            try:
                with self.telemetry.span(
                    f"step.{step.id}",
                    {"regression.run_id": run.id, "step.type": step.type, "deployment.version": deployment.version},
                ):
                    if step.type in browser_types and page is None:
                        raise StepFailure(browser_error or "Browser is unavailable")
                    summary, expected, actual, evidence = await self._execute_step(
                        step, page, run, deployment, writer
                    )
                result.status = ResultStatus.PASSED
                result.summary = summary
                result.expected = expected
                result.actual = redact(actual)
                for artifact in evidence:
                    run.evidence.append(artifact)
                    result.evidence_ids.append(artifact.id)
            except EvidenceUnavailable as exc:
                result.status = ResultStatus.NEEDS_REVIEW
                result.summary = str(exc)
            except StepFailure as exc:
                result.status = ResultStatus.FAILED
                result.summary = exc.summary
                result.expected = exc.expected
                result.actual = redact(exc.actual)
            except Exception as exc:
                result.status = ResultStatus.ERROR
                result.summary = str(exc)

            capture_mailbox = step.id == "confirmation-email"
            capture_evidence = step.id in EVIDENCE_SCREENSHOT_STEPS
            if page is not None and (step.type in browser_types or capture_mailbox or capture_evidence):
                try:
                    if capture_mailbox:
                        await page.goto(self.settings.mailpit_api_url, wait_until="networkidle")
                        search = page.get_by_placeholder("Search mailbox")
                        await search.fill(run.id)
                        await search.press("Enter")
                        await page.wait_for_timeout(350)
                    elif capture_evidence:
                        evidence = self._step_evidence_payload(step, result, run, writer)
                        await page.evaluate(
                            EVIDENCE_SCREEN_SCRIPT,
                            {
                                "kind": EVIDENCE_SCREENSHOT_STEPS[step.id],
                                "name": step.name,
                                "status": str(result.status),
                                "summary": result.summary,
                                "stepType": str(step.type),
                                "runId": run.id,
                                "source": evidence["source"],
                                "color": "#a8e63d" if result.status == ResultStatus.PASSED else (
                                    "#e0b95b" if result.status == ResultStatus.NEEDS_REVIEW else "#ff6846"
                                ),
                                "evidence": json.dumps(evidence["payload"], indent=2, ensure_ascii=False, default=str)[:10000],
                            },
                        )
                    screenshot_path = writer.run_dir / f"{len(run.step_results):02d}-{step.id}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    artifact = writer.artifact(
                        kind="screenshot",
                        label=(
                            f"Mailpit mailbox for {run.id} — {result.status}"
                            if capture_mailbox else (
                                f"{EVIDENCE_SCREENSHOT_STEPS[step.id]} for {run.id} — {result.status}"
                                if capture_evidence else f"{step.name} — {result.status}"
                            )
                        ),
                        step_id=step.id,
                        path=screenshot_path,
                        mime_type="image/png",
                        metadata={
                            "status": result.status,
                            "surface": "mailpit" if capture_mailbox else (
                                "signoz" if step.id == "signoz-errors" else (
                                    "evidence" if capture_evidence else "forgecart"
                                )
                            ),
                        },
                    )
                    run.evidence.append(artifact)
                    result.evidence_ids.append(artifact.id)
                except Exception:
                    pass
                finally:
                    if capture_evidence:
                        try:
                            await page.evaluate(
                                'document.getElementById("regressionforge-evidence-screen")?.remove()'
                            )
                        except Exception:
                            pass
            for step_artifact in run.evidence:
                if step_artifact.step_id == step.id and step_artifact.id not in result.evidence_ids:
                    result.evidence_ids.append(step_artifact.id)
            result.completed_at = now()
            result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self.store.save("run", run)
            await self.broker.publish(
                run.id,
                "step.completed",
                {
                    "step_id": step.id,
                    "status": result.status,
                    "summary": result.summary,
                    "duration_ms": result.duration_ms,
                    "evidence_ids": result.evidence_ids,
                },
            )

        if context:
            try:
                trace_path = writer.run_dir / "playwright-trace.zip"
                await context.tracing.stop(path=str(trace_path))
                run.evidence.append(
                    writer.artifact(
                        kind="trace",
                        label="Playwright browser trace",
                        path=trace_path,
                        mime_type="application/zip",
                    )
                )
                if page and page.video:
                    video_path = Path(await page.video.path())
            except Exception:
                pass
            await context.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

        videos = sorted(video_dir.glob("*.webm"))
        video_path = videos[0] if videos else video_path
        if video_path and video_path.exists():
            run.evidence.append(
                writer.artifact(
                    kind="video",
                    label="Same-run browser recording",
                    path=video_path,
                    mime_type="video/webm",
                    metadata={"run_id": run.id, "trace_id": run.trace_id},
                )
            )
            with self.telemetry.span("glasskit.evaluate", {"regression.run_id": run.id}):
                glasskit_report, glasskit_state = await self.glasskit.evaluate(writer.run_dir, video_path)
            run.integration_status["glasskit"] = glasskit_state
            glasskit_artifact = writer.json(
                kind="glasskit",
                label="GlassKit repeated-trial visual report",
                filename="glasskit-report-summary.json",
                data=glasskit_report,
            )
            run.evidence.append(glasskit_artifact)
            checkpoint = next(
                (result for result in run.step_results if result.step_id == "order-confirmed"), None
            )
            if checkpoint:
                checkpoint.evidence_ids.append(glasskit_artifact.id)
                if glasskit_state == IntegrationState.COMPLETE and glasskit_report.get("status") != "passed":
                    checkpoint.status = ResultStatus.FAILED
                    checkpoint.summary += " GlassKit's repeated visual checkpoint was not stable."
                elif glasskit_state == IntegrationState.UNAVAILABLE and checkpoint.status == ResultStatus.PASSED:
                    checkpoint.status = ResultStatus.NEEDS_REVIEW
                    checkpoint.summary += " GlassKit visual evidence was unavailable."
        else:
            run.integration_status["glasskit"] = IntegrationState.UNAVAILABLE

        if run.console_errors:
            run.evidence.append(
                writer.json(
                    kind="console",
                    label="Browser console warnings and errors",
                    filename="console.json",
                    data=run.console_errors,
                )
            )
        if run.network_events:
            run.evidence.append(
                writer.json(
                    kind="network",
                    label="Correlated browser network activity",
                    filename="network.json",
                    data=run.network_events,
                )
            )
        self.store.save("run", run)

    def _step_evidence_payload(
        self,
        step: WorkflowStep,
        result: StepResult,
        run: RegressionRun,
        writer: ArtifactWriter,
    ) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        sources: list[str] = []
        for artifact in run.evidence:
            if artifact.step_id != step.id:
                continue
            item: dict[str, Any] = {"kind": artifact.kind, "label": artifact.label}
            if artifact.path:
                path = writer.run_dir.parent / artifact.path
                if path.exists() and artifact.mime_type == "application/json":
                    try:
                        item["data"] = json.loads(path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        item["data"] = {"status": "artifact unreadable"}
            artifacts.append(item)
            sources.append(artifact.kind)
        payload = redact({
            "expected": result.expected,
            "observed": result.actual,
            "artifacts": artifacts,
        })
        source = " + ".join(sources) if sources else "deterministic browser evidence"
        return {"payload": payload, "source": source.upper()}

    async def _execute_step(
        self,
        step: WorkflowStep,
        page: Any,
        run: RegressionRun,
        deployment: Deployment,
        writer: ArtifactWriter,
    ) -> tuple[str, Any, Any, list[EvidenceArtifact]]:
        config = step.config
        if step.type == StepType.NAVIGATE:
            target = f"{deployment.storefront_url.rstrip('/')}{config.get('path', '/')}?rf_run_id={run.id}"
            response = await page.goto(target, wait_until="networkidle")
            status = response.status if response else 0
            if status >= 400 or not response:
                raise StepFailure(f"Navigation returned HTTP {status}", "HTTP < 400", status)
            return f"Loaded {target}", "HTTP < 400", status, []

        if step.type == StepType.CLICK:
            selector = config["selector"]
            if config.get("capture_response"):
                async with page.expect_response(
                    lambda response: config["capture_response"] in response.url, timeout=10000
                ) as pending:
                    await page.click(selector)
                response = await pending.value
                try:
                    body = await response.json()
                except Exception:
                    body = await response.text()
                network = redact(
                    {
                        "method": response.request.method,
                        "url": response.url,
                        "status": response.status,
                        "request_headers": await response.request.all_headers(),
                        "request_body": response.request.post_data,
                        "response_headers": await response.all_headers(),
                        "response_body": body,
                        "run_id": run.id,
                    }
                )
                run.network_events.append(network)
                artifact = writer.json(
                    kind="http",
                    label=f"{response.request.method} {response.url} → {response.status}",
                    filename=f"{step.id}-http.json",
                    data=network,
                    step_id=step.id,
                )
                expected_status = int(config["expect_status"])
                if response.status != expected_status:
                    run.evidence.append(artifact)
                    raise StepFailure(
                        f"Checkout returned HTTP {response.status}", expected_status, network
                    )
                return "Checkout request returned HTTP 200", expected_status, response.status, [artifact]
            await page.click(selector)
            return f"Clicked {selector}", "element actionable", "clicked", []

        if step.type == StepType.FILL:
            await page.fill(config["selector"], config["value"])
            return f"Filled {config['selector']}", "value entered", "entered", []

        if step.type == StepType.ASSERT_VISIBLE:
            locator = page.locator(config["selector"])
            try:
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                error_text = ""
                try:
                    error_text = await page.locator("[data-testid='checkout-error']").inner_text(timeout=500)
                except Exception:
                    pass
                raise StepFailure(
                    f"Required confirmation was not visible{': ' + error_text if error_text else ''}",
                    "visible",
                    "not visible",
                )
            return "Order confirmation is visible", "visible", "visible", []

        if step.type == StepType.ASSERT_TEXT:
            actual = await page.locator(config["selector"]).inner_text()
            expected = config["contains"]
            if expected.casefold() not in actual.casefold():
                raise StepFailure(f"Expected text {expected!r} was absent", expected, actual)
            return f"Visible text contains {expected!r}", expected, actual, []

        if step.type == StepType.ASSERT_HTTP:
            headers = {
                "x-regressionforge-run-id": run.id,
                "x-deployment-version": deployment.version,
            }
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    f"{deployment.api_url.rstrip('/')}{config['path']}",
                    params={"run_id": run.id},
                    headers=headers,
                )
            try:
                body = response.json()
            except Exception:
                body = response.text
            payload = redact({"status": response.status_code, "url": str(response.url), "body": body})
            artifact = writer.json(
                kind="http", label="Public order API response", filename=f"{step.id}.json", data=payload, step_id=step.id
            )
            minimum = int(config.get("minimum_items", 1))
            count = len(body) if isinstance(body, list) else 0
            if response.status_code != 200 or count < minimum:
                run.evidence.append(artifact)
                raise StepFailure("No correlated order was returned by the public API", f">={minimum} order", payload)
            return f"Public API returned {count} correlated order", f">={minimum} order", count, [artifact]

        if step.type == StepType.ASSERT_EMAIL:
            messages: list[dict] = []
            async with httpx.AsyncClient(timeout=8) as client:
                for _ in range(8):
                    try:
                        response = await client.get(f"{self.settings.mailpit_api_url.rstrip('/')}/api/v1/messages")
                        response.raise_for_status()
                        summaries = response.json().get("messages", response.json().get("Messages", []))
                        for item in summaries:
                            message_id = item.get("ID") or item.get("id")
                            detail = item
                            if message_id:
                                detail_response = await client.get(
                                    f"{self.settings.mailpit_api_url.rstrip('/')}/api/v1/message/{message_id}"
                                )
                                if detail_response.is_success:
                                    detail = detail_response.json()
                            messages.append(detail)
                        found = [message for message in messages if run.id in json.dumps(message)]
                        if found:
                            messages = found
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
            artifact = writer.json(
                kind="email",
                label="Mailpit confirmation email evidence",
                filename=f"{step.id}.json",
                data=messages,
                step_id=step.id,
            )
            if not messages or not any(run.id in json.dumps(message) for message in messages):
                run.evidence.append(artifact)
                raise StepFailure("No confirmation email was found for this run", "matching email", 0)
            return "Mailpit contains a confirmation email carrying this run ID", "matching email", len(messages), [artifact]

        if step.type == StepType.ASSERT_WEBHOOK:
            hooks: list[dict] = []
            for _ in range(8):
                hooks = self.store.webhooks(run.id)
                if hooks:
                    break
                await asyncio.sleep(0.5)
            artifact = writer.json(
                kind="webhook",
                label="Fulfillment receiver payload",
                filename=f"{step.id}.json",
                data=hooks,
                step_id=step.id,
            )
            expected_event = config["event"]
            matching = [hook for hook in hooks if hook.get("event") == expected_event]
            if not matching:
                run.evidence.append(artifact)
                raise StepFailure("No correlated fulfillment webhook was received", expected_event, hooks)
            return "Fulfillment receiver contains the correlated webhook", expected_event, matching[0], [artifact]

        if step.type == StepType.ASSERT_SIGNOZ_LOGS:
            with self.telemetry.span("signoz.query", {"regression.run_id": run.id}):
                logs, available = await self.signoz.query(run.id, deployment.version)
            artifact = writer.json(
                kind="signoz",
                label=f"Correlated observability query — {logs.get('source', 'unknown')}",
                filename=f"{step.id}.json",
                data=logs,
                step_id=step.id,
            )
            run.evidence.append(artifact)
            if not available:
                raise EvidenceUnavailable("Required SigNoz/log evidence was unavailable; PASS is prohibited")
            serialized = json.dumps(logs).lower()
            error_count = sum(serialized.count(marker) for marker in ['"severity": "error"', "contract_error", '"status": "error"'])
            maximum = int(config.get("maximum_errors", 0))
            if error_count > maximum:
                raise StepFailure(f"Found {error_count} correlated error log signals", maximum, logs)
            return "No correlated error logs were found", maximum, error_count, []

        raise StepFailure(f"Unsupported approved step type: {step.type}")

    async def _changed_files(self, deployment: Deployment) -> list[str]:
        repo = self.settings.repo_path
        if not (repo / ".git").exists():
            candidate = repo / "backend/forgecart/contracts" / f"{deployment.version.split('-')[-1]}.py"
            return [str(candidate.relative_to(repo))] if candidate.exists() else []
        process = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo), "diff", "--name-only", "HEAD~1", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return [line for line in stdout.decode().splitlines() if line][:20]
