"""Run the unchanged production ingestion and analysis pipeline on real cases."""

import csv
import hashlib
import json
import math
import subprocess
from collections import Counter
from datetime import datetime, timezone
from statistics import median
from time import perf_counter

from build_real_cases import endpoints
from common import CACHE, HERE, REFERENCE, SEED, SOURCE, CachedGoldRush, dataset_hash

from app.engine import VERSION, analyze
from app.goldrush import GoldRushProvider
from app.label_loader import load_labels
from app.models import Chain, InvestigationRequest

FIELDS = [
    "case_id",
    "source_wallet",
    "expected_vasp",
    "expected_endpoint",
    "expected_hops",
    "predicted_nearest_vasp",
    "predicted_highest_confidence_vasp",
    "top_candidates",
    "predicted_hops",
    "attribution_score",
    "no_attribution_result",
    "correct_top1",
    "correct_top3",
    "nearest_correct",
    "hop_error",
    "direct_hop_correct",
    "internal_label_overlap",
    "label_stratum",
    "retrieval_status",
    "analysis_status",
    "evaluation_status",
    "failure_reason",
    "exclusion_reason",
    "expected_transfer_observed",
    "engine_latency_ms",
    "end_to_end_latency_ms",
    "ground_truth_dataset",
    "ground_truth_source",
    "ground_truth_reference",
    "ground_truth_service_url",
    "transaction_hash",
    "actual_api_calls",
    "cache_hits",
]


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return round(values[low] + (values[high] - values[low]) * (position - low), 3)


def rate(rows, field):
    values = [r[field] for r in rows if r[field] is not None]
    return {
        "value": round(sum(values) / len(values), 4) if values else None,
        "numerator": sum(values),
        "denominator": len(values),
    }


def group_metrics(rows):
    evaluated = [
        r for r in rows if r["evaluation_status"] in {"evaluable", "evaluable_partial"}
    ]
    timings = [
        r["engine_latency_ms"] for r in rows if r["engine_latency_ms"] is not None
    ]
    end_to_end = [
        r["end_to_end_latency_ms"]
        for r in rows
        if r["end_to_end_latency_ms"] is not None and r["cache_hits"] == 0
    ]
    hops = [r["hop_error"] for r in evaluated if r["hop_error"] is not None]
    nearest = [r for r in evaluated if r["nearest_correct"] is not None]
    return {
        "attempted": len(rows),
        "retrieval_success": rate(
            [{"ok": int(r["expected_transfer_observed"] == 1)} for r in rows], "ok"
        ),
        "complete_retrieval": rate(
            [{"ok": int(r["retrieval_status"] == "complete")} for r in rows], "ok"
        ),
        "evaluable": len(evaluated),
        "top1": rate(evaluated, "correct_top1"),
        "top3": rate(evaluated, "correct_top3"),
        "nearest": rate(nearest, "nearest_correct"),
        "hop_mae": {
            "value": round(sum(hops) / len(hops), 4) if hops else None,
            "denominator": len(hops),
        },
        "direct_hop_accuracy": rate(evaluated, "direct_hop_correct"),
        "median_engine_ms": {
            "value": round(median(timings), 3) if timings else None,
            "denominator": len(timings),
        },
        "p95_engine_ms": {
            "value": percentile(timings, 0.95),
            "denominator": len(timings),
        },
        "median_uncached_end_to_end_ms": {
            "value": round(median(end_to_end), 3) if end_to_end else None,
            "denominator": len(end_to_end),
        },
        "p95_uncached_end_to_end_ms": {
            "value": percentile(end_to_end, 0.95),
            "denominator": len(end_to_end),
        },
        "end_to_end_success": rate(
            [
                {
                    "ok": int(
                        r["evaluation_status"] in {"evaluable", "evaluable_partial"}
                        and r["correct_top1"] == 1
                    )
                }
                for r in rows
            ],
            "ok",
        ),
    }


def evaluate():
    with (HERE / "real_cases.csv").open(newline="") as file:
        cases = list(csv.DictReader(file))
    labels = load_labels(Chain.ethereum)
    external_endpoints = {
        endpoint: item["entity"] for endpoint, item in endpoints()[1].items()
    }
    internal_endpoints = {
        label.address: label.entity
        for label in labels
        if label.entity_type in {"vasp", "exchange"}
    }
    provider = GoldRushProvider()
    output = []
    CACHE.mkdir(parents=True, exist_ok=True)
    progress_file = CACHE / "pilot2_evaluation_progress.jsonl"
    split_hash = hashlib.sha256((HERE / "label_split.json").read_bytes()).hexdigest()
    provider_hash = hashlib.sha256((HERE.parent / "app" / "goldrush.py").read_bytes()).hexdigest()
    completed = {}
    if progress_file.exists():
        for line in progress_file.read_text().splitlines():
            try:
                item = json.loads(line)
                completed[item["signature"]] = item["row"]
            except (ValueError, KeyError):
                continue
    with CachedGoldRush() as api:
        for case in cases:
            signature = hashlib.sha256(
                json.dumps(
                    [
                        dataset_hash(),
                        split_hash,
                        provider_hash,
                        VERSION,
                        case["case_id"],
                        case["source_wallet"],
                        case["transaction_hash"],
                    ]
                ).encode()
            ).hexdigest()
            if signature in completed:
                output.append(completed[signature])
                continue
            start = perf_counter()
            before_calls, before_hits, before_errors = (
                api.calls,
                api.hits,
                len(api.errors),
            )
            row = {key: None for key in FIELDS}
            row.update(
                {
                    key: case.get(key)
                    for key in [
                        "case_id",
                        "source_wallet",
                        "expected_vasp",
                        "expected_endpoint",
                        "expected_hops",
                        "internal_label_overlap",
                        "label_stratum",
                        "ground_truth_dataset",
                        "ground_truth_source",
                        "ground_truth_reference",
                        "ground_truth_service_url",
                        "transaction_hash",
                    ]
                }
            )
            row.update(
                {
                    "retrieval_status": "not_attempted",
                    "analysis_status": "not_attempted",
                    "evaluation_status": "not_evaluable",
                }
            )
            try:
                transactions, _ = provider.fetch(case["source_wallet"], Chain.ethereum)
                row["retrieval_status"] = (
                    "complete" if len(api.errors) == before_errors else "partial_error"
                )
                row["expected_transfer_observed"] = int(
                    any(
                        t.tx_hash == case["transaction_hash"]
                        and t.from_address == case["source_wallet"]
                        and t.to_address == case["expected_endpoint"]
                        for t in transactions
                    )
                )
                if not row["expected_transfer_observed"]:
                    row["failure_reason"] = (
                        "expected_transfer_outside_retrieved_evidence"
                    )
                elif any(
                    (
                        external_endpoints.get(t.to_address)
                        or internal_endpoints.get(t.to_address)
                    )
                    not in (None, case["expected_vasp"])
                    for t in transactions
                    if t.from_address == case["source_wallet"]
                ):
                    row["exclusion_reason"] = (
                        "ambiguous_multiple_direct_vasp_entities_in_retrieved_evidence"
                    )
                    row["evaluation_status"] = "excluded_ambiguous"
                else:
                    request = InvestigationRequest(
                        target=case["source_wallet"],
                        chain=Chain.ethereum,
                        mode="live",
                        max_hops=4,
                        title="Evaluation baseline",
                        transactions=transactions,
                        labels=labels,
                    )
                    engine_start = perf_counter()
                    analysis = analyze(request, transactions, labels)
                    row["engine_latency_ms"] = round(
                        (perf_counter() - engine_start) * 1000, 3
                    )
                    row["analysis_status"] = "complete"
                    row["evaluation_status"] = (
                        "evaluable"
                        if row["retrieval_status"] == "complete"
                        else "evaluable_partial"
                    )
                    candidates = analysis["candidates"]
                    highest, nearest = (
                        analysis["highest_confidence_vasp"],
                        analysis["nearest_vasp"],
                    )
                    row["top_candidates"] = json.dumps(
                        [c["entity"] for c in candidates]
                    )
                    row["no_attribution_result"] = int(not candidates)
                    row["predicted_highest_confidence_vasp"] = (
                        highest["entity"] if highest else None
                    )
                    row["predicted_nearest_vasp"] = (
                        nearest["entity"] if nearest else None
                    )
                    row["attribution_score"] = highest["score"] if highest else None
                    row["predicted_hops"] = next(
                        (
                            c["shortest_hops"]
                            for c in candidates
                            if c["entity"] == case["expected_vasp"]
                        ),
                        None,
                    )
                    row["correct_top1"] = int(
                        bool(highest) and highest["entity"] == case["expected_vasp"]
                    )
                    row["correct_top3"] = int(
                        case["expected_vasp"] in [c["entity"] for c in candidates[:3]]
                    )
                    row["direct_hop_correct"] = int(row["predicted_hops"] == 1)
                    # The observed edge does not establish a globally nearest VASP.
                    if row["predicted_hops"] is not None:
                        row["hop_error"] = abs(
                            row["predicted_hops"] - int(case["expected_hops"])
                        )
            except Exception as exc:
                row["failure_reason"] = type(exc).__name__
                row["analysis_status"] = (
                    "error"
                    if row["retrieval_status"] in {"complete", "partial_error"}
                    else "not_attempted"
                )
                row["retrieval_status"] = (
                    "error"
                    if row["retrieval_status"] == "not_attempted"
                    else row["retrieval_status"]
                )
            row["actual_api_calls"] = api.calls - before_calls
            row["cache_hits"] = api.hits - before_hits
            row["end_to_end_latency_ms"] = round((perf_counter() - start) * 1000, 3)
            output.append(row)
            with progress_file.open("a") as progress:
                progress.write(json.dumps({"signature": signature, "row": row}) + "\n")
            print(
                case["case_id"],
                row["evaluation_status"],
                row["failure_reason"] or "",
                flush=True,
            )
    with (HERE / "results.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(output)
    metrics = {
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=HERE, text=True
        ).strip(),
        "model_version": VERSION,
        "chain": "ethereum",
        "sample_seed": SEED,
        "dataset": SOURCE,
        "dataset_reference": REFERENCE,
        "dataset_sha256": dataset_hash(),
        "label_split_sha256": split_hash,
        "provider_sha256": provider_hash,
        "candidate_count": len(cases),
        "attempted_count": len(output),
        "retrieval_success_count": sum(
            r["expected_transfer_observed"] == 1 for r in output
        ),
        "complete_retrieval_count": sum(
            r["retrieval_status"] == "complete" for r in output
        ),
        "evaluable_count": sum(
            r["evaluation_status"] in {"evaluable", "evaluable_partial"} for r in output
        ),
        "partial_evaluable_count": sum(
            r["evaluation_status"] == "evaluable_partial" for r in output
        ),
        "exclusion_and_failure_reasons": dict(
            Counter(r["failure_reason"] for r in output if r["failure_reason"])
        ),
        "exclusion_reasons": dict(
            Counter(r["exclusion_reason"] for r in output if r["exclusion_reason"])
        ),
        "actual_api_calls": sum(r["actual_api_calls"] for r in output),
        "cache_hits": sum(r["cache_hits"] for r in output),
        "all": group_metrics(output),
        "known_label": group_metrics([r for r in output if r["label_stratum"] == "operational"]),
        "unseen_label": group_metrics([r for r in output if r["label_stratum"] == "held_out"]),
        "specificity": None,
        "specificity_reason": "Specificity not measured due to lack of independently verified negative ground truth.",
        "fixture_validation": (
            {
                key: json.loads((HERE / "fixture_results.json").read_text())[key]
                for key in ("passed", "total")
            }
            if (HERE / "fixture_results.json").exists()
            else None
        ),
        "limitations": [
            "Published endpoint labels are assertions, not independently verified ownership.",
            "The source dataset and internal labels share Etherscan provenance.",
            "GoldRush target history may omit the expected transfer; such cases stay in the attempted denominator.",
            "The provider reads a bounded five-page recent history and decoded token logs; direct-transfer accuracy is conditional on the expected edge being present and does not imply complete wallet history.",
            "Operational public labels have unknown source confidence/reliability; the engine applies a conservative zero quality cap, which is not a calibrated uncertainty estimate.",
            "Nearest-VASP accuracy is not measured: an observed direct edge does not establish the nearest service across complete history.",
            "Hop error is conditional on a predicted path to the expected VASP; missing paths are reported separately.",
            "The confidence score is not a calibrated probability.",
        ],
    }
    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: metrics[k]
                for k in [
                    "candidate_count",
                    "attempted_count",
                    "retrieval_success_count",
                    "evaluable_count",
                    "exclusion_and_failure_reasons",
                    "actual_api_calls",
                    "cache_hits",
                    "all",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    evaluate()
