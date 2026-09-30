"""
GoldRush (Covalent) blockchain history provider.

Fetches recent native transfers and decoded ERC-20/BEP-20 transfer logs for an
address, normalizes into the existing Transaction model.

API docs: https://goldrush.dev/docs/
Chain names: eth-mainnet, bsc-mainnet
"""

import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from .models import Chain, Label, Transaction

GOLDRUSH_API_BASE = "https://api.covalenthq.com/v1"
GOLDRUSH_CHAIN_NAMES = {
    Chain.ethereum: "eth-mainnet",
    Chain.bnb: "bsc-mainnet",
}
# Limit pages fetched per request to keep response times reasonable for demo.
# The returned history is a recent window, not a complete wallet history.
MAX_PAGES = 5
RETRY_DELAYS = [1, 2, 4]


def _get_api_key() -> str:
    key = os.getenv("GOLDRUSH_API_KEY", "")
    if not key:
        raise ValueError("GOLDRUSH_API_KEY is not set")
    return key


def _goldrush_request(path: str, params: Optional[dict] = None) -> dict:
    """Single HTTP request with retry/backoff. Returns parsed JSON data."""
    url = f"{GOLDRUSH_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            resp = httpx.get(url, headers=headers, params=params or {}, timeout=30)
            if resp.status_code == 429:
                # Rate limited — always retry
                time.sleep(delay or 5)
                continue
            # Bad requests cannot be repaired by retrying the same parameters.
            if 500 <= resp.status_code < 600 and attempt < len(RETRY_DELAYS):
                continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("error"):
                raise ValueError(f"GoldRush API error: {body.get('error_message', 'unknown')}")
            return body.get("data", {})
        except httpx.HTTPStatusError:
            raise
    raise ValueError("GoldRush request failed after retries")


def _parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _safe_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        if d < 0 or not d.is_finite():
            return None
        return d
    except (InvalidOperation, TypeError):
        return None


class GoldRushProvider:
    """
    Fetches real blockchain history from GoldRush (Covalent) API.

    Returns normalized Transaction + Label lists. Labels list is empty —
    labels come from the curated label files in backend/data/labels/.
    """

    def fetch(self, target: str, chain: Chain) -> tuple[list[Transaction], list[Label]]:
        chain_name = GOLDRUSH_CHAIN_NAMES.get(chain)
        if not chain_name:
            raise ValueError(f"Unsupported chain: {chain}")

        transactions: list[Transaction] = []
        seen_ids: set[str] = set()

        # Fetch recent native transactions and decoded token-transfer logs.
        self._fetch_transactions(target, chain, chain_name, transactions, seen_ids)

        # Sort by block/tx ordering deterministically
        transactions.sort(key=lambda t: (
            t.timestamp,
            t.block_number,
            t.transaction_index,
            t.event_index,
            t.tx_hash,
        ))

        return transactions, []

    def _fetch_transactions(
        self,
        target: str,
        chain: Chain,
        chain_name: str,
        out: list[Transaction],
        seen: set[str],
    ):
        """Fetch the latest page and up to four preceding pages."""
        page = None
        for _ in range(MAX_PAGES):
            try:
                path = f"/{chain_name}/address/{target}/transactions_v3/"
                if page is not None:
                    path += f"page/{page}/"
                data = _goldrush_request(path, params={"no-logs": "false"})
            except Exception:
                break

            items = data.get("items") or []
            if not items:
                break

            for item in items:
                self._normalize_tx(item, target, chain, out, seen)

            # The unnumbered URL starts at the most recent page. Page zero is
            # the oldest; walk backward using the returned page number.
            current_page = data.get("current_page")
            if not isinstance(current_page, int) or current_page <= 0:
                break
            page = current_page - 1

    def _normalize_tx(self, item: dict, target: str, chain: Chain, out: list, seen: set):
        """Normalize a single transaction item (native transfer)."""
        tx_hash = (item.get("tx_hash") or "").lower()
        if not tx_hash or len(tx_hash) != 66 or not tx_hash.startswith("0x"):
            return
        if not item.get("successful", True):
            return  # Skip failed transactions

        from_addr = (item.get("from_address") or "").lower()
        to_addr = (item.get("to_address") or "").lower()
        if not from_addr or not to_addr:
            return
        if from_addr == to_addr:
            return  # Skip self-transfers

        block_number = item.get("block_height") or item.get("block_number") or 0
        tx_index = item.get("tx_offset") or item.get("transaction_index") or 0
        ts = _parse_timestamp(item.get("block_signed_at"))
        if ts is None:
            return

        # Native value transfer (ETH/BNB)
        value_wei = item.get("value")
        if value_wei and str(value_wei) not in ("0", "0x0", ""):
            try:
                amount_wei = Decimal(str(value_wei))
                if amount_wei > 0:
                    amount = amount_wei / Decimal("1000000000000000000")  # 18 decimals
                    usd_value_str = item.get("value_quote")
                    usd = _safe_decimal(usd_value_str) if usd_value_str else None
                    evidence_id = f"{chain.value}:{tx_hash}:0"
                    if evidence_id not in seen:
                        seen.add(evidence_id)
                        try:
                            out.append(Transaction(
                                tx_hash=tx_hash,
                                event_index=0,
                                chain=chain,
                                block_number=int(block_number),
                                transaction_index=int(tx_index),
                                timestamp=ts,
                                from_address=from_addr,
                                to_address=to_addr,
                                asset="ETH" if chain == Chain.ethereum else "BNB",
                                amount=str(amount),
                                usd_value=str(usd) if usd is not None else None,
                                contract_address=None,
                                transaction_type="native",
                                source="GoldRush API (Covalent); eth-mainnet transactions_v3",
                                source_confidence=0.95,
                            ))
                        except Exception:
                            pass
            except (InvalidOperation, ValueError):
                pass

        # Decoded log events (ERC-20 transfers in the same tx)
        log_events = item.get("log_events") or []
        for log_idx, log in enumerate(log_events):
            self._normalize_log_event(
                log, tx_hash, block_number, tx_index, ts, target, chain, out, seen,
                event_offset=log_idx + 1,
            )

    def _normalize_log_event(
        self, log: dict, tx_hash: str, block_number, tx_index, ts: datetime,
        target: str, chain: Chain, out: list, seen: set, event_offset: int,
    ):
        """Normalize a decoded ERC-20 Transfer log event."""
        decoded = log.get("decoded") or {}
        if decoded.get("name") != "Transfer":
            return
        params = {p["name"]: p["value"] for p in (decoded.get("params") or [])}
        from_addr = (params.get("from") or params.get("_from") or "").lower()
        to_addr = (params.get("to") or params.get("_to") or "").lower()
        value = params.get("value") or params.get("_value")
        contract_addr = (log.get("sender_address") or "").lower()
        symbol = log.get("sender_contract_ticker_symbol") or "TOKEN"
        decimals = log.get("sender_contract_decimals") or 18
        usd_quote = log.get("value_quote")

        if not from_addr or not to_addr or not value or not contract_addr:
            return
        if from_addr == to_addr:
            return
        # Only include if involves the target
        if from_addr != target and to_addr != target:
            return

        try:
            raw_amount = Decimal(str(value))
            if raw_amount <= 0:
                return
            amount = raw_amount / Decimal(10) ** int(decimals)
            if amount <= 0:
                return
        except (InvalidOperation, ValueError):
            return

        usd = _safe_decimal(usd_quote) if usd_quote else None
        if not (len(contract_addr) == 42 and contract_addr.startswith("0x")):
            return

        evidence_id = f"{chain.value}:{tx_hash}:{event_offset}"
        if evidence_id in seen:
            return
        seen.add(evidence_id)
        try:
            out.append(Transaction(
                tx_hash=tx_hash,
                event_index=event_offset,
                chain=chain,
                block_number=int(block_number),
                transaction_index=int(tx_index),
                timestamp=ts,
                from_address=from_addr,
                to_address=to_addr,
                asset=symbol[:20],
                amount=str(amount),
                usd_value=str(usd) if usd is not None else None,
                contract_address=contract_addr,
                transaction_type="token",
                source="GoldRush API (Covalent); decoded ERC-20 log event",
                source_confidence=0.90,
            ))
        except Exception:
            pass
