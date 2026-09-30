"""Post-analysis, deterministic explanations; never changes engine output."""

import json
import os
from collections import defaultdict

from .engine import analyze
from .label_loader import DATA_DIR, LABEL_FILES
from .models import Label


def supported_path_threshold():
    """Configurable review heuristic, not a scientific or legal standard."""
    raw = os.getenv("ASSESSMENT_MIN_INDEPENDENT_PATHS", "2")
    if not raw.isdecimal() or not 1 <= int(raw) <= 10:
        raise ValueError(
            "ASSESSMENT_MIN_INDEPENDENT_PATHS must be an integer from 1 to 10"
        )
    return int(raw)


def source_assertions(chain, addresses):
    """Read original assertions, including records hidden by loader priority."""
    found = defaultdict(list)
    for name in LABEL_FILES.get(chain, []):
        path = DATA_DIR / name
        if not path.exists():
            continue
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for record in records:
            address = record.get("address", "").lower()
            if address not in addresses:
                continue
            try:
                assertion = Label(**{**record, "chain": chain.value}).model_dump(
                    mode="json"
                )
            except (ValueError, TypeError):
                continue
            found[address].append(assertion)
    return found


def _rank(candidates):
    return sorted(candidates, key=lambda c: (-c["score"], c["entity"]))


def _component_outcome(candidates, removed, leading):
    changed = []
    for candidate in candidates:
        points = sum(
            value["points"]
            for name, value in candidate["components"].items()
            if name != removed
        )
        changed.append(
            {
                "entity": candidate["entity"],
                "score": round(min(points, candidate["quality_cap"]), 1),
            }
        )
    ranked = _rank(changed)
    winner = ranked[0]
    # Six displayed components are rounded to 0.01 point each and the score
    # is rounded to 0.1. A margin <= 0.2 cannot support a unique ranking.
    close = len(ranked) > 1 and winner["score"] - ranked[1]["score"] <= 0.2
    return {
        "removed_component": removed,
        "original_leading_vasp": leading["entity"],
        "counterfactual_leading_vasp": None if close else winner["entity"],
        "original_score": leading["score"],
        "counterfactual_score": None if close else winner["score"],
        "attribution_changed": None if close else winner["entity"] != leading["entity"],
        "became_ambiguous": close,
        "became_unsupported": False,
        "rounding_indeterminate": close,
        "score_basis": "rounded_display_components",
    }


def assess(request, transactions, labels, analysis):
    candidates = analysis["candidates"]
    leading = candidates[0] if candidates else None
    nearest = analysis["nearest_vasp"]
    tx_count = len(transactions)
    endpoint_addresses = {address for c in candidates for address in c["addresses"]}
    assertions = (
        source_assertions(request.chain, endpoint_addresses)
        if request.mode == "live"
        else {}
    )
    # The imported evidence contract has one assertion per address. Demo labels
    # are synthetic, so only live curated/public source overlap is compared.
    conflicts = []
    for address, claims in sorted(assertions.items()):
        if len({claim["entity"] for claim in claims}) > 1:
            conflicts.append(
                {
                    "address": address,
                    "status": "UNRESOLVED_ENTITY_CONFLICT",
                    "assertions": [
                        {
                            "entity": c["entity"],
                            "source": c["source"],
                            "source_url": c["source_url"],
                        }
                        for c in claims
                    ],
                }
            )
    leading_conflict = bool(
        leading and set(leading["addresses"]) & {c["address"] for c in conflicts}
    )
    profiles = []
    if leading:
        for label in leading["labels"]:
            profiles.append(
                {
                    "address": label["address"],
                    "entity": label["entity"],
                    "source": label["source"],
                    "source_url": label.get("source_url"),
                    "provenance_type": (
                        "synthetic"
                        if label["synthetic"]
                        else (
                            "public"
                            if "Dataverse" in label["source"]
                            else "curated" if request.mode == "live" else "imported"
                        )
                    ),
                    "numeric_quality_known": label["confidence"] is not None,
                    "reliability_known": label["source_reliability"] is not None,
                    "observation_date_known": label["observed_at"] is not None,
                    "conflict_status": (
                        "UNRESOLVED_ENTITY_CONFLICT"
                        if label["address"] in {c["address"] for c in conflicts}
                        else "NONE_OBSERVED"
                    ),
                    "independent_corroboration_count": None,
                }
            )

    coverage = []
    if request.mode == "live":
        coverage.append("PARTIAL_PROVIDER_HISTORY")
    target_outgoing = [
        tx
        for tx in transactions
        if tx.from_address == request.target and tx.to_address != request.target
    ]
    if not tx_count or not target_outgoing:
        coverage.append("INSUFFICIENT_BLOCKCHAIN_EVIDENCE")
    if not candidates:
        coverage.append("NO_SUPPORTED_VASP_PATH")
    if len(candidates) > 1:
        coverage.append("MULTIPLE_COMPETING_VASPS")
    if leading and any(
        not p["numeric_quality_known"] or not p["reliability_known"] for p in profiles
    ):
        coverage.append("LIMITED_LABEL_QUALITY_METADATA")
    if conflicts:
        coverage.append("UNRESOLVED_LABEL_CONFLICT")
    if leading and any(not p["source_url"] for p in profiles):
        coverage.append("LIMITED_LABEL_PROVENANCE")
    if not coverage:
        coverage.append("OBSERVED_PATH_EVIDENCED")

    supporting, competing, limitations = [], [], []
    if leading:
        supporting.append(
            f"Observed transaction path reaches a supplied {leading['entity']} endpoint label at {leading['shortest_hops']} hop(s)."
        )
        supporting.append(
            f"{leading['path_count']} supported path(s); {leading['independent_paths']} transaction-edge-disjoint path(s)."
        )
        if leading["traced_usd"] > 0:
            supporting.append(
                f"Modelled valued exposure: ${leading['traced_usd']:,.2f}; {leading['value_share']}% of valued target outflow."
            )
        for candidate in candidates[1:]:
            competing.append(
                f"{candidate['entity']}: {candidate['shortest_hops']} hop(s), {candidate['path_count']} supported path(s)."
            )
    if request.mode == "live":
        limitations.append(
            "GoldRush acquisition is bounded to at most five recent pages; complete history is not established."
        )
    if leading and any(not p["numeric_quality_known"] for p in profiles):
        limitations.append(
            "At least one endpoint label has no numeric confidence value; a zero engine score does not mean the label is absent."
        )
    if leading and any(not p["reliability_known"] for p in profiles):
        limitations.append(
            "At least one endpoint label has no numeric source-reliability value."
        )
    if leading and any(not p["source_url"] for p in profiles):
        limitations.append(
            "At least one endpoint label has no source URL for independent review."
        )
    if conflicts:
        limitations.append(
            "Sources disagree on a service endpoint; unique attribution from that endpoint is unresolved."
        )
    if leading and leading["independent_paths"] < supported_path_threshold():
        limitations.append(
            "Fewer independently edge-disjoint paths than the configured review heuristic; this is not an evidentiary standard."
        )
    if not target_outgoing:
        state = "INSUFFICIENT_EVIDENCE"
    elif not leading:
        state = "NO_VASP_SUPPORTED"
    elif leading_conflict or len(candidates) > 1:
        state = "AMBIGUOUS"
    elif limitations:
        state = "SUPPORTED_WITH_LIMITATIONS"
    else:
        state = "SUPPORTED"

    counterfactuals = []
    if leading:
        # Replay the existing score's published component points and quality cap.
        # This is a bounded sensitivity calculation, not a new attribution model.
        for component in leading["components"]:
            counterfactuals.append(_component_outcome(candidates, component, leading))
        filtered = [
            label for label in labels if label.address not in set(leading["addresses"])
        ]
        alternate = analyze(
            request.model_copy(update={"labels": filtered}), transactions, filtered
        )
        winner = alternate["highest_confidence_vasp"]
        counterfactuals.append(
            {
                "removed_component": "leading_endpoint_service_intelligence",
                "original_leading_vasp": leading["entity"],
                "counterfactual_leading_vasp": winner["entity"] if winner else None,
                "original_score": leading["score"],
                "counterfactual_score": winner["score"] if winner else None,
                "attribution_changed": winner is None
                or winner["entity"] != leading["entity"],
                "became_ambiguous": len(alternate["candidates"]) > 1
                and alternate["candidates"][0]["score"]
                == alternate["candidates"][1]["score"],
                "became_unsupported": winner is None,
                "rounding_indeterminate": False,
                "score_basis": "engine_reanalysis",
            }
        )
    retained = sum(
        c["attribution_changed"] is False and not c["became_ambiguous"]
        for c in counterfactuals
    )
    stability = {
        "retained": retained,
        "applicable": len(counterfactuals),
        "ratio": f"{retained}/{len(counterfactuals)}" if counterfactuals else None,
    }

    actions = []

    def action(priority, code, recommendation, reason):
        actions.append(
            {
                "priority": priority,
                "code": code,
                "recommendation": recommendation,
                "reason": reason,
            }
        )

    if conflicts:
        action(
            1,
            "RESOLVE_LABEL_CONFLICT",
            "Resolve conflicting service-label assertions.",
            "A disputed endpoint cannot support a unique entity conclusion on its own.",
        )
    if len(candidates) > 1:
        action(
            2,
            "DISTINGUISH_CANDIDATES",
            "Investigate the transaction paths to competing VASP endpoints.",
            "More path evidence could distinguish the observed candidates.",
        )
    if request.mode == "live":
        action(
            3,
            "EXPAND_PROVIDER_HISTORY",
            "Expand or retry blockchain-history acquisition.",
            "Current GoldRush acquisition is bounded; older transfers may be absent.",
        )
    if target_outgoing and not candidates:
        labelled = {label.address for label in labels}
        unknown_transfers = [
            tx for tx in target_outgoing if tx.to_address not in labelled
        ]
        unknown_transfers.sort(key=lambda tx: (-(tx.usd_value or 0), tx.to_address))
        unknown = unknown_transfers[0].to_address if unknown_transfers else None
        if unknown:
            action(
                2,
                "RESOLVE_SERVICE_ADDRESS",
                f"Check service intelligence for {unknown}.",
                "The target sent an observed transfer to this unlabeled address; its service role is unknown.",
            )
    if not target_outgoing:
        reason = (
            "No transfers were supplied or normalized."
            if not tx_count
            else "No outgoing transfer from the target is present in the supplied evidence."
        )
        action(
            4,
            "ACQUIRE_BLOCKCHAIN_EVIDENCE",
            "Acquire outgoing transaction evidence for the target.",
            reason,
        )
    if state in {"SUPPORTED", "SUPPORTED_WITH_LIMITATIONS"}:
        action(
            5,
            "REVIEW_SIMULATED_ROUTING",
            "Review the existing SIMULATED lawful-request workflow if an authorized basis is available.",
            "A supported candidate can be considered for further review; no request is sent.",
        )
    actions.sort(key=lambda a: (a["priority"], a["code"]))
    if leading_conflict:
        summary = f"The existing ranking places {leading['entity']} first, but conflicting endpoint labels prevent unique entity attribution. "
    elif leading:
        summary = f"Observed paths support {leading['entity']} as the existing top-ranked VASP candidate. "
    elif state == "INSUFFICIENT_EVIDENCE":
        summary = "Insufficient target-outgoing blockchain evidence to assess VASP attribution. "
    else:
        summary = "No VASP attribution supported by available evidence. "
    summary += f"Evidence state: {state}. "
    if stability["ratio"]:
        summary += f"{stability['ratio']} evidence-removal tests retained the leading candidate without a score tie. "
    if actions:
        summary += f"Next investigative step: {actions[0]['recommendation']}"
    return {
        "leading_vasp": leading["entity"] if leading else None,
        "nearest_vasp": nearest["entity"] if nearest else None,
        "evidence_state": state,
        "evidence_coverage": coverage,
        "supporting_evidence": supporting,
        "competing_evidence": competing,
        "limitations": limitations,
        "label_profile": profiles,
        "intelligence_conflicts": conflicts,
        "counterfactuals": counterfactuals,
        "stability": stability,
        "next_actions": actions,
        "investigator_summary": summary,
    }
