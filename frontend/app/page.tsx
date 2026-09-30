"use client";
import { useEffect, useState, useRef } from "react";
import dynamic from "next/dynamic";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  ChevronRight,
  Download,
  FileText,
  FolderOpen,
  GitBranch,
  Layers,
  Search,
  ShieldCheck,
  Upload,
  X,
  CircleHelp,
  Check,
  Fingerprint,
  LoaderCircle,
} from "lucide-react";
import {
  type Case,
  type CaseSummary,
  type Candidate,
  type GraphNode,
  type Transaction,
  type Routing,
  type Audit,
  short,
  money,
  time,
} from "@/lib/types";
const FlowGraph = dynamic(() => import("@/components/FlowGraph"), {
  ssr: false,
  loading: () => <div className="loading">Loading graph…</div>,
});
const DEMO = "0x71a000000000000000000000000000000000092f";
const tabs = [
  "Overview",
  "Transaction graph",
  "VASP attribution",
  "Risk & typology",
  "Transactions",
  "Report",
];
const allowedStates: Record<string, string[]> = {
  prepared: ["sent"],
  sent: ["acknowledged"],
  acknowledged: ["info_requested", "complied", "refused"],
  info_requested: ["complied", "refused"],
  refused: ["escalated"],
};
async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({
      detail:
        "The analysis service is unavailable. Start the backend and try again.",
    }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  }
  return res.json();
}
export default function Dashboard() {
  const [current, setCurrent] = useState<Case | null>(null),
    [cases, setCases] = useState<CaseSummary[]>([]);
  const [wallet, setWallet] = useState(DEMO),
    [chain, setChain] = useState("ethereum"),
    [tab, setTab] = useState("Overview");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<Candidate | null>(null);
  const [detail, setDetail] = useState<GraphNode | Transaction | null>(null),
    [report, setReport] = useState("");
  const [query, setQuery] = useState(""),
    [showCases, setShowCases] = useState(false);
  const [routing, setRouting] = useState<Routing | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [caseReference, setCaseReference] = useState("");
  const [agency, setAgency] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [routingBusy, setRoutingBusy] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const a = current?.analysis;
  const nearest =
    a?.nearest_vasp ??
    (a?.candidates.length
      ? [...a.candidates].sort(
          (left, right) =>
            left.shortest_hops - right.shortest_hops ||
            right.score - left.score ||
            left.entity.localeCompare(right.entity),
        )[0]
      : null);
  const highest = a?.highest_confidence_vasp ?? a?.candidates[0] ?? null;
  useEffect(() => {
    api<CaseSummary[]>("/api/cases")
      .then(setCases)
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!current) return;
    const controller = new AbortController();
    setReport("");
    fetch(`/api/cases/${current.id}/report`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error("Report unavailable");
        return r.text();
      })
      .then(setReport)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [current]);
  useEffect(() => {
    if (!current) return;
    api<{ routing: Routing | null }>(`/api/cases/${current.id}/routing`)
      .then((data) => setRouting(data.routing))
      .catch((e) => setError((e as Error).message));
    api<Audit>(`/api/cases/${current.id}/audit`)
      .then(setAudit)
      .catch((e) => setError((e as Error).message));
    api<{ minimum_score: number }>("/api/simulation-policy")
      .then((data) => setThreshold(data.minimum_score))
      .catch((e) => setError((e as Error).message));
  }, [current]);
  function activate(c: Case) {
    setCurrent(c);
    setSelected(c.analysis.candidates[0] || null);
    setDetail(null);
    setTab("Overview");
    setWallet(c.analysis.target);
    setChain(c.analysis.chain);
    setRouting(null);
    setAudit(null);
    setCaseReference("");
    setAgency("");
    setAuthorized(false);
    setConfirmed(false);
  }
  async function refreshAudit(caseId: string) {
    setAudit(await api<Audit>(`/api/cases/${caseId}/audit`));
  }
  async function refreshReport(caseId: string) {
    const response = await fetch(`/api/cases/${caseId}/report`);
    if (!response.ok) throw new Error("Report unavailable");
    setReport(await response.text());
    await refreshAudit(caseId);
  }
  async function prepareSimulation() {
    if (!current || !selected) return;
    setRoutingBusy(true);
    setError("");
    try {
      const result = await api<Routing>(`/api/cases/${current.id}/routing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_entity: selected.entity,
          case_reference: caseReference,
          investigating_agency: agency,
          authorized_investigation: authorized,
          investigator_confirmed: confirmed,
        }),
      });
      setRouting(result);
      await refreshReport(current.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRoutingBusy(false);
    }
  }
  async function changeSimulationState(state: string) {
    if (!current) return;
    setRoutingBusy(true);
    setError("");
    try {
      const result = await api<Routing>(
        `/api/cases/${current.id}/routing/state`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state }),
        },
      );
      setRouting(result);
      await refreshReport(current.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRoutingBusy(false);
    }
  }
  async function investigate(payload?: unknown) {
    setBusy(true);
    setError("");
    try {
      const c = await api<Case>("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          payload || {
            target: wallet,
            chain,
            mode: "demo",
            max_hops: 4,
            title: "Service endpoint investigation",
          },
        ),
      });
      activate(c);
      setCases(await api<CaseSummary[]>("/api/cases"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadCase(id: string) {
    setBusy(true);
    setError("");
    try {
      activate(await api<Case>(`/api/cases/${id}`));
      setShowCases(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function investigateLive() {
    setBusy(true);
    setError("");
    try {
      const c = await api<Case>("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: wallet,
          chain,
          max_hops: 4,
          title: `Live investigation — ${wallet.slice(0, 10)}`,
        }),
      });
      activate(c);
      setCases(await api<CaseSummary[]>("/api/cases"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importFile(file?: File) {
    if (!file) return;
    try {
      if (file.size > 10_000_000)
        throw new Error("Import must be smaller than 10 MB.");
      const data = JSON.parse(await file.text());
      await investigate({ ...data, mode: "import" });
    } catch (e) {
      setError((e as Error).message);
    }
    if (importRef.current) importRef.current.value = "";
  }
  const graph = a && (
    <section className="card graph-card">
      <div className="card-heading">
        <div>
          <h2>Follow the funds</h2>
          <p>
            Time-ordered transfers · {a.graph.nodes.length} addresses ·{" "}
            {a.graph.edges.length} events
          </p>
        </div>
        <span className="badge purple">
          {selected ? `Paths to ${selected.entity}` : "All observed paths"}
        </span>
      </div>
      <FlowGraph
        key={current!.id}
        analysis={a}
        candidate={selected}
        onSelect={setDetail}
      />
    </section>
  );
  const candidatePanel = a && (
    <section className="card candidates">
      <div className="card-heading">
        <div>
          <h2>VASP candidates</h2>
          <p>Ranked by supporting evidence</p>
        </div>
        <Fingerprint size={20} />
      </div>
      <div className="table-label">
        <span>SERVICE ENDPOINT</span>
        <span>CONFIDENCE / 100</span>
      </div>
      {a.candidates.length ? (
        a.candidates.map((c, i) => (
          <button
            key={c.entity}
            className={`candidate ${selected?.entity === c.entity ? "selected" : ""}`}
            onClick={() =>
              setSelected(selected?.entity === c.entity ? null : c)
            }
          >
            <span className="rank">0{i + 1}</span>
            <div className="candidate-name">
              <strong>{c.entity}</strong>
              <span className="candidate-flags">
                {nearest?.entity === c.entity && <em>Nearest VASP</em>}
                {highest?.entity === c.entity && <em>Highest confidence</em>}
              </span>
              <span>
                {c.shortest_hops} hop{c.shortest_hops === 1 ? "" : "s"} ·{" "}
                {money(c.traced_usd)} · {c.value_share}% of valued outflow
              </span>
              <div className="bar">
                <i style={{ width: `${c.score}%` }} />
              </div>
            </div>
            <strong className="candidate-score">
              {c.score}
              <ChevronRight size={14} />
            </strong>
          </button>
        ))
      ) : (
        <p className="empty">
          No VASP attribution supported by available evidence.
        </p>
      )}
      <p className="panel-note">
        <CircleHelp size={14} />
        Evidence scores, not probabilities of ownership.
      </p>
    </section>
  );
  const evidencePanel = selected && (
    <section className="card evidence">
      <div className="card-heading">
        <div>
          <span className="eyebrow">EXPLAINABLE ATTRIBUTION</span>
          <h2>Why {selected.entity}?</h2>
        </div>
        <span className="score-circle">{selected.score}</span>
      </div>
      <div className="evidence-grid">
        {[
          [selected.independent_paths, "Edge-disjoint paths"],
          [`${selected.shortest_hops} hops`, "Nearest supported path"],
          [`${selected.median_hops} hops`, "Median distance"],
          [`${selected.value_share}%`, "Valued outflow"],
          [selected.addresses.length, "Labelled addresses"],
        ].map(([value, label]) => (
          <div key={label}>
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <div className="components">
        {Object.entries(selected.components).map(([k, v]) => (
          <div key={k}>
            <span>{k.replaceAll("_", " ")}</span>
            <div className="bar">
              <i style={{ width: `${v.value}%` }} />
            </div>
            <strong>
              {v.points.toFixed(1)}
              <small> / {v.weight * 100}</small>
            </strong>
          </div>
        ))}
      </div>
      <div className="evidence-footer">
        <ShieldCheck size={16} />
        Score capped at {selected.quality_cap} by evidence quality.
      </div>
      <div className="label-source">
        <strong>Supporting transaction paths</strong>
        <p>
          {selected.interaction_count} endpoint transfer
          {selected.interaction_count === 1 ? "" : "s"}; last seen{" "}
          {time(selected.last_seen)}.
        </p>
        {selected.paths.map((path, index) => (
          <p key={index} className="path-hashes">
            Path {index + 1}:{" "}
            {path.map((id) => short(id.split(":")[1])).join(" → ")}{" "}
            <span title={path.join(" → ")}>({path.length} hops)</span>
          </p>
        ))}
      </div>
      {tab === "VASP attribution" &&
        selected.labels.map((l) => (
          <div className="label-source" key={l.address}>
            <strong>
              {short(l.address)} · {l.entity_type} · {l.chain} · {l.strength}{" "}
              label
            </strong>
            <p>{l.source}</p>
            {l.source_url && (
              <a href={l.source_url} target="_blank" rel="noopener noreferrer">
                Label source ↗
              </a>
            )}
            <span>
              Address {l.address} · Observed {time(l.observed_at)} · Label
              confidence {l.confidence * 100}% · Reliability{" "}
              {l.source_reliability * 100}% · FIU-IND{" "}
              {l.fiu_registered == null
                ? "unknown — manual verification required"
                : l.fiu_registered
                  ? "registered"
                  : "unregistered"}
            </span>
          </div>
        ))}
    </section>
  );
  const routingPanel = a && (
    <section className="card simulation-panel">
      <div className="card-heading">
        <div>
          <h2>SAHYOG-ready routing simulation</h2>
          <p>SIMULATED — No connection to the live SAHYOG Portal</p>
        </div>
      </div>
      <div className="simulation-body">
        <p>
          Configurable simulation threshold:{" "}
          {threshold == null ? "Loading" : `${threshold}/100`}. This is not a
          legal or evidentiary standard.
        </p>
        {routing ? (
          <>
            <div className="simulation-result">
              <strong>{routing.reference}</strong>
              <span>
                State: {routing.state.replaceAll("_", " ")} · Candidate:{" "}
                {routing.candidate_entity} · {routing.candidate_score}/100
              </span>
            </div>
            <p>{routing.legal_note}</p>
            <div className="simulation-actions">
              {(allowedStates[routing.state] || []).map((state) => (
                <button
                  className="button secondary"
                  disabled={routingBusy}
                  key={state}
                  onClick={() => void changeSimulationState(state)}
                >
                  Mark {state.replaceAll("_", " ")} (simulated)
                </button>
              ))}
            </div>
          </>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void prepareSimulation();
            }}
          >
            <p>
              Selected candidate:{" "}
              {selected
                ? `${selected.entity} · ${selected.shortest_hops} hops · ${selected.score}/100`
                : "No supported candidate selected"}
            </p>
            <label>
              Case/FIR reference
              <input
                aria-label="Case/FIR reference"
                required
                maxLength={150}
                value={caseReference}
                onChange={(event) => setCaseReference(event.target.value)}
              />
            </label>
            <label>
              Investigating agency
              <input
                aria-label="Investigating agency"
                required
                maxLength={150}
                value={agency}
                onChange={(event) => setAgency(event.target.value)}
              />
            </label>
            <label className="simulation-check">
              <input
                type="checkbox"
                checked={authorized}
                onChange={(event) => setAuthorized(event.target.checked)}
              />{" "}
              I confirm this forms part of an authorized investigation.
            </label>
            <label className="simulation-check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />{" "}
              I have reviewed the attribution evidence and confirm simulated
              preparation.
            </label>
            <button
              className="button primary"
              disabled={routingBusy || !selected || threshold == null}
            >
              Prepare simulated request
            </button>
            <p>
              BNSS Section 94 requires case-specific legal assessment and does
              not automatically authorize freezing.
            </p>
          </form>
        )}
      </div>
    </section>
  );
  const integrityPanel = a && (
    <section className="card integrity-panel">
      <div className="card-heading">
        <div>
          <h2>Evidence integrity / chain of custody</h2>
          <p>Hash-linked case events for tamper-evident comparison</p>
        </div>
      </div>
      <div className="simulation-body">
        <p>
          Evidence digest: <code>{current?.evidence_digest}</code>
        </p>
        <p>
          Audit chain:{" "}
          {audit ? (audit.valid ? "Valid" : "Verification failed") : "Loading"}{" "}
          · Head hash: <code>{audit?.head_hash || "None"}</code>
        </p>
        {audit?.historical_events_unavailable && (
          <p>
            This case predates the audit trail. Earlier events were not
            backfilled.
          </p>
        )}
        <div className="audit-list">
          {audit?.events.map((event, index) => (
            <div key={`${event.audit_hash}-${index}`}>
              <strong>{event.action.replaceAll("_", " ")}</strong>
              <span>
                {time(event.timestamp)} · {short(event.audit_hash)}
              </span>
            </div>
          ))}
        </div>
        <p>
          Hash chaining does not authenticate external evidence or establish
          legal admissibility.
        </p>
      </div>
    </section>
  );
  const riskPanel = a && (
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>Risk & behavioral signals</h2>
          <p>Indicators for further review</p>
        </div>
        <span className="badge amber">{a.risk.score} / 100</span>
      </div>
      <div className="risk-list">
        {a.risk.factors.length ? (
          a.risk.factors.map((r) => (
            <button
              key={r.name}
              onClick={() => {
                const t = a.transactions.find(
                  (t) => t.id === r.evidence_ids[0],
                );
                if (t) setDetail(t);
              }}
            >
              <span className="risk-icon">
                <Activity size={17} />
              </span>
              <div>
                <strong>{r.name}</strong>
                <p>{r.explanation}</p>
              </div>
              <span>+{r.points}</span>
            </button>
          ))
        ) : (
          <p className="empty">
            No implemented risk rule was triggered. This does not establish an
            absence of risk.
          </p>
        )}
      </div>
      <p className="panel-note">
        A pattern is an investigative signal. It does not establish wrongdoing.
      </p>
    </section>
  );
  const timeline = a && (
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>Movement timeline</h2>
          <p>Chronological evidence · UTC</p>
        </div>
        <Activity size={19} />
      </div>
      <div className="timeline">
        {a.transactions.map((t) => (
          <button key={t.id} onClick={() => setDetail(t)}>
            <span className="timeline-dot" />
            <time>{time(t.timestamp)}</time>
            <div>
              <strong>
                {short(t.from_address)} <span>→</span>{" "}
                {a.graph.nodes.find((n) => n.id === t.to_address)?.label ===
                "Unlabelled wallet"
                  ? short(t.to_address)
                  : a.graph.nodes.find((n) => n.id === t.to_address)?.label ||
                    short(t.to_address)}
              </strong>
              <small>
                {t.asset} · Block {t.block_number.toLocaleString()}
              </small>
            </div>
            <b>
              {t.usd_value === null
                ? `${t.amount} ${t.asset}`
                : money(Number(t.usd_value))}
            </b>
          </button>
        ))}
      </div>
    </section>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span>
            <GitBranch size={23} />
          </span>
          tracepoint<span className="brand-period">.</span>
        </a>
        <div className="workspace-label">INVESTIGATION WORKSPACE</div>
        <button className="side-item active" onClick={() => setTab("Overview")}>
          <Layers size={18} />
          Investigations<span className="count">{cases.length}</span>
        </button>
        <button className="side-item" onClick={() => setShowCases(true)}>
          <FolderOpen size={18} />
          Case library
        </button>
        <button
          className="side-item"
          onClick={() => importRef.current?.click()}
          disabled={busy}
        >
          <Upload size={18} />
          Import evidence
        </button>
        <div className="sidebar-note">
          <ShieldCheck size={21} />
          <strong>Evidence before inference.</strong>
          <p>Transparent models. Traceable sources. Human judgment.</p>
          <span>SIH 2026 · PROTOTYPE</span>
        </div>
        <div className="analyst">
          <div>IN</div>
          <span>
            <strong>Investigator workspace</strong>
            <small>Local development</small>
          </span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} /> Investigations{" "}
            <ChevronRight size={14} />
            <strong>{current?.id || "New investigation"}</strong>
          </div>
          <span>
            <i />
            Analysis model v{a?.model_version || "0.1.0"}
          </span>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">BLOCKCHAIN INTELLIGENCE</div>
              <h1>Every trail tells a story.</h1>
              <p>
                Trace fund flows. Surface service endpoints. Understand the
                evidence.
              </p>
            </div>
            <button
              className="button secondary"
              disabled={!current || !report}
              onClick={() => {
                if (current)
                  window.location.href = `/api/cases/${current.id}/report?download=true`;
              }}
            >
              <Download size={16} />
              Export report
            </button>
          </div>
          <form
            className="search-bar"
            onSubmit={(e) => {
              e.preventDefault();
              if (wallet === DEMO) {
                void investigate();
              } else {
                void investigateLive();
              }
            }}
          >
            <Search size={20} />
            <input
              aria-label="Wallet address"
              value={wallet}
              onChange={(e) => setWallet(e.target.value)}
              placeholder="Enter an EVM wallet address"
              pattern="0x[a-fA-F0-9]{40}"
              required
            />
            <select
              aria-label="Network"
              value={chain}
              onChange={(e) => setChain(e.target.value)}
            >
              <option value="ethereum">Ethereum</option>
              <option value="bnb">BNB Chain</option>
            </select>
            <button
              className="button primary"
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                if (wallet === DEMO) {
                  void investigate();
                } else {
                  void investigateLive();
                }
              }}
            >
              {busy ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <GitBranch size={17} />
              )}{" "}
              {busy
                ? "Analyzing…"
                : wallet === DEMO
                  ? "Run demo"
                  : "Investigate live"}
            </button>
          </form>
          <div className="demo-notice">
            <span className="badge amber">SYNTHETIC DEMO</span>
            <span>
              The demo address runs a synthetic scenario. Enter any other EVM
              address to run a live investigation via GoldRush, or{" "}
              <button
                onClick={() => importRef.current?.click()}
                disabled={busy}
              >
                import normalized evidence
              </button>
              .
            </span>
          </div>
          <input
            ref={importRef}
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => void importFile(e.target.files?.[0])}
          />
          {error && (
            <div role="alert" className="error">
              <strong>Could not complete the request.</strong> {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {!a ? (
            <section className="welcome card">
              <span className="welcome-icon">
                <GitBranch size={38} />
              </span>
              <div className="eyebrow">
                FROM AN ADDRESS TO AN AUDITABLE TRAIL
              </div>
              <h2>Open your first investigation.</h2>
              <p>
                Explore a controlled fund-flow scenario with multiple service
                endpoints, transparent confidence scoring and an evidence-backed
                report.
              </p>
              <button
                className="button primary"
                disabled={busy}
                onClick={() =>
                  void investigate({
                    target: DEMO,
                    chain,
                    mode: "demo",
                    max_hops: 4,
                    title: "SIH demonstration",
                  })
                }
              >
                {busy ? "Analyzing…" : "Explore demo investigation"}{" "}
                <ArrowUpRight size={16} />
              </button>
              <div className="welcome-features">
                <span>
                  <Check size={16} />
                  Ethereum & BNB
                </span>
                <span>
                  <Check size={16} />
                  Deterministic analysis
                </span>
                <span>
                  <Check size={16} />
                  Auditable evidence
                </span>
              </div>
            </section>
          ) : (
            <>
              <div className="case-heading">
                <div>
                  <span className="badge green">
                    <Check size={12} />
                    Analyzed
                  </span>
                  <h2>{current!.id}</h2>
                  <code>{short(a.target)}</code>
                  <span className="network">
                    {a.chain === "bnb" ? "BNB Chain" : "Ethereum"}
                  </span>
                  <span className="badge">
                    {a.mode === "demo"
                      ? "SYNTHETIC DEMO"
                      : a.mode === "live"
                        ? "LIVE BLOCKCHAIN TRACE"
                        : "IMPORT"}
                  </span>
                </div>
                <small>{time(current!.created_at)}</small>
              </div>
              <div className="stats">
                <div>
                  <span>
                    Gross outgoing value <ArrowUpRight size={16} />
                  </span>
                  <strong>{money(a.metrics.outgoing_usd)}</strong>
                  <small>
                    {a.metrics.valuation_coverage ?? 0}% of outgoing transfers
                    valued
                  </small>
                </div>
                <div>
                  <span>
                    VASP endpoint exposure <ArrowDownLeft size={16} />
                  </span>
                  <strong>{money(a.metrics.attributed_usd)}</strong>
                  <small>
                    {money(a.metrics.unresolved_usd)} unresolved /
                    boundary-stopped
                  </small>
                </div>
                <div>
                  <span>
                    Leading VASP candidate <Fingerprint size={16} />
                  </span>
                  <strong className="entity-stat">
                    {a.candidates[0]?.entity || "No candidate"}
                  </strong>
                  <small>
                    {a.candidates[0]
                      ? `${a.candidates[0].score}/100 attribution confidence`
                      : "Insufficient endpoint evidence"}
                  </small>
                </div>
                <div>
                  <span>
                    Investigative risk indicator <Activity size={16} />
                  </span>
                  <strong>
                    {a.risk.score}
                    <em>/100</em>
                  </strong>
                  <small>{a.risk.factors.length} evidence-backed signals</small>
                </div>
              </div>
              <div className="attribution-summary card">
                {nearest && highest ? (
                  <>
                    <div>
                      <span>NEAREST VASP</span>
                      <strong>{nearest.entity}</strong>
                      <small>
                        {nearest.shortest_hops} hop
                        {nearest.shortest_hops === 1 ? "" : "s"} ·{" "}
                        {nearest.score}/100 confidence
                      </small>
                    </div>
                    <div>
                      <span>HIGHEST-CONFIDENCE VASP</span>
                      <strong>{highest.entity}</strong>
                      <small>
                        {highest.shortest_hops} hop
                        {highest.shortest_hops === 1 ? "" : "s"} ·{" "}
                        {highest.score}/100 confidence
                      </small>
                    </div>
                  </>
                ) : (
                  <p>No VASP attribution supported by available evidence.</p>
                )}
              </div>
              <nav className="tabs" aria-label="Investigation views">
                {tabs.map((t) => (
                  <button
                    key={t}
                    className={tab === t ? "active" : ""}
                    onClick={() => setTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </nav>
              {tab === "Overview" && (
                <>
                  <div className="overview-grid">
                    {graph}
                    <div className="right-column">
                      {candidatePanel}
                      {evidencePanel}
                    </div>
                  </div>
                  <div className="two-column">
                    {riskPanel}
                    {timeline}
                  </div>
                </>
              )}
              {tab === "Transaction graph" && graph}
              {tab === "VASP attribution" && (
                <>
                  <div className="two-column">
                    {candidatePanel}
                    {evidencePanel || (
                      <div className="card empty">
                        Select a candidate to inspect the model.
                      </div>
                    )}
                  </div>
                  {routingPanel}
                  {integrityPanel}
                </>
              )}
              {tab === "Risk & typology" && (
                <>
                  <div className="two-column">
                    {riskPanel}
                    {timeline}
                  </div>
                  <section className="card quant">
                    <div className="card-heading">
                      <h2>Fund-flow statistics</h2>
                    </div>
                    <div className="evidence-grid">
                      {[
                        [
                          "Target transactions",
                          a.metrics.target_transaction_count,
                        ],
                        ["Counterparties", a.metrics.counterparties],
                        [
                          "Median outgoing",
                          money(a.metrics.median_outgoing_usd),
                        ],
                        ["Maximum outgoing", money(a.metrics.max_outgoing_usd)],
                        [
                          "Observed transactions / hour",
                          a.metrics.transactions_per_hour ?? "N/A",
                        ],
                        ["Exposure HHI", a.metrics.exposure_hhi ?? "N/A"],
                        [
                          "Exposure entropy",
                          a.metrics.exposure_entropy ?? "N/A",
                        ],
                        ["Net valued flow", money(a.metrics.net_usd)],
                      ].map(([label, value]) => (
                        <div key={label}>
                          <strong>{value}</strong>
                          <span>{label}</span>
                        </div>
                      ))}
                    </div>
                    <p className="panel-note">
                      HHI and entropy include unresolved value as one bucket.
                      Velocity uses the observed target activity window, which
                      may be short.
                    </p>
                  </section>
                </>
              )}
              {tab === "Transactions" && (
                <section className="card transaction-card">
                  <div className="card-heading">
                    <h2>Transaction evidence</h2>
                    <input
                      aria-label="Search transactions"
                      placeholder="Filter address, hash, asset…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Transaction</th>
                          <th>From → To</th>
                          <th>Value</th>
                          <th>Asset</th>
                          <th>Time (UTC)</th>
                          <th>Direction</th>
                        </tr>
                      </thead>
                      <tbody>
                        {a.transactions
                          .filter((t) =>
                            `${t.tx_hash} ${t.from_address} ${t.to_address} ${t.asset}`
                              .toLowerCase()
                              .includes(query.toLowerCase()),
                          )
                          .map((t) => (
                            <tr key={t.id} onClick={() => setDetail(t)}>
                              <td>
                                <button onClick={() => setDetail(t)}>
                                  {short(t.tx_hash)}
                                </button>
                              </td>
                              <td>
                                {short(t.from_address)} → {short(t.to_address)}
                              </td>
                              <td>
                                {t.usd_value === null
                                  ? "Unvalued"
                                  : money(Number(t.usd_value))}
                              </td>
                              <td>
                                {t.amount} {t.asset}
                              </td>
                              <td>{time(t.timestamp)}</td>
                              <td>
                                <span className="badge">{t.direction}</span>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
              {tab === "Report" && (
                <>
                  <section className="card report">
                    <div className="card-heading">
                      <div>
                        <h2>Investigation report</h2>
                        <p>Generated from stored evidence · No LLM inference</p>
                      </div>
                      <a
                        className="button secondary"
                        href={`/api/cases/${current!.id}/evidence`}
                        download={`${current!.id}-evidence.json`}
                      >
                        <Download size={15} />
                        Evidence JSON
                      </a>
                    </div>
                    <pre>{report || "Preparing report…"}</pre>
                  </section>
                  {routingPanel}
                  {integrityPanel}
                </>
              )}
              <footer>
                <ShieldCheck size={15} />
                <span>
                  Service endpoint attribution does not establish wallet
                  ownership.{" "}
                  {a.mode === "demo"
                    ? "All transactions and labels shown are synthetic."
                    : a.mode === "live"
                      ? "Live results depend on provider coverage and labels require validation."
                      : "Imported labels require independent validation."}
                </span>
                <button onClick={() => setTab("Report")}>
                  Methodology & limitations <ChevronRight size={13} />
                </button>
              </footer>
            </>
          )}
        </div>
      </main>
      {detail && (
        <div className="drawer-backdrop" onClick={() => setDetail(null)}>
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Evidence details"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close"
              aria-label="Close evidence"
              onClick={() => setDetail(null)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">AUDITABLE EVIDENCE</span>
            <h2>
              {"tx_hash" in detail ? "Transaction detail" : "Address detail"}
            </h2>
            {"tx_hash" in detail ? (
              <>
                <p className="badge purple">{detail.direction} transfer</p>
                {Object.entries(detail).map(([key, value]) => (
                  <div className="detail-row" key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <code>
                      {value === null ? "Unavailable" : String(value)}
                    </code>
                  </div>
                ))}
              </>
            ) : (
              <>
                <div className="detail-row">
                  <span>Address</span>
                  <code>{detail.id}</code>
                </div>
                <div className="detail-row">
                  <span>Label inference</span>
                  <strong>{detail.label}</strong>
                </div>
                <div className="detail-row">
                  <span>Type / hop distance</span>
                  {detail.type} / {detail.hop < 0 ? "Incoming" : detail.hop}
                </div>
                {detail.metadata &&
                  Object.entries(detail.metadata).map(([key, value]) => (
                    <div className="detail-row" key={key}>
                      <span>{key.replaceAll("_", " ")}</span>
                      <code>{String(value)}</code>
                    </div>
                  ))}
                <p className="panel-note">
                  A service label is an assertion about this address. It does
                  not identify the owner of the investigated wallet.
                </p>
              </>
            )}
          </aside>
        </div>
      )}
      {showCases && (
        <div className="drawer-backdrop" onClick={() => setShowCases(false)}>
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Case library"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="close"
              aria-label="Close case library"
              onClick={() => setShowCases(false)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">PERSISTED INVESTIGATIONS</span>
            <h2>Case library</h2>
            {cases.length ? (
              cases.map((c) => (
                <button
                  className="case-list-item"
                  key={c.id}
                  disabled={busy}
                  onClick={() => void loadCase(c.id)}
                >
                  <FileText size={20} />
                  <div>
                    <strong>{c.id}</strong>
                    <span>{c.title}</span>
                    <small>
                      {c.chain} · {c.mode} · {time(c.created_at)}
                    </small>
                  </div>
                  <ChevronRight size={15} />
                </button>
              ))
            ) : (
              <p className="empty">No saved investigations yet.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
