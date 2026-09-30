import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()  # loads backend/.env

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import Field, field_validator

from .engine import TraceBudgetExceeded, analyze
from .goldrush import GoldRushProvider
from .label_loader import load_labels
from .models import Chain, InvestigationRequest, StrictModel
from .providers import DEMO_TARGET, SyntheticProvider
from .report import report
from .routing import (
    RoutingPreparation,
    RoutingTransition,
    confidence_threshold,
    prepare,
    SIMULATION_NOTICE,
)
from .storage import CaseStore


@asynccontextmanager
async def lifespan(app):
    app.state.store = CaseStore()
    yield
    app.state.store.engine.dispose()


app = FastAPI(title="VASP Investigator", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "live_ingestion": bool(os.getenv("GOLDRUSH_API_KEY")),
    }


@app.get("/api/demo")
def demo():
    return {"target": DEMO_TARGET, "chains": ["ethereum", "bnb"]}


@app.get("/api/cases")
def list_cases():
    return app.state.store.list()


@app.post("/api/cases", status_code=201)
def create_case(request: InvestigationRequest):
    if request.mode == "live":
        raise HTTPException(
            422,
            "Live cases must use /api/investigate so evidence is retrieved from GoldRush.",
        )
    if request.mode == "demo":
        try:
            txs, labels = SyntheticProvider().fetch(request.target, request.chain)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    else:
        txs, labels = request.transactions, request.labels
    evidence = {
        "transactions": [t.model_dump(mode="json") for t in txs],
        "labels": [label.model_dump(mode="json") for label in labels],
    }
    digest = sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        analysis = analyze(request, txs, labels)
    except TraceBudgetExceeded as exc:
        raise HTTPException(422, str(exc))
    case = {
        "id": "CASE-" + uuid4().hex[:12].upper(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": request.title,
        "evidence_digest": digest,
        "audit_initialized": True,
        "evidence": evidence,
        "analysis": analysis,
    }
    app.state.store.save(case)
    return case


def require_case(case_id):
    case = app.state.store.get(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    return require_case(case_id)


@app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
def get_report(case_id: str, download: bool = False):
    case = require_case(case_id)
    try:
        app.state.store.record_report(case_id, exported=download)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return PlainTextResponse(
        report(case, app.state.store.routing(case_id), app.state.store.audit(case_id)),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{case["id"]}.md"'},
    )


@app.get("/api/cases/{case_id}/evidence")
def get_evidence(case_id: str):
    case = require_case(case_id)
    return {
        "case_id": case["id"],
        "sha256": case["evidence_digest"],
        "evidence": case["evidence"],
        "analysis": case["analysis"],
    }


class InvestigateRequest(StrictModel):
    target: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")
    chain: Chain = Chain.ethereum
    max_hops: int = Field(default=4, ge=1, le=6)
    title: str = Field(default="Live investigation", min_length=1, max_length=100)

    @field_validator("target")
    @classmethod
    def lowercase(cls, v):
        return v.lower()


@app.post("/api/investigate", status_code=201)
def investigate(request: InvestigateRequest):
    try:
        provider = GoldRushProvider()
        txs, _ = provider.fetch(request.target, request.chain)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(503, f"Blockchain data unavailable: {exc}")

    labels = load_labels(request.chain)
    # Build an InvestigationRequest to reuse the existing analysis pipeline
    inv_request = InvestigationRequest(
        target=request.target,
        chain=request.chain,
        mode="live",
        max_hops=request.max_hops,
        title=request.title,
        transactions=txs,
        labels=labels,
    )
    evidence = {
        "transactions": [t.model_dump(mode="json") for t in txs],
        "labels": [label.model_dump(mode="json") for label in labels],
    }
    digest = sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        analysis = analyze(inv_request, txs, labels)
    except TraceBudgetExceeded as exc:
        raise HTTPException(422, str(exc))
    case = {
        "id": "CASE-" + uuid4().hex[:12].upper(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": request.title,
        "evidence_digest": digest,
        "audit_initialized": True,
        "evidence": evidence,
        "analysis": analysis,
    }
    app.state.store.save(case, live=True)
    return case


@app.get("/api/simulation-policy")
def simulation_policy():
    try:
        threshold = confidence_threshold()
    except ValueError as exc:
        raise HTTPException(503, str(exc))
    return {
        "notice": SIMULATION_NOTICE,
        "minimum_score": threshold,
        "meaning": "Configurable simulation rule only; not a legal or evidentiary standard.",
    }


@app.get("/api/cases/{case_id}/audit")
def case_audit(case_id: str):
    case = require_case(case_id)
    audit = app.state.store.audit(case_id)
    audit["historical_events_unavailable"] = not case.get("audit_initialized", False)
    return {"case_id": case_id, "evidence_digest": case["evidence_digest"], **audit}


@app.get("/api/cases/{case_id}/routing")
def get_routing(case_id: str):
    require_case(case_id)
    return {"notice": SIMULATION_NOTICE, "routing": app.state.store.routing(case_id)}


@app.post("/api/cases/{case_id}/routing", status_code=201)
def prepare_routing(case_id: str, request: RoutingPreparation):
    case = require_case(case_id)
    try:
        routing = prepare(case, request)
        return app.state.store.prepare_routing(case, routing)
    except ValueError as exc:
        raise HTTPException(409 if "verification failed" in str(exc) else 422, str(exc))


@app.post("/api/cases/{case_id}/routing/state")
def transition_routing(case_id: str, request: RoutingTransition):
    require_case(case_id)
    try:
        return app.state.store.transition_routing(case_id, request.state)
    except ValueError as exc:
        raise HTTPException(409 if "verification failed" in str(exc) else 422, str(exc))
