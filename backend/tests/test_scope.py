"""Focused tests for the SIH scope without real-wallet validation claims."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import verify
from app.engine import analyze
from app.label_loader import load_labels
from app.main import app
from app.models import Chain, InvestigationRequest, Label, Transaction
from app.providers import address
from app.storage import AuditRecord, CaseRecord

FIXTURES = Path(__file__).parents[1] / "data" / "test_cases"


def fixture(name):
    return InvestigationRequest.model_validate_json((FIXTURES / name).read_text())


def sample(i, source, destination, value, minute):
    return Transaction(
        tx_hash="0x" + f"{i:064x}",
        chain=Chain.ethereum,
        block_number=i,
        timestamp=f"2026-09-01T00:{minute:02}:00Z",
        from_address=address(source),
        to_address=address(destination),
        asset="ETH",
        amount=str(value),
        usd_value=str(value),
        source="Synthetic regression fixture",
        source_confidence=1,
    )


def service(number, entity, confidence):
    return Label(
        address=address(number),
        chain=Chain.ethereum,
        entity=entity,
        entity_type="vasp",
        confidence=confidence,
        strength="weak" if confidence < 0.5 else "strong",
        source="Synthetic regression fixture",
        source_reliability=1,
        observed_at="2026-09-01T00:00:00Z",
        synthetic=True,
    )


def test_direct_multi_hop_and_no_attribution_fixtures():
    strong = fixture("01_strong_vasp.json")
    analyzed = analyze(strong, strong.transactions, strong.labels)
    assert analyzed["nearest_vasp"]["entity"] == "Binance"
    assert analyzed["highest_confidence_vasp"]["entity"] == "Binance"
    assert analyzed["nearest_vasp"]["shortest_hops"] == 2
    mixed = fixture("02_mixed_flow.json")
    analyzed = analyze(mixed, mixed.transactions, mixed.labels)
    assert len(analyzed["candidates"]) == 2
    assert all(candidate["shortest_hops"] == 1 for candidate in analyzed["candidates"])
    unknown = fixture("05_unknown.json")
    analyzed = analyze(unknown, unknown.transactions, unknown.labels)
    assert analyzed["candidates"] == []
    assert analyzed["nearest_vasp"] is None
    assert analyzed["highest_confidence_vasp"] is None
    assert (
        analyzed["attribution_result"]
        == "No VASP attribution supported by available evidence."
    )


def test_nearest_and_highest_are_independent_of_scoring():
    transactions = [
        sample(1, 0, 1, 10, 1),
        sample(2, 0, 2, 90, 2),
        sample(3, 2, 3, 90, 3),
    ]
    labels = [service(1, "Near", 0.1), service(3, "High", 1)]
    request = InvestigationRequest(
        target=address(0),
        mode="import",
        transactions=transactions,
        labels=[label.model_copy(update={"synthetic": False}) for label in labels],
    )
    analyzed = analyze(request, transactions, labels)
    assert analyzed["nearest_vasp"]["entity"] == "Near"
    assert analyzed["nearest_vasp"]["shortest_hops"] == 1
    assert analyzed["highest_confidence_vasp"]["entity"] == "High"
    assert analyzed["highest_confidence_vasp"]["shortest_hops"] == 2
    assert analyzed["candidates"][0]["entity"] == "High"
    assert analyzed["nearest_vasp"]["score"] == next(
        c["score"] for c in analyzed["candidates"] if c["entity"] == "Near"
    )


def test_source_url_retained_and_fiu_unknown():
    labels = load_labels(Chain.ethereum)
    assert labels
    assert all(label.source_url for label in labels)
    assert all(label.fiu_registered is None for label in labels)
    with pytest.raises(ValidationError):
        Label.model_validate({**labels[0].model_dump(), "fiu_registered": True})


def valid_route(case, **updates):
    return {
        "candidate_entity": case["analysis"]["candidates"][0]["entity"],
        "case_reference": "FIR-TEST-001",
        "investigating_agency": "Fixture agency",
        "authorized_investigation": True,
        "investigator_confirmed": True,
        **updates,
    }


def test_routing_gates_lifecycle_report_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/scope.db")
    monkeypatch.setenv("SAHYOG_SIMULATION_MIN_SCORE", "0")
    with TestClient(app) as client:
        original = fixture("01_strong_vasp.json").model_dump(mode="json")
        response = client.post("/api/cases", json=original)
        assert response.status_code == 201
        case = response.json()
        cid = case["id"]
        endpoint = f"/api/cases/{cid}/routing"
        audit = client.get(f"/api/cases/{cid}/audit").json()
        assert audit["valid"]
        assert [event["action"] for event in audit["events"]] == [
            "case_created",
            "analysis_executed",
        ]
        assert audit["events"][0]["evidence_digest"] == case["evidence_digest"]
        assert (
            client.post(endpoint, json=valid_route(case, case_reference="")).status_code
            == 422
        )
        assert (
            client.post(
                endpoint, json=valid_route(case, investigating_agency=" ")
            ).status_code
            == 422
        )
        assert (
            client.post(
                endpoint, json=valid_route(case, authorized_investigation=False)
            ).status_code
            == 422
        )
        assert (
            client.post(
                endpoint, json=valid_route(case, investigator_confirmed=False)
            ).status_code
            == 422
        )
        assert client.get(endpoint).json()["routing"] is None
        created = client.post(endpoint, json=valid_route(case))
        assert created.status_code == 201
        routing = created.json()
        assert routing["state"] == "prepared" and routing["reference"].startswith(
            "SIM-SAHYOG-"
        )
        assert "No connection to the live SAHYOG Portal" in routing["notice"]
        assert client.post(endpoint, json=valid_route(case)).status_code == 422
        state_url = endpoint + "/state"
        assert client.post(state_url, json={"state": "complied"}).status_code == 422
        for state in ["sent", "acknowledged", "info_requested", "refused", "escalated"]:
            updated = client.post(state_url, json={"state": state})
            assert updated.status_code == 200
            assert updated.json()["state"] == state
        assert client.post(state_url, json={"state": "sent"}).status_code == 422
        report = client.get(f"/api/cases/{cid}/report")
        assert report.status_code == 200
        assert "Case/FIR reference: FIR-TEST-001" in report.text
        assert (
            "Nearest VASP:" in report.text and "Highest-confidence VASP:" in report.text
        )
        assert routing["reference"] in report.text
        assert (
            "does not independently establish wallet ownership or criminal liability"
            in report.text
        )
        assert "does not establish legal admissibility" in report.text
        audit = client.get(f"/api/cases/{cid}/audit").json()
        assert audit["valid"] and verify(audit["events"])
        assert audit["events"][-1]["action"] == "report_generated"
        assert client.get(f"/api/cases/{cid}/report?download=true").status_code == 200
        audit = client.get(f"/api/cases/{cid}/audit").json()
        assert audit["events"][-1]["action"] == "report_exported"
        assert audit["head_hash"] == audit["events"][-1]["audit_hash"]
        with Session(app.state.store.engine) as session, session.begin():
            first = (
                session.query(AuditRecord)
                .filter_by(case_id=cid)
                .order_by(AuditRecord.id)
                .first()
            )
            first.payload = {**first.payload, "action": "altered"}
        assert not client.get(f"/api/cases/{cid}/audit").json()["valid"]
        assert client.post(state_url, json={"state": "sent"}).status_code == 422
        assert client.get(f"/api/cases/{cid}/report").status_code == 409


def test_low_confidence_and_no_attribution_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/threshold.db")
    monkeypatch.setenv("SAHYOG_SIMULATION_MIN_SCORE", "100")
    with TestClient(app) as client:
        case = client.post(
            "/api/cases", json=fixture("01_strong_vasp.json").model_dump(mode="json")
        ).json()
        blocked = client.post(
            f"/api/cases/{case['id']}/routing", json=valid_route(case)
        )
        assert (
            blocked.status_code == 422
            and "Insufficient evidence" in blocked.json()["detail"]
        )
        unknown = client.post(
            "/api/cases", json=fixture("05_unknown.json").model_dump(mode="json")
        ).json()
        no_attribution = client.post(
            f"/api/cases/{unknown['id']}/routing", json=valid_route(case)
        )
        assert no_attribution.status_code == 422
        assert (
            no_attribution.json()["detail"]
            == "No VASP attribution supported by available evidence."
        )
        report = client.get(f"/api/cases/{unknown['id']}/report").text
        assert "No VASP attribution supported by available evidence." in report


def test_live_classification_and_retrieval_event(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/live.db")
    monkeypatch.setenv("GOLDRUSH_API_KEY", "test-only")
    source = fixture("02_mixed_flow.json")
    monkeypatch.setattr(
        main.GoldRushProvider,
        "fetch",
        lambda _self, _target, _chain: (source.transactions, []),
    )
    monkeypatch.setattr(main, "load_labels", lambda _chain: source.labels)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/cases", json={"target": source.target, "mode": "live"}
            ).status_code
            == 422
        )
        response = client.post(
            "/api/investigate", json={"target": source.target, "chain": "ethereum"}
        )
        assert response.status_code == 201
        case = response.json()
        assert case["analysis"]["mode"] == "live"
        assert (
            client.get(f"/api/cases/{case['id']}/audit").json()["events"][1]["action"]
            == "live_evidence_retrieved"
        )
        assert (
            "Evidence mode: LIVE" in client.get(f"/api/cases/{case['id']}/report").text
        )


def test_existing_case_has_no_backfilled_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/legacy.db")
    with TestClient(app) as client:
        current = client.post(
            "/api/cases", json=fixture("05_unknown.json").model_dump(mode="json")
        ).json()
        old = {k: v for k, v in current.items() if k != "audit_initialized"}
        old["id"] = "CASE-LEGACY"
        with Session(app.state.store.engine) as session, session.begin():
            session.add(
                CaseRecord(id=old["id"], created_at=old["created_at"], payload=old)
            )
        first = client.get("/api/cases/CASE-LEGACY/audit").json()
        assert first["events"] == [] and first["historical_events_unavailable"]
        assert (
            "predates the audit trail"
            in client.get("/api/cases/CASE-LEGACY/report").text
        )
        later = client.get("/api/cases/CASE-LEGACY/audit").json()
        assert [event["action"] for event in later["events"]] == ["report_generated"]
        assert later["historical_events_unavailable"]


def test_evidence_digest_detects_modified_stored_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/evidence.db")
    with TestClient(app) as client:
        case = client.post(
            "/api/cases", json=fixture("05_unknown.json").model_dump(mode="json")
        ).json()
        with Session(app.state.store.engine) as session, session.begin():
            row = session.get(CaseRecord, case["id"])
            changed = {
                **row.payload,
                "evidence": {**row.payload["evidence"], "transactions": []},
            }
            row.payload = changed
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert (
            audit["chain_valid"] and not audit["evidence_valid"] and not audit["valid"]
        )
        assert client.get(f"/api/cases/{case['id']}/report").status_code == 409
