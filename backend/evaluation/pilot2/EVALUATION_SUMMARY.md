# Tracepoint second real-world pilot — Ethereum

**Second pilot only; the 100–150-case final benchmark has not run.** The first 15-case pilot is preserved in `pilot1/`. Dataset: Somin *ERC-20 Auxiliary Data* ([Harvard Dataverse](https://doi.org/10.7910/DVN/MBF0GC)), 10,627 rows, 370 CEX endpoints across 16 published entities, SHA-256 `579b42862499032390ea519da5aca00470643ca1c06bdd392f39c9af55e71157`. Published labels are Etherscan-derived assertions, not independently verified ownership. Seed `2612026` split these into 259 operational and 111 held-out endpoints, with all 16 entities represented in each. The app loads 243 non-curated operational public labels and retains 16 overlapping curated labels at higher priority.

The builder probed 46 endpoints and constructed 40 unique observed direct-transfer cases. Before prediction, a fixed entity-round-robin rule selected 20 cases: 14 operational and 6 held-out, covering all 16 published entities. All 20 were attempted. Five expected source-to-endpoint transfers were outside the bounded retrieved evidence. Six retrieved cases were excluded from single-label accuracy because the source directly interacted with multiple published VASPs. Nine were evaluable. No case was replaced after its result.

| Measure | Second-pilot value | Denominator / meaning |
|---|---:|---|
| Expected transfer retrieved | 15/20 (75.0%) | Exact observed source-to-endpoint edge in production source history. |
| Provider requests without reported error | 20/20 | Does **not** imply complete wallet history; retrieval remains capped at five recent pages. |
| Evaluable unambiguous cases | 9/20 (45.0%) | Conditional accuracy denominator. |
| Conditional Top-1 entity attribution | 6/9 (66.7%) | Includes one disputed public-versus-curated entity case; see below. |
| Conditional Top-3 entity attribution | 6/9 (66.7%) | Same conditional denominator. |
| Direct-hop accuracy | 6/9 (66.7%) | Missing path to expected entity counts as incorrect. |
| Hop-distance MAE | 0.0 hops (N=6) | Only predicted paths to the expected entity; misses excluded from MAE, disclosed above. |
| Median engine latency | 6.236 ms (N=9) | Analysis only. |
| P95 engine latency | 8.841 ms (N=9) | Analysis only. |
| Median uncached end-to-end latency | 4,178.957 ms (N=20) | Provider retrieval and evaluation; excludes discovery. |
| P95 uncached end-to-end latency | 24,071.162 ms (N=20) | Same denominator. |
| End-to-end Top-1 success | 6/20 (30.0%) | Correct Top-1 over every attempted case. |
| Nearest-VASP accuracy | Not measured | A direct edge cannot establish global nearest VASP across a bounded history. |

**Operational stratum:** 14 attempted, 9 expected transfers retrieved, 6 evaluable, Top-1 and Top-3 each 5/6, direct hop 5/6, end-to-end Top-1 5/14. **Held-out stratum:** 6 attempted, all 6 expected transfers retrieved, 3 evaluable, Top-1 and Top-3 each 1/3, direct hop 1/3, end-to-end Top-1 1/6. The single held-out entity match was Coinbase, which also had other operational labels. It does **not** show that Tracepoint recognized the held-out endpoint itself or generalized to an unknown service.

The Bittrex-labeled pilot endpoint is curated as OKX at the same address. Another external OKX endpoint is curated as Bybit. Both disagreements are listed in `label_conflicts.json`. The Bittrex/OKX case was retained as an incorrect Top-1 in the raw 6/9 pilot result, but it is not uncontested single-label ground truth. The final benchmark must freeze a conflict exclusion rule before sampling. This pilot's 6/9 figure is descriptive, not a validated system accuracy claim.

Discovery recorded 29 uncached request-wrapper calls, 17 cache hits, and one retrieval error across 46 probes. Evaluation recorded 48 uncached request-wrapper calls and zero cache hits: 77 uncached wrapper calls in this phase, plus reused public discovery responses. Internal HTTP retries can make wire attempts higher. Evaluation of the 20 cases consumed 178.54 seconds of summed end-to-end time; discovery took additional time. No quota or price claim is made.

Controlled functional validation: **5/5** separate fixtures passed. Software checks: **37/37** backend tests, **4/4** browser tests, TypeScript check, production build, changed-file Python lint, and `git diff --check` pass. Full-repository Python lint reports 15 existing violations in untouched `app/main.py`, `app/storage.py`, and `tests/test_scope.py`; this scoped benchmark did not alter those files.

Real-world specificity was not measured because independently verified negative ground truth was unavailable. Precision, recall and F1 are not reported. Scores are uncalibrated evidence scores, not probabilities of ownership. A VASP association does not prove wallet ownership or criminal liability. This endpoint-derived, small pilot is not representative of arbitrary Ethereum investigations; missing older history and source-label conflicts remain material limitations. No final benchmark was run.
