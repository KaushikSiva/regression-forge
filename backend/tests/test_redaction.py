from regressionforge.redaction import redact


def test_nested_secrets_are_redacted():
    result = redact({"Authorization": "Bearer live-secret", "url": "https://x.test?q=1&token=abc"})
    assert result["Authorization"] == "[REDACTED]"
    assert "abc" not in result["url"]

