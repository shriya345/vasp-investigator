"""Controlled functional validation; never included in real-world denominators."""

import json
from time import perf_counter

from common import HERE

from app.engine import analyze
from app.models import InvestigationRequest

FIXTURES = HERE.parent / "data" / "test_cases"
NONE = "No VASP attribution supported by available evidence."


def run():
    rows = []
    for filename in sorted(FIXTURES.glob("*.json")):
        request = InvestigationRequest.model_validate_json(filename.read_text())
        start = perf_counter()
        result = analyze(request, request.transactions, request.labels)
        elapsed = round((perf_counter() - start) * 1000, 3)
        candidates = result["candidates"]
        nearest = result["nearest_vasp"]
        highest = result["highest_confidence_vasp"]
        expected = {
            "01_strong_vasp.json": (
                "Binance at 2 hops",
                bool(
                    nearest
                    and highest
                    and nearest["entity"] == highest["entity"] == "Binance"
                    and nearest["shortest_hops"] == 2
                ),
            ),
            "02_mixed_flow.json": (
                "Coinbase and Kraken both direct; no unique required winner",
                {c["entity"] for c in candidates} == {"Coinbase", "Kraken"}
                and all(c["shortest_hops"] == 1 for c in candidates),
            ),
            "03_mixer_risk.json": (
                "Binance candidate plus mixer exposure",
                any(c["entity"] == "Binance" for c in candidates)
                and any(
                    f["name"] == "Mixer exposure detected"
                    for f in result["risk"]["factors"]
                ),
            ),
            "04_dex_flow.json": (
                "DEX boundary and no VASP candidate",
                not candidates
                and any(n["type"] == "dex" for n in result["graph"]["nodes"])
                and result["attribution_result"] == NONE,
            ),
            "05_unknown.json": (
                "No VASP attribution",
                not candidates
                and nearest is None
                and highest is None
                and result["attribution_result"] == NONE,
            ),
        }[filename.name]
        rows.append(
            {
                "fixture": filename.name,
                "expected_behavior": expected[0],
                "passed": bool(expected[1]),
                "nearest_vasp": nearest["entity"] if nearest else None,
                "highest_confidence_vasp": highest["entity"] if highest else None,
                "nearest_hops": nearest["shortest_hops"] if nearest else None,
                "no_attribution": result["attribution_result"] == NONE,
                "runtime_ms": elapsed,
            }
        )
    output = {
        "title": "Controlled Functional Fixture Validation",
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
        "cases": rows,
    }
    (HERE / "fixture_results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    run()
