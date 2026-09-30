"""Local SAHYOG routing simulation; no external portal calls are made."""

import os
from math import isfinite
from uuid import uuid4

from pydantic import Field, field_validator

from .models import StrictModel

SIMULATION_NOTICE = "SIMULATED — No connection to the live SAHYOG Portal"
TRANSITIONS = {
    "prepared": {"sent"},
    "sent": {"acknowledged"},
    "acknowledged": {"info_requested", "complied", "refused"},
    "info_requested": {"complied", "refused"},
    "refused": {"escalated"},
    "complied": set(),
    "escalated": set(),
}


class RoutingPreparation(StrictModel):
    candidate_entity: str = Field(min_length=1, max_length=100)
    case_reference: str = Field(min_length=1, max_length=150)
    investigating_agency: str = Field(min_length=1, max_length=150)
    authorized_investigation: bool
    investigator_confirmed: bool

    @field_validator("case_reference", "investigating_agency")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class RoutingTransition(StrictModel):
    state: str = Field(
        pattern=r"^(sent|acknowledged|info_requested|complied|refused|escalated)$"
    )


def confidence_threshold():
    """Illustrative, configurable simulation rule; no legal meaning."""
    try:
        value = float(os.getenv("SAHYOG_SIMULATION_MIN_SCORE", "60"))
    except ValueError as exc:
        raise ValueError(
            "SAHYOG_SIMULATION_MIN_SCORE must be a number from 0 to 100"
        ) from exc
    if not isfinite(value) or not 0 <= value <= 100:
        raise ValueError("SAHYOG_SIMULATION_MIN_SCORE must be a number from 0 to 100")
    return value


def prepare(case, request: RoutingPreparation):
    analysis = case["analysis"]
    candidate = next(
        (c for c in analysis["candidates"] if c["entity"] == request.candidate_entity),
        None,
    )
    if candidate is None or not candidate.get("paths"):
        raise ValueError("No VASP attribution supported by available evidence.")
    threshold = confidence_threshold()
    if candidate["score"] < threshold:
        raise ValueError(
            f"Insufficient evidence for simulated routing: {candidate['score']}/100 is below the configured simulation threshold of {threshold:g}/100."
        )
    if not request.authorized_investigation:
        raise ValueError("Confirm that this forms part of an authorized investigation.")
    if not request.investigator_confirmed:
        raise ValueError(
            "Investigator confirmation is required before simulated preparation."
        )
    return {
        "reference": "SIM-SAHYOG-" + uuid4().hex[:12].upper(),
        "state": "prepared",
        "case_reference": request.case_reference,
        "investigating_agency": request.investigating_agency,
        "authorized_investigation": True,
        "investigator_confirmed": True,
        "candidate_entity": candidate["entity"],
        "candidate_score": candidate["score"],
        "candidate_hops": candidate["shortest_hops"],
        "simulation_threshold": threshold,
        "evidence_digest": case["evidence_digest"],
        "notice": SIMULATION_NOTICE,
        "legal_note": (
            "A Case/FIR reference and investigator confirmation are recorded for this "
            "simulation. BNSS Section 94 must be assessed in the case context; it does "
            "not automatically authorize freezing. No real request has been transmitted."
        ),
    }


def next_state(current, requested):
    if requested not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid simulated transition: {current} → {requested}.")
    return requested
