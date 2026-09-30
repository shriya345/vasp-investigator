"""Construct observed direct-transfer cases from independently published labels."""

import argparse
import csv
import json
import random
from collections import Counter
from datetime import datetime, timezone

from common import (
    ALIASES,
    HERE,
    REFERENCE,
    SEED,
    SOURCE,
    CachedGoldRush,
    address,
    dataset_hash,
    dataset_rows,
)

from app.goldrush import GoldRushProvider
from app.label_loader import load_labels
from app.models import Chain

FIELDS = [
    "case_id",
    "chain",
    "source_wallet",
    "expected_vasp",
    "expected_endpoint",
    "expected_hops",
    "case_type",
    "ground_truth_dataset",
    "ground_truth_source",
    "ground_truth_reference",
    "ground_truth_service_url",
    "ground_truth_date",
    "dataset_version",
    "verification_status",
    "internal_label_overlap",
    "label_stratum",
    "transaction_hash",
    "block_number",
    "observation_timestamp",
    "inclusion_reason",
    "notes",
]


def endpoints():
    rows = dataset_rows()
    selected = {}
    rejects = Counter()
    for row in rows:
        if (row.get("type") or "").strip().lower() != "centralized exchange":
            continue
        entity = ALIASES.get((row.get("name") or "").strip().lower())
        endpoint = address(row.get("address"))
        if not entity or not endpoint:
            rejects["unknown_entity_or_invalid_address"] += 1
            continue
        old = selected.get(endpoint)
        if old and old["entity"] != entity:
            rejects["conflicting_entity_label"] += 1
            selected.pop(endpoint)
            continue
        if old:
            rejects["duplicate_endpoint"] += 1
            continue
        selected[endpoint] = {"entity": entity, "url": row.get("url", "")}
    return rows, selected, rejects


def balanced_order(selected, split):
    groups = {}
    for endpoint, item in selected.items():
        key = (split[endpoint]["stratum"], item["entity"])
        groups.setdefault(key, []).append(endpoint)
    for key, group in groups.items():
        group.sort()
        random.Random(f"{SEED}:{key[0]}:{key[1]}").shuffle(group)
    ordered = []
    while any(groups.values()):
        for key in sorted(groups):
            if groups[key]:
                ordered.append(groups[key].pop())
    return ordered


def pilot_sample(cases, size):
    # Predeclared 70/30 operational/held-out mix; round-robin entities in each.
    chosen = []
    for stratum, quota in (("operational", round(size * .7)), ("held_out", size - round(size * .7))):
        groups = {}
        for case in cases:
            if case["label_stratum"] == stratum:
                groups.setdefault(case["expected_vasp"], []).append(case)
        for group in groups.values():
            group.sort(key=lambda c: c["case_id"])
        while len([c for c in chosen if c["label_stratum"] == stratum]) < quota and any(groups.values()):
            for entity in sorted(groups):
                if groups[entity] and len([c for c in chosen if c["label_stratum"] == stratum]) < quota:
                    chosen.append(groups[entity].pop(0))
    return chosen


def build(limit, max_probes, pilot_size):
    rows, selected, rejects = endpoints()
    split = {row["address"]: row for row in json.loads((HERE / "label_split.json").read_text())["endpoints"]}
    all_published_addresses = {a for row in rows if (a := address(row.get("address")))}
    internal = {
        v.address: v.entity
        for v in load_labels(Chain.ethereum)
        if v.entity_type in {"vasp", "exchange"}
    }
    ordered = balanced_order(selected, split)
    cases = []
    exclusions = []
    probes_attempted = 0
    used_sources = set()
    previous = HERE / "pilot1" / "real_cases.csv"
    if previous.exists():
        with previous.open(newline="") as file:
            used_sources.update(row["source_wallet"] for row in csv.DictReader(file))
    provider = GoldRushProvider()
    with CachedGoldRush() as api:
        for endpoint in ordered[:max_probes]:
            if len(cases) >= limit:
                break
            probes_attempted += 1
            path = f"/eth-mainnet/address/{endpoint}/transactions_v3/"
            try:
                payload = api.request(path, {"no-logs": "false"})
            except Exception as exc:
                exclusions.append(
                    {
                        "endpoint": endpoint,
                        "reason": "discovery_retrieval_error",
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            transfers = []
            seen = set()
            for item in payload.get("items") or []:
                provider._normalize_tx(item, endpoint, Chain.ethereum, transfers, seen)
            inbound = sorted(
                (
                    t
                    for t in transfers
                    if t.to_address == endpoint and t.from_address != endpoint
                ),
                key=lambda t: (t.timestamp, t.tx_hash),
                reverse=True,
            )
            eligible = [
                t
                for t in inbound
                if t.from_address not in all_published_addresses
                and t.from_address not in internal
                and t.from_address not in used_sources
                and t.from_address != "0x" + "0" * 40
            ]
            if not eligible:
                exclusions.append(
                    {
                        "endpoint": endpoint,
                        "reason": "no_distinct_unlabelled_source_in_observed_page",
                    }
                )
                continue
            t = eligible[0]
            used_sources.add(t.from_address)
            entity = selected[endpoint]["entity"]
            cases.append(
                {
                    "case_id": f"REAL-{len(cases) + 1:04d}",
                    "chain": "ethereum",
                    "source_wallet": t.from_address,
                    "expected_vasp": entity,
                    "expected_endpoint": endpoint,
                    "expected_hops": "1",
                    "case_type": "direct",
                    "ground_truth_dataset": SOURCE,
                    "ground_truth_source": "published Etherscan-derived entity assertion; observed GoldRush transfer",
                    "ground_truth_reference": REFERENCE,
                    "ground_truth_service_url": selected[endpoint]["url"],
                    "ground_truth_date": "",
                    "dataset_version": "2025 publication; file checksum in dataset_quality.json",
                    "verification_status": "published_label_plus_observed_transfer_not_owner_verified",
                    "internal_label_overlap": str(endpoint in internal).lower(),
                    "label_stratum": split[endpoint]["stratum"],
                    "transaction_hash": t.tx_hash,
                    "block_number": t.block_number,
                    "observation_timestamp": t.timestamp.isoformat(),
                    "inclusion_reason": "distinct source directly transferred to published centralized-exchange endpoint",
                    "notes": "source selection is deterministic; one case per endpoint and source",
                }
            )
    with (HERE / "case_pool.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(cases)
    pilot = pilot_sample(cases, pilot_size)
    with (HERE / "real_cases.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        writer.writerows(pilot)
    quality = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": SOURCE,
        "dataset_reference": REFERENCE,
        "dataset_sha256": dataset_hash(),
        "raw_rows": len(rows),
        "centralized_exchange_rows": sum(
            (r.get("type") or "").strip().lower() == "centralized exchange"
            for r in rows
        ),
        "unique_endpoints": len(selected),
        "entity_endpoint_counts": dict(Counter(v["entity"] for v in selected.values())),
        "dataset_rejections": dict(rejects),
        "sample_seed": SEED,
        "endpoint_probes": probes_attempted,
        "cases_constructed": len(cases),
        "pilot_cases_selected": len(pilot),
        "case_entities": dict(Counter(c["expected_vasp"] for c in cases)),
        "pilot_entities": dict(Counter(c["expected_vasp"] for c in pilot)),
        "pilot_strata": dict(Counter(c["label_stratum"] for c in pilot)),
        "known_label_cases": sum(c["internal_label_overlap"] == "true" for c in cases),
        "unseen_label_cases": sum(
            c["internal_label_overlap"] == "false" for c in cases
        ),
        "exclusions": exclusions,
        "discovery_api_calls": api.calls,
        "discovery_cache_hits": api.hits,
        "api_errors": api.errors,
    }
    (HERE / "dataset_quality.json").write_text(json.dumps(quality, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: quality[k]
                for k in [
                    "raw_rows",
                    "centralized_exchange_rows",
                    "unique_endpoints",
                    "endpoint_probes",
                    "cases_constructed",
                    "case_entities",
                    "known_label_cases",
                    "unseen_label_cases",
                    "discovery_api_calls",
                    "discovery_cache_hits",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--max-probes", type=int, default=50)
    parser.add_argument("--pilot-size", type=int, default=20)
    args = parser.parse_args()
    build(args.limit, args.max_probes, args.pilot_size)
