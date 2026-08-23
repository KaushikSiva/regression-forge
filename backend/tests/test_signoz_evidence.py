from regressionforge.runner import Runner


def test_signoz_error_count_counts_each_log_once() -> None:
    logs = {
        "source": "signoz",
        "result": {
            "data": {
                "data": {
                    "results": [
                        {
                            "rows": [
                                {
                                    "data": {
                                        "severity_text": "ERROR",
                                        "body": '{"event":"checkout.contract_error","severity":"ERROR"}',
                                    }
                                },
                                {
                                    "data": {
                                        "severity_text": "INFO",
                                        "body": '{"event":"checkout.order_persisted","severity":"INFO"}',
                                    }
                                },
                            ]
                        }
                    ]
                }
            }
        },
    }

    assert Runner._error_log_count(logs) == 1


def test_local_audit_error_count_uses_structured_records() -> None:
    logs = {
        "source": "local_otel_audit",
        "records": [
            {"event": "checkout.email_failed", "severity": "ERROR"},
            {"event": "checkout.webhook_sent", "severity": "INFO"},
        ],
    }

    assert Runner._error_log_count(logs) == 1
