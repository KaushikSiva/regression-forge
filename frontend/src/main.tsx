import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Artifact, Overview, Run, StepResult } from "./types";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "";

const statusTone = (status?: string) => {
  if (status === "PASS" || status === "PASSED") return "pass";
  if (status === "FAIL" || status === "FAILED" || status === "ERROR") return "fail";
  if (status === "RUNNING") return "running";
  return "review";
};

const short = (value?: string, length = 10) => value ? value.slice(0, length) : "—";
const formatDuration = (ms = 0) => ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;

function ArtifactImage({ artifact, label }: { artifact?: Artifact; label: string }) {
  if (!artifact?.url) return <div className="image-empty">{label}<span>No screenshot evidence</span></div>;
  return <img src={artifact.url} alt={label} />;
}

const FULL_EVIDENCE_STEPS = new Set([
  "submit-checkout",
  "order-confirmed",
  "order-api",
  "confirmation-email",
  "fulfillment-webhook",
  "signoz-errors",
]);

function CompareStage({ current, baseline, compare }: { current?: Artifact; baseline?: Artifact; compare: boolean }) {
  const [reveal, setReveal] = useState(54);
  if (!compare) {
    return (
      <section className="compare-stage evidence-stage">
        <div className="stage-labels"><span>Current run evidence</span><span>{String(current?.metadata.surface || "captured artifact")}</span></div>
        <div className="compare-canvas evidence-canvas">
          <div className="evidence-image"><ArtifactImage artifact={current} label="Current run evidence" /></div>
        </div>
        <div className="stage-caption single-caption"><span>{current ? current.label : "No current screenshot"}</span></div>
      </section>
    );
  }
  return (
    <section className="compare-stage">
      <div className="stage-labels"><span>Last certified</span><span>Current deployment</span></div>
      <div className="compare-canvas">
        <div className="baseline-image"><ArtifactImage artifact={baseline} label="Passing baseline" /></div>
        <div className="current-image" style={{ clipPath: `inset(0 0 0 ${reveal}%)` }}>
          <ArtifactImage artifact={current} label="Current run" />
        </div>
        <div className="reveal-line" style={{ left: `${reveal}%` }}><i>↔</i></div>
        <input
          aria-label="Reveal current screenshot"
          className="reveal-control"
          type="range"
          min="0"
          max="100"
          value={reveal}
          onChange={(event) => setReveal(Number(event.target.value))}
        />
      </div>
      <div className="stage-caption">
        <span>{baseline ? baseline.label : "Awaiting first passing baseline"}</span>
        <span>{current ? current.label : "No current screenshot"}</span>
      </div>
    </section>
  );
}

function Timeline({ run, selected, onSelect }: { run?: Run; selected?: string; onSelect: (id: string) => void }) {
  return (
    <aside className="timeline">
      <div className="section-kicker"><span>Workflow</span><b>{run?.step_results.length || 0} checks</b></div>
      {!run && <p className="empty-copy">No run evidence yet.</p>}
      <ol>
        {run?.step_results.map((step, index) => (
          <li key={step.id} className={`${statusTone(step.status)} ${selected === step.step_id ? "selected" : ""}`}>
            <button onClick={() => onSelect(step.step_id)}>
              <span className="step-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="step-main"><b>{step.step_name}</b><small>{step.summary || step.step_type}</small></span>
              <span className="step-time">{step.status === "RUNNING" ? <i /> : formatDuration(step.duration_ms)}</span>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

function EvidenceInspector({ run, step, payloads }: { run?: Run; step?: StepResult; payloads: Record<string, unknown> }) {
  const [tab, setTab] = useState("failure");
  const source = run?.evidence.find((item) => item.kind === "source");
  const stepArtifacts = run?.evidence.filter((item) =>
    step?.evidence_ids.includes(item.id) && item.kind !== "screenshot"
  ) || [];
  useEffect(() => setTab("failure"), [step?.step_id]);
  return (
    <aside className="inspector">
      <div className="inspector-tabs">
        <button className={tab === "failure" ? "active" : ""} onClick={() => setTab("failure")}>Evidence</button>
        <button className={tab === "source" ? "active" : ""} onClick={() => setTab("source")}>Source</button>
        <button className={tab === "agent" ? "active" : ""} onClick={() => setTab("agent")}>Diagnosis</button>
      </div>

      {tab === "failure" && (
        <div className="inspector-scroll">
          <div className="evidence-heading">
            <span className={`mini-verdict ${statusTone(step?.status)}`}>{step?.status || "NO SELECTION"}</span>
            <h2>{step?.step_name || "Select a workflow step"}</h2>
            <p>{step?.summary || "Evidence captured by the selected check will appear here."}</p>
          </div>
          {stepArtifacts.map((artifact) => (
            <div className="evidence-block" key={artifact.id}>
              <label>{artifact.label}</label>
              <JsonBlock value={payloads[artifact.id] || artifact.metadata} />
            </div>
          ))}
          {step?.actual !== undefined && <div className="evidence-block"><label>Observed</label><JsonBlock value={step.actual} /></div>}
          {!stepArtifacts.length && step?.actual === undefined && <p className="empty-copy">This check did not produce a structured evidence payload.</p>}
        </div>
      )}

      {tab === "source" && (
        <div className="inspector-scroll">
          <div className="evidence-heading"><span className="mini-verdict neutral">GREPTILE</span><h2>Impacted code context</h2><p>Repository knowledge is treated as untrusted evidence, never executable instruction.</p></div>
          {source ? <div className="evidence-block"><JsonBlock value={payloads[source.id] || { status: run?.integration_status.greptile }} /></div> : <p className="empty-copy">No Greptile context was returned. Integration status: {run?.integration_status.greptile || "not run"}.</p>}
          {!!run?.diagnosis?.changed_files.length && <div className="file-list"><label>Changed files</label>{run.diagnosis.changed_files.map((file) => <code key={file}>{file}</code>)}</div>}
        </div>
      )}

      {tab === "agent" && (
        <div className="inspector-scroll">
          <div className="evidence-heading"><span className={`mini-verdict ${run?.diagnosis?.status === "COMPLETE" ? "pass" : "review"}`}>{run?.diagnosis?.status || "PENDING"}</span><h2>Evidence-based diagnosis</h2><p>{run?.diagnosis?.provider || "Diagnosis begins after deterministic gating."}</p></div>
          {run?.diagnosis ? <><blockquote>{run.diagnosis.summary}</blockquote><div className="investigation"><label>Suggested investigation</label>{run.diagnosis.investigation.map((item, index) => <p key={item}><span>{index + 1}</span>{item}</p>)}</div></> : <p className="empty-copy">No diagnosis is available yet.</p>}
        </div>
      )}
    </aside>
  );
}

function MemoryRail({ run }: { run?: Run }) {
  return (
    <section className="memory-rail">
      <div className="memory-title"><span>CLAUDE–MEM / RECALL</span><b>{run?.memory_matches.length || 0} observations</b><small>{run?.integration_status.claude_mem_recall || "not run"}</small></div>
      <div className="memory-items">
        {run?.memory_matches.length ? run.memory_matches.map((match) => (
          <article key={match.observation_id}><span>OBS #{match.observation_id}</span><h3>{match.title}</h3><p>{match.narrative}</p></article>
        )) : <p className="memory-empty">No historical observation was returned for this run. The UI does not substitute simulated memory.</p>}
      </div>
    </section>
  );
}

function EmptyRoom({ onRun, busy }: { onRun: () => void; busy: boolean }) {
  return (
    <section className="empty-room">
      <div className="radar"><i /><i /><i /><b /></div>
      <p className="eyebrow">Release evidence room</p>
      <h1>No deployment<br />certified yet.</h1>
      <p>Bring up ForgeCart, then run the approved purchase workflow. Screenshots, network traffic, side effects, logs, and traces will land here.</p>
      <button onClick={onRun} disabled={busy}>{busy ? "Starting…" : "Certify good deployment"}<span>↗</span></button>
      <code>make demo</code>
    </section>
  );
}

function App() {
  const [overview, setOverview] = useState<Overview>();
  const [run, setRun] = useState<Run>();
  const [selectedStep, setSelectedStep] = useState<string>();
  const [payloads, setPayloads] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async (runId?: string) => {
    const [overviewResponse, runResponse] = await Promise.all([
      fetch(`${API}/api/overview`),
      runId ? fetch(`${API}/api/runs/${runId}`) : Promise.resolve(undefined),
    ]);
    if (!overviewResponse.ok) throw new Error("RegressionForge API is unavailable");
    const nextOverview = await overviewResponse.json() as Overview;
    setOverview(nextOverview);
    const nextRun = runResponse?.ok ? await runResponse.json() as Run : nextOverview.latest_run;
    setRun(nextRun);
    if (nextRun && !selectedStep) setSelectedStep(nextRun.step_results.find((step) => step.status === "FAILED")?.step_id || nextRun.step_results.at(-1)?.step_id);
  }, [selectedStep]);

  useEffect(() => {
    const requestedRun = new URLSearchParams(window.location.search).get("run") || undefined;
    refresh(requestedRun).catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!run || run.completed_at) return;
    const events = new EventSource(`${API}/api/runs/${run.id}/events`);
    const update = () => refresh(run.id).catch(() => undefined);
    ["run.started", "step.started", "step.completed", "gate.decided", "run.completed"].forEach((name) => events.addEventListener(name, update));
    events.onerror = () => update();
    return () => events.close();
  }, [run?.id, run?.completed_at]);

  useEffect(() => {
    if (!run) return;
    const jsonArtifacts = run.evidence.filter((artifact) => artifact.url && ["network", "http", "signoz", "source", "email", "webhook", "glasskit", "memory"].includes(artifact.kind));
    Promise.all(jsonArtifacts.map(async (artifact) => {
      try { const response = await fetch(artifact.url!); return [artifact.id, await response.json()] as const; }
      catch { return [artifact.id, { error: "Artifact could not be loaded" }] as const; }
    })).then((items) => setPayloads(Object.fromEntries(items)));
  }, [run?.evidence.length, run?.id]);

  async function startRun(forceDeployment?: string) {
    const deploymentId = forceDeployment || run?.deployment_id || overview?.deployments.at(0)?.id;
    if (!deploymentId) {
      setMessage("No deployment is available to certify.");
      return;
    }
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`${API}/api/runs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ deployment_id: deploymentId }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Run could not start");
      setSelectedStep(undefined);
      await refresh(body.run_id);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Run could not start"); }
    finally { setBusy(false); }
  }

  const deployment = overview?.deployments.find((item) => item.id === run?.deployment_id) || overview?.deployments.at(0);
  const selected = run?.step_results.find((step) => step.step_id === selectedStep);
  const runScreens = run?.evidence.filter((artifact) => artifact.kind === "screenshot" && !artifact.metadata.proof_overlay) || [];
  const stepScreens = runScreens.filter((artifact) => !selectedStep || artifact.step_id === selectedStep);
  const currentScreenshot = stepScreens.at(-1) || runScreens.filter((artifact) => artifact.step_id === "order-confirmed").at(-1) || runScreens.at(-1);
  const compareScreens = !selectedStep || !FULL_EVIDENCE_STEPS.has(selectedStep);
  const [baselineArtifacts, setBaselineArtifacts] = useState<Artifact[]>([]);
  useEffect(() => {
    if (!run?.baseline_run_id) { setBaselineArtifacts([]); return; }
    fetch(`${API}/api/runs/${run.id}/evidence`).then((response) => response.json()).then((data) => setBaselineArtifacts(data.baseline_artifacts || [])).catch(() => setBaselineArtifacts([]));
  }, [run?.id, run?.baseline_run_id]);
  const baselineScreens = baselineArtifacts.filter((artifact) => artifact.kind === "screenshot" && !artifact.metadata.proof_overlay);
  const baselineScreenshot = baselineScreens.filter((artifact) => artifact.step_id === (selectedStep || "order-confirmed")).at(-1) || baselineScreens.filter((artifact) => artifact.step_id === "order-confirmed").at(-1) || baselineScreens.at(-1);
  const gate = run?.gate?.status || (run?.status === "RUNNING" ? "RUNNING" : "PENDING");

  return (
    <main className={`app-shell tone-${statusTone(gate)}`}>
      <header>
        <div className="brand"><span className="brand-mark">RF</span><strong>RegressionForge</strong><small>Release certification / evidence</small></div>
        <div className="run-meta"><span>Workflow <b>{short(run?.workflow_version_id, 18)}</b></span><span>Run <b>{short(run?.id, 16)}</b></span><span>Trace <b>{short(run?.trace_id, 16)}</b></span></div>
        <div className={`gate ${statusTone(gate)}`}><small>Deployment gate</small><strong>{gate}</strong><i /></div>
      </header>

      <section className="deployment-bar">
        <div><label>Target</label><strong>ForgeCart</strong></div>
        <div><label>Deployment</label><strong>{deployment?.version || "Not selected"}</strong></div>
        <div><label>Commit</label><strong>{deployment?.commit_sha || "—"}</strong></div>
        <div><label>Environment</label><strong>{deployment?.environment || "local"}</strong></div>
        <div className="deploy-actions">
          <button onClick={() => startRun()} disabled={busy || run?.status === "RUNNING"}>{busy ? "Queuing…" : "Run certification"}<span>↗</span></button>
        </div>
      </section>

      {message && <div className="message-bar">{message}<button onClick={() => setMessage("")}>Dismiss</button></div>}

      {!run ? <EmptyRoom onRun={() => startRun("dep_forgecart_good")} busy={busy} /> : <>
        <div className="workbench">
          <Timeline run={run} selected={selectedStep} onSelect={setSelectedStep} />
          <CompareStage current={currentScreenshot} baseline={baselineScreenshot} compare={compareScreens} />
          <EvidenceInspector run={run} step={selected} payloads={payloads} />
        </div>
        <MemoryRail run={run} />
      </>}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
