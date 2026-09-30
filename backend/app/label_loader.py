"""
Load curated and operational public label JSON files from backend/data/labels/.
Returns a list of Label objects for a given chain.
"""

import json
from functools import lru_cache
from pathlib import Path

from .models import Chain, Label

DATA_DIR = Path(__file__).parent.parent / "data" / "labels"

LABEL_FILES = {
    Chain.ethereum: [
        "ethereum_vasps.json",
        "ethereum_public_cex.json",
        "mixers.json",
        "bridges.json",
        "dex.json",
        "scams.json",
    ],
    Chain.bnb: [
        "bnb_vasps.json",
        "mixers.json",
        "bridges.json",
        "dex.json",
        "scams.json",
    ],
}


@lru_cache(maxsize=None)
def load_labels(chain: Chain) -> list[Label]:
    """Load and validate all label files for a chain. Cached after first call."""
    labels: list[Label] = []
    seen_addresses: set[str] = set()
    files = LABEL_FILES.get(chain, [])
    for fname in files:
        fpath = DATA_DIR / fname
        if not fpath.exists():
            continue
        try:
            records = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for record in records:
            # Override chain to match requested chain (mixer/bridge/dex files are chain-agnostic)
            record = dict(record)
            record["chain"] = chain.value
            address = record.get("address", "").lower()
            if not address or address in seen_addresses:
                continue
            try:
                label = Label(**record)
                labels.append(label)
                seen_addresses.add(address)
            except Exception:
                continue
    return labels
