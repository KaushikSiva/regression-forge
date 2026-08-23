# RegressionForge

> Evidence, not hope, after every deploy.

RegressionForge runs an approved, versioned customer journey against a deployment and returns a deterministic `PASS`, `FAIL`, or `NEEDS_REVIEW` backed by artifacts from the browser, API, email, webhook receiver, telemetry, repository context, and persistent memory.

This repository is independent from the target application in `../regressionforge-demo-store`. No InflationForge or RobotForge source is modified.

## Three-minute demo

Requirements: Docker Desktop with at least 4 GB available, Python 3.12, and ports `4301`, `4310`, `4400`, `4410`, `8025`, and `1025` free.

```bash
make demo
```

Open the evidence room at <http://localhost:4410>. The first run exercises the good ForgeCart release and creates the passing screenshot baseline.

Then run the regression sequence:

```bash
make deploy-broken
make deploy-fixed
```

Each deployment command recreates the ForgeCart API container with an allowlisted release, registers a real deployment record, and queues a certification run. The broken release changes the backend checkout contract from `total_cents` to `amount_cents`; the unchanged storefront therefore receives HTTP 500. Because checkout stops before side effects, the correlated order, email, and fulfillment webhook checks also fail.

The fixed release accepts both field names and returns the same immutable workflow version to `PASS`.

```text
good deploy   → browser + order + email + webhook + logs → PASS
broken deploy → checkout 500 → missing downstream evidence → FAIL
fixed deploy  → same workflow hash, restored contract     → PASS
```

## What is real

- The UI journey is executed by Chromium through Playwright. Screenshots, WebM video, a Playwright trace, console errors, and network exchanges are saved under the same run ID.
- ForgeCart persists orders to SQLite, sends SMTP mail to Mailpit, and posts to a real HTTP webhook receiver.
- Request correlation propagates `x-regressionforge-run-id`, `x-deployment-version`, and W3C trace context.
- Gate decisions are pure policy over required step results. A diagnosis cannot change them.
- The local GlassKit Eval checkout is installed into the runner image and evaluates the browser recording three times with a zero-flake stability gate.
- SigNoz can receive OTLP traces and answer log queries. When it is absent, the local demo can use the same structured OTel audit; setting `ALLOW_LOCAL_OTEL_AUDIT=false` proves that missing observability evidence yields `NEEDS_REVIEW`.
- Greptile, Codex, and Claude-Mem return explicit integration states. No fallback labels itself as those services and no missing service produces invented observations.

## Services

| Surface | URL | Purpose |
|---|---|---|
| Evidence room | <http://localhost:4410> | Deployment verdict and live evidence |
| RegressionForge API | <http://localhost:4400/docs> | Workflows, deployments, runs, SSE, artifacts |
| ForgeCart | <http://localhost:4310> | Target storefront |
| ForgeCart API | <http://localhost:4301/docs> | Orders, checkout, correlated local telemetry |
| Mailpit | <http://localhost:8025> | Delivered confirmation emails |

## API

Core endpoints:

```text
POST /api/workflows/draft
POST /api/workflows/{version_id}/approve
GET  /api/workflows
POST /api/deployments/webhook
POST /api/runs                         # 202 Accepted
GET  /api/runs/{id}
GET  /api/runs/{id}/events            # server-sent events
GET  /api/runs/{id}/evidence
GET  /api/runs/{id}/diagnosis
POST /api/demo/deploy/{good|broken|fixed}
```

The demo deployment endpoint is disabled in Docker by default. When enabled for a trusted local host process, it invokes only `scripts/deploy.py` with one of three enumerated release values. It never accepts a command or argument vector from the request.

## Optional integrations

Copy `.env.example` to `.env` and configure only the integrations you have. The local deterministic run works without them.

### SigNoz

Current SigNoz self-hosting uses Foundry. Install `foundryctl`, then:

```bash
make signoz-up
```

The checked-in `observability/casting.yaml` produces the supported Docker Compose deployment. Point the app containers at the host OTLP receiver and query service:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318
SIGNOZ_URL=http://host.docker.internal:8080
ALLOW_LOCAL_OTEL_AUDIT=false
```

If the query is unavailable, the observability step is `NEEDS_REVIEW`; it never silently passes.

### Codex

RegressionForge uses the official Python Codex SDK (`openai-codex`) and `Sandbox.read_only`. The agent receives only redacted evidence, Greptile output marked as untrusted, and a read-only target repository. Enable it after Codex authentication is available in the runner environment:

```dotenv
CODEX_ENABLED=true
CODEX_MODEL=gpt-5.6-terra
```

### Greptile

Index the ForgeCart remote in Greptile, enable its repository knowledge base, and set:

```dotenv
GREPTILE_API_KEY=...
GREPTILE_REPOSITORY=owner/regressionforge-demo-store
```

The client talks to `https://api.greptile.com/mcp` with Streamable HTTP and uses `list_knowledge_bases` followed by `search_knowledge_base`. Greptile text is treated as untrusted evidence.

### Claude-Mem

Install the current Codex-compatible worker interactively:

```bash
npx claude-mem install
```

Expose its worker URL to the container and set `CLAUDE_MEM_URL`. RegressionForge writes observations through the worker's session endpoints and recalls real observations through `/api/observations`; the UI shows observation IDs. A stopped or unconfigured worker remains visibly unavailable.

## Development and tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt pytest
cd frontend && npm install && npm run build
cd ../backend && playwright install chromium
cd .. && make test
```

Targeted unit tests cover workflow hashing, tamper detection, gate precedence, missing-observability behavior, secret redaction, and all three ForgeCart contracts.

## Architecture and trust boundaries

- Workflow drafts contain only the nine allowlisted step types. Human approval is mandatory and the step content is hashed.
- Arbitrary generated Python or JavaScript is never executed.
- Browser/API results and side effects are correlated by the run ID; deployment and trace identifiers are stored alongside them.
- Evidence is redacted before persistence and API exposure. Authorization, cookies, tokens, API keys, and common secret forms are removed.
- External failures degrade diagnosis, not deterministic execution. `FAIL` takes precedence over `NEEDS_REVIEW`; otherwise any unavailable required evidence prohibits `PASS`.
- Render blueprints demonstrate remote-target support. Local Docker remains the judging path because it owns SMTP, webhook, telemetry, and release switching deterministically.

See [docs/DEMO.md](docs/DEMO.md) for the presentation script and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the evidence flow.

