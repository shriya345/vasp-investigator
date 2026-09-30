# Tracepoint — VASP Investigator

A runnable SIH 2026 prototype for explainable attribution of cryptocurrency fund flows to labelled service endpoints. It identifies **evidence-supported VASP candidates**, not people or wallet ownership.

Intended investigator workflow: NCRP / LEA case context → suspect VDA wallet → Tracepoint → live blockchain intelligence → transaction tracing → risk and service detection → nearest VASP and highest-confidence comparison → evidence review → investigator review → lawful-basis gate → SAHYOG-ready **simulation** → report and case audit trail. There is no integration with I4C, NCRP or the live SAHYOG Portal, and no government endorsement is claimed.

## Installation

### Prerequisites

- Python 3.9+ (3.12 recommended)
- Node.js 20.9+
- A free [GoldRush API key](https://goldrush.dev) for live investigations

### 1. Clone the repository

```sh
git clone https://github.com/your-org/vasp-investigator.git
cd vasp-investigator
```

### 2. Set up environment variables

```sh
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in your GoldRush API key:

```env
GOLDRUSH_API_KEY=your_key_here
```

The demo and import modes work without any API key. Only live investigation (`POST /api/investigate`) requires one.

### 3. Install dependencies and start

```sh
./scripts/setup.sh   # creates backend/.venv and installs Python + Node deps
./scripts/dev.sh     # starts API on :8000 and dashboard on :3000
```

On Windows, run the equivalent commands manually:

```sh
# Backend
python -m venv backend/.venv
backend\.venv\Scripts\pip install -r backend/requirements.lock

# Frontend
cd frontend && npm ci && cd ..

# Start API
cd backend && .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000

# Start dashboard (in a second terminal)
cd frontend && npm run dev
```

### 4. Open the app

- Dashboard: http://127.0.0.1:3000
- API docs: http://127.0.0.1:8000/docs

### Live investigation

Enter any Ethereum or BNB Chain wallet address and click **Investigate live**. The backend fetches a bounded recent transaction history from GoldRush (Covalent), applies the available VASP/risk labels, and runs the trace engine.

Requires a GoldRush API key. Create a free account at https://goldrush.dev, then add the key to `backend/.env`:

```env
GOLDRUSH_API_KEY=your_key_here
```

### Synthetic demo

The demo address runs a fully deterministic synthetic scenario with no API key required. Click **Explore demo investigation** on the welcome screen or enter the demo address:

```
0x71a000000000000000000000000000000000092f
```

### Import evidence

Use the sidebar's **Import evidence** button to load a pre-built investigation package. Five ready-to-use fixtures are included in `backend/data/test_cases/`. See [the import guide](docs/IMPORT.md) for the full JSON schema.

## What's implemented

### Blockchain ingestion
- GoldRush (Covalent) provider: up to five recent transaction pages with native transfers and decoded ERC-20/BEP-20 Transfer logs for Ethereum and BNB Chain, with retry/backoff and failed-transaction filtering.
- Normalized evidence contracts (chain, block ordering, contract-based token identity, duplicate-event rejection, timezone validation).

### VASP / risk label dataset
- 18 sourced Ethereum VASP address labels: Binance, Coinbase, Kraken, OKX, Bybit, KuCoin — sourced from Etherscan labels.
- For locally reproduced evaluation only, a deterministic operational subset of published Ethereum CEX endpoints can add 243 non-curated labels across 16 entities; 111 endpoints were held out in the recorded benchmark. The derived address file is **not distributed** in this public repository because file-level redistribution rights were not verified. A fresh clone runs with the independently curated labels above. See [evaluation methodology](backend/evaluation/README.md).
- 5 BNB Chain VASP addresses sourced from BscScan labels.
- 5 Tornado Cash pool addresses (OFAC SDN-listed).
- Polygon, Optimism, Avalanche bridges.
- Uniswap V2/V3, SushiSwap DEX routers.
- Sanctioned and scam addresses.
- Curated label files carry source URLs, confidence, source reliability, and an observation timestamp. The loader preserves available URLs. These assertions still require independent manual verification. FIU-IND status is unknown for all current labels.

### Trace engine
- Chronological, same-asset proportional tracing, hop limits, cycle boundaries, and conservative service endpoint stops.
- Transparent six-component weighted attribution scores (proximity, interaction, independent paths, recency, label quality, cluster support) with evidence quality cap. Nearest VASP uses shortest supported temporal path; highest-confidence VASP uses the unchanged score. Both are reported separately.
- Rule-based risk signals: mixer, bridge, sanctions, scam, rapid layering, large-value transfer.
- Valuation coverage, velocity, HHI and entropy metrics.

### Dashboard (six views)
- Overview: fund-flow graph, ranked VASP candidates, explainable evidence breakdown, risk signals, movement timeline.
- Transaction graph: React Flow with zoom/pan, hop depth / min value / date / entity-type filters, risk highlights, candidate-path highlighting.
- VASP attribution: component-level score breakdown with label provenance.
- Risk & typology: evidence-linked risk factors and fund-flow statistics.
- Transactions: searchable evidence table with per-transaction drawer.
- Report: rendered Markdown report with nearest/highest-confidence results, evidence, case details when supplied, simulated routing and SHA-256 integrity references; downloadable.

### Persistence and export
- SQLite (default) or PostgreSQL via `DATABASE_URL`.
- Saved cases with title, chain, mode, target, and creation time.
- Downloadable Markdown investigation report and JSON evidence bundle.
- SHA-256 evidence digest for content comparison alongside timestamped, hash-chained case audit events. The audit view recomputes the evidence digest and verifies each event against its case and digest. Existing cases are not assigned historical events retroactively.

## Verify

```sh
cd backend
python -m pytest -q
cd ../frontend
npm run build
npm run typecheck
npx playwright install chromium
# With both local servers running:
npm run test:e2e
```

Backend tests cover engine correctness (conservation, ordering, contracts, dilution, boundaries, hop limits, label quality, cycles, complexity budget), provider pagination, label handling, and full API lifecycle. Frontend build and type-check run in CI. Browser tests cover demo analysis, candidate selection, graph filtering, evidence inspection, report download, imported no-evidence cases, persistence, and mobile viewport.

## Ethereum evaluation

The [frozen real-world evaluation](backend/evaluation/EVALUATION_SUMMARY.md) attempted 150 observed direct-transfer cases across 16 published CEX entities from a 220-case candidate pool. Conditional operational Top-1 was 48/48 among retrieved, unambiguous, conflict-free known-endpoint cases; all-case end-to-end Top-1 was 49/150. See the [methodology and limitations](backend/evaluation/README.md) before citing either number. These results do not establish wallet ownership or performance on arbitrary Ethereum wallets.

Publication policy: Tracepoint does not redistribute the underlying **ERC-20 Auxiliary Data** by **Shahar Somin** or its address-level derivatives. To reproduce the evaluation locally, obtain `labeled_addresses__enriched.csv` yourself from the original publisher at [Harvard Dataverse DOI 10.7910/DVN/MBF0GC](https://doi.org/10.7910/DVN/MBF0GC), then follow the [local dataset setup](backend/evaluation/README.md#local-dataset-setup-and-publication-policy). Raw data, derived labels, case manifests, per-case results, caches, and credentials remain uncommitted. Published benchmark figures are aggregate historical results; the exact frozen per-case replay requires locally retained excluded artifacts and the recorded pre-commit Git state.

## Project structure

```text
backend/app/models.py        Validated evidence schema (Transaction, Label, InvestigationRequest)
backend/app/providers.py     Provider interface and synthetic demo scenario
backend/app/goldrush.py      GoldRush (Covalent) blockchain history provider
backend/app/label_loader.py  Curated label dataset loader
backend/app/engine.py        Tracing, attribution, risk and quantitative metrics
backend/app/storage.py       SQLAlchemy case, simulation, and audit persistence
backend/app/routing.py       Simulated routing gate and state transitions
backend/app/audit.py         Hash-chained audit events and verification
backend/app/report.py        Deterministic Markdown report
backend/app/main.py          HTTP API (FastAPI)
backend/data/labels/         Curated VASP, mixer, bridge, DEX, sanctions labels
backend/data/test_cases/     Five deterministic importable investigation fixtures
frontend/app/                Dashboard and global styles
frontend/components/         Interactive React Flow graph
frontend/lib/types.ts        Shared TypeScript types
frontend/tests/              Playwright browser workflow tests
docs/METHODOLOGY.md          Tracing model, attribution formula, risk model, limitations
docs/IMPORT.md               API reference and JSON evidence format
docs/ROADMAP.md              Next implementation milestones
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Service health and ingestion capability |
| `GET` | `/api/demo` | Demo target address and supported chains |
| `POST` | `/api/investigate` | Live investigation via GoldRush + curated labels |
| `POST` | `/api/cases` | Analyze and persist (demo or import mode) |
| `GET` | `/api/cases` | Latest 100 case summaries |
| `GET` | `/api/cases/{id}` | Full stored case with analysis and evidence |
| `GET` | `/api/cases/{id}/report` | Markdown report attachment |
| `GET` | `/api/cases/{id}/evidence` | Normalized evidence, digest and analysis |
| `GET` | `/api/cases/{id}/audit` | Audit events and hash-chain verification |
| `GET` | `/api/simulation-policy` | Configured simulation threshold |
| `GET` | `/api/cases/{id}/routing` | Current simulated routing state |
| `POST` | `/api/cases/{id}/routing` | Prepare a gated simulated request |
| `POST` | `/api/cases/{id}/routing/state` | Validated simulated state transition |

## PostgreSQL / containers

```sh
docker compose up --build
```

Runs PostgreSQL, the API and the dashboard. Set `DATABASE_URL=postgresql+psycopg://user:password@host/database` for a separately managed database.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOLDRUSH_API_KEY` | For live investigation | GoldRush (Covalent) API key |
| `DATABASE_URL` | No | PostgreSQL connection string; defaults to SQLite |
| `SAHYOG_SIMULATION_MIN_SCORE` | No | Score gate from 0–100; defaults to 60. This is a simulation rule, not a legal or evidentiary standard. |

Never commit `backend/.env` to Git — it is excluded by `.gitignore`.

## Scope and operating boundaries

This is a **local, single-investigator prototype**. It has no authentication, multi-user isolation, or production deployment hardening. Keep it on localhost. Do not expose it as a public service.

Attribution scores are uncalibrated evidence scores, not ownership probabilities. Attribution represents an evidence-supported association and does not independently establish wallet ownership or criminal liability. VASP labels are sourced assertions requiring manual verification.

**Implemented:** Ethereum/BNB GoldRush ingestion when an API key is configured, normalization, tracing, ranking, risk signals, provenance retention, reports, and local case/audit persistence. GoldRush currently retrieves the target address history and may not provide enough intermediary history for live multi-hop attribution. Provider and label facts have not been independently validated in this implementation.

**SIMULATED — No connection to the live SAHYOG Portal:** A local workflow checks the selected candidate against the configured score gate, then requires a Case/FIR reference, agency, authorization confirmation, and investigator confirmation. It creates a simulated reference and supports prepared → sent → acknowledged → info_requested → complied/refused, with escalation after refusal. No real disclosure or freezing request is transmitted. BNSS Section 94 requires case-specific assessment and does not automatically authorize freezing.

**Future work:** Manual verification of live transactions and source labels, verified FIU-IND regulatory data, broader provider coverage, and production security and deployment controls. No FIU registration status is inferred from an address label.

The evidence digest and append-only application audit chain support tamper-evident evidence integrity / chain-of-custody review. Hashing alone does not authenticate external evidence or make it legally admissible. Existing cases display a legacy notice rather than fabricated earlier audit events. Database administrators could still replace an entire trail; this is not a production immutable log. SQLite files and `.env` are excluded from Git.

See [methodology](docs/METHODOLOGY.md) for the full model description and limitations.

The separate [baseline evaluation](backend/evaluation/README.md) measures the unchanged engine against published Ethereum exchange labels and observed transfers; its five controlled fixtures are reported separately from real-world cases. Results are conditional on retrieved evidence and disclosed label overlap.

The post-baseline attribution assessment adds an evidence state, explicit coverage limits, source profiles and conflicts, deterministic evidence-removal sensitivity tests, and prioritized investigative next steps. It leaves the engine's scoring and the frozen benchmark unchanged. Separate analysis and assessment SHA-256 digests are anchored to the case audit event. The related-cases view compares shared outgoing or supported-path addresses among locally saved cases with verified analysis seals, without claiming shared ownership or identity. See [assessment methodology](docs/METHODOLOGY.md#post-baseline-evidence-assessment) for exact rules and limitations.

## Framework references

- [Next.js](https://nextjs.org/docs/app/getting-started/installation)
- [React Flow](https://reactflow.dev/learn)
- [FastAPI](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [GoldRush API](https://goldrush.dev/docs/)
