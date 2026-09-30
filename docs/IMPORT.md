# Import normalized evidence

Use the sidebar's **Import evidence** button and select a JSON file. The browser forces `mode: "import"`, so input cannot accidentally invoke the demo. Import limits: 10 MB in the UI, 5,000 transfer events, 1,000 labels, and 1–6 trace hops. Tracing also stops with an explicit error at 100,000 inventory allocation operations; reduce the imported window when this limit is reached. The API schema at `/docs` lists the full contract.

A minimal example is available at `docs/example-import.json`. Its transfer is a documentation fixture; it has no real service labels and must not be used as on-chain evidence.

```json
{
  "target": "0x0000000000000000000000000000000000000001",
  "chain": "ethereum",
  "mode": "import",
  "title": "My investigation",
  "max_hops": 4,
  "transactions": [],
  "labels": []
}
```

Every transfer requires a 32-byte transaction hash, chain, block number, timezone-aware timestamp, sender, recipient, symbol, positive decimal amount, source and source confidence [0,1]. `usd_value` is optional. Use decimal strings. `transaction_type` is native, token or internal. Tokens require a 20-byte contract address; token identity never relies on the symbol. Native/internal transfers must not include a token contract address.

`transaction_index` identifies ordering within a block. `event_index` must uniquely identify a normalized transfer within its transaction, including native/internal/token events. An adapter should reserve distinct indexes when mixing event types; raw ERC-20 log index alone may conflict with a native transfer. Duplicate `(chain, tx_hash, event_index)` records are rejected. Addresses are normalized to lowercase, not verified by EIP-55 checksum.

Labels require address, chain, entity, entity_type, confidence, strength (`strong`, `probable`, `weak`), source, source_reliability and timezone-aware observed_at. Allowed entity types: vasp, exchange, mixer, bridge, dex, contract, scam, sanctioned. Imported labels cannot be synthetic and duplicate address labels are rejected. The importer supplies provenance; the backend does not retrieve or validate the source. Do not import conflicting, stale or unsupported labels as verified facts.

Only successful transfers on the selected chain should be included. Record API coverage/pagination and historical valuations in source metadata. Missing history, unobserved opening balances, fees and unavailable internal transfers must be assessed by the investigator. Network calls are not made from supplied label-source strings.

## API

- `GET /api/health`: service health and ingestion capability.
- `GET /api/demo`: demo address and networks.
- `POST /api/cases`: analyze and persist a validated request.
- `GET /api/cases`: latest 100 case summaries.
- `GET /api/cases/{id}`: stored case with analysis and evidence.
- `GET /api/cases/{id}/report`: Markdown report attachment.
- `GET /api/cases/{id}/evidence`: normalized evidence, digest and analysis.

The frontend forwards `/api/*` to the local FastAPI service. `API_URL` configures the upstream when the frontend builds. The API does not enable cross-origin browser access by default.

## Provenance and simulation endpoints

`Label` also accepts optional `source_url` (HTTPS). Current datasets do not substantiate FIU-IND registration; `fiu_registered` must be null or omitted. A non-null value is rejected. `observed_at` dates the label assertion; it is not a certified verification date.

`POST /api/investigate` stores `mode: live`; imported cases use `mode: import`. `GET /api/simulation-policy` exposes the configured illustrative score threshold. `POST /api/cases/{id}/routing` requires `candidate_entity`, `case_reference`, `investigating_agency`, `authorized_investigation: true`, and `investigator_confirmed: true`. `GET /api/cases/{id}/routing` reads the local simulation; `POST /api/cases/{id}/routing/state` accepts an allowed next `state`. `GET /api/cases/{id}/audit` returns the hash-linked event trail and verification result. No endpoint connects to the live SAHYOG Portal.
