from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

from regressionforge.integrations import (
    ClaudeMemClient,
    CodexDiagnoser,
    _mcp_tool_data,
    _review_ids,
    _string_list,
)
from regressionforge.models import GateDecision, GateStatus, RegressionRun


def test_mcp_tool_data_prefers_structured_content():
    assert _mcp_tool_data(
        {"result": {"structuredContent": {"comments": [{"id": "one"}]}}}
    ) == {"comments": [{"id": "one"}]}


def test_review_ids_uses_current_greptile_shape():
    assert _review_ids({"codeReviews": [{"id": "review_123"}]}) == ["review_123"]


def test_string_list_accepts_one_or_many_structured_values():
    assert _string_list("Inspect the checkout request.") == ["Inspect the checkout request."]
    assert _string_list(["one", "two", None, 3]) == ["one", "two"]
    assert _string_list(None) == []


def test_claude_mem_recall_uses_authenticated_server_v1(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "observations": [
                    {
                        "id": 17,
                        "content": '{"title":"Passing ForgeCart baseline","narrative":"Checkout, email, webhook, and logs passed."}',
                        "createdAtEpoch": 1787504400000,
                    }
                ]
            }

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, headers: dict, json: dict):
            assert url == "http://memory.test/v1/search"
            assert headers == {"Authorization": "Bearer memory-secret"}
            assert json["projectId"] == "project-17"
            assert "platformSource" not in json
            return Response()

    monkeypatch.setattr("regressionforge.integrations.httpx.AsyncClient", Client)
    client = ClaudeMemClient(
        SimpleNamespace(
            claude_mem_url="http://memory.test",
            claude_mem_api_key="memory-secret",
            claude_mem_project_id="project-17",
        )
    )

    matches, state = asyncio.run(client.recall("ForgeCart checkout baseline"))

    assert state == "COMPLETE"
    assert matches[0].observation_id == "17"


def test_claude_mem_save_uses_authenticated_server_memory_route(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class Response:
        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, headers: dict, json: dict):
            assert headers == {"Authorization": "Bearer memory-secret"}
            calls.append((url, json))
            return Response()

    monkeypatch.setattr("regressionforge.integrations.httpx.AsyncClient", Client)
    client = ClaudeMemClient(
        SimpleNamespace(
            claude_mem_url="http://memory.test",
            claude_mem_api_key="memory-secret",
            claude_mem_project_id="project-17",
        )
    )
    run = RegressionRun(
        id="run_ci_test",
        project_id="prj_forgecart",
        deployment_id="dep_ci_test",
        workflow_version_id="wfv_purchase_v1",
        gate=GateDecision(
            status=GateStatus.PASS,
            reason="All checks passed",
            passed_required=11,
            failed_required=0,
            review_required=0,
        ),
    )

    state = asyncio.run(client.save(run))

    assert state == "COMPLETE"
    assert [url for url, _ in calls] == ["http://memory.test/v1/memories"]
    assert calls[0][1]["projectId"] == "project-17"
    assert calls[0][1]["metadata"]["runId"] == "run_ci_test"
    assert '"gate": "PASS"' in calls[0][1]["content"]


def test_codex_diagnosis_logs_in_with_configured_api_key(monkeypatch, tmp_path):
    calls: list[tuple[str, object]] = []

    class Thread:
        async def run(self, _prompt: str):
            return SimpleNamespace(
                final_response=json.dumps(
                    {
                        "summary": "The evidence proves the checkout request failed.",
                        "evidence_citations": ["ev_http"],
                        "changed_files": ["backend/forgecart/contracts/good.py"],
                        "investigation": ["Inspect the checkout request contract."],
                        "confidence": "high",
                    }
                )
            )

    class AsyncCodex:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def login_api_key(self, api_key: str):
            calls.append(("login", api_key))

        async def thread_start(self, **kwargs):
            calls.append(("thread_start", kwargs))
            return Thread()

    class Sandbox:
        read_only = "read-only"

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setitem(
        sys.modules,
        "openai_codex",
        SimpleNamespace(AsyncCodex=AsyncCodex, Sandbox=Sandbox),
    )
    diagnoser = CodexDiagnoser(
        SimpleNamespace(codex_enabled=True, codex_model="gpt-5.6-terra", repo_path=tmp_path)
    )
    run = RegressionRun(
        id="run_codex_test",
        project_id="prj_forgecart",
        deployment_id="dep_codex_test",
        workflow_version_id="wfv_purchase_v1",
        gate=GateDecision(
            status=GateStatus.FAIL,
            reason="Checkout failed",
            passed_required=5,
            failed_required=6,
            review_required=0,
        ),
    )

    diagnosis = asyncio.run(
        diagnoser.diagnose(run, [], ["backend/forgecart/contracts/good.py"])
    )

    assert calls[0] == ("login", "test-openai-key")
    assert calls[1][0] == "thread_start"
    assert diagnosis.status == "COMPLETE"
    assert diagnosis.provider == "OpenAI Codex SDK / read-only sandbox"
