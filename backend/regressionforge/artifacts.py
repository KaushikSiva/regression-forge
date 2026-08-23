from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import EvidenceArtifact
from .redaction import redact


class ArtifactWriter:
    def __init__(self, root: Path, public_api_url: str, run_id: str):
        self.run_id = run_id
        self.run_dir = root / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.public_api_url = public_api_url.rstrip("/")

    def artifact(
        self,
        *,
        kind: str,
        label: str,
        step_id: str | None = None,
        path: Path | None = None,
        metadata: dict[str, Any] | None = None,
        mime_type: str = "application/json",
    ) -> EvidenceArtifact:
        digest = None
        relative = None
        url = None
        if path and path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = str(path.relative_to(self.run_dir.parent))
            url = f"{self.public_api_url}/artifacts/{relative}"
        return EvidenceArtifact(
            run_id=self.run_id,
            step_id=step_id,
            kind=kind,  # type: ignore[arg-type]
            label=label,
            path=relative,
            url=url,
            mime_type=mime_type,
            sha256=digest,
            metadata=redact(metadata or {}),
        )

    def json(
        self, *, kind: str, label: str, filename: str, data: Any, step_id: str | None = None
    ) -> EvidenceArtifact:
        path = self.run_dir / filename
        path.write_text(json.dumps(redact(data), indent=2, default=str), encoding="utf-8")
        return self.artifact(kind=kind, label=label, step_id=step_id, path=path)

