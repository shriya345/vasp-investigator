# Model v0.1.0

## Evidence and inference

A transfer record is supplied evidence, a label is a sourced assertion, and a confidence score is model output. Neither the label nor the score establishes the target wallet's owner. Demo evidence is fictional and never suitable for routing an actual request.

## Tracing

1. Sort normalized events by UTC timestamp, block number, transaction index, event index and hash. Providers must supply accurate execution ordering and successful transfers only.
2. Each outgoing target transfer starts an origin lot. Its USD valuation, if available, follows its quantity; downstream valuations cannot inflate origin exposure.
3. Maintain per-address, per-token-contract inventory. The chain-native asset uses a separate inventory key. An outgoing transfer consumes observed balances proportionally. Any quantity exceeding the observed balance is untracked.
4. Unknown opening balances are not inferred. Consequently traced exposure is a **modelled allocation conditional on supplied history**, not proof that identifiable coins followed that route. External funding before the observation window can materially reduce attributable fractions.
5. Stop on cycles, hop limits and first VASP/exchange/mixer/bridge/DEX endpoint. Later movement beyond such endpoints remains untracked. Expanding the visualization only reveals loaded evidence, not newly fetched history.
6. Aggregate origin-valued arrivals by supplied entity label. Gross target outflow is the denominator. Returned/re-spent capital can appear more than once in gross outflow. A self-transfer neither starts a seed nor changes inventory.

An edge in the graph is an observed supplied transfer, not necessarily a time-valid attributable flow. Purple candidate paths specifically identify model-supported temporal paths. Graph hop labels are topological BFS distances and may differ from temporal candidate-path lengths. The graph includes direct incoming counterparties and outgoing neighborhoods; coverage need not be complete.

## Attribution formula

Each component is normalized to [0, 1]:

| Component | Weight | Normalization |
|---|---:|---|
| Proximity | 25% | 1 / shortest supported path length |
| Interaction | 25% | candidate origin-valued arrivals / gross valued outflow |
| Independent paths | 15% | min(edge-disjoint support / 3, 1) |
| Recency | 15% | 1 / (1 + days since last arrival / 30) |
| Label quality | 10% | minimum label confidence × source reliability × minimum path source confidence |
| Cluster support | 10% | min(distinct supplied entity addresses / 3, 1) |

Recency is relative to the final transaction in the supplied dataset, not the current date. Scores are capped at label quality × 100 so strong volume cannot override unreliable identity evidence. Weights are illustrative, uncalibrated and versioned. Scores across candidates need not sum to 100.

Independent support is a deterministic greedy lower bound on edge-disjoint observed event paths, ordered by path length and event identity. It is not the optimal maximum disjoint-path count, nor does it establish independent underlying actors. Cluster support uses only supplied relationships; interactions never create ownership clusters.

## Risk model

- Mixer arrival: 25 points.
- Bridge arrival: 10 points.
- Scam-labelled arrival: 25 points.
- Sanctions-labelled arrival: 30 points.
- At least 3 chronological hops within 30 minutes on a path reaching a labelled endpoint: 20 points.
- Target outgoing transfer with supplied USD value ≥ $10,000: 10 points. This is an illustrative review threshold, not a legal threshold.

Each factor is counted at most once and links to transaction evidence. Total is capped at 100. Labelled risk exposure requires label validation, especially sanctions labels. These rules are limited pattern detectors; lack of a signal does not establish lack of risk. Structuring, dormant activation, swap tracing and exchange hopping are not implemented.

## Quantitative outputs

Incoming/outgoing/net USD use only supplied valued target transfers, excluding self-transfers. Coverage is the count fraction of outgoing transfers with valuations; unvalued assets are not converted using assumed prices. Medians/maxima use valued outgoing transfers. Velocity is target transfer count divided by the observed activity window, not a long-run baseline. HHI and Shannon entropy use VASP shares plus a single unresolved bucket; they are not market-concentration estimates. Asset amounts use Decimal; presentation statistics are rounded numbers.

## Reproducibility

Cases store raw normalized evidence, source metadata, analysis, model version and SHA-256 of compact sorted-key UTF-8 JSON evidence. Evidence array order is included in the digest. Reports cite the digest and event-level paths. A digest is a content fingerprint, not independently authenticated provenance. The demo uses a fixed period for deterministic outputs.

## Nearest and highest-confidence results

Only candidates reached by supported, chronological paths are considered. Nearest VASP is the candidate with the smallest `shortest_hops`; ties favor the higher existing score, then entity name. Highest-confidence VASP is the first candidate in the existing score ranking. This does not change the six-component formula. If there are no candidates, all outputs explicitly say: **No VASP attribution supported by available evidence.** A low-scoring candidate may still be displayed for review but cannot pass a higher simulated routing threshold.

## Label and regulatory information

The existing `Label` model retains source, optional HTTPS source URL, reliability, confidence and observation time. Observation time is not proof of external verification. The current repository has no reliable FIU-IND registration dataset; `fiu_registered` remains null, and non-null submissions are rejected until a verified source and review process exist. Regulatory status would be entity-level context, never evidence of address ownership.

## Lawful-basis and SAHYOG simulation

**SIMULATED — No connection to the live SAHYOG Portal.** Preparation requires a supported candidate whose existing score meets `SAHYOG_SIMULATION_MIN_SCORE` (default 60/100), plus a nonblank Case/FIR reference, investigating agency, explicit authorized-investigation confirmation and investigator confirmation. The threshold is a configurable simulation rule, not a legal or evidentiary standard. BNSS Section 94 must be considered in the circumstances of a case and does not automatically authorize freezing.

The local state machine permits prepared → sent → acknowledged → info_requested → complied or refused; acknowledged may also move directly to complied/refused; refused → escalated. States and references are fictional. No external request is sent. Invalid transitions are rejected.

## Audit integrity

Every new case receives creation and analysis events; live cases also receive a live evidence retrieval event. Reviewed/prepared routing, each simulated state transition and report generation append timestamped events with case ID, evidence digest, reference, previous hash and SHA-256 current hash. The append path verifies the existing chain first. Cases created before this feature have no fabricated historical events; subsequent real actions can begin a chain with a legacy warning. Verification detects changes to retained events but does not prevent replacement of an entire database trail, authenticate upstream blockchain evidence, or make material legally admissible.

## Post-baseline evidence assessment

The frozen 150-case evaluation is the **before** baseline. The assessment is a post-analysis layer stored separately from `analysis`; it neither changes candidate scoring/ranking nor rewrites baseline artifacts. Its states are deterministic review categories, not calibrated probabilities or legal standards:

- `INSUFFICIENT_EVIDENCE`: no observed outgoing transfer from the target, including empty or incoming-only evidence.
- `NO_VASP_SUPPORTED`: transactions exist but no temporal path reaches a supplied VASP label.
- `AMBIGUOUS`: multiple supported candidate entities or an unresolved entity conflict on the leading endpoint.
- `SUPPORTED_WITH_LIMITATIONS`: one candidate with a bounded live history, missing numeric label-quality metadata, another disclosed limitation, or fewer edge-disjoint paths than `ASSESSMENT_MIN_INDEPENDENT_PATHS` (default 2).
- `SUPPORTED`: one candidate meeting that path review heuristic and none of those disclosed limitations. This still does not establish ownership or complete external evidence. The 1–10 path setting is configurable, illustrative, and was not tuned to the frozen benchmark.

Coverage flags describe observed evidence rather than assign a fake completeness percentage. `OBSERVED_PATH_EVIDENCED` means only that the supplied candidate path is internally evidenced; it never means complete chain history. Live GoldRush history is always flagged `PARTIAL_PROVIDER_HISTORY` because acquisition is bounded to five pages and fetch failures are not reliably exposed by the existing provider contract. Other flags identify insufficient target-outgoing evidence, no supported VASP path, multiple candidates, missing numeric label quality or source URL, and unresolved label conflicts.

Endpoint profiles preserve the loaded label's source URL and disclose whether confidence, reliability and observation date are known. Unknown stays unknown. For live cases, the assessment reads both curated and public label assertions for candidate endpoint addresses, even when the production loader's priority chose one. A disagreement is shown as an unresolved entity conflict with both sources; the engine's legacy priority remains unchanged. Imported evidence allows one assertion per address, so absent external assertions cannot be interpreted as corroboration. A label is an assertion, not independently verified ownership.

Counterfactual component tests subtract each displayed component's points from each existing candidate's displayed score ingredients and retain the existing quality cap. These sensitivity scores use rounded displayed component values. A winning margin of 0.2 points or less is reported as indeterminate at displayed precision, rather than as a unique winner. The service-intelligence test runs the unchanged engine on a copied label list with the leading entity's endpoint labels removed; blockchain transactions remain in place. Stability is the number of applicable removals retaining the same untied leader divided by the number of applicable removals. It is a sensitivity ratio, not a probability.

Next actions use fixed priority: resolve conflicting service assertions, distinguish competing VASP paths, expand bounded live history, resolve an observed unlabeled reachable address or acquire absent transactions, then review the existing **SIMULATED** routing workflow for a supported candidate. These are investigative suggestions, not legal advice or automatic requests. The deterministic summary is assembled from the card state, stability and first action.

The related-cases view compares only locally saved, same-chain cases with a verified analysis seal. It reports shared addresses on candidate-supported paths as intermediaries or VASP endpoints, and shared directly observed outgoing counterparties separately. Incoming-only graph neighbors and older cases without a sealed analysis are excluded. It does not infer common ownership, identity or criminal association. Related links are a current local-database snapshot and are separate from the signed case evidence.

New cases store separate SHA-256 digests of structured analysis and assessment alongside the existing evidence digest. The `analysis_executed` audit event anchors a digest of both output digests; audit verification checks all three content digests and the event hash chain. Cases created before analysis sealing retain their prior assessment-only anchor, and legacy cases are not assigned historical anchors. A digest detects local changes but does not authenticate upstream sources or guarantee legal admissibility.

The live API rejects absent credentials and histories exceeding the request model's 5,000-event limit instead of creating a misleading empty case or silently truncating events. GoldRush's existing adapter can still suppress page-level errors and return partial or empty history without a success/failure status. Until that provider contract is changed and separately validated, live acquisition cannot claim complete retrieval; the assessment always marks it bounded and partial. An empty live case records an acquisition attempt, not a successful evidence retrieval.
