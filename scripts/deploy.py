from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


RELEASES = {
    "good": {"version": "forgecart-good", "fallback_sha": "2f31a0d"},
    "broken": {"version": "forgecart-broken", "fallback_sha": "8cb0d91"},
    "fixed": {"version": "forgecart-fixed", "fallback_sha": "d4a821e"},
}
ROOT = Path(__file__).resolve().parent.parent
STORE_REPO = ROOT.parent / "regressionforge-demo-store"
API = os.getenv("REGRESSIONFORGE_API", "http://localhost:4400")


def request_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def wait_ready(url: str, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            if request_json(url).get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


def commit_for(release: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(STORE_REPO), "rev-parse", f"release-{release}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()[:12] if completed.returncode == 0 else RELEASES[release]["fallback_sha"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy one allowlisted ForgeCart release")
    parser.add_argument("release", choices=sorted(RELEASES))
    parser.add_argument("--compose", action="store_true", help="recreate the target Docker container")
    parser.add_argument("--run", action="store_true", help="start certification after deployment")
    args = parser.parse_args()
    release = RELEASES[args.release]
    if args.compose:
        environment = os.environ.copy()
        environment["FORGECART_RELEASE"] = args.release
        environment["FORGECART_DEPLOYMENT_VERSION"] = release["version"]
        completed = subprocess.run(
            [
                "docker",
                "compose",
                "up",
                "-d",
                "--build",
                "--force-recreate",
                "--no-deps",
                "forgecart-api",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
        )
        if completed.returncode:
            return completed.returncode
    wait_ready("http://localhost:4301/health")
    wait_ready(f"{API}/health")
    deployment = request_json(
        f"{API}/api/deployments/webhook",
        "POST",
        {
            "project_id": "prj_forgecart",
            "environment": "local",
            "version": release["version"],
            "commit_sha": commit_for(args.release),
            "storefront_url": "http://forgecart-web",
            "api_url": "http://forgecart-api:8000",
        },
    )
    state = {"release": args.release, "deployment": deployment}
    (ROOT / ".demo-release").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Deployed {release['version']} at {deployment['commit_sha']}")
    if args.run:
        run = request_json(f"{API}/api/runs", "POST", {"deployment_id": deployment["id"]})
        print(f"Certification queued: {run['run_id']}")
        print("Evidence room: http://localhost:4410")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
