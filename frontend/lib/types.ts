export type Transaction = {
  id: string;
  tx_hash: string;
  chain: string;
  block_number: number;
  timestamp: string;
  from_address: string;
  to_address: string;
  asset: string;
  amount: string;
  usd_value: string | null;
  direction: string;
  source: string;
  source_confidence: number;
  contract_address: string | null;
};
export type Label = {
  address: string;
  chain: string;
  entity: string;
  entity_type: string;
  confidence: number | null;
  strength: string;
  source: string;
  source_url?: string | null;
  source_reliability: number | null;
  observed_at: string | null;
  fiu_registered?: boolean | null;
  synthetic: boolean;
};
export type GraphNode = {
  id: string;
  label: string;
  type: string;
  hop: number;
  metadata: Label | null;
  in_degree: number;
  out_degree: number;
};
export type Candidate = {
  entity: string;
  score: number;
  traced_usd: number;
  value_share: number;
  shortest_hops: number;
  median_hops: number;
  independent_paths: number;
  path_count: number;
  interaction_count: number;
  addresses: string[];
  paths: string[][];
  last_seen: string;
  quality_cap: number;
  labels: Label[];
  components: Record<string, { value: number; weight: number; points: number }>;
};
export type Analysis = {
  target: string;
  chain: string;
  mode: string;
  max_hops: number;
  model_version: string;
  period: { start: string | null; end: string | null };
  graph: {
    nodes: GraphNode[];
    edges: Transaction[];
    connected_components: number;
  };
  transactions: Transaction[];
  candidates: Candidate[];
  nearest_vasp?: Candidate | null;
  highest_confidence_vasp?: Candidate | null;
  attribution_result?: string;
  risk: {
    score: number;
    factors: {
      name: string;
      points: number;
      evidence_ids: string[];
      explanation: string;
    }[];
  };
  metrics: Record<string, number | null>;
  limitations: string[];
};
export type Case = {
  id: string;
  title: string;
  created_at: string;
  evidence_digest: string;
  analysis: Analysis;
  assessment?: AttributionAssessment;
  assessment_digest?: string;
  analysis_digest?: string;
};
export type AttributionAssessment = {
  leading_vasp: string | null;
  nearest_vasp: string | null;
  evidence_state: string;
  evidence_coverage: string[];
  supporting_evidence: string[];
  competing_evidence: string[];
  limitations: string[];
  label_profile: { address: string; entity: string; source: string; source_url: string | null; provenance_type: string; numeric_quality_known: boolean; reliability_known: boolean; observation_date_known: boolean; conflict_status: string }[];
  intelligence_conflicts: { address: string; status: string; assertions: { entity: string; source: string; source_url: string | null }[] }[];
  counterfactuals: { removed_component: string; counterfactual_leading_vasp: string | null; counterfactual_score: number | null; attribution_changed: boolean | null; became_ambiguous: boolean; became_unsupported: boolean; rounding_indeterminate: boolean; score_basis: string }[];
  stability: { retained: number; applicable: number; ratio: string | null };
  next_actions: { priority: number; code: string; recommendation: string; reason: string }[];
  investigator_summary: string;
};
export type CaseSummary = {
  id: string;
  title: string;
  target: string;
  chain: string;
  mode: string;
  created_at: string;
};
export type Routing = {
  reference: string;
  state: string;
  case_reference: string;
  investigating_agency: string;
  candidate_entity: string;
  candidate_score: number;
  candidate_hops: number;
  simulation_threshold: number;
  notice: string;
  legal_note: string;
};
export type Audit = {
  valid: boolean;
  head_hash: string | null;
  historical_events_unavailable: boolean;
  events: {
    timestamp: string;
    action: string;
    audit_hash: string;
    previous_hash: string | null;
    evidence_digest: string;
    reference: string | null;
  }[];
};
export const short = (s: string) => `${s.slice(0, 6)}…${s.slice(-4)}`;
export const money = (n: number | null | undefined) =>
  n == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(n);
export const time = (s: string) =>
  new Date(s).toLocaleString("en-GB", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
