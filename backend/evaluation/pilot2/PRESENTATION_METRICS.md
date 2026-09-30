# SIH slide candidate — second pilot, not final benchmark

**Suggested title:** Tracepoint Ethereum attribution: 20-case method pilot

**Method:** We constructed 40 observed source-to-published-CEX transfers from the Somin Harvard Dataverse dataset, then selected 20 across 16 entities using a deterministic rule. We separated operational endpoint intelligence from held-out endpoints and retained missing and ambiguous cases.

- 20 real attempted cases; 16 published CEX entities represented.
- Exact expected transfer retrieved: **15/20 (75%)**.
- Unambiguous evaluable cases: **9/20 (45%)**.
- Conditional Top-1 entity match: **6/9 (66.7%)**, including one disputed public/curated label case.
- End-to-end Top-1 success: **6/20 (30%)**.
- Median engine time: **6.236 ms** on nine evaluable cases.
- Controlled functional validation: **5/5**; backend **37/37**, browser **4/4** tests pass.

**Limitations footnote:** This is a small second pilot, not final accuracy. Two external/curated entity labels conflict; the source labels are published assertions, history is bounded, and VASP association does not establish wallet ownership.

**30-second explanation for judges:** “We selected 20 real Ethereum transfers before evaluating the system. It retrieved the exact transfer in 15 and produced an unambiguous result for nine; six of those nine matched the published VASP entity. We kept missing evidence and ambiguous cases in the accounting, separated known and held-out endpoints, and found two source-label conflicts that must be excluded by a frozen rule before the larger benchmark. Our five controlled scenarios and software tests pass, but this pilot is not a claim of general real-world accuracy.”

**How did you validate it?** Exact transaction-hash checks, deterministic case selection, separate held-out and known strata, controlled fixtures, and software tests.

**Where did ground truth come from?** A published Harvard Dataverse Etherscan-derived endpoint assertion plus an observed GoldRush transfer. It is not independently verified ownership ground truth.

**Is the dataset independent?** It is external to Tracepoint's implementation, but it shares Etherscan provenance with curated labels; two entity conflicts were discovered.

**Did you train or tune on test cases?** No ML training or score-weight tuning occurred. The endpoint split and case selection were fixed before second-pilot predictions.

**Can you identify completely unseen VASP endpoints?** A held-out endpoint cannot be named directly without operational service intelligence. An entity can still match via another known endpoint; that does not identify the held-out address.

**Why no precision/recall/F1?** Independently verified real-world negative ground truth is unavailable; controlled no-attribution fixtures are not substitutes.

**Does attribution prove ownership?** No. It supports association with a labelled endpoint, not sender ownership or criminal liability.
