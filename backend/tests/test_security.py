from regressionforge.security import valid_bearer_token


def test_ci_bearer_token_requires_exact_match():
    assert valid_bearer_token("Bearer demo-secret", "demo-secret")
    assert not valid_bearer_token("Bearer wrong", "demo-secret")
    assert not valid_bearer_token("Basic demo-secret", "demo-secret")
    assert not valid_bearer_token("Bearer demo-secret", "")
