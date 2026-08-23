#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
TERMINAL_STATUSES = {"PASSED", "FAILED", "NEEDS_REVIEW", "ERROR"}


def request_json(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    token: str = "",
    timeout: int = 15,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"RegressionForge returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach RegressionForge at {url}: {error.reason}") from error


def wait_for_health(url: str, attempts: int = 90) -> None:
    for _ in range(attempts):
        try:
            if request_json(url).get("status") == "ok":
                return
        except RuntimeError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


def changed_files(source: Path, base_sha: str, head_sha: str) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(source), "diff", "--name-only", f"{base_sha}...{head_sha}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "Could not calculate the pull-request diff")
    return [line for line in completed.stdout.splitlines() if line][:100]


def deploy_pull_request(source: Path, version: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "FORGECART_SOURCE_DIR": str(source.resolve()),
            # The demo PR changes the active good.py contract itself, so the
            # exact checked-out PR revision determines whether checkout works.
            "FORGECART_RELEASE": "good",
            "FORGECART_DEPLOYMENT_VERSION": version,
        }
    )
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "docker-compose.yml"),
            "up",
            "-d",
            "--build",
            "--force-recreate",
            "--no-deps",
            "regressionforge-api",
            "forgecart-api",
            "forgecart-web",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("Docker could not deploy the pull-request revision")


def append_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")


def write_summary(run: dict, evidence_url: str) -> None:
    gate = (run.get("gate") or {}).get("status", "UNKNOWN")
    reason = (run.get("gate") or {}).get("reason", "Certification did not return a gate reason")
    failed = [
        result.get("step_name", result.get("step_id", "Unknown step"))
        for result in run.get("step_results", [])
        if result.get("status") in {"FAILED", "ERROR", "NEEDS_REVIEW"}
    ]
    lines = [
        "## RegressionForge deployment certification",
        "",
        f"**Gate:** `{gate}`  ",
        f"**Run:** `{run.get('id', 'unknown')}`  ",
        f"**Reason:** {reason}  ",
        f"**Evidence room:** [Open evidence]({evidence_url})",
    ]
    if failed:
        lines.extend(["", "**Non-passing checks:**", *[f"- {name}" for name in failed]])
    summary = "\n".join(lines) + "\n"
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as output:
            output.write(summary)
    print(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy the exact ForgeCart PR revision and block CI on its RegressionForge gate"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api = (os.getenv("REGRESSIONFORGE_API") or "http://localhost:4400").rstrip("/")
    token = os.getenv("REGRESSIONFORGE_CI_TOKEN", "")
    if not token:
        raise RuntimeError("REGRESSIONFORGE_CI_TOKEN is required")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        raise RuntimeError("--repository must use owner/repository format")
    if args.pr_number < 1:
        raise RuntimeError("--pr-number must be positive")
    if not args.source_dir.joinpath(".git").exists():
        # actions/checkout may use a .git file for a linked worktree.
        if not args.source_dir.joinpath(".git").is_file():
            raise RuntimeError(f"{args.source_dir} is not a Git checkout")

    wait_for_health(f"{api}/health", attempts=10)
    files = changed_files(args.source_dir, args.base_sha, args.head_sha)
    version = f"pr-{args.pr_number}-{args.head_sha[:8]}"
    print(f"Deploying {args.repository} PR #{args.pr_number} at {args.head_sha[:12]}")
    deploy_pull_request(args.source_dir, version)
    wait_for_health(f"{api}/health")
    wait_for_health("http://localhost:4301/health")

    certification = request_json(
        f"{api}/api/ci/certifications",
        "POST",
        {
            "project_id": "prj_forgecart",
            "environment": "pull-request",
            "version": version,
            "commit_sha": args.head_sha,
            "storefront_url": "http://forgecart-web",
            "api_url": "http://forgecart-api:8000",
            "repository": args.repository,
            "repository_provider": "github",
            "default_branch": args.default_branch,
            "pull_request_number": args.pr_number,
            "pull_request_url": args.pr_url,
            "base_sha": args.base_sha,
            "head_sha": args.head_sha,
            "changed_files": files,
        },
        token=token,
    )
    run_id = certification["run_id"]
    evidence_url = certification["evidence_room_url"]
    append_output("run-id", run_id)
    append_output("evidence-room-url", evidence_url)
    print(f"Certification queued: {run_id}")

    deadline = time.monotonic() + args.timeout
    last_status = ""
    while time.monotonic() < deadline:
        run = request_json(f"{api}/api/runs/{run_id}")
        current = str(run.get("status", "UNKNOWN"))
        if current != last_status:
            print(f"RegressionForge status: {current}")
            last_status = current
        if current in TERMINAL_STATUSES and run.get("gate"):
            gate = run["gate"]["status"]
            append_output("gate", gate)
            write_summary(run, evidence_url)
            return 0 if gate == "PASS" else 1
        time.sleep(2)
    raise RuntimeError(f"Certification {run_id} did not finish within {args.timeout} seconds")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
