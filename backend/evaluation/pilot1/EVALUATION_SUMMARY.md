# Tracepoint baseline evaluation — pilot only

## Real-world evaluation — Ethereum

Dataset: Somin, *ERC-20 Auxiliary Data*, `labeled_addresses__enriched.csv` ([Harvard Dataverse](https://doi.org/10.7910/DVN/MBF0GC)). This file has 10,627 rows, of which 370 are distinct addresses marked `Centralized Exchange`, covering 16 published entity names. Dataset SHA-256: `579b42862499032390ea519da5aca00470643ca1c06bdd392f39c9af55e71157`. The file does not provide a per-address verification date. Fixed endpoint-sampling seed: `2612026`. Baseline Git commit: `e1bbc8964a1fcf99bcc0686113afec8a841fb1d8`; engine version: `0.1.0`.

This **pilot** probed 19 endpoints to construct 15 observed direct-transfer cases. The cases cover OKX, KuCoin, Bitfinex, Binance, Huobi, Poloniex, Kraken, and Coinbase. Every source address differs from its published VASP endpoint. Discovery excluded three endpoints without a distinct unlabelled source in the observed page and one endpoint with a retrieval error. These exclusions and all source-to-endpoint evidence are retained in `dataset_quality.json` and `real_cases.csv`.

The published file supplies a service URL for 11 of the 15 selected endpoints; four have no URL in that field. The dataset publication year is recorded separately from the unavailable per-address verification date.

| Measure | Pilot result | Denominator and interpretation |
|---|---:|---|
| Candidate cases / attempted | 15 / 15 | All constructed cases were attempted. |
| Expected transfer retrieved | 9 / 15 (60.0%) | Six known transfers were absent from production source-wallet evidence. |
| Complete provider retrieval | 0 / 15 | The secondary token-transfer endpoint errored on all pilot source fetches; direct evidence was still present in some transaction pages. |
| Evaluable direct cases | 5 / 15 | All five have partial provider coverage. Four retrieved cases were excluded because multiple named VASPs were directly observed. |
| Conditional top-1 VASP attribution | 1 / 5 (20.0%) | Only cases with the expected direct edge present and no observed multi-VASP ambiguity. |
| Conditional top-3 VASP attribution | 1 / 5 (20.0%) | Same five-case denominator. |
| Nearest-VASP accuracy | Not measured (N=0) | A direct transfer does not establish globally nearest VASP across full history and labels. |
| Hop-distance MAE | 0.0 hops (N=1) | Only one case produced a supported path to the expected entity; missing predictions are not converted to zero error. |
| Median / P95 engine latency | 1.990 / 13.509 ms (N=5) | `analyze()` only. |
| Median / P95 uncached end-to-end latency | 18,473.030 / 54,173.858 ms (N=12) | Source retrieval plus evaluation for uncached cases; small, mixed-status sample. |
| End-to-end top-1 success | 1 / 15 (6.67%) | Correct top-1 over **all attempted** cases. |

The discovery and evaluator made 19 and 55 uncached GoldRush request-wrapper invocations respectively, **74 total**. Retries inside the production adapter may make actual HTTP attempts higher. Nine evaluator requests used cached public responses. No large benchmark has been started.

**Real-world specificity was not measured because independently verified negative ground truth was unavailable.** Precision, recall, and F1 are likewise not reported. The controlled negative fixtures are not real-world negatives.

## Label coverage

One of the 15 cases used an endpoint already in Tracepoint's internal VASP labels: top-1 and top-3 were each 1/1 for its single evaluable case. Four evaluable cases had endpoints absent from internal labels: top-1 and top-3 were each 0/4. The full attempted split is 1 known-label and 14 unseen-label cases. These are tiny pilot strata, not generalizable accuracy estimates. The current label-dependent engine cannot directly name an unseen endpoint solely from the external evaluation label, which was deliberately withheld from analysis.

All four evaluable unseen-label cases returned no supported VASP attribution from the current internal labels. This describes label coverage in this sample; it is not a real-world no-attribution specificity result.

## Controlled functional fixture validation

**5/5 scenarios passed**, including the ambiguous Coinbase/Kraken fixture and both no-attribution fixtures. Details and per-fixture runtimes are in `fixture_results.json`; these scenarios are excluded from real-world denominators.

## Software verification

- Backend: **32 passed** in 0.45 s with `GOLDRUSH_API_KEY=` for the existing key-free test expectation. With the configured key loaded, the existing health test expected `live_ingestion: false` and failed (31 passed, 1 failed); this is an environment-sensitive test assertion, not a benchmark change.
- Browser/E2E: **4 passed** in 3.6 s.
- TypeScript check: passed.
- Frontend production build: passed.
- Evaluation Python lint and `git diff --check`: passed.

## Limits and next decision

External endpoint labels are published assertions, not independently proven ownership, and they share Etherscan provenance with some internal labels. The production GoldRush adapter retrieves limited target-wallet history, which omitted six independently observed transfers here; its secondary token-transfer request failed on every pilot source. All five evaluable cases therefore have partial retrieval. The sample is selected from exchange endpoints and does not represent Ethereum generally. Confidence scores are uncalibrated evidence scores, not ownership probabilities. A transfer to a VASP-associated endpoint does not establish the sender's owner or criminal liability.

**Do not launch 100–150 cases on the current pilot evidence without reviewing quota and coverage.** The next approved step would inspect the GoldRush endpoint failures and decide whether this baseline's partial-coverage method is acceptable; production behavior and the original baseline must remain preserved before any fix or optimization.
