from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .models import IntegrationState


ADAPTER_SOURCE = '''
class Evaluator:
    async def evaluate(self, sample, target):
        image = sample.image.convert("RGB")
        width, height = image.size
        if width < 320 or height < 240:
            return {"rendered": False, "dimensions": [width, height]}
        pixels = image.resize((32, 32)).getdata()
        luminance = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
        spread = max(luminance) - min(luminance)
        return {"rendered": spread >= 35, "dimensions_ok": width >= height}

def create_evaluator(context):
    return Evaluator()
'''.lstrip()


class GlassKitEvaluator:
    """Deterministic repeated-trial video render gate powered by local GlassKit Eval."""

    def __init__(self, settings: Settings):
        self.enabled = settings.glasskit_enabled
        configured = Path(settings.glasskit_bin)
        host_fallback = Path("/Users/kaushiksivakumar/workspace/GlassKit/cli/.venv/bin/glasskit")
        self.bin = configured if configured.exists() else host_fallback

    async def evaluate(self, run_dir: Path, video: Path) -> tuple[dict[str, Any], IntegrationState]:
        if not self.enabled:
            return {"status": "disabled"}, IntegrationState.NOT_CONFIGURED
        if not self.bin.exists() or not video.exists():
            return {"status": "unavailable", "reason": "GlassKit executable or video is missing"}, IntegrationState.UNAVAILABLE
        eval_dir = run_dir / "glasskit-eval"
        cases = eval_dir / "cases"
        cases.mkdir(parents=True, exist_ok=True)
        adapter = eval_dir / "adapter.py"
        adapter.write_text(ADAPTER_SOURCE, encoding="utf-8")
        case = {
            "video": str(video.resolve()),
            "description": "Approved ForgeCart browser-recording render checkpoint",
            "targets": {
                "forgecart_rendered": {
                    "samples": [{"at": 1.0, "field": "rendered", "expect": True}],
                }
            },
        }
        (cases / "forgecart-run.yaml").write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
        report = eval_dir / "report.json"
        artifacts = eval_dir / "artifacts"
        process = await asyncio.create_subprocess_exec(
            str(self.bin),
            "eval",
            "run",
            "--eval-dir",
            str(eval_dir),
            "--repeat",
            "3",
            "--min-pass-rate",
            "1",
            "--max-flaky-samples",
            "0",
            "--output-json",
            str(report),
            "--artifacts-dir",
            str(artifacts),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        payload: dict[str, Any] = {
            "engine": "GlassKit Eval",
            "repeat": 3,
            "exit_code": process.returncode,
            "stdout_tail": stdout.decode(errors="replace")[-1600:],
            "stderr_tail": stderr.decode(errors="replace")[-1600:],
        }
        if report.exists():
            try:
                payload["report"] = json.loads(report.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload["report_error"] = "GlassKit report was not valid JSON"
        state = IntegrationState.COMPLETE if process.returncode in {0, 1} else IntegrationState.UNAVAILABLE
        payload["status"] = "passed" if process.returncode == 0 else "failed"
        return payload, state
