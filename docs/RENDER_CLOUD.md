# Render cloud deployment

This is the cloud judging path. After one-time setup, the Mac only opens one of
three ForgeCart pull requests. GitHub Actions deploys that exact PR SHA to the
Render candidate services, waits for both deploys, and asks the hosted
RegressionForge service for an evidence-backed gate.

## Cloud topology

Deploy both Blueprints into the **same Render workspace and Oregon region** so
their private DNS names resolve.

```text
demo-ecom-store Blueprint
├── forgecart-storefront         Render web service
├── forgecart-api                Render web service + SQLite disk
├── forgecart-mailpit            self-hosted Mailpit + disk
└── self-hosted SigNoz
    ├── signoz-signoz-0          UI and query API
    ├── signoz-ingester-0        OTLP receiver
    ├── ClickHouse + Keeper      telemetry storage
    ├── schema migrator
    └── Render Postgres          metadata

regression-forge Blueprint
├── regressionforge-evidence-room
├── regressionforge-api         Playwright + GlassKit + Codex SDK
├── self-hosted Claude-Mem
│   ├── API server
│   ├── generation worker
│   ├── Valkey + disk
│   └── Render Postgres
└── persistent run/artifact disk

Greptile is the hosted GitHub App/API installed only on demo-ecom-store.
It is queried by RegressionForge and is not represented by a fake container.
```

The checked-in SigNoz files preserve the official SigNoz Foundry Render
service layout. The complete observability stack uses `standard` instances,
including 20 GB for ClickHouse and 5 GB for Keeper. Claude-Mem and the browser
runner also use `standard` instances. Review Render's cost estimate before
applying the Blueprints; scale down or delete the resources after judging if
you do not need a continuously running demo.

## 1. Deploy RegressionForge

In Render, create a Blueprint from
`https://github.com/KaushikSiva/regression-forge` and its root
`render.yaml`. Keep all services in the same workspace and Oregon region.

Enter these initial values when Render prompts for `sync: false` variables:

| Variable | Initial value |
|---|---|
| `PUBLIC_API_URL` | Public URL Render assigns to `regressionforge-api` |
| `EVIDENCE_ROOM_URL` | Public URL assigned to `regressionforge-evidence-room` |
| `REGRESSIONFORGE_CI_TOKEN` | One random value, for example `openssl rand -hex 32` |
| `OPENAI_API_KEY` | Server-side OpenAI API key used by the Codex SDK |
| `GREPTILE_API_KEY` | Greptile organization API key |
| `CLAUDE_MEM_API_KEY` | `pending-bootstrap`; replace in step 2 |
| `CLAUDE_MEM_PROJECT_ID` | `pending-bootstrap`; replace in step 2 |
| `SIGNOZ_API_KEY` | `pending-bootstrap`; replace in step 4 |
| `SIGNOZ_EMAIL` / `SIGNOZ_PASSWORD` | Temporary non-empty values; replace in step 4 |
| `ANTHROPIC_API_KEY` | Provider key for the Claude-Mem generation worker |

Do not commit any of these values. `CODEX_ENABLED`, the read-only target
checkout, GlassKit, private Claude-Mem URL, and private SigNoz/ForgeCart DNS
names are already defined by the Blueprint.

## 2. Bootstrap Claude-Mem once

Wait until `regressionforge-claude-mem` is healthy. Open that service's Render
Shell and run:

```bash
bun /opt/claude-mem/scripts/server-service.cjs server api-key create \
  --name regressionforge \
  --scope memories:read,memories:write
```

The command prints the raw key only once. Copy its `key` into
`CLAUDE_MEM_API_KEY` on `regressionforge-api`. Copy its `projectId` into a new
`CLAUDE_MEM_PROJECT_ID` environment variable on the same service, then deploy
the latest commit for `regressionforge-api`.

RegressionForge now writes certified run summaries through Claude-Mem's real
`POST /v1/memories` endpoint and recalls them through `POST /v1/search`. If the
server or key is unavailable, the UI reports that integration as unavailable;
it never inserts simulated memory.

## 3. Deploy ForgeCart, Mailpit, and SigNoz

Create a second Blueprint from
`https://github.com/KaushikSiva/demo-ecom-store` and its root `render.yaml` in
the **same workspace and Oregon region**. For `FULFILLMENT_WEBHOOK_URL`, enter:

```text
https://<your-regressionforge-api>.onrender.com/api/webhooks/fulfillment
```

Wait for every service to become healthy. `forgecart-api` and
`forgecart-storefront` deliberately have automatic deploys disabled because
GitHub Actions promotes an exact PR SHA into this shared candidate environment.

## 4. Bootstrap SigNoz once

Open the public URL for `signoz-signoz-0` and create the first organization and
user. In SigNoz organization settings, create an API key.

Update these variables on `regressionforge-api` and deploy it again:

```text
SIGNOZ_API_KEY=<SigNoz API key>
SIGNOZ_EMAIL=<SigNoz login email>
SIGNOZ_PASSWORD=<SigNoz login password>
```

The API key is used for the deterministic log query. The email and password
are used only inside a separate Playwright context to capture the real SigNoz
Logs Explorer without adding credentials to the workflow trace. Check 11
filters on `regression.run_id` and `deployment.version` and displays that real
SigNoz UI screenshot in the center evidence surface.

## 5. Configure GitHub Actions

In `KaushikSiva/demo-ecom-store`, add these Actions variables:

| Variable | Value |
|---|---|
| `RENDER_FORGECART_API_SERVICE_ID` | Render `srv-...` ID for `forgecart-api` |
| `RENDER_FORGECART_WEB_SERVICE_ID` | Render `srv-...` ID for `forgecart-storefront` |
| `REGRESSIONFORGE_API_URL` | Public RegressionForge API URL |
| `FORGECART_API_URL` | Public ForgeCart API URL |
| `FORGECART_STOREFRONT_URL` | Public ForgeCart storefront URL |

Add these Actions secrets:

| Secret | Value |
|---|---|
| `RENDER_API_KEY` | Render API key allowed to deploy the two candidate services |
| `REGRESSIONFORGE_CI_TOKEN` | Exact value configured on RegressionForge |

The workflow runs on GitHub-hosted `ubuntu-latest`; no self-hosted Mac runner,
Docker Desktop, local checkout path, or local credential helper is involved.
It uses Render's Trigger Deploy API with `commitId`, checks the resulting deploy
object, and then verifies `/health` reports the same full
`RENDER_GIT_COMMIT`.

## 6. Install Greptile only on ForgeCart

Install the Greptile GitHub App for only
`KaushikSiva/demo-ecom-store`, wait for indexing, and enable its status check.
The repository already includes `greptile.json`. The Greptile API key belongs
only on the RegressionForge Render service; it does not go into GitHub Actions.

## 7. Run the three-PR demo from the Mac

Use a clean `main` checkout of `demo-ecom-store`:

```bash
./scripts/create-good-pr.sh
./scripts/create-broken-pr.sh
./scripts/create-fixed-pr.sh
```

Run them in that order and leave the broken PR unmerged:

1. `good` creates a harmless compatible-contract PR and should produce `PASS`.
   Claude-Mem stores this passing baseline.
2. `broken` changes the active backend contract to `amount_cents`; it should
   produce `FAIL` with HTTP 500, missing side effects, and a correlated SigNoz
   error. Claude-Mem recalls the passing baseline.
3. `fixed` opens a separate PR from `main` accepting both names and should
   return to `PASS` with the same approved workflow version.

Each script also supports `--dry-run`. The GitHub job summary links directly to
the hosted evidence room. The shared candidate environment is serialized with
GitHub Actions concurrency so two PR SHAs cannot race each other.

## Rollback and cleanup

If a cloud certification is stuck, cancel the GitHub Actions run first. In the
Render dashboard, open **Deploys** for both `forgecart-api` and
`forgecart-storefront` and roll each service back to the previous live deploy.
The previous deploy remains recoverable; do not delete its disk.

To undo a generated PR without merging it:

```bash
gh pr close <PR-URL> --delete-branch
```

The creation scripts use temporary Git worktrees and clean them automatically,
so they do not alter the Mac's current branch. Do not merge the intentionally
broken PR.

To stop recurring cost after the demo, suspend or delete the two Blueprints in
Render. Deleting the RegressionForge disk, ClickHouse disk, Mailpit disk,
Claude-Mem Postgres, or SigNoz Postgres is destructive; download any evidence
you want first. Removing Greptile access is independent and is done from the
GitHub App installation settings.
