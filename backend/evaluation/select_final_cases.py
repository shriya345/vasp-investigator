"""Select the frozen final manifest without reading any predictions."""

import csv
import hashlib
import json
from collections import Counter, defaultdict

from common import HERE, dataset_hash

POOL = HERE / "case_pool.csv"
FINAL = HERE / "final_cases.csv"
FREEZE = HERE / "benchmark_freeze.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def round_robin(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[case["expected_vasp"]].append(case)
    for group in groups.values():
        group.sort(key=lambda row: int(row["case_id"].split("-")[-1]))
    ordered = []
    while any(groups.values()):
        for entity in sorted(groups):
            if groups[entity]:
                ordered.append(groups[entity].pop(0))
    return ordered


def select():
    freeze = json.loads(FREEZE.read_text())
    if freeze["state"] != "methodology_frozen":
        raise ValueError("Benchmark methodology is not awaiting a final manifest")
    if dataset_hash() != freeze["dataset"]["sha256"]:
        raise ValueError("Dataset checksum changed")
    if digest(HERE / "label_split.json") != freeze["labels"]["split_sha256"]:
        raise ValueError("Label split changed")
    if digest(HERE / "label_conflicts.json") != freeze["labels"]["conflicts_sha256"]:
        raise ValueError("Conflict record changed")
    with POOL.open(newline="") as file:
        pool = list(csv.DictReader(file))
    if len(pool) < 100:
        raise ValueError(f"Only {len(pool)} candidate cases; final prediction must not run")
    if len({row["source_wallet"] for row in pool}) != len(pool):
        raise ValueError("Duplicate source wallet in candidate pool")
    if len({row["expected_endpoint"] for row in pool}) != len(pool):
        raise ValueError("Duplicate endpoint in candidate pool")
    if len({(row["source_wallet"], row["transaction_hash"]) for row in pool}) != len(pool):
        raise ValueError("Duplicate source/transaction in candidate pool")
    n = min(150, len(pool))
    operational = round_robin([r for r in pool if r["label_stratum"] == "operational"])
    held_out = round_robin([r for r in pool if r["label_stratum"] == "held_out"])
    target_operational = round(n * 0.7)
    selected = operational[:target_operational] + held_out[: n - target_operational]
    if len(selected) < n:
        chosen = {r["case_id"] for r in selected}
        remaining = round_robin([r for r in pool if r["case_id"] not in chosen])
        selected.extend(remaining[: n - len(selected)])
    if len(selected) != n:
        raise ValueError("Insufficient distinct cases after deterministic selection")
    conflicts = {r["address"] for r in json.loads((HERE / "label_conflicts.json").read_text())}
    fields = list(selected[0]) + ["ground_truth_conflict"]
    with FINAL.open("w", newline="") as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        for row in selected:
            writer.writerow({**row, "ground_truth_conflict": str(row["expected_endpoint"] in conflicts).lower()})
    freeze["state"] = "final_cases_frozen"
    freeze["candidate_pool"] = {"path": "case_pool.csv", "sha256": digest(POOL), "count": len(pool)}
    freeze["final_cases"] = {
        "path": "final_cases.csv", "sha256": digest(FINAL), "count": n,
        "operational": sum(r["label_stratum"] == "operational" for r in selected),
        "held_out": sum(r["label_stratum"] == "held_out" for r in selected),
        "ground_truth_conflicts": sum(r["expected_endpoint"] in conflicts for r in selected),
        "entities": dict(sorted(Counter(r["expected_vasp"] for r in selected).items())),
    }
    FREEZE.write_text(json.dumps(freeze, indent=2) + "\n")
    print(json.dumps(freeze["final_cases"], indent=2))


if __name__ == "__main__":
    select()
