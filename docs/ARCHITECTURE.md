# Architecture

## Certification flow

```text
approved WorkflowVersion
        │
        ▼
Playwright browser ─── screenshots / video / trace / console / network
        │
        ├── ForgeCart public API ─── SQLite order evidence
        ├── Mailpit API ──────────── confirmation-email evidence
        ├── webhook receiver ─────── fulfillment evidence
        └── SigNoz or OTel audit ─── correlated error-log evidence
                                        │
                                        ▼
                               deterministic gate
                                   │         │
                                 verdict   redacted bundle
                                             │
                        Claude-Mem recall ───┼─── Greptile context
                                             │
                                         Codex diagnosis
```

The verdict is already final before diagnosis starts. Codex may explain why evidence points toward an investigation, but has no path to mutate step statuses or the gate.

## Persistence

SQLite stores projects, deployments, workflows, immutable workflow versions, run snapshots, SSE events, and received webhooks. Large artifacts live in a run-scoped directory and are referenced by SHA-256. Each artifact includes the owning run and, when applicable, step ID.

## Reproducibility

A workflow version hash is computed from canonical JSON for its declarative steps. Outcome wording, runtime IDs, agent output, and timestamps do not affect the hash. An incoming nonmatching hash is rejected.

## Observability

Both services emit spans with `regression.run_id` and `deployment.version`. RegressionForge records a local JSONL audit in addition to optional OTLP export so there is inspectable local evidence when running without SigNoz. Local evidence acceptance is a deliberate demo policy controlled by `ALLOW_LOCAL_OTEL_AUDIT`; disabling it demonstrates the production-safe `NEEDS_REVIEW` behavior.

