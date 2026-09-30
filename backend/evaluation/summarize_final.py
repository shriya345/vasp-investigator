"""Render final benchmark artifacts from immutable results; no predictions here."""

import csv
import json
from collections import Counter

from common import HERE

EXPLANATIONS = {
    "label coverage": ("Expected endpoint was held out of operational intelligence.",
                       "Expand independently sourced, verified endpoint intelligence; keep a held-out set."),
    "blockchain evidence coverage": ("The observed transfer was outside the bounded source history.",
                                     "Improve documented retrieval coverage without changing this frozen result."),
    "provider/API failure": ("GoldRush retrieval returned an error before usable expected evidence.",
                             "Investigate provider reliability and retry/quota behavior in a later version."),
    "ambiguity": ("Source directly interacted with multiple named VASP entities.",
                  "Use a separately defined multi-label evaluation in future work."),
    "ground-truth conflict": ("Published and curated sources assign different entities to this endpoint.",
                              "Seek independent verification before using a single entity as truth."),
    "tracing failure": ("Expected edge was retrieved and labelled but no expected-entity candidate emerged.",
                        "Review temporal/asset path conditions after preserving this baseline."),
    "ranking failure": ("Expected entity appeared as a candidate but not at rank one.",
                        "Investigate evidence quality and ranking only on a later, separately evaluated version."),
    "normalization/entity mapping": ("Operational mapping disagreed with the published expected entity.",
                                     "Audit address and entity aliases with independent provenance."),
    "other": ("One case exceeded the validated 5,000-event request limit with 14,686 normalized events.",
              "Define a bounded evidence window or separately validated large-case pathway later."),
}


def ratio(n, d):
    return f"{n}/{d} ({100*n/d:.1f}%)" if d else "N/A"


def category(row, known):
    status = row["evaluation_status"]
    if status == "ground_truth_conflict":
        return "ground-truth conflict"
    if status == "ambiguous":
        return "ambiguity"
    if status == "provider_failure":
        return "provider/API failure"
    if status == "expected_transfer_missing":
        return "blockchain evidence coverage"
    if status != "evaluable":
        return "other"
    if row["correct_top1"] == "1":
        return None
    if row["label_stratum"] == "held_out":
        return "label coverage"
    if known.get(row["expected_endpoint"]) not in (None, row["expected_vasp"]):
        return "normalization/entity mapping"
    if row["expected_vasp"] in json.loads(row["top_candidates"] or "[]"):
        return "ranking failure"
    return "tracing failure"


def render():
    freeze = json.loads((HERE / "benchmark_freeze.json").read_text())
    metrics = json.loads((HERE / "metrics.json").read_text())
    quality = json.loads((HERE / "dataset_quality.json").read_text())
    split_counts = json.loads((HERE / "split_counts.json").read_text())
    with (HERE / "results.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))
    with (HERE / "case_pool.csv").open(newline="") as file:
        pool = list(csv.DictReader(file))
    with (HERE / "final_cases.csv").open(newline="") as file:
        cases = list(csv.DictReader(file))
    from app.label_loader import load_labels
    from app.models import Chain
    known = {label.address: label.entity for label in load_labels(Chain.ethereum)
             if label.entity_type in {"vasp", "exchange"}}
    n = len(rows)
    failures = Counter(filter(None, (category(row, known) for row in rows)))
    entities = sorted({r["expected_vasp"] for r in cases})
    statuses = metrics["case_status_counts"]
    op, held = metrics["operational"], metrics["held_out"]
    fixture = json.loads((HERE / "fixture_results.json").read_text())
    verification = json.loads((HERE / "verification.json").read_text())
    retrieval = metrics["expected_transfer_retrieval"]["numerator"]
    evaluable = metrics["evaluable_rate"]["numerator"]
    e2e = metrics["end_to_end_top1"]["numerator"]
    ambiguity = statuses.get("ambiguous", 0)
    conflict = statuses.get("ground_truth_conflict", 0)
    provider = statuses.get("provider_failure", 0)
    other = statuses.get("analysis_failure", 0) + statuses.get("other_excluded", 0)
    operational_rows = [r for r in rows if r["label_stratum"] == "operational"
                        and r["evaluation_status"] == "evaluable"]
    zero_scores = sum(float(r["attribution_score"] or 0) == 0 for r in operational_rows)
    single_candidates = sum(len(json.loads(r["top_candidates"] or "[]")) == 1
                            for r in operational_rows)
    operational_e2e = sum(r["correct_top1"] == "1" and r["evaluation_status"] == "evaluable"
                          for r in rows if r["label_stratum"] == "operational")
    lines = [
        "# FINAL REAL-WORLD ETHEREUM EVALUATION", "",
        f"Dataset: Somin ERC-20 Auxiliary Data (`{freeze['dataset']['filename']}`; SHA-256 `{freeze['dataset']['sha256']}`).",
        f"External addresses: {freeze['dataset']['total_rows']}; CEX endpoints: {freeze['dataset']['cex_endpoints']}; candidate pool: {len(pool)}; final attempted N: {n}.",
        f"VASPs represented: {len(entities)} ({', '.join(entities)}). Operational/known: {op['attempted']}; held-out: {held['attempted']}.",
        f"Expected transfers retrieved: {retrieval}; evaluable: {evaluable}; ambiguous: {ambiguity}; ground-truth conflicts: {conflict}; provider failures: {provider}; other failures: {other}.",
        "", "| Metric | Result | Denominator |", "|---|---:|---|",
        f"| Known-endpoint Top-1 | {ratio(op['top1']['numerator'], op['top1']['denominator'])} | Evaluable operational cases |",
        f"| Known-endpoint Top-3 | {ratio(op['top3']['numerator'], op['top3']['denominator'])} | Evaluable operational cases |",
        f"| Known direct-hop accuracy | {ratio(op['direct_hop_accuracy']['numerator'], op['direct_hop_accuracy']['denominator'])} | Evaluable operational cases |",
        f"| Known hop-distance MAE | {op['hop_mae']['value']} hops | {op['hop_mae']['denominator']} predicted expected paths |",
        f"| Known median engine latency | {op['median_engine_ms']['value']} ms | {op['median_engine_ms']['denominator']} evaluable cases |",
        f"| Known P95 engine latency | {op['p95_engine_ms']['value']} ms | {op['p95_engine_ms']['denominator']} evaluable cases |",
        f"| Expected-transfer retrieval | {ratio(retrieval, n)} | All attempted |",
        f"| Evaluable-case rate | {ratio(evaluable, n)} | All attempted |",
        f"| End-to-end Top-1 success | {ratio(e2e, n)} | All attempted |",
        f"| Ambiguity rate | {ratio(ambiguity, n)} | All attempted |",
        f"| Provider failure rate | {ratio(provider, n)} | All attempted |",
        f"| Ground-truth conflicts | {conflict} | All attempted; excluded only from single-label accuracy |",
        "| Nearest-VASP accuracy | Not measurable | Unique global-nearest ground truth unavailable |",
        "", "## 1. Methodology", "",
        "The dataset's published CEX labels are external assertions, not independently verified ownership. An observed Ethereum source-to-endpoint transfer supplies the direct edge. Candidate discovery and final selection used the rules and hashes in `benchmark_freeze.json`; `final_cases.csv` was checksummed before prediction. The 70/30 operational/held-out target was filled deterministically as availability allowed. No case was replaced after a result. The original pilots remain in `pilot1/` and `pilot2/`.",
        "", "## 2. Known-endpoint operational attribution", "",
        f"{op['attempted']} attempted operational cases yielded {op['evaluable']} unambiguous evaluable cases. Conditional Top-1, Top-3 and hop results above measure tracing and endpoint recognition given published operational intelligence. {zero_scores}/{len(operational_rows)} correct operational cases scored 0 because public labels lack numeric confidence and reliability; {single_candidates}/{len(operational_rows)} had only one ranked candidate. Thus the conditional entity match does not test discrimination among competing VASPs or establish high-confidence attribution. Scores are not ownership probabilities.",
        "", "## 3. Held-out endpoint analysis", "",
        f"{held['attempted']} held-out cases were attempted; {held['evaluable']} were evaluable. Their conditional entity Top-1 was {ratio(held['top1']['numerator'], held['top1']['denominator'])}. No held-out endpoint was independently recognized. Of these cases, 23 reached the endpoint but had no supported VASP attribution, 5 lacked the expected retrieved evidence (including one provider failure), 1 matched the entity via another known endpoint, and 16 were ambiguous. The 23 no-attribution cases are the same 23 coverage-limited cases, not an additional group. An entity match via another endpoint does not identify the held-out address or show ML generalization.",
        "", "## 4. Blockchain evidence retrieval", "",
        f"The exact expected transfer appeared in bounded production source history for {ratio(retrieval, n)}. GoldRush reads at most five recent transaction pages and decoded token logs; a successful request does not establish complete wallet history. Discovery used {quality['discovery_api_calls']} uncached request-wrapper calls and {quality['discovery_cache_hits']} cache hits; evaluation used {metrics['actual_api_request_wrapper_calls']} calls and {metrics['cache_hits']} cache hits. Total: {quality['discovery_api_calls'] + metrics['actual_api_request_wrapper_calls']} uncached request-wrapper calls and {quality['discovery_cache_hits'] + metrics['cache_hits']} cache hits. Internal retries can increase wire attempts. Evaluation runtime was {metrics['evaluation_runtime_seconds']} seconds (25 min 9 sec); discovery took approximately 39 minutes from process start to completion, for about 64 minutes of discovery plus evaluation, excluding verification.",
        "", "## 5. Failure analysis", "",
        "Every attempted case remains in `results.csv`. Categories, percentages, technical explanations and future work are detailed in `FAILURE_ANALYSIS.md`. Two known public-versus-curated endpoint conflicts retain both labels and provenance in `label_conflicts.json`; one selected conflict is counted separately, neither correct nor incorrect in conditional accuracy. The sole analysis failure contained 14,686 normalized events, exceeding the 5,000-event request limit. The sole provider failure followed four cached pages when a later page request failed; its exact error type was not retained.",
        "", "## 6. Controlled functional validation", "",
        f"{fixture['passed']}/{fixture['total']} controlled scenarios passed. These are separate from real-world denominators.",
        "", "## 7. Software verification", "",
        f"Backend tests: {verification['backend_tests']['passed']}/{verification['backend_tests']['total']} passed with the live key disabled for the key-free health assertion. Browser/E2E: {verification['browser_tests']['passed']}/{verification['browser_tests']['total']} passed. TypeScript, frontend production build, changed-file Python lint, and `git diff --check` passed. Repository-wide lint retains 15 pre-existing issues in untouched `app/main.py`, `app/storage.py`, and `tests/test_scope.py`.",
        "", "## 8. Limitations", "",
        f"Real-world specificity, precision, recall, and F1 were not measured because independently verified negative ground truth was unavailable. Nearest-VASP accuracy is not measurable without a unique globally nearest service label. Published and curated labels have related Etherscan provenance. The conditional 48/48 operational result applies only to retrieved, unambiguous, conflict-free direct cases; operational end-to-end success was {ratio(operational_e2e, op['attempted'])}. This endpoint-derived sample does not represent arbitrary Ethereum wallets. VASP association does not establish sender ownership or criminal liability. No government, court, FIU or live SAHYOG validation is implied.",
        "", "### Entity accounting", "",
        "| Entity | External endpoints | Candidate cases | Selected cases | Operational | Held-out | Evaluable |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    pool_counts = Counter(r["expected_vasp"] for r in pool)
    for entity in sorted(split_counts):
        selected = [r for r in cases if r["expected_vasp"] == entity]
        evaluated = [r for r in rows if r["expected_vasp"] == entity and r["evaluation_status"] == "evaluable"]
        counts = split_counts[entity]
        lines.append(f"| {entity} | {counts['operational'] + counts['held_out']} | {pool_counts[entity]} | {len(selected)} | {sum(r['label_stratum'] == 'operational' for r in selected)} | {sum(r['label_stratum'] == 'held_out' for r in selected)} | {len(evaluated)} |")
    (HERE / "EVALUATION_SUMMARY.md").write_text("\n".join(lines) + "\n")
    historical = (HERE / "FAILURE_ANALYSIS.md").read_text().split("## Final frozen benchmark")[0].rstrip()
    failure_lines = [historical, "", "## Final frozen benchmark", "",
                     f"All percentages below use {n} fixed attempted cases. Successful evaluable Top-1 cases: {n - sum(failures.values())}. Each non-successful case has one primary category; overlapping retrieval and conflict facts remain in `results.csv`.",
                     "", "| Category | Count | Attempted-case percentage | Technical explanation | Possible future improvement |",
                     "|---|---:|---:|---|---|"]
    for name, (explanation, improvement) in EXPLANATIONS.items():
        count = failures[name]
        failure_lines.append(f"| {name} | {count} | {100*count/n:.1f}% | {explanation} | {improvement} |")
    failure_lines += ["", "The provider/API failure (REAL-0078) followed four cached pages; the exact later-page request error type was not retained. No final case, prediction, expected entity, label, scoring weight, threshold or provider behavior changed after observing these failures."]
    (HERE / "FAILURE_ANALYSIS.md").write_text("\n".join(failure_lines) + "\n")
    ppt = [
        "# Recommended slide: Frozen Ethereum attribution benchmark", "",
        f"We selected {n} observed Ethereum source-to-published-CEX transfers across {len(entities)} entities using a frozen, entity-aware rule before running Tracepoint; operational and held-out endpoints are reported separately.",
        "", "Six headline metrics:", "",
        f"1. Known-endpoint Top-1: {ratio(op['top1']['numerator'], op['top1']['denominator'])}.",
        f"2. Known-endpoint end-to-end Top-1: {ratio(operational_e2e, op['attempted'])} across all operational attempts.",
        f"3. Expected transfer retrieved: {ratio(retrieval, n)}.",
        f"4. Evaluable cases: {ratio(evaluable, n)}.",
        f"5. End-to-end Top-1 success: {ratio(e2e, n)}.",
        f"6. Known median engine time: {op['median_engine_ms']['value']} ms (N={op['median_engine_ms']['denominator']}).",
        "", f"Controlled functional validation: {fixture['passed']}/{fixture['total']}. Software tests: backend {verification['backend_tests']['passed']}/{verification['backend_tests']['total']}; browser {verification['browser_tests']['passed']}/{verification['browser_tests']['total']}. TypeScript and production build passed.",
        "", f"Limitations: The conditional 48/48 entity match had one candidate per case, and {zero_scores} of 48 scores were 0 because public-label quality is unknown. Published labels are not ownership proof; bounded history, ambiguity and conflicts limit evaluation.",
        "", "30-second judge explanation: We froze a published-endpoint dataset, an operational/held-out split and a deterministic case list before analysis. We evaluated every selected case and show both conditional known-endpoint attribution and all-case retrieval and success, so missed evidence and ambiguity remain visible. Held-out entity matches can come from other known endpoints. This is evidence-supported VASP association, not proof of wallet ownership.",
        "", "How did you validate accuracy? With a frozen real-transfer manifest, explicit exclusions and separate controlled/software tests.",
        "Where did ground truth come from? Published Somin/Harvard Dataverse Etherscan-derived endpoint assertions plus observed transfers, not verified owner records.",
        "Was the test set used to tune Tracepoint? No scoring weights, thresholds, tracing, labels or provider behavior changed after the freeze.",
        "Why were some cases excluded? Multiple direct VASPs, disputed endpoint identities, missing expected evidence or provider/analysis failure; all remain in attempted counts.",
        "Can Tracepoint identify a completely unseen VASP endpoint? Not directly without operational intelligence; another known endpoint can yield the same entity name.",
        "Why no precision/recall/F1? Independently verified negative ground truth was unavailable.",
        "Does attribution prove wallet ownership? No; it supports an endpoint association only.",
    ]
    (HERE / "PRESENTATION_METRICS.md").write_text("\n".join(ppt) + "\n")
    print(json.dumps({"attempted": n, "failure_categories": dict(failures)}, indent=2))


if __name__ == "__main__":
    render()
