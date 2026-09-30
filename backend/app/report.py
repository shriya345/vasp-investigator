"""Reports are rendered exclusively from stored structured evidence."""

from datetime import datetime, timezone


def report(case, routing=None, audit=None):
    a = case["analysis"]
    m = a["metrics"]
    transactions_by_id = {
        transaction["id"]: transaction for transaction in a["transactions"]
    }
    nearest = a.get("nearest_vasp")
    highest = a.get("highest_confidence_vasp")
    if nearest is None and a.get("candidates"):
        nearest = min(
            a["candidates"],
            key=lambda c: (c["shortest_hops"], -c["score"], c["entity"]),
        )
    if highest is None and a.get("candidates"):
        highest = a["candidates"][0]
    lines = [
        f"# Investigation {case['id']}",
        "",
        case["title"],
        "",
        f"- Evidence mode: {a['mode'].upper()}",
        f"- Case/FIR reference: {routing['case_reference'] if routing else 'Not recorded'}",
        f"- Investigating agency: {routing['investigating_agency'] if routing else 'Not recorded'}",
        f"- Report generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Target: {a['target']}",
        f"- Network: {a['chain']}",
        f"- Created: {case['created_at']}",
        f"- Evidence digest (SHA-256): {case['evidence_digest']}",
        f"- Model version: {a['model_version']}",
        f"- Period: {a['period']['start']} to {a['period']['end']}",
        "",
        "## Fund flow",
        f"Gross outgoing valued transfers: ${m['outgoing_usd']:,.2f}.",
        f"Modelled value reaching VASP endpoints: ${m['attributed_usd']:,.2f}.",
        f"Unresolved or boundary-stopped value: ${m['unresolved_usd']:,.2f}.",
        f"Valuation coverage: {m['valuation_coverage']}% of outgoing transfers.",
        f"Graph: {len(a['graph']['nodes'])} nodes; {len(a['graph']['edges'])} transfers; tracing limit {a['max_hops']} hops.",
        "",
        "## Ranked VASP candidates",
        f"Nearest VASP: {nearest['entity']} — {nearest['shortest_hops']} hops; {nearest['score']}/100 confidence."
        if nearest
        else "Nearest VASP: none supported.",
        f"Highest-confidence VASP: {highest['entity']} — {highest['shortest_hops']} hops; {highest['score']}/100 confidence."
        if highest
        else "Highest-confidence VASP: none supported.",
        a.get(
            "attribution_result",
            "No VASP attribution supported by available evidence."
            if not a["candidates"]
            else "Evidence-supported VASP candidates found.",
        ),
    ]
    for c in a["candidates"]:
        lines += [
            f"### {c['entity']} — {c['score']}/100 attribution confidence",
            f"Modelled exposure: ${c['traced_usd']:,.2f} ({c['value_share']}% of valued gross outflow).",
            f"Supporting paths: {c['path_count']}; edge-disjoint support: {c['independent_paths']}; shortest/median distance: {c['shortest_hops']}/{c['median_hops']} hops.",
            f"Evidence quality cap: {c['quality_cap']}/100.",
        ]
        lines += [
            f"- {k}: {v['value']}/100 × {v['weight']} = {v['points']} points"
            for k, v in c["components"].items()
        ]
        lines += [
            f"- Label inference: {label['address']} → {label['entity']} ({label['entity_type']}, {label['chain']}); {label['strength']}; confidence {label['confidence']}; source reliability {label['source_reliability']}; source: {label['source']}; URL: {label.get('source_url') or 'Not supplied'}; observed {label['observed_at']}; FIU-IND: {('registered' if label.get('fiu_registered') else 'unregistered') if label.get('fiu_registered') is not None else 'unknown — requires manual verification'}"
            for label in c["labels"]
        ]
        for path in c["paths"]:
            transfers = [
                transactions_by_id[event_id]
                for event_id in path
                if event_id in transactions_by_id
            ]
            address_path = " → ".join(
                [a["target"]] + [transfer["to_address"] for transfer in transfers]
            )
            lines += [
                f"- Supporting address path: {address_path}",
                f"  Transaction evidence: {' → '.join(path)}",
            ]
    if not a["candidates"]:
        lines += ["No VASP attribution supported by available evidence."]
    lines += ["", f"## Risk indicators — {a['risk']['score']}/100"]
    for r in a["risk"]["factors"]:
        lines += [
            f"- {r['name']} (+{r['points']}): {r['explanation']}",
            f"  Evidence: {', '.join(r['evidence_ids'])}",
        ]
    lines += [
        "",
        "## SAHYOG-ready routing simulation",
        "SIMULATED — No connection to the live SAHYOG Portal",
    ]
    if routing:
        lines += [
            f"Simulation reference: {routing['reference']}; state: {routing['state']}.",
            f"Candidate: {routing['candidate_entity']}; confidence {routing['candidate_score']}/100; simulation threshold {routing['simulation_threshold']}/100.",
            routing["legal_note"],
        ]
    else:
        lines += ["No simulated routing request prepared."]
    lines += ["", "## Suggested routing"]
    if a["mode"] == "demo":
        lines += [
            "Demonstration only. Do not send any disclosure or freezing request based on synthetic evidence."
        ]
    elif a["candidates"]:
        lines += [
            f"Review {a['candidates'][0]['entity']} as the first potential service contact. Independently validate labels, evidence and the appropriate authorized contact before considering a request. No request has been generated or sent."
        ]
    else:
        lines += ["Insufficient evidence to suggest a VASP contact."]
    lines += [
        "",
        "## Evidence integrity and chain of custody",
        f"Evidence digest (SHA-256): {case['evidence_digest']}.",
    ]
    if audit and audit["events"]:
        lines += [
            f"Audit chain verification: {'valid' if audit.get('chain_valid', audit['valid']) else 'FAILED'}; evidence digest comparison: {'valid' if audit.get('evidence_valid', True) else 'FAILED'}; head hash: {audit['head_hash']}."
        ]
        lines += [
            f"- {event['timestamp']} | {event['action']} | previous {event['previous_hash'] or 'GENESIS'} | hash {event['audit_hash']} | reference {event['reference'] or 'none'}"
            for event in audit["events"]
        ]
    else:
        lines += ["No audit events recorded for this case."]
    if not case.get("audit_initialized", False):
        lines += [
            "This case predates the audit trail. Earlier events were not backfilled."
        ]
    lines += [
        "Hash chaining supports tamper-evident integrity checks; it does not establish legal admissibility or authenticate external evidence."
    ]
    lines += ["", "## Transaction evidence"]
    for t in a["transactions"]:
        lines += [
            f"- {t['id']} | {t['timestamp']} | {t['from_address']} → {t['to_address']} | {t['amount']} {t['asset']} | block {t['block_number']} | source: {t['source']}"
        ]
    lines += ["", "## Limitations and uncertainty"] + [
        f"- {s}" for s in a["limitations"]
    ]
    lines += [
        "- Attribution represents an evidence-supported association and does not independently establish wallet ownership or criminal liability."
    ]
    return "\n".join(lines) + "\n"
