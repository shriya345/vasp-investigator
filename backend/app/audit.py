"""Content-addressed, append-only case event chain.

Hashing detects later changes within a supplied trail. It does not authenticate
external evidence, prevent database administrators from replacing a whole trail,
or establish legal admissibility.
"""

import json
from datetime import datetime, timezone
from hashlib import sha256


def canonical(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def make_event(
    case_id, action, evidence_digest, reference, previous_hash, timestamp=None
):
    body = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "action": action,
        "case_id": case_id,
        "evidence_digest": evidence_digest,
        "reference": reference,
        "previous_hash": previous_hash,
    }
    return {**body, "audit_hash": sha256(canonical(body).encode()).hexdigest()}


def verify(events, case_id=None, evidence_digest=None):
    previous = None
    for event in events:
        body = {key: value for key, value in event.items() if key != "audit_hash"}
        if case_id is not None and body.get("case_id") != case_id:
            return False
        if (
            evidence_digest is not None
            and body.get("evidence_digest") != evidence_digest
        ):
            return False
        if body.get("previous_hash") != previous:
            return False
        if sha256(canonical(body).encode()).hexdigest() != event.get("audit_hash"):
            return False
        previous = event["audit_hash"]
    return True
