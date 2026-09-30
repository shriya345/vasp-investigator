# FINAL REAL-WORLD ETHEREUM EVALUATION

Dataset: Somin ERC-20 Auxiliary Data (`labeled_addresses__enriched.csv`; SHA-256 `579b42862499032390ea519da5aca00470643ca1c06bdd392f39c9af55e71157`).
External addresses: 10627; CEX endpoints: 370; candidate pool: 220; final attempted N: 150.
VASPs represented: 16 (Binance, Bitfinex, Bithumb, Bitstamp, Bittrex, Coinbase, Crypto.com, Gemini, HitBTC, Hotbit, Huobi, Kraken, KuCoin, OKX, Poloniex, Upbit). Operational/known: 105; held-out: 45.
Expected transfers retrieved: 123; evaluable: 72; ambiguous: 49; ground-truth conflicts: 1; provider failures: 1; other failures: 1.

| Metric | Result | Denominator |
|---|---:|---|
| Known-endpoint Top-1 | 48/48 (100.0%) | Evaluable operational cases |
| Known-endpoint Top-3 | 48/48 (100.0%) | Evaluable operational cases |
| Known direct-hop accuracy | 48/48 (100.0%) | Evaluable operational cases |
| Known hop-distance MAE | 0.0 hops | 48 predicted expected paths |
| Known median engine latency | 1.734 ms | 48 evaluable cases |
| Known P95 engine latency | 9.112 ms | 48 evaluable cases |
| Expected-transfer retrieval | 123/150 (82.0%) | All attempted |
| Evaluable-case rate | 72/150 (48.0%) | All attempted |
| End-to-end Top-1 success | 49/150 (32.7%) | All attempted |
| Ambiguity rate | 49/150 (32.7%) | All attempted |
| Provider failure rate | 1/150 (0.7%) | All attempted |
| Ground-truth conflicts | 1 | All attempted; excluded only from single-label accuracy |
| Nearest-VASP accuracy | Not measurable | Unique global-nearest ground truth unavailable |

## 1. Methodology

The dataset's published CEX labels are external assertions, not independently verified ownership. An observed Ethereum source-to-endpoint transfer supplies the direct edge. Candidate discovery and final selection used the rules and hashes in `benchmark_freeze.json`; `final_cases.csv` was checksummed before prediction. The 70/30 operational/held-out target was filled deterministically as availability allowed. No case was replaced after a result. The original pilots remain in `pilot1/` and `pilot2/`.

## 2. Known-endpoint operational attribution

105 attempted operational cases yielded 48 unambiguous evaluable cases. Conditional Top-1, Top-3 and hop results above measure tracing and endpoint recognition given published operational intelligence. 44/48 correct operational cases scored 0 because public labels lack numeric confidence and reliability; 48/48 had only one ranked candidate. Thus the conditional entity match does not test discrimination among competing VASPs or establish high-confidence attribution. Scores are not ownership probabilities.

## 3. Held-out endpoint analysis

45 held-out cases were attempted; 24 were evaluable. Their conditional entity Top-1 was 1/24 (4.2%). No held-out endpoint was independently recognized. Of these cases, 23 reached the endpoint but had no supported VASP attribution, 5 lacked the expected retrieved evidence (including one provider failure), 1 matched the entity via another known endpoint, and 16 were ambiguous. The 23 no-attribution cases are the same 23 coverage-limited cases, not an additional group. An entity match via another endpoint does not identify the held-out address or show ML generalization.

## 4. Blockchain evidence retrieval

The exact expected transfer appeared in bounded production source history for 123/150 (82.0%). GoldRush reads at most five recent transaction pages and decoded token logs; a successful request does not establish complete wallet history. Discovery used 213 uncached request-wrapper calls and 54 cache hits; evaluation used 327 calls and 48 cache hits. Total: 540 uncached request-wrapper calls and 102 cache hits. Internal retries can increase wire attempts. Evaluation runtime was 1509.214 seconds (25 min 9 sec); discovery took approximately 39 minutes from process start to completion, for about 64 minutes of discovery plus evaluation, excluding verification.

## 5. Failure analysis

Every attempted case remains in `results.csv`. Categories, percentages, technical explanations and future work are detailed in `FAILURE_ANALYSIS.md`. Two known public-versus-curated endpoint conflicts retain both labels and provenance in `label_conflicts.json`; one selected conflict is counted separately, neither correct nor incorrect in conditional accuracy. The sole analysis failure contained 14,686 normalized events, exceeding the 5,000-event request limit. The sole provider failure followed four cached pages when a later page request failed; its exact error type was not retained.

## 6. Controlled functional validation

5/5 controlled scenarios passed. These are separate from real-world denominators.

## 7. Software verification

Backend tests: 39/39 passed with the live key disabled for the key-free health assertion. Browser/E2E: 4/4 passed. TypeScript, frontend production build, changed-file Python lint, and `git diff --check` passed. Repository-wide lint retains 15 pre-existing issues in untouched `app/main.py`, `app/storage.py`, and `tests/test_scope.py`.

## 8. Limitations

Real-world specificity, precision, recall, and F1 were not measured because independently verified negative ground truth was unavailable. Nearest-VASP accuracy is not measurable without a unique globally nearest service label. Published and curated labels have related Etherscan provenance. The conditional 48/48 operational result applies only to retrieved, unambiguous, conflict-free direct cases; operational end-to-end success was 48/105 (45.7%). This endpoint-derived sample does not represent arbitrary Ethereum wallets. VASP association does not establish sender ownership or criminal liability. No government, court, FIU or live SAHYOG validation is implied.

### Entity accounting

| Entity | External endpoints | Candidate cases | Selected cases | Operational | Held-out | Evaluable |
|---|---:|---:|---:|---:|---:|---:|
| Binance | 57 | 25 | 13 | 9 | 4 | 4 |
| Bitfinex | 40 | 19 | 13 | 9 | 4 | 10 |
| Bithumb | 18 | 18 | 13 | 9 | 4 | 3 |
| Bitstamp | 9 | 8 | 8 | 6 | 2 | 4 |
| Bittrex | 4 | 3 | 3 | 3 | 0 | 1 |
| Coinbase | 25 | 20 | 13 | 9 | 4 | 9 |
| Crypto.com | 21 | 12 | 10 | 6 | 4 | 4 |
| Gemini | 13 | 8 | 8 | 5 | 3 | 3 |
| HitBTC | 6 | 4 | 4 | 3 | 1 | 2 |
| Hotbit | 4 | 4 | 4 | 3 | 1 | 0 |
| Huobi | 85 | 23 | 12 | 8 | 4 | 8 |
| Kraken | 18 | 17 | 12 | 8 | 4 | 4 |
| KuCoin | 20 | 16 | 11 | 8 | 3 | 5 |
| OKX | 26 | 21 | 11 | 8 | 3 | 7 |
| Poloniex | 20 | 18 | 11 | 8 | 3 | 7 |
| Upbit | 4 | 4 | 4 | 3 | 1 | 1 |
