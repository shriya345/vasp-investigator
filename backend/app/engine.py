"""Deterministic temporal tracing with conserved per-asset lots and explicit boundaries."""

from collections import defaultdict
from decimal import Decimal, localcontext
from math import log2
from statistics import median

import networkx as nx

from .models import InvestigationRequest

VERSION = "0.1.0"
MAX_TRACE_OPERATIONS = 100_000


class TraceBudgetExceeded(ValueError):
    pass


WEIGHTS = {
    "proximity": 0.25,
    "interaction": 0.25,
    "independent_paths": 0.15,
    "recency": 0.15,
    "label_quality": 0.10,
    "cluster_support": 0.10,
}
BOUNDARIES = {"vasp", "exchange", "mixer", "bridge", "dex"}
LIMITATIONS = [
    "Attribution scores are uncalibrated evidence scores, not ownership probabilities. No real-world owner is identified.",
    "Tracing uses proportional allocation of observed same-asset balances. Unknown opening balances, missing transfers and off-chain activity can change results.",
    "Tracing stops at VASPs, mixers, bridges and DEXs. No claim is made about cross-chain movement, swaps or activity beyond these boundaries.",
    "USD exposure uses origin-transfer valuations supplied in the evidence. Missing valuations are excluded, not treated as zero-valued evidence.",
    "Independent support is a conservative greedy count of transaction-edge-disjoint paths, not proof of independent ownership.",
    "Labels are supplied assertions with provenance, not independently verified by this prototype. Risk signals do not establish wrongdoing.",
    "The denominator is gross target outgoing value in the supplied period; it is not wallet balance or distinct capital. Fees are excluded.",
]


def analyze(request: InvestigationRequest, transactions, labels):
    with localcontext() as context:
        context.prec = 96
        return _analyze(request, transactions, labels)


def _analyze(request: InvestigationRequest, transactions, labels):
    target = request.target
    txs = sorted(
        transactions,
        key=lambda t: (
            t.timestamp,
            t.block_number,
            t.transaction_index,
            t.event_index,
            t.tx_hash,
        ),
    )
    label_map = {label.address: label for label in labels}
    graph = nx.MultiDiGraph()
    graph.add_node(target)
    for t in txs:
        graph.add_edge(t.from_address, t.to_address, key=t.evidence_id)
    distances = dict(
        nx.single_source_shortest_path_length(graph, target, cutoff=request.max_hops)
    )
    visible = set(distances) | {t.from_address for t in txs if t.to_address == target}
    relevant = [t for t in txs if t.from_address in visible and t.to_address in visible]
    inventory = defaultdict(list)
    arrivals = defaultdict(list)
    outgoing = [t for t in txs if t.from_address == target and t.to_address != target]
    incoming = [t for t in txs if t.to_address == target and t.from_address != target]
    denominator = sum((t.usd_value or Decimal(0) for t in outgoing), Decimal(0))
    seed_count = len(outgoing)
    # A lot's origin USD value follows its token quantity; downstream spot prices never inflate it.
    operations = 0
    for t in txs:
        if t.from_address == t.to_address:
            continue
        key = (t.from_address, t.asset_key)
        if t.from_address == target:
            portions = [
                {
                    "amount": t.amount,
                    "usd": t.usd_value,
                    "path": [],
                    "addresses": [target],
                    "confidence": t.source_confidence,
                }
            ]
        else:
            lots = inventory[key]
            total = sum((lot["amount"] for lot in lots), Decimal(0))
            ratio = min(Decimal(1), t.amount / total) if total else Decimal(0)
            portions = []
            for lot in lots:
                operations += 1
                if operations > MAX_TRACE_OPERATIONS:
                    raise TraceBudgetExceeded(
                        "Trace complexity limit reached. Import a smaller time window or reduce hop depth."
                    )
                used = lot["amount"] * ratio
                if used <= 0:
                    continue
                portions.append(
                    {
                        **lot,
                        "amount": used,
                        "usd": lot["usd"] * ratio if lot["usd"] is not None else None,
                    }
                )
                lot["amount"] -= used
                if lot["usd"] is not None:
                    lot["usd"] *= 1 - ratio
            inventory[key] = [lot for lot in lots if lot["amount"] > 0]
            if total < t.amount:
                portions.append(
                    {
                        "amount": t.amount - total,
                        "usd": None,
                        "path": None,
                        "addresses": [],
                        "confidence": t.source_confidence,
                    }
                )
        for lot in portions:
            if lot["path"] is None:
                inventory[(t.to_address, t.asset_key)].append(lot)
                continue
            path = lot["path"] + [t.evidence_id]
            if len(path) > request.max_hops or t.to_address in lot["addresses"]:
                # Consumed but no longer traceable; keep the untracked quantity for dilution.
                inventory[(t.to_address, t.asset_key)].append(
                    {**lot, "path": None, "usd": None}
                )
                continue
            moved = {
                **lot,
                "path": path,
                "addresses": lot["addresses"] + [t.to_address],
                "confidence": min(lot["confidence"], t.source_confidence),
                "timestamp": t.timestamp.isoformat(),
                "asset": t.asset,
                "asset_key": t.asset_key,
            }
            label = label_map.get(t.to_address)
            if label and label.entity_type in BOUNDARIES:
                arrivals[t.to_address].append(moved)
                inventory[(t.to_address, t.asset_key)].append(
                    {**moved, "path": None, "usd": None}
                )
            else:
                inventory[(t.to_address, t.asset_key)].append(moved)
                if label:
                    arrivals[t.to_address].append(moved)
    grouped = defaultdict(list)
    for address, lots in arrivals.items():
        label = label_map[address]
        if label.entity_type in {"vasp", "exchange"}:
            grouped[label.entity].extend((address, lot) for lot in lots)
    reference = max((t.timestamp for t in txs), default=None)
    candidates = []
    for entity, records in grouped.items():
        paths = sorted(
            {tuple(lot["path"]) for _, lot in records}, key=lambda p: (len(p), p)
        )
        used_edges, independent = set(), 0
        for path in paths:
            if not used_edges.intersection(path):
                independent += 1
                used_edges.update(path)
        addresses = sorted({a for a, _ in records})
        value = sum((lot["usd"] or Decimal(0) for _, lot in records), Decimal(0))
        share = float(value / denominator) if denominator else 0
        hops = [len(p) for p in paths]
        terminal_ids = {p[-1] for p in paths}
        last = max(t.timestamp for t in txs if t.evidence_id in terminal_ids)
        age = (reference - last).total_seconds() / 86400 if reference else 0
        quality = min(
            label_map[a].confidence * label_map[a].source_reliability for a in addresses
        )
        quality *= min(lot["confidence"] for _, lot in records)
        components = {
            "proximity": 1 / min(hops),
            "interaction": min(1, share),
            "independent_paths": min(1, independent / 3),
            "recency": 1 / (1 + age / 30),
            "label_quality": quality,
            "cluster_support": min(1, len(addresses) / 3),
        }
        # Evidence quality caps the entire score; weak labels cannot be masked by volume.
        raw = sum(WEIGHTS[k] * v for k, v in components.items()) * 100
        score = round(min(raw, quality * 100), 1)
        candidates.append(
            {
                "entity": entity,
                "score": score,
                "traced_usd": float(value),
                "value_share": round(share * 100, 2),
                "shortest_hops": min(hops),
                "median_hops": median(hops),
                "independent_paths": independent,
                "path_count": len(paths),
                "interaction_count": len(terminal_ids),
                "addresses": addresses,
                "paths": [list(p) for p in paths],
                "last_seen": last.isoformat(),
                "components": {
                    k: {
                        "value": round(v * 100, 2),
                        "weight": WEIGHTS[k],
                        "points": round(v * WEIGHTS[k] * 100, 2),
                    }
                    for k, v in components.items()
                },
                "quality_cap": round(quality * 100, 2),
                "labels": [label_map[a].model_dump(mode="json") for a in addresses],
            }
        )
    candidates.sort(key=lambda c: (-c["score"], c["entity"]))
    # Only temporal, evidence-supported candidate paths reach this list. Keep the
    # existing scoring and order; proximity is a separate question.
    highest_confidence = candidates[0] if candidates else None
    nearest = (
        min(candidates, key=lambda c: (c["shortest_hops"], -c["score"], c["entity"]))
        if candidates
        else None
    )
    risks = []
    for kind, title, points in [
        ("mixer", "Mixer exposure detected", 25),
        ("bridge", "Bridge interaction detected", 10),
        ("scam", "Labelled scam counterparty exposure", 25),
        ("sanctioned", "Sanctions-labelled counterparty exposure", 30),
    ]:
        evidence = sorted(
            {
                lot["path"][-1]
                for a, lots in arrivals.items()
                if label_map[a].entity_type == kind
                for lot in lots
            }
        )
        if evidence:
            risks.append(
                {
                    "name": title,
                    "points": points,
                    "evidence_ids": evidence,
                    "explanation": "A time-ordered traced path reaches a supplied label. Validate the label and context.",
                }
            )
    by_id = {t.evidence_id: t for t in txs}
    rapid = sorted(
        {
            p
            for lots in arrivals.values()
            for lot in lots
            for p in [tuple(lot["path"])]
            if len(p) >= 3
            and (by_id[p[-1]].timestamp - by_id[p[0]].timestamp).total_seconds() <= 1800
        }
    )
    if rapid:
        risks.append(
            {
                "name": "Potential rapid layering pattern",
                "points": 20,
                "evidence_ids": sorted({e for p in rapid for e in p}),
                "explanation": "At least three chronological hops occurred within 30 minutes. This pattern alone does not establish laundering.",
            }
        )
    big = [
        t.evidence_id
        for t in outgoing
        if t.usd_value is not None and t.usd_value >= 10000
    ]
    if big:
        risks.append(
            {
                "name": "Large-value outgoing transfer",
                "points": 10,
                "evidence_ids": big,
                "explanation": "An outgoing transfer meets the illustrative $10,000 review threshold; this is not a legal reporting threshold.",
            }
        )
    vals = [float(t.usd_value) for t in outgoing if t.usd_value is not None]
    in_usd = sum(float(t.usd_value) for t in incoming if t.usd_value is not None)
    target_txs = incoming + outgoing
    duration = (
        (
            max(t.timestamp for t in target_txs) - min(t.timestamp for t in target_txs)
        ).total_seconds()
        / 3600
        if target_txs
        else 0
    )
    shares = (
        [c["traced_usd"] / float(denominator) for c in candidates]
        if denominator
        else []
    )
    unresolved = max(0, 1 - sum(shares)) if denominator else 0
    buckets = shares + ([unresolved] if unresolved else [])
    nodes = [
        {
            "id": a,
            "label": label_map[a].entity
            if a in label_map
            else ("Target wallet" if a == target else "Unlabelled wallet"),
            "type": "target"
            if a == target
            else (label_map[a].entity_type if a in label_map else "wallet"),
            "hop": distances.get(a, -1),
            "metadata": label_map[a].model_dump(mode="json")
            if a in label_map
            else None,
            "in_degree": graph.in_degree(a),
            "out_degree": graph.out_degree(a),
        }
        for a in sorted(visible)
    ]
    serialized = [
        {
            **t.model_dump(mode="json"),
            "id": t.evidence_id,
            "direction": "outgoing"
            if t.from_address == target
            else ("incoming" if t.to_address == target else "downstream"),
        }
        for t in relevant
    ]
    return {
        "model_version": VERSION,
        "target": target,
        "chain": request.chain.value,
        "mode": request.mode,
        "max_hops": request.max_hops,
        "period": {
            "start": txs[0].timestamp.isoformat() if txs else None,
            "end": txs[-1].timestamp.isoformat() if txs else None,
        },
        "graph": {
            "nodes": nodes,
            "edges": serialized,
            "connected_components": nx.number_weakly_connected_components(graph),
        },
        "transactions": serialized,
        "candidates": candidates,
        "nearest_vasp": nearest,
        "highest_confidence_vasp": highest_confidence,
        "attribution_result": (
            "Evidence-supported VASP candidates found."
            if candidates
            else "No VASP attribution supported by available evidence."
        ),
        "risk": {"score": min(100, sum(r["points"] for r in risks)), "factors": risks},
        "metrics": {
            "incoming_usd": in_usd,
            "outgoing_usd": float(denominator),
            "net_usd": in_usd - float(denominator),
            "target_transaction_count": len(target_txs),
            "evidence_transaction_count": len(txs),
            "counterparties": len(
                {t.from_address for t in incoming} | {t.to_address for t in outgoing}
            ),
            "median_outgoing_usd": median(vals) if vals else None,
            "max_outgoing_usd": max(vals) if vals else None,
            "transactions_per_hour": round(len(target_txs) / duration, 2)
            if duration
            else None,
            "valuation_coverage": round(len(vals) / seed_count * 100, 1)
            if seed_count
            else None,
            "attributed_usd": sum(c["traced_usd"] for c in candidates),
            "unresolved_usd": max(
                0, float(denominator) - sum(c["traced_usd"] for c in candidates)
            ),
            "exposure_hhi": round(sum(s * s for s in buckets), 4) if buckets else None,
            "exposure_entropy": round(-sum(s * log2(s) for s in buckets if s > 0), 4)
            if buckets
            else None,
        },
        "limitations": LIMITATIONS
        + (
            [
                "All addresses, labels and transfers in this case are synthetic demo evidence."
            ]
            if request.mode == "demo"
            else []
        ),
        "coverage": {
            "live_ingestion": False,
            "complete_history": False,
            "trace_boundary": "First labelled service endpoint",
            "ordering": "timestamp, block number, transaction index, event index, hash",
        },
    }
