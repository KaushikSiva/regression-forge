from __future__ import annotations

import pytest

from scripts import ci_certify


def test_request_json_wraps_connection_reset_for_health_retry(monkeypatch):
    def reset_connection(*_args, **_kwargs):
        raise ConnectionResetError("container is restarting")

    monkeypatch.setattr(ci_certify, "urlopen", reset_connection)

    with pytest.raises(RuntimeError, match="container is restarting"):
        ci_certify.request_json("http://localhost:4400/health")
