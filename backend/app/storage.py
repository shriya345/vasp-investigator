"""Case, simulation and audit storage with transactional event appends."""

import os
import json
from hashlib import sha256

from sqlalchemy import JSON, Column, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import Session, declarative_base

from .audit import make_event, verify

Base = declarative_base()


class CaseRecord(Base):
    __tablename__ = "cases"
    id = Column(String(40), primary_key=True)
    created_at = Column(String(40), nullable=False, index=True)
    payload = Column(JSON, nullable=False)


class RoutingRecord(Base):
    __tablename__ = "simulated_routing"
    case_id = Column(String(40), ForeignKey("cases.id"), primary_key=True)
    payload = Column(JSON, nullable=False)


class AuditRecord(Base):
    __tablename__ = "case_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(40), ForeignKey("cases.id"), nullable=False, index=True)
    payload = Column(JSON, nullable=False)


class CaseStore:
    def __init__(self, url=None):
        url = url or os.getenv("DATABASE_URL", "sqlite:///./investigations.db")
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False}
            if url.startswith("sqlite")
            else {},
        )
        Base.metadata.create_all(self.engine)

    def _append(self, session, case_id, action, digest, reference=None):
        case = session.get(CaseRecord, case_id)
        actual_digest = sha256(
            json.dumps(
                case.payload["evidence"], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if actual_digest != digest or case.payload["evidence_digest"] != digest:
            raise ValueError("Evidence digest verification failed; append blocked.")
        existing = session.scalars(
            select(AuditRecord)
            .where(AuditRecord.case_id == case_id)
            .order_by(AuditRecord.id)
        ).all()
        if not verify([record.payload for record in existing], case_id, digest):
            raise ValueError("Audit hash chain verification failed; append blocked.")
        previous = existing[-1] if existing else None
        event = make_event(
            case_id,
            action,
            digest,
            reference,
            previous.payload["audit_hash"] if previous else None,
        )
        session.add(AuditRecord(case_id=case_id, payload=event))
        session.flush()
        return event

    def save(self, case, *, live=False):
        with Session(self.engine) as session, session.begin():
            session.add(
                CaseRecord(id=case["id"], created_at=case["created_at"], payload=case)
            )
            session.flush()
            self._append(session, case["id"], "case_created", case["evidence_digest"])
            if live:
                self._append(
                    session,
                    case["id"],
                    "live_evidence_retrieved",
                    case["evidence_digest"],
                )
            self._append(
                session, case["id"], "analysis_executed", case["evidence_digest"]
            )

    def get(self, case_id):
        with Session(self.engine) as session:
            record = session.get(CaseRecord, case_id)
            return record.payload if record else None

    def list(self):
        with Session(self.engine) as session:
            records = session.scalars(
                select(CaseRecord).order_by(CaseRecord.created_at.desc()).limit(100)
            )
            return [
                {
                    "id": r.id,
                    "title": r.payload["title"],
                    "created_at": r.created_at,
                    "target": r.payload["analysis"]["target"],
                    "chain": r.payload["analysis"]["chain"],
                    "mode": r.payload["analysis"]["mode"],
                }
                for r in records
            ]

    def audit(self, case_id):
        with Session(self.engine) as session:
            case = session.get(CaseRecord, case_id)
            events = session.scalars(
                select(AuditRecord)
                .where(AuditRecord.case_id == case_id)
                .order_by(AuditRecord.id)
            ).all()
            data = [event.payload for event in events]
            chain_valid = verify(data, case_id, case.payload["evidence_digest"])
            calculated_digest = sha256(
                json.dumps(
                    case.payload["evidence"], sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            evidence_valid = calculated_digest == case.payload["evidence_digest"]
            return {
                "events": data,
                "valid": chain_valid and evidence_valid,
                "chain_valid": chain_valid,
                "evidence_valid": evidence_valid,
                "head_hash": data[-1]["audit_hash"] if data else None,
                "historical_events_unavailable": not data,
            }

    def routing(self, case_id):
        with Session(self.engine) as session:
            row = session.get(RoutingRecord, case_id)
            return row.payload if row else None

    def prepare_routing(self, case, routing):
        with Session(self.engine) as session, session.begin():
            # Lock the case row on PostgreSQL so state and audit append are ordered.
            row = session.execute(
                select(CaseRecord).where(CaseRecord.id == case["id"]).with_for_update()
            ).scalar_one()
            if session.get(RoutingRecord, case["id"]):
                raise ValueError(
                    "A simulated routing request already exists for this case."
                )
            session.add(RoutingRecord(case_id=case["id"], payload=routing))
            session.flush()
            self._append(
                session,
                case["id"],
                "routing_reviewed",
                row.payload["evidence_digest"],
                routing["reference"],
            )
            self._append(
                session,
                case["id"],
                "routing_prepared",
                row.payload["evidence_digest"],
                routing["reference"],
            )
            return routing

    def transition_routing(self, case_id, new_state):
        from .routing import next_state

        with Session(self.engine) as session, session.begin():
            case = session.execute(
                select(CaseRecord).where(CaseRecord.id == case_id).with_for_update()
            ).scalar_one_or_none()
            if case is None:
                raise KeyError("Case not found")
            row = session.get(RoutingRecord, case_id)
            if row is None:
                raise ValueError("Prepare simulated routing before changing its state.")
            next_state(row.payload["state"], new_state)
            payload = {**row.payload, "state": new_state}
            row.payload = payload
            self._append(
                session,
                case_id,
                "routing_state_" + new_state,
                case.payload["evidence_digest"],
                payload["reference"],
            )
            return payload

    def record_report(self, case_id, *, exported=False):
        with Session(self.engine) as session, session.begin():
            case = session.execute(
                select(CaseRecord).where(CaseRecord.id == case_id).with_for_update()
            ).scalar_one()
            return self._append(
                session,
                case_id,
                "report_exported" if exported else "report_generated",
                case.payload["evidence_digest"],
            )
