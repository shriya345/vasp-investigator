"""Freeze an entity-aware operational/held-out endpoint split before evaluation."""

import hashlib
import json
import random
from collections import defaultdict

from build_real_cases import endpoints
from common import HERE, REFERENCE, SEED, SOURCE, dataset_hash

from app.label_loader import DATA_DIR, load_labels

LABEL_FILE = HERE.parent / "data" / "labels" / "ethereum_public_cex.json"
SPLIT_FILE = HERE / "label_split.json"


def make_split():
    _, selected, _ = endpoints()
    curated_records = {row["address"].lower(): row for row in json.loads(
        (DATA_DIR / "ethereum_vasps.json").read_text()
    )}
    curated = set(curated_records)
    groups = defaultdict(list)
    for endpoint, item in selected.items():
        groups[item["entity"]].append(endpoint)
    assignments = {}
    for entity in sorted(groups):
        addresses = sorted(groups[entity])
        remaining = [a for a in addresses if a not in curated]
        random.Random(f"{SEED}:{entity}").shuffle(remaining)
        held_out_count = max(1, round(len(addresses) * 0.3)) if len(addresses) > 1 else 0
        held_out = set(remaining[:min(held_out_count, max(0, len(remaining) - 1))])
        for endpoint in addresses:
            assignments[endpoint] = {
                "address": endpoint,
                "entity": entity,
                "stratum": "held_out" if endpoint in held_out else "operational",
                "curated_overlap": endpoint in curated,
                "dataset_service_url": selected[endpoint]["url"],
            }
    operational = [
        {
            "address": a,
            "chain": "ethereum",
            "entity": row["entity"],
            "entity_type": "vasp",
            "strength": "weak",
            "source": f"{SOURCE}; published Etherscan-derived assertion; no ownership verification",
            "source_url": REFERENCE,
            "confidence": None,
            "source_reliability": None,
            "observed_at": None,
            "fiu_registered": None,
            "synthetic": False,
        }
        for a, row in sorted(assignments.items())
        if row["stratum"] == "operational" and not row["curated_overlap"]
    ]
    manifest = {
        "dataset": SOURCE,
        "reference": REFERENCE,
        "dataset_sha256": dataset_hash(),
        "seed": SEED,
        "rule": "Per entity: keep curated overlaps operational; shuffle other sorted addresses using seed:entity; hold out approximately 30%, retaining at least one operational non-curated endpoint.",
        "endpoints": [assignments[a] for a in sorted(assignments)],
    }
    SPLIT_FILE.write_text(json.dumps(manifest, indent=2) + "\n")
    LABEL_FILE.write_text(json.dumps(operational, indent=2) + "\n")
    counts = {
        entity: {
            "operational": sum(row["entity"] == entity and row["stratum"] == "operational" for row in assignments.values()),
            "held_out": sum(row["entity"] == entity and row["stratum"] == "held_out" for row in assignments.values()),
        }
        for entity in sorted(groups)
    }
    (HERE / "split_counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    conflicts = [
        {
            "address": a,
            "status": "ground_truth_conflict",
            "exclusion_reason": "ground_truth_conflict",
            "published_label": {
                "entity": row["entity"], "source": SOURCE,
                "source_url": REFERENCE,
                "dataset_service_url": row["dataset_service_url"],
                "dataset_sha256": dataset_hash(),
            },
            "curated_label": {
                "entity": curated_records[a]["entity"],
                "source": curated_records[a]["source"],
                "source_url": curated_records[a].get("source_url"),
                "observed_at": curated_records[a].get("observed_at"),
            },
        }
        for a, row in sorted(assignments.items())
        if a in curated_records and row["entity"] != curated_records[a]["entity"]
    ]
    (HERE / "label_conflicts.json").write_text(json.dumps(conflicts, indent=2) + "\n")
    load_labels.cache_clear()
    print(json.dumps({
        "total": len(assignments),
        "operational": sum(v["stratum"] == "operational" for v in assignments.values()),
        "held_out": sum(v["stratum"] == "held_out" for v in assignments.values()),
        "operational_entities": sorted({v["entity"] for v in assignments.values() if v["stratum"] == "operational"}),
        "held_out_entities": sorted({v["entity"] for v in assignments.values() if v["stratum"] == "held_out"}),
        "manifest_sha256": hashlib.sha256(SPLIT_FILE.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    make_split()
