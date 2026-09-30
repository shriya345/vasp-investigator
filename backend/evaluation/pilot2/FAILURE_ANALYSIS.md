# First-pilot failure analysis

This is the preserved 15-case baseline before the provider and label changes. “Retrieved” means the exact independently observed transfer was present in source-wallet evidence. “Ambiguous” means multiple named VASP entities were directly observed; these cases were excluded from single-label accuracy.

| Case | Entity | Curated endpoint | Transfer retrieved | Ambiguous | Evaluable | Primary finding |
|---|---|---|---|---|---|---|
| REAL-0001 | OKX | no | yes | no | yes | No candidate: expected endpoint absent from operational labels |
| REAL-0002 | KuCoin | no | no | no | no | Expected edge outside bounded source retrieval |
| REAL-0003 | Bitfinex | no | yes | yes | no | Multiple directly observed VASP entities |
| REAL-0004 | Bitfinex | no | no | no | no | Expected edge outside bounded source retrieval |
| REAL-0005 | Binance | no | yes | no | yes | No candidate: expected endpoint absent from operational labels |
| REAL-0006 | Huobi | no | no | no | no | Expected edge outside bounded source retrieval |
| REAL-0007 | Huobi | no | yes | yes | no | Multiple directly observed VASP entities |
| REAL-0008 | OKX | no | yes | yes | no | Multiple directly observed VASP entities |
| REAL-0009 | OKX | no | yes | no | yes | No candidate: expected endpoint absent from operational labels |
| REAL-0010 | Huobi | no | no | no | no | Expected edge outside bounded source retrieval |
| REAL-0011 | Poloniex | no | yes | yes | no | Multiple directly observed VASP entities |
| REAL-0012 | Bitfinex | no | yes | no | yes | No candidate: expected endpoint absent from operational labels |
| REAL-0013 | Kraken | no | no | no | no | Expected edge outside bounded source retrieval |
| REAL-0014 | Coinbase | yes | yes | no | yes | Correct known-label attribution |
| REAL-0015 | Huobi | no | no | no | no | Expected edge outside bounded source retrieval |

Four unseen, evaluable cases (REAL-0001, 0005, 0009, 0012) returned an empty candidate list despite the expected edge being retrieved. Their expected endpoints lacked operational labels, so this is label coverage failure, not demonstrated path tracing or ranking failure. REAL-0014 was curated-known and correctly attributed.

All 15 source retrievals were marked partial because the secondary `transfers_v2` call failed. A live status probe returned HTTP 400 with the provider message that `contract-address` is required; the adapter omitted it and retried the unrecoverable 400. The transactions adapter also fetched numbered pages 0–4 (oldest first), whereas the unnumbered v3 endpoint returns the most recent page. That bounded oldest-first window can omit the recent transfer observed during endpoint discovery. Six such expected edges were absent; per-case causation beyond this bounded-window issue is not proven. The corrected adapter uses the recent page and preceding pages, parses its decoded Transfer logs, and does not make an unfiltered invalid `transfers_v2` call.

No ownership proof, FIU status, negative ground truth, or full-wallet completeness is established by this pilot. Original inputs, results, metrics, quality summary and report are preserved under `pilot1/`.

## Second-pilot case accounting

The 20 second-pilot cases below were fixed before predictions. Categories describe this pilot only; they do not silently remove any attempted case.

| Case | Stratum | Expected | Retrieved | Status | Top-1 | Category |
|---|---|---|---|---|---|---|
| REAL-0016 | operational | Binance | no | not_evaluable | — | Bounded provider history omitted expected edge |
| REAL-0017 | operational | Bithumb | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |
| REAL-0018 | operational | Bitstamp | yes | evaluable | Bitstamp | Expected entity ranked first |
| REAL-0019 | operational | Bittrex | yes | evaluable | OKX | External Bittrex / curated OKX entity conflict |
| REAL-0020 | operational | Coinbase | no | not_evaluable | — | Bounded provider history omitted expected edge |
| REAL-0021 | operational | Gemini | no | not_evaluable | — | Bounded provider history omitted expected edge |
| REAL-0022 | operational | HitBTC | yes | evaluable | HitBTC | Expected entity ranked first |
| REAL-0023 | operational | Hotbit | no | not_evaluable | — | Bounded provider history omitted expected edge |
| REAL-0024 | operational | Huobi | yes | evaluable | Huobi | Expected entity ranked first |
| REAL-0025 | operational | Kraken | yes | evaluable | Kraken | Expected entity ranked first |
| REAL-0026 | operational | KuCoin | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |
| REAL-0027 | operational | OKX | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |
| REAL-0028 | operational | Poloniex | no | not_evaluable | — | Bounded provider history omitted expected edge |
| REAL-0029 | operational | Upbit | yes | evaluable | Upbit | Expected entity ranked first |
| REAL-0001 | held_out | Binance | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |
| REAL-0002 | held_out | Bitfinex | yes | evaluable | — | Held-out endpoint absent from operational labels |
| REAL-0003 | held_out | Bithumb | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |
| REAL-0004 | held_out | Bitstamp | yes | evaluable | — | Held-out endpoint absent from operational labels |
| REAL-0005 | held_out | Coinbase | yes | evaluable | Coinbase | Entity matched via another known endpoint; held-out address not recognized |
| REAL-0006 | held_out | Crypto.com | yes | excluded_ambiguous | — | Multiple directly observed VASP entities |

Counts: 5 missing expected edges, 6 ambiguous, 2 held-out label-coverage failures, 1 entity conflict, and 6 published-entity Top-1 matches (one via another known endpoint). The conflict case is retained as a failure in the raw pilot metric, but the published entity is disputed and is not suitable as uncontested final-benchmark truth. There were no analysis exceptions in the second pilot.
