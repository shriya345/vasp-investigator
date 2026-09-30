"""Post-baseline explanation tests. The frozen evaluator is not invoked."""

from copy import deepcopy
from hashlib import sha256

from fastapi.testclient import TestClient

from app import assessment
from app.engine import analyze
from app.main import app
from app.models import Chain, InvestigationRequest
from app.providers import DEMO_TARGET, SyntheticProvider, address
from app.storage import CaseRecord
from sqlalchemy.orm import Session
from test_engine import label, tx


def evaluate(txs, labels, mode="import"):
    request = InvestigationRequest(
        target=address(0), mode=mode, transactions=txs, labels=labels
    )
    result = analyze(request, txs, labels)
    before = deepcopy(result)
    card = assessment.assess(request, txs, labels, result)
    assert result == before
    assert card == assessment.assess(request, txs, labels, result)
    return result, card


def test_supported_and_fragile_attribution():
    sourced = label(2).model_copy(update={"source_url": "https://example.com/source"})
    result, card = evaluate([tx(1, 0, 2, 100), tx(2, 0, 2, 100)], [sourced])
    assert result["candidates"][0]["entity"] == "Exchange"
    assert card["evidence_state"] == "SUPPORTED"
    assert card["stability"]["applicable"] == 7
    assert card["counterfactuals"][-1]["became_unsupported"]
    assert card["counterfactuals"][-1]["counterfactual_leading_vasp"] is None
    assert "SIMULATED" in card["next_actions"][0]["recommendation"]


def test_public_label_unknown_quality_is_still_supported():
    public = label(2).model_copy(
        update={
            "confidence": None,
            "source_reliability": None,
            "source_url": "https://example.com/source",
        }
    )
    result, card = evaluate([tx(1, 0, 2, 100)], [public])
    assert result["candidates"][0]["score"] == 0
    assert card["evidence_state"] == "SUPPORTED_WITH_LIMITATIONS"
    assert card["label_profile"][0]["numeric_quality_known"] is False
    assert card["label_profile"][0]["source_url"] == "https://example.com/source"
    assert not any("two independent" in item for item in card["supporting_evidence"])


def test_competing_and_no_attribution_actions():
    _, competing = evaluate(
        [tx(1, 0, 2, 100), tx(2, 0, 3, 100)], [label(2, "A"), label(3, "B")]
    )
    assert competing["evidence_state"] == "AMBIGUOUS"
    assert competing["next_actions"][0]["code"] == "DISTINGUISH_CANDIDATES"
    _, unknown = evaluate([tx(1, 0, 4, 100)], [])
    assert unknown["evidence_state"] == "NO_VASP_SUPPORTED"
    assert unknown["next_actions"][0]["code"] == "RESOLVE_SERVICE_ADDRESS"
    _, empty = evaluate([], [])
    assert empty["evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert empty["leading_vasp"] is None
    assert empty["stability"]["ratio"] is None


def test_live_conflict_and_bounded_history(monkeypatch):
    first = label(2, "A")
    second = label(2, "B")
    monkeypatch.setattr(
        assessment,
        "source_assertions",
        lambda chain, addresses: {
            address(2): [first.model_dump(mode="json"), second.model_dump(mode="json")]
        },
    )
    request = InvestigationRequest(
        target=address(0), mode="live", transactions=[tx(1, 0, 2, 100)], labels=[first]
    )
    result = analyze(request, request.transactions, request.labels)
    card = assessment.assess(request, request.transactions, request.labels, result)
    assert card["evidence_state"] == "AMBIGUOUS"
    assert card["intelligence_conflicts"][0]["status"] == "UNRESOLVED_ENTITY_CONFLICT"
    assert {c["entity"] for c in card["intelligence_conflicts"][0]["assertions"]} == {
        "A",
        "B",
    }
    assert card["next_actions"][0]["code"] == "RESOLVE_LABEL_CONFLICT"
    assert "PARTIAL_PROVIDER_HISTORY" in card["evidence_coverage"]
    assert "conflicting endpoint labels" in card["investigator_summary"]


def test_demo_report_and_assessment_audit_anchor(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/assessment.db")
    with TestClient(app) as client:
        response = client.post("/api/cases", json={"target": DEMO_TARGET})
        assert response.status_code == 201
        case = response.json()
        assert case["analysis"]["candidates"]
        assert case["assessment"]["counterfactuals"]
        report = client.get(f"/api/cases/{case['id']}/report").text
        assert "## Attribution assessment" in report
        assert case["assessment_digest"] in report
        assert "does not independently establish wallet ownership" in report
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert audit["valid"] and audit["assessment_anchor_valid"]
        anchor = sha256(
            (case["analysis_digest"] + case["assessment_digest"]).encode()
        ).hexdigest()
        assert any(
            e["action"] == "analysis_executed" and e["reference"] == anchor
            for e in audit["events"]
        )


def test_original_demo_output_unchanged():
    request = InvestigationRequest(target=DEMO_TARGET)
    txs, labels = SyntheticProvider().fetch(DEMO_TARGET, Chain.ethereum)
    before = analyze(request, txs, labels)
    assessment.assess(request, txs, labels, before)
    assert before == analyze(request, txs, labels)


def test_incoming_only_is_insufficient_and_not_linked(tmp_path, monkeypatch):
    _, card = evaluate([tx(1, 7, 0, 100)], [])
    assert card["evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert card["next_actions"][0]["code"] == "ACQUIRE_BLOCKCHAIN_EVIDENCE"
    assert "No outgoing transfer" in card["next_actions"][0]["reason"]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/incoming.db")
    with TestClient(app) as client:
        cases = []
        for target in [0, 1]:
            response = client.post(
                "/api/cases",
                json={
                    "target": address(target),
                    "mode": "import",
                    "transactions": [
                        tx(target + 1, 7, target, 100).model_dump(mode="json")
                    ],
                },
            )
            assert response.status_code == 201
            cases.append(response.json()["id"])
        assert client.get(f"/api/cases/{cases[0]}/related").json()["links"] == []


def test_rounded_score_tie_is_indeterminate():
    _, card = evaluate(
        [tx(1, 0, 2, 100), tx(2, 0, 3, 100)],
        [label(2, "A", confidence=None), label(3, "B", confidence=None)],
    )
    component = card["counterfactuals"][0]
    assert component["rounding_indeterminate"]
    assert component["counterfactual_leading_vasp"] is None
    assert component["attribution_changed"] is None
    assert not component["became_unsupported"]
    assert "OBSERVED_PATH_EVIDENCED" not in card["evidence_coverage"]


def test_related_cases_and_no_identity_inference(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/links.db")
    with TestClient(app) as client:

        def create(target, intermediary, endpoint):
            outgoing = tx(1, target, intermediary, 100).model_dump(mode="json")
            terminal = tx(2, intermediary, endpoint, 100).model_dump(mode="json")
            response = client.post(
                "/api/cases",
                json={
                    "target": address(target),
                    "mode": "import",
                    "transactions": [outgoing, terminal],
                    "labels": [label(endpoint, "Exchange").model_dump(mode="json")],
                },
            )
            assert response.status_code == 201
            return response.json()["id"]

        a = create(0, 4, 8)
        b = create(1, 4, 8)
        c = create(2, 5, 9)
        links = client.get(f"/api/cases/{a}/related").json()
        assert {(x["case_id"], x["relationship"]) for x in links["links"]} == {
            (b, "shared intermediary address"),
            (b, "shared VASP endpoint"),
        }
        assert c not in {x["case_id"] for x in links["links"]}
        assert "no ownership" in links["meaning"]


def test_assessment_tamper_breaks_audit_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/tamper.db")
    with TestClient(app) as client:
        case = client.post("/api/cases", json={"target": DEMO_TARGET}).json()
        with Session(app.state.store.engine) as session, session.begin():
            row = session.get(CaseRecord, case["id"])
            payload = deepcopy(row.payload)
            payload["assessment"]["evidence_state"] = "SUPPORTED"
            row.payload = payload
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert not audit["valid"] and not audit["assessment_valid"]
        assert audit["evidence_valid"]
        assert client.get(f"/api/cases/{case['id']}").status_code == 409
        assert client.get(f"/api/cases/{case['id']}/evidence").status_code == 409
        assert client.get(f"/api/cases/{case['id']}/report").status_code == 409


def test_analysis_tamper_breaks_audit_and_related_links(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/analysis-tamper.db")
    with TestClient(app) as client:
        case = client.post("/api/cases", json={"target": DEMO_TARGET}).json()
        with Session(app.state.store.engine) as session, session.begin():
            row = session.get(CaseRecord, case["id"])
            payload = deepcopy(row.payload)
            payload["analysis"]["graph"]["nodes"].append(
                {"id": address(9999), "type": "wallet"}
            )
            row.payload = payload
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert not audit["valid"] and not audit["analysis_valid"]
        assert audit["evidence_valid"] and audit["assessment_valid"]
        assert client.get(f"/api/cases/{case['id']}/related").status_code == 409
        assert client.get(f"/api/cases/{case['id']}/report").status_code == 409


def test_rehashed_analysis_cannot_bypass_audit_anchor(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/rehashed.db")
    with TestClient(app) as client:
        case = client.post("/api/cases", json={"target": DEMO_TARGET}).json()
        with Session(app.state.store.engine) as session, session.begin():
            row = session.get(CaseRecord, case["id"])
            payload = deepcopy(row.payload)
            payload["analysis"]["model_version"] = "tampered"
            payload["analysis_digest"] = sha256(
                json.dumps(
                    payload["analysis"], sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            row.payload = payload
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert audit["analysis_valid"]
        assert not audit["assessment_anchor_valid"]
        assert not audit["valid"]


def test_live_api_rejects_missing_key_and_oversized_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/live-limit.db")
    with TestClient(app) as client:
        monkeypatch.setenv("GOLDRUSH_API_KEY", "")
        missing = client.post("/api/investigate", json={"target": address(0)})
        assert missing.status_code == 503
        monkeypatch.setenv("GOLDRUSH_API_KEY", "test-only")
        from app.goldrush import GoldRushProvider

        monkeypatch.setattr(
            GoldRushProvider,
            "fetch",
            lambda self, target, chain: ([tx(1, 0, 2, 1)] * 5001, []),
        )
        oversized = client.post("/api/investigate", json={"target": address(0)})
        assert oversized.status_code == 413
        assert "no events were silently discarded" in oversized.json()["detail"]


def test_empty_live_acquisition_audit_is_an_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/empty-live.db")
    monkeypatch.setenv("GOLDRUSH_API_KEY", "test-only")
    from app.goldrush import GoldRushProvider

    monkeypatch.setattr(GoldRushProvider, "fetch", lambda self, target, chain: ([], []))
    with TestClient(app) as client:
        response = client.post("/api/investigate", json={"target": address(0)})
        assert response.status_code == 201
        case = response.json()
        assert case["assessment"]["evidence_state"] == "INSUFFICIENT_EVIDENCE"
        audit = client.get(f"/api/cases/{case['id']}/audit").json()
        assert audit["valid"]
        assert audit["events"][1]["action"] == "live_acquisition_attempted"
