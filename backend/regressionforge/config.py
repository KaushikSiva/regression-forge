from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("REGRESSIONFORGE_DATA", "data"))
    artifacts_dir: Path = Path(os.getenv("REGRESSIONFORGE_ARTIFACTS", "artifacts"))
    public_api_url: str = os.getenv("PUBLIC_API_URL", "http://localhost:4400")
    storefront_url: str = os.getenv("FORGECART_STOREFRONT_URL", "http://localhost:4310")
    store_api_url: str = os.getenv("FORGECART_API_URL", "http://localhost:4301")
    mailpit_api_url: str = os.getenv("MAILPIT_API_URL", "http://localhost:8025")
    otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    signoz_url: str = os.getenv("SIGNOZ_URL", "")
    allow_local_otel_audit: bool = os.getenv("ALLOW_LOCAL_OTEL_AUDIT", "true").lower() == "true"
    glasskit_bin: str = os.getenv(
        "GLASSKIT_BIN", "/opt/glasskit/.venv/bin/glasskit"
    )
    glasskit_enabled: bool = os.getenv("GLASSKIT_ENABLED", "true").lower() == "true"
    greptile_api_key: str = os.getenv("GREPTILE_API_KEY", "")
    greptile_repo: str = os.getenv("GREPTILE_REPOSITORY", "")
    greptile_mcp_url: str = os.getenv("GREPTILE_MCP_URL", "https://api.greptile.com/mcp")
    claude_mem_url: str = os.getenv("CLAUDE_MEM_URL", "")
    codex_enabled: bool = os.getenv("CODEX_ENABLED", "false").lower() == "true"
    codex_model: str = os.getenv("CODEX_MODEL", "gpt-5.6-terra")
    repo_path: Path = Path(
        os.getenv("TARGET_REPOSITORY", "/workspace/regressionforge-demo-store")
    )
    enable_demo_deployments: bool = os.getenv("ENABLE_DEMO_DEPLOYMENTS", "false").lower() == "true"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

