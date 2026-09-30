"""Checks for frozen benchmark selection and metric denominators."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "evaluation"))

from evaluate_final import stratum_metrics  # noqa: E402
from select_final_cases import round_robin  # noqa: E402


def test_entity_round_robin_is_deterministic():
    cases = [
        {"case_id": "REAL-0003", "expected_vasp": "B"},
        {"case_id": "REAL-0002", "expected_vasp": "A"},
        {"case_id": "REAL-0001", "expected_vasp": "A"},
    ]
    assert [row["case_id"] for row in round_robin(cases)] == [
        "REAL-0001",
        "REAL-0003",
        "REAL-0002",
    ]


def test_conflicts_and_missing_evidence_do_not_enter_conditional_accuracy():
    rows = [
        {"evaluation_status": "ground_truth_conflict"},
        {"evaluation_status": "expected_transfer_missing"},
        {
            "evaluation_status": "evaluable",
            "correct_top1": 1,
            "correct_top3": 1,
            "direct_hop_correct": 1,
            "hop_error": 0,
            "engine_latency_ms": 2.0,
        },
        {
            "evaluation_status": "evaluable",
            "correct_top1": 0,
            "correct_top3": 0,
            "direct_hop_correct": 0,
            "hop_error": None,
            "engine_latency_ms": 4.0,
        },
    ]
    metrics = stratum_metrics(rows)
    assert metrics["attempted"] == 4
    assert metrics["evaluable"] == 2
    assert metrics["top1"] == {"numerator": 1, "denominator": 2, "percentage": 50.0}
    assert metrics["hop_mae"] == {"value": 0.0, "denominator": 1}
