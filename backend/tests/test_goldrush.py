from datetime import datetime, timezone

import httpx
import pytest

from app import goldrush
from app.engine import analyze
from app.label_loader import load_labels
from app.models import Chain, InvestigationRequest, Label, Transaction


def test_fetches_recent_pages_backwards_without_invalid_unfiltered_transfer_call(
    monkeypatch,
):
    paths = []
    target = "0x" + "1" * 40

    def request(path, params=None):
        paths.append(path)
        page = 2 if len(paths) == 1 else 1 if len(paths) == 2 else 0
        return {
            "current_page": page,
            "items": [
                {
                    "tx_hash": "0x" + format(page + 1, "064x"),
                    "successful": True,
                    "from_address": target,
                    "to_address": "0x" + "2" * 40,
                    "block_height": page + 1,
                    "block_signed_at": "2026-09-30T00:00:00Z",
                    "value": "1000000000000000000",
                }
            ],
        }

    monkeypatch.setattr(goldrush, "_goldrush_request", request)
    txs, _ = goldrush.GoldRushProvider().fetch(target, Chain.ethereum)
    assert paths == [
        f"/eth-mainnet/address/{target}/transactions_v3/",
        f"/eth-mainnet/address/{target}/transactions_v3/page/1/",
        f"/eth-mainnet/address/{target}/transactions_v3/page/0/",
    ]
    assert len(txs) == 3


def test_bad_request_is_not_retried(monkeypatch):
    calls = []

    def bad_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(400, request=httpx.Request("GET", url))

    monkeypatch.setenv("GOLDRUSH_API_KEY", "test-only")
    monkeypatch.setattr(goldrush.httpx, "get", bad_get)
    try:
        goldrush._goldrush_request("/invalid/")
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
    assert len(calls) == 1


def test_unknown_public_label_quality_is_not_fabricated():
    address = "0x" + "3" * 40
    target = "0x" + "4" * 40
    label = Label(
        address=address,
        chain=Chain.ethereum,
        entity="Published service",
        entity_type="vasp",
        strength="weak",
        source="published assertion",
        source_url="https://example.org/reference",
    )
    tx = Transaction(
        tx_hash="0x" + "5" * 64,
        chain=Chain.ethereum,
        block_number=1,
        timestamp=datetime(2026, 9, 30, tzinfo=timezone.utc),
        from_address=target,
        to_address=address,
        asset="ETH",
        amount="1",
        source="test",
        source_confidence=1,
    )
    request = InvestigationRequest(
        target=target,
        chain=Chain.ethereum,
        mode="import",
        transactions=[tx],
        labels=[label],
    )
    candidate = analyze(request, [tx], [label])["candidates"][0]
    assert candidate["entity"] == "Published service"
    assert candidate["score"] == 0
    assert candidate["labels"][0]["confidence"] is None


def test_operational_public_labels_exclude_held_out_addresses():
    import json
    from pathlib import Path

    split_file = Path(__file__).parents[1] / "evaluation" / "label_split.json"
    if not split_file.exists():
        pytest.skip("Locally generated licensed address-level split is not distributed")
    split = json.loads(split_file.read_text())
    held_out = {
        row["address"] for row in split["endpoints"] if row["stratum"] == "held_out"
    }
    known = {label.address for label in load_labels(Chain.ethereum)}
    assert len(split["endpoints"]) == 370
    assert not held_out & known


def test_curated_entity_has_priority_over_conflicting_public_assertion():
    labels = {label.address: label for label in load_labels(Chain.ethereum)}
    assert labels["0x66f820a414680b5bcda5eeca5dea238543f42054"].entity == "OKX"
    assert labels["0x236f9f97e0e62388479bf9e5ba4889e46b0273c3"].entity == "Bybit"
