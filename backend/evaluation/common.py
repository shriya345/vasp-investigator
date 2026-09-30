"""Small, separate helpers for the reproducible evaluation baseline."""

import csv
import hashlib
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app import goldrush  # noqa: E402

DATASET = HERE / "raw" / "labeled_addresses__enriched.csv"
CACHE = HERE / "cache"
SEED = 2612026
SOURCE = (
    "Somin, ERC-20 Auxiliary Data (Harvard Dataverse), labeled_addresses__enriched.csv"
)
REFERENCE = "https://doi.org/10.7910/DVN/MBF0GC"

ALIASES = {
    "binance": "Binance",
    "coinbase": "Coinbase",
    "kraken": "Kraken",
    "okx": "OKX",
    "kucoin": "KuCoin",
    "huobi": "Huobi",
    "bitfinex": "Bitfinex",
    "crypto-com": "Crypto.com",
    "poloniex": "Poloniex",
    "bithumb": "Bithumb",
    "gemini": "Gemini",
    "bitstamp": "Bitstamp",
    "hitbtc": "HitBTC",
    "bittrex": "Bittrex",
    "upbit": "Upbit",
    "hotbit": "Hotbit",
}


def address(value):
    value = (value or "").strip().lower()
    value = value.removeprefix("0x")
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        return None
    return "0x" + value


def dataset_rows():
    with DATASET.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def dataset_hash():
    return hashlib.sha256(DATASET.read_bytes()).hexdigest()


class CachedGoldRush:
    """Cache parsed public responses and count actual requests, including failures."""

    def __init__(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.hits = 0
        self.errors = []
        self.original = goldrush._goldrush_request

    def request(self, path, params=None):
        params = params or {}
        cache_key = hashlib.sha256(
            json.dumps([path, params], sort_keys=True).encode()
        ).hexdigest()
        location = CACHE / f"{cache_key}.json"
        if location.exists():
            self.hits += 1
            return json.loads(location.read_text())
        self.calls += 1
        try:
            data = self.original(path, params)
        except Exception as exc:
            # Never persist authentication headers or exception text that might contain secrets.
            self.errors.append({"path": path, "type": type(exc).__name__})
            raise
        location.write_text(json.dumps(data, separators=(",", ":")))
        return data

    def __enter__(self):
        goldrush._goldrush_request = self.request
        return self

    def __exit__(self, *_):
        goldrush._goldrush_request = self.original
