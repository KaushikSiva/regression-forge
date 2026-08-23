from __future__ import annotations

import asyncio
from types import SimpleNamespace

from regressionforge.integrations import (
    ClaudeMemClient,
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


def test_claude_mem_recall_uses_paginated_items(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "id": 17,
                        "title": "Passing ForgeCart baseline",
                        "narrative": "Checkout, email, webhook, and logs passed.",
                        "created_at": "2026-08-23T10:00:00Z",
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

        async def get(self, _url: str, params: dict):
            assert params["project"] == "RegressionForge"
            return Response()

    monkeypatch.setattr("regressionforge.integrations.httpx.AsyncClient", Client)
    client = ClaudeMemClient(SimpleNamespace(claude_mem_url="http://memory.test"))

    matches, state = asyncio.run(client.recall("ForgeCart checkout baseline"))

    assert state == "COMPLETE"
    assert matches[0].observation_id == "17"


def test_claude_mem_save_uses_current_session_routes(monkeypatch):
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

        async def post(self, url: str, json: dict):
            calls.append((url, json))
            return Response()

    monkeypatch.setattr("regressionforge.integrations.httpx.AsyncClient", Client)
    client = ClaudeMemClient(SimpleNamespace(claude_mem_url="http://memory.test"))
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
    assert [url for url, _ in calls] == [
        "http://memory.test/api/sessions/init",
        "http://memory.test/api/sessions/observations",
        "http://memory.test/api/sessions/summarize",
    ]
    assert calls[1][1]["contentSessionId"] == "run_ci_test"
    assert "tool_response" in calls[1][1]
