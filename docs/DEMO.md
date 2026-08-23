# Three-minute demo script

## 0:00–0:35 — The claim

Open the evidence room and ForgeCart. Say: “A green deploy should mean the customer journey, the API, and every promised side effect actually worked. RegressionForge produces that certificate.”

Run `make demo`. Show the timeline filling through checkout, order API, Mailpit, webhook, telemetry, and the GlassKit report. Land on the large `PASS`.

## 0:35–1:15 — Proof, not a test log

Drag the baseline/current divider. Select timeline steps to show their screenshot. Open the evidence inspector and show the same run ID in the checkout exchange, email, webhook, trace, and log artifact. Point out the workflow hash and human approval.

## 1:15–2:10 — Ship a real regression

Run:

```bash
make deploy-broken
```

The command recreates only the ForgeCart API with the incompatible contract release. Watch checkout return 500. Select the failed checkout step; show the request body containing `total_cents` and the response. Then show missing order, email, and webhook evidence plus the correlated contract error.

Open Source and Diagnosis. Explain that Greptile/Codex states are explicit, and that the diagnosis carefully distinguishes proven sequence from a hypothesized root cause. Show Claude-Mem's recalled baseline IDs if the worker is connected.

## 2:10–2:45 — Safety and determinism

Point at the `FAIL` gate: deterministic results precede and cannot be overridden by the agent. Mention declarative allowlisted steps, human approval, evidence redaction, and `NEEDS_REVIEW` when observability is missing.

## 2:45–3:00 — Close the loop

Run:

```bash
make deploy-fixed
```

The fixed backend accepts both contracts. The identical workflow hash returns to `PASS`. Close with: “RegressionForge turns every deploy into an evidence-backed release decision.”

