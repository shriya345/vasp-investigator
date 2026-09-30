# Recommended slide: Frozen Ethereum attribution benchmark

We selected 150 observed Ethereum source-to-published-CEX transfers across 16 entities using a frozen, entity-aware rule before running Tracepoint; operational and held-out endpoints are reported separately.

Six headline metrics:

1. Known-endpoint Top-1: 48/48 (100.0%).
2. Known-endpoint end-to-end Top-1: 48/105 (45.7%) across all operational attempts.
3. Expected transfer retrieved: 123/150 (82.0%).
4. Evaluable cases: 72/150 (48.0%).
5. End-to-end Top-1 success: 49/150 (32.7%).
6. Known median engine time: 1.734 ms (N=48).

Controlled functional validation: 5/5. Software tests: backend 39/39; browser 4/4. TypeScript and production build passed.

Limitations: The conditional 48/48 entity match had one candidate per case, and 44 of 48 scores were 0 because public-label quality is unknown. Published labels are not ownership proof; bounded history, ambiguity and conflicts limit evaluation.

30-second judge explanation: We froze a published-endpoint dataset, an operational/held-out split and a deterministic case list before analysis. We evaluated every selected case and show both conditional known-endpoint attribution and all-case retrieval and success, so missed evidence and ambiguity remain visible. Held-out entity matches can come from other known endpoints. This is evidence-supported VASP association, not proof of wallet ownership.

How did you validate accuracy? With a frozen real-transfer manifest, explicit exclusions and separate controlled/software tests.
Where did ground truth come from? Published Somin/Harvard Dataverse Etherscan-derived endpoint assertions plus observed transfers, not verified owner records.
Was the test set used to tune Tracepoint? No scoring weights, thresholds, tracing, labels or provider behavior changed after the freeze.
Why were some cases excluded? Multiple direct VASPs, disputed endpoint identities, missing expected evidence or provider/analysis failure; all remain in attempted counts.
Can Tracepoint identify a completely unseen VASP endpoint? Not directly without operational intelligence; another known endpoint can yield the same entity name.
Why no precision/recall/F1? Independently verified negative ground truth was unavailable.
Does attribution prove wallet ownership? No; it supports an endpoint association only.
