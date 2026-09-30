"""Evaluate a frozen final manifest with the production provider and engine."""

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
from common import CACHE, HERE, CachedGoldRush, dataset_hash

from app.engine import VERSION, analyze
from app.goldrush import GoldRushProvider
from app.label_loader import load_labels
from app.models import Chain, InvestigationRequest

FIELDS = [
    "case_id", "source_wallet", "expected_vasp", "expected_endpoint", "expected_hops",
    "label_stratum", "ground_truth_conflict", "transaction_hash",
    "retrieval_status", "expected_transfer_observed", "analysis_status", "evaluation_status",
    "exclusion_reason", "failure_reason", "held_out_category",
    "predicted_nearest_vasp", "predicted_highest_confidence_vasp", "top_candidates",
    "predicted_hops", "attribution_score", "no_attribution_result",
    "correct_top1", "correct_top3", "direct_hop_correct", "hop_error",
    "engine_latency_ms", "end_to_end_latency_ms", "actual_api_calls", "cache_hits",
    "ground_truth_dataset", "ground_truth_source", "ground_truth_reference",
    "ground_truth_service_url",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(rows, field):
    values = [int(row[field]) for row in rows if row[field] is not None]
    return {"numerator": sum(values), "denominator": len(values),
            "percentage": round(100 * sum(values) / len(values), 2) if values else None}


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 3)


def stratum_metrics(rows):
    eligible = [r for r in rows if r["evaluation_status"] == "evaluable"]
    hops = [r["hop_error"] for r in eligible if r["hop_error"] is not None]
    latencies = [r["engine_latency_ms"] for r in eligible if r["engine_latency_ms"] is not None]
    return {
        "attempted": len(rows), "evaluable": len(eligible),
        "top1": metric(eligible, "correct_top1"),
        "top3": metric(eligible, "correct_top3"),
        "direct_hop_accuracy": metric(eligible, "direct_hop_correct"),
        "hop_mae": {"value": round(sum(hops) / len(hops), 4) if hops else None,
                    "denominator": len(hops)},
        "median_engine_ms": {"value": round(median(latencies), 3) if latencies else None,
                             "denominator": len(latencies)},
        "p95_engine_ms": {"value": percentile(latencies, .95), "denominator": len(latencies)},
    }


def validate_freeze():
    freeze_path = HERE / "benchmark_freeze.json"
    freeze = json.loads(freeze_path.read_text())
    if freeze["state"] != "final_cases_frozen":
        raise ValueError("Final case manifest is not frozen")
    checks = [
        (HERE / "final_cases.csv", freeze["final_cases"]["sha256"]),
        (HERE / "case_pool.csv", freeze["candidate_pool"]["sha256"]),
        (HERE / "label_split.json", freeze["labels"]["split_sha256"]),
        (HERE / "label_conflicts.json", freeze["labels"]["conflicts_sha256"]),
        (HERE.parent / "data" / "labels" / "ethereum_public_cex.json", freeze["labels"]["operational_file_sha256"]),
        (HERE.parent / "data" / "labels" / "ethereum_vasps.json", freeze["labels"]["curated_file_sha256"]),
        (HERE.parent / "app" / "engine.py", freeze["implementation"]["engine_sha256"]),
        (HERE.parent / "app" / "goldrush.py", freeze["implementation"]["goldrush_sha256"]),
        (HERE / "evaluate_final.py", freeze["implementation"]["evaluator_sha256"]),
        (HERE / "select_final_cases.py", freeze["implementation"]["selector_sha256"]),
    ]
    if any(digest(path) != expected for path, expected in checks):
        raise ValueError("Frozen benchmark artifact changed")
    if dataset_hash() != freeze["dataset"]["sha256"]:
        raise ValueError("Frozen dataset changed")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip() != freeze["git"]["reference"]:
        raise ValueError("Git HEAD differs from benchmark freeze")
    return freeze, digest(freeze_path)


def evaluate():
    freeze, freeze_hash = validate_freeze()
    with (HERE / "final_cases.csv").open(newline="") as file:
        cases = list(csv.DictReader(file))
    if len(cases) != freeze["final_cases"]["count"]:
        raise ValueError("Frozen case count differs")
    labels = load_labels(Chain.ethereum)
    internal = {label.address: label.entity for label in labels if label.entity_type in {"vasp", "exchange"}}
    external = {a: item["entity"] for a, item in endpoints()[1].items()}
    conflicts = {item["address"] for item in json.loads((HERE / "label_conflicts.json").read_text())}
    progress_file = CACHE / "final_evaluation_progress.jsonl"
    completed = {}
    if progress_file.exists():
        for line in progress_file.read_text().splitlines():
            try:
                item = json.loads(line)
                completed[item["signature"]] = item["row"]
            except (ValueError, KeyError):
                continue
    provider = GoldRushProvider()
    output = []
    start_all = perf_counter()
    with CachedGoldRush() as api:
        for case in cases:
            signature = hashlib.sha256(json.dumps([
                freeze_hash, case["case_id"], case["source_wallet"], case["transaction_hash"]
            ]).encode()).hexdigest()
            if signature in completed:
                output.append(completed[signature])
                continue
            row = {field: None for field in FIELDS}
            row.update({key: case.get(key) for key in FIELDS if key in case})
            row.update({"retrieval_status": "not_attempted", "analysis_status": "not_attempted",
                        "evaluation_status": "other_excluded"})
            before_calls, before_hits, before_errors = api.calls, api.hits, len(api.errors)
            start = perf_counter()
            try:
                txs, _ = provider.fetch(case["source_wallet"], Chain.ethereum)
                had_error = len(api.errors) > before_errors
                row["retrieval_status"] = "partial_error" if had_error else "bounded_fetch_ok"
                row["expected_transfer_observed"] = int(any(
                    tx.tx_hash == case["transaction_hash"]
                    and tx.from_address == case["source_wallet"]
                    and tx.to_address == case["expected_endpoint"] for tx in txs
                ))
                if case["expected_endpoint"] in conflicts:
                    row["evaluation_status"] = "ground_truth_conflict"
                    row["exclusion_reason"] = "ground_truth_conflict"
                elif had_error and not row["expected_transfer_observed"]:
                    row["evaluation_status"] = "provider_failure"
                    row["failure_reason"] = "goldrush_request_error"
                elif not row["expected_transfer_observed"]:
                    row["evaluation_status"] = "expected_transfer_missing"
                    row["failure_reason"] = "expected_transfer_outside_retrieved_evidence"
                elif any((external.get(tx.to_address) or internal.get(tx.to_address))
                         not in (None, case["expected_vasp"])
                         for tx in txs if tx.from_address == case["source_wallet"]):
                    row["evaluation_status"] = "ambiguous"
                    row["exclusion_reason"] = "multiple_direct_vasp_entities"
                else:
                    request = InvestigationRequest(
                        target=case["source_wallet"], chain=Chain.ethereum,
                        mode="live", max_hops=4, title="Frozen Ethereum evaluation",
                        transactions=txs, labels=labels,
                    )
                    engine_start = perf_counter()
                    analysis = analyze(request, txs, labels)
                    row["engine_latency_ms"] = round((perf_counter() - engine_start) * 1000, 3)
                    row["analysis_status"] = "complete"
                    row["evaluation_status"] = "evaluable"
                    candidates = analysis["candidates"]
                    highest, nearest = analysis["highest_confidence_vasp"], analysis["nearest_vasp"]
                    row["top_candidates"] = json.dumps([candidate["entity"] for candidate in candidates])
                    row["predicted_highest_confidence_vasp"] = highest["entity"] if highest else None
                    row["predicted_nearest_vasp"] = nearest["entity"] if nearest else None
                    row["attribution_score"] = highest["score"] if highest else None
                    row["no_attribution_result"] = int(not candidates)
                    row["predicted_hops"] = next((candidate["shortest_hops"] for candidate in candidates
                                                  if candidate["entity"] == case["expected_vasp"]), None)
                    row["correct_top1"] = int(bool(highest) and highest["entity"] == case["expected_vasp"])
                    row["correct_top3"] = int(case["expected_vasp"] in [candidate["entity"] for candidate in candidates[:3]])
                    row["direct_hop_correct"] = int(row["predicted_hops"] == 1)
                    if row["predicted_hops"] is not None:
                        row["hop_error"] = abs(row["predicted_hops"] - int(case["expected_hops"]))
                if case["label_stratum"] == "held_out":
                    if case["expected_endpoint"] in internal:
                        row["held_out_category"] = "endpoint_itself_recognized"
                    elif not row["expected_transfer_observed"]:
                        row["held_out_category"] = "expected_evidence_not_retrieved"
                    elif row["predicted_highest_confidence_vasp"] == case["expected_vasp"]:
                        row["held_out_category"] = "same_entity_via_other_known_endpoint"
                    elif row["no_attribution_result"] == 1:
                        row["held_out_category"] = "reached_endpoint_no_supported_attribution"
                    else:
                        row["held_out_category"] = "reached_endpoint_not_identified"
            except Exception as exc:
                row["evaluation_status"] = "analysis_failure" if row["retrieval_status"] != "not_attempted" else "provider_failure"
                row["analysis_status"] = "error" if row["retrieval_status"] != "not_attempted" else "not_attempted"
                row["retrieval_status"] = "error" if row["retrieval_status"] == "not_attempted" else row["retrieval_status"]
                row["failure_reason"] = type(exc).__name__
            row["actual_api_calls"] = api.calls - before_calls
            row["cache_hits"] = api.hits - before_hits
            row["end_to_end_latency_ms"] = round((perf_counter() - start) * 1000, 3)
            output.append(row)
            with progress_file.open("a") as progress:
                progress.write(json.dumps({"signature": signature, "row": row}) + "\n")
            print(case["case_id"], row["evaluation_status"], flush=True)
    with (HERE / "results.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(output)
    attempted = len(output)
    eligible = [r for r in output if r["evaluation_status"] == "evaluable"]
    metrics = {
        "title": "Final frozen Ethereum real-world evaluation",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "freeze_sha256": freeze_hash,
        "final_cases_sha256": freeze["final_cases"]["sha256"],
        "dataset_sha256": dataset_hash(),
        "model_version": VERSION,
        "attempted": attempted,
        "case_status_counts": dict(Counter(r["evaluation_status"] for r in output)),
        "expected_transfer_retrieval": {"numerator": sum(r["expected_transfer_observed"] == 1 for r in output),
                                        "denominator": attempted},
        "evaluable_rate": {"numerator": len(eligible), "denominator": attempted},
        "end_to_end_top1": {"numerator": sum(r["correct_top1"] == 1 and r["evaluation_status"] == "evaluable" for r in output),
                            "denominator": attempted},
        "operational": stratum_metrics([r for r in output if r["label_stratum"] == "operational"]),
        "held_out": stratum_metrics([r for r in output if r["label_stratum"] == "held_out"]),
        "held_out_categories": dict(Counter(r["held_out_category"] for r in output
                                            if r["label_stratum"] == "held_out")),
        "actual_api_request_wrapper_calls": sum(r["actual_api_calls"] for r in output),
        "cache_hits": sum(r["cache_hits"] for r in output),
        "evaluation_runtime_seconds": round(perf_counter() - start_all, 3),
        "nearest_vasp_accuracy": None,
        "real_world_specificity": None,
        "real_world_precision": None,
        "real_world_recall": None,
        "real_world_f1": None,
        "negative_ground_truth_note": "Real-world specificity, precision, recall, and F1 were not measured because independently verified negative ground truth was unavailable.",
    }
    for key in ("expected_transfer_retrieval", "evaluable_rate", "end_to_end_top1"):
        value = metrics[key]
        value["percentage"] = round(100 * value["numerator"] / value["denominator"], 2) if value["denominator"] else None
    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in (
        "attempted", "case_status_counts", "expected_transfer_retrieval", "evaluable_rate",
        "operational", "held_out", "actual_api_request_wrapper_calls", "cache_hits",
        "evaluation_runtime_seconds")}, indent=2))


if __name__ == "__main__":
    evaluate()
